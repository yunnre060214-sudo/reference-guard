#!/usr/bin/env python3
"""Offline workflow: doctor, init, audit and export. Never certifies source truth."""
# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from doi_metadata import normalize_doi, record_digest
from review_gate import check_release, originals_hash, packet_hash, read_json

VERSION = "2.0.0"
ROOT = Path(__file__).resolve().parents[1]


def normalized(value):
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]*>", "", text)
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def first(value):
    return value[0] if isinstance(value, list) and value else value


def registry_fields(row):
    record, registry = row.get("record"), row.get("registry")
    if row.get("status") != "record_found" or not isinstance(record, dict) or registry not in ("Crossref", "DataCite"):
        raise ValueError("No usable registry record")
    doi = record.get("DOI" if registry == "Crossref" else "doi")
    if normalize_doi(doi).casefold() != normalize_doi(row.get("doi")).casefold():
        raise ValueError("Registry and requested DOI differ")
    if row.get("record_sha256") and row["record_sha256"] != record_digest(record):
        raise ValueError("Registry record digest mismatch")
    dates = {}
    if registry == "Crossref":
        for key in ("published", "published-print", "published-online", "issued"):
            value = record.get(key)
            if isinstance(value, dict):
                parts = value.get("date-parts")
                if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                    dates[key] = parts[0]
        authors = record.get("author", [])
        return {"DOI": doi, "title": first(record.get("title")),
                "container-title": first(record.get("container-title")),
                "volume": record.get("volume"), "issue": record.get("issue"),
                "page": record.get("page"), "article-number": record.get("article-number"),
                "author": authors, "dates": dates}
    titles = record.get("titles")
    titles = titles if isinstance(titles, list) else []
    title = next((item.get("title") for item in titles if isinstance(item, dict) and not item.get("titleType")), None)
    creators = record.get("creators", [])
    authors = [{"family": item.get("familyName"), "given": item.get("givenName"),
                "literal": item.get("name") if not item.get("familyName") else None}
               for item in creators if isinstance(item, dict)] if isinstance(creators, list) else []
    return {"DOI": doi, "title": title, "author": authors,
            "dates": {"publicationYear": [record["publicationYear"]]} if record.get("publicationYear") else {}}


def audit(items, metadata):
    if not isinstance(items, list) or not items or any(not isinstance(item, dict) for item in items):
        raise ValueError("Items must be a nonempty CSL-JSON array")
    ids = [item.get("id") for item in items]
    if any(not isinstance(key, str) or not key.strip() for key in ids) or len(set(ids)) != len(ids):
        raise ValueError("CSL item IDs must be unique nonempty strings")
    if not isinstance(metadata, list) or any(not isinstance(row, dict) for row in metadata):
        raise ValueError("Metadata must be the JSON array returned by doi_metadata.py")
    records, duplicates, results = {}, {}, []
    for row in metadata:
        try:
            key = normalize_doi(row.get("doi")).casefold()
            fields = registry_fields(row)
        except ValueError:
            continue
        records.setdefault(key, []).append((row, fields))
    for item in items:
        findings, comparisons = [], []
        result = {"id": item["id"], "status": "manual_review_required", "findings": findings,
                  "comparisons": comparisons}
        results.append(result)
        if not item.get("DOI"):
            result["status"] = "needs_non_doi_verification"
            continue
        try:
            key = normalize_doi(item["DOI"]).casefold()
        except ValueError as error:
            findings.append({"code": "invalid_doi", "detail": str(error)})
            continue
        duplicates.setdefault(key, []).append(item["id"])
        choices = records.get(key, [])
        if not choices:
            findings.append({"code": "registry_record_unavailable", "detail": "No usable matching record in supplied metadata; verify through other sources."})
            continue
        # Never choose between conflicting snapshots by order, majority, or age.
        signatures = {record_digest(fields) for _, fields in choices}
        if len(signatures) > 1:
            findings.append({"code": "registry_records_conflict", "detail": "Multiple different records supplied; compare authoritative publication versions."})
            continue
        source, fields = choices[0]
        result["source_url"] = source.get("source_url")
        result["registry_dates"] = fields["dates"]
        for field in ("title", "container-title", "volume", "issue", "page", "article-number"):
            proposed, actual = item.get(field), fields.get(field)
            if proposed is None and actual is None:
                continue
            state = "not_compared" if proposed is None or actual is None else "normalized_match" if normalized(proposed) == normalized(actual) else "different"
            comparison = {"field": field, "proposed": proposed, "registry": actual, "assessment": state}
            if field == "title" and proposed and actual:
                comparison["similarity_hint"] = round(SequenceMatcher(None, normalized(proposed), normalized(actual)).ratio(), 3)
            comparisons.append(comparison)
            if state == "different":
                findings.append({"code": field.replace("-", "_") + "_differs", "detail": "Supplied field differs from registry; resolve using the publication record."})
        proposed_authors = item.get("author")
        actual_authors = fields.get("author")
        if isinstance(proposed_authors, list) and isinstance(actual_authors, list) and actual_authors:
            def names(rows):
                return [normalized(str(row.get("family") or row.get("literal") or row.get("name") or "") + " " + str(row.get("given") or ""))
                        for row in rows if isinstance(row, dict)]
            state = "normalized_match" if names(proposed_authors) == names(actual_authors) else "different"
            comparisons.append({"field": "author", "proposed": proposed_authors, "registry": actual_authors, "assessment": state})
            if state == "different":
                findings.append({"code": "authors_differ", "detail": "Names/order differ; initials, scripts, institutional names and truncation require manual interpretation."})
        issued = item.get("issued")
        parts = issued.get("date-parts") if isinstance(issued, dict) else None
        year = parts[0][0] if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0] else None
        years = {str(date[0]) for date in fields["dates"].values() if date}
        if year is not None and years and str(year) not in years:
            findings.append({"code": "year_differs", "detail": "Proposed year differs from all supplied registry publication dates."})
        if len(years) > 1:
            findings.append({"code": "multiple_publication_years", "detail": "Registry dates differ; determine the cited publication version before choosing a year."})
    return {"schema_version": 2, "status": "diagnostic_only", "entries": results,
            "duplicate_doi_groups": [{"doi": key, "ids": ids} for key, ids in duplicates.items() if len(ids) > 1],
            "scope": "Field comparison hints only. Normalized matches and shared DOIs do not establish identity, justify merging or replace independent review."}


def doctor():
    errors, assets = [], []
    try:
        manifest = read_json(ROOT / "assets" / "manifest.json")
        for relative, info in manifest["files"].items():
            target = (ROOT / "assets" / relative).resolve()
            if (ROOT / "assets").resolve() not in target.parents:
                raise ValueError("Asset path escapes assets directory")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            passed = digest == info["sha256"]
            assets.append({"path": relative, "sha256": digest, "passed": passed})
            if not passed:
                errors.append("Asset integrity mismatch: " + relative)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        errors.append(str(error))
    node = shutil.which("node")
    version = None
    if node:
        try:
            run = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10, check=True)
            version = run.stdout.strip()
            major = int(version.lstrip("v").split(".")[0])
            if major < 20:
                errors.append("Node.js 20 or later is required")
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            errors.append(str(error))
    else:
        errors.append("Node.js not found; DOI, audit and review tools remain usable")
    return {"version": VERSION, "offline_checks_passed": not errors, "python": sys.version.split()[0],
            "node": version, "assets": assets, "errors": errors,
            "requires_host_check": ["Actual source/standard access", "Real independent subagent creation"],
            "scope": "Offline runtime/integrity checks only; does not test source access or delegation."}


def initialize(path, kind, agent_id, style=None, no_requirement=False):
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8-sig")
    originals = text.splitlines() if kind == "lines" else read_json(path)
    if not isinstance(originals, list) or not originals or any(not isinstance(row, str) or not row.strip() for row in originals):
        raise ValueError("Input must be a nonempty JSON string array or one complete nonempty reference per line")
    selection = "user_no_requirement" if no_requirement else "user_explicit" if style else "pending"
    entries = [{"id": "R" + str(i), "original": original, "decision": "unresolved",
                "candidate": None, "evidence_status": "unresolved", "sources": []}
               for i, original in enumerate(originals, 1)]
    return {"schema_version": 2, "main_agent_id": agent_id,
            "input": {"filename": Path(path).name, "sha256": hashlib.sha256(raw).hexdigest(),
                      "entry_count": len(originals), "originals_sha256": originals_hash(entries)},
            "style": {"name": "GB/T 7714—2025" if no_requirement else style, "selection": selection, "rules": []},
            "entries": entries}


def export_release(draft, review, output_dir, *, allow_partial=False, artifact_root=None):
    checked = check_release(draft, review, artifact_root)
    if not checked["structural_checks_passed"]:
        raise ValueError("Release blocked: " + "; ".join(checked["errors"]))
    if not checked["complete"] and not allow_partial:
        raise ValueError("Pending references remain; explicitly use --allow-partial to export the verified subset")
    if not checked["released_ids"]:
        raise ValueError("No reviewed references available for export")
    directory = Path(output_dir)
    # Exclusive directory creation prevents silently replacing an earlier release.
    by_id = {row["id"]: row for row in draft["entries"]}
    entries = [by_id[key] for key in checked["released_ids"]]
    bibliography = "\n".join(row["candidate"] for row in entries) + "\n"
    status = "complete" if checked["complete"] else "partial"
    release = {"schema_version": 2, "status": status, "packet_sha256": packet_hash(draft),
               "checks": checked, "draft": draft, "review": review,
               "scope": "Frozen checked materials; structural validation cannot authenticate sources or agent identity."}
    report = ["# Reference Guard " + status + " release", "",
              "Structural checks passed. Source evidence and genuine delegation must be inspected separately.", "",
              "Reviewed: " + str(checked["review_count"]) + "; released: " + str(len(entries)) +
              "; pending: " + str(len(checked["pending_ids"])) + "; duplicates: " + str(len(checked["duplicate_ids"])), ""]
    reviews_by_id = {row["id"]: row for row in review["rows"]}
    for row in draft["entries"]:
        report += ["## " + row["id"], "", "Original (JSON): " + json.dumps(row["original"], ensure_ascii=False), "",
                   "Decision: " + row["decision"], ""]
        for source in row.get("sources", []):
            report.append("Source (JSON): " + json.dumps(source, ensure_ascii=False))
        review_row = reviews_by_id[row["id"]]
        for issue in review_row.get("original_issues", []) + review_row.get("issues", []):
            report.append("Finding (JSON): " + json.dumps(issue, ensure_ascii=False))
        if row.get("duplicate_of"):
            report.append("Duplicate of: " + row["duplicate_of"])
        report.append("")
    files = {"bibliography.txt": bibliography.encode("utf-8"),
             "release.json": (json.dumps(release, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"),
             "report.md": ("\n".join(report) + "\n").encode("utf-8")}
    directory.mkdir(parents=True, exist_ok=False)
    try:
        for name, content in files.items():
            (directory / name).write_bytes(content)
        manifest = {"version": VERSION, "status": status, "packet_sha256": packet_hash(draft),
                    "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError):
        shutil.rmtree(directory)
        raise
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Offline runtime and all bundled asset checks")
    init = commands.add_parser("init", help="Preserve original references and create an unresolved draft")
    init.add_argument("--input", required=True)
    init.add_argument("--input-format", choices=("lines", "json"), default="json")
    init.add_argument("--main-agent-id", required=True)
    selection = init.add_mutually_exclusive_group()
    selection.add_argument("--style")
    selection.add_argument("--no-style-requirement", action="store_true")
    init.add_argument("--output", required=True)
    compare = commands.add_parser("audit", help="Compare CSL fields with retrieved registry records")
    compare.add_argument("--items", required=True)
    compare.add_argument("--metadata", required=True)
    compare.add_argument("--output")
    export = commands.add_parser("export", help="Export exact reviewed text, evidence and content hashes")
    export.add_argument("--draft", required=True)
    export.add_argument("--review", required=True)
    export.add_argument("--output-dir", required=True)
    export.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor()
        elif args.command == "init":
            result = initialize(args.input, args.input_format, args.main_agent_id, args.style, args.no_style_requirement)
        elif args.command == "audit":
            result = audit(read_json(args.items), read_json(args.metadata))
        else:
            result = export_release(read_json(args.draft), read_json(args.review), args.output_dir,
                                    allow_partial=args.allow_partial, artifact_root=Path(args.draft).resolve().parent)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if getattr(args, "output", None):
            with Path(args.output).open("x", encoding="utf-8") as handle:
                handle.write(rendered)
        else:
            print(rendered, end="")
        return 1 if args.command == "doctor" and not result["offline_checks_passed"] else 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        print(json.dumps({"status": "blocked", "errors": [str(error)]}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
