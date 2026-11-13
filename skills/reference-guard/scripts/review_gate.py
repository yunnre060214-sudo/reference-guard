#!/usr/bin/env python3
"""Check review coverage and frozen release consistency, not bibliographic truth."""
# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip()) and "\x00" not in value


def valid_id(value):
    return nonempty_string(value) and value == value.strip()


def originals_hash(entries):
    payload = [{"id": row.get("id"), "original": row.get("original")} for row in entries]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def valid_issues(issues):
    return isinstance(issues, list) and all(isinstance(issue, dict) and nonempty_string(issue.get("code"))
                                          and nonempty_string(issue.get("detail")) for issue in issues)


def has_sources(rows):
    if not isinstance(rows, list) or not rows:
        return False
    for row in rows:
        if not isinstance(row, dict) or not nonempty_string(row.get("locator")):
            return False
        if "url" in row:
            if not nonempty_string(row["url"]):
                return False
            try:
                url = urlsplit(row["url"])
                if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
                    return False
            except ValueError:
                return False
        elif not nonempty_string(row.get("path")):
            return False
    return True


def draft_errors(draft):
    errors = []
    if not isinstance(draft, dict):
        return ["Draft must be a JSON object"]
    if type(draft.get("schema_version")) is not int or draft["schema_version"] not in (1, 2):
        errors.append("Draft must have schema_version 1 or 2")
    entries = draft.get("entries")
    if not isinstance(entries, list) or not entries or any(not isinstance(row, dict) for row in entries):
        return errors + ["Draft entries must be a nonempty list of objects"]
    ids = [row.get("id") for row in entries]
    if any(not valid_id(value) for value in ids):
        errors.append("Every original entry needs a unique nonempty string ID without edge whitespace")
    elif len(set(ids)) != len(ids):
        errors.append("Every original entry needs a unique nonempty string ID")
    for row in entries:
        if not nonempty_string(row.get("original")):
            errors.append(str(row.get("id")) + ": original reference missing")
    if "input" in draft:
        inventory = draft["input"]
        if (not isinstance(inventory, dict) or type(inventory.get("entry_count")) is not int
                or inventory["entry_count"] != len(entries)
                or inventory.get("originals_sha256") != originals_hash(entries)):
            errors.append("Input inventory count or original ID/text fingerprint differs from draft entries")
    if "presentation" in draft and not isinstance(draft["presentation"], dict):
        errors.append("Presentation settings must be an object when provided")
    if "artifacts" in draft:
        artifacts = draft["artifacts"]
        if not isinstance(artifacts, list) or any(
            not isinstance(row, dict) or not nonempty_string(row.get("path"))
            or not isinstance(row.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"])
            for row in artifacts
        ):
            errors.append("Artifacts must list relative paths and lowercase SHA-256 digests")
    return errors


def make_packet(draft):
    errors = draft_errors(draft)
    if errors:
        raise ValueError("; ".join(errors))
    packet = {"schema_version": 2, "style": draft.get("style"),
              "entries": [{key: row.get(key) for key in ("id", "original", "candidate", "candidate_html")
                           if key != "candidate_html" or key in row} for row in draft["entries"]]}
    for key in ("presentation", "artifacts", "bibliography_order"):
        if key in draft:
            packet[key] = draft[key]
    return packet


def packet_hash(draft):
    # Seal ALL inputs, including hidden decisions and evidence. Do not expose the
    # ledger in a blind packet merely to bind it to the independent review.
    payload = json.dumps({"hash_contract": "reference-guard-release-v2", "draft": draft},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def artifact_errors(draft, root):
    errors = []
    for artifact in draft.get("artifacts", []):
        path = Path(artifact["path"])
        if root is None:
            errors.append("Artifact verification requires the draft directory")
            continue
        base = Path(root).resolve()
        target = (base / path).resolve()
        if path.is_absolute() or base not in target.parents:
            errors.append("Artifact path escapes draft directory: " + str(path))
            continue
        try:
            digest = hashlib.sha256()
            with target.open("rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
            if digest.hexdigest() != artifact["sha256"]:
                errors.append("Artifact changed after review: " + str(path))
        except OSError as error:
            errors.append("Artifact unavailable: " + str(path) + ": " + str(error))
    return errors


def check_release(draft, review, artifact_root=None):
    errors, released, pending, duplicates = draft_errors(draft), [], [], []
    result = {"structural_checks_passed": False, "complete": False, "original_count": 0,
              "review_count": 0, "released_ids": [], "pending_ids": [], "duplicate_ids": [],
              "errors": errors, "scope": "Coverage and version consistency only; inspect genuine delegation and source evidence separately."}
    if errors:
        return result
    entries = draft["entries"]
    result["original_count"] = len(entries)
    if not isinstance(review, dict) or not isinstance(review.get("rows"), list) or any(not isinstance(row, dict) for row in review["rows"]):
        errors.append("Review must be an object with a rows list of objects")
        return result
    rows = review["rows"]
    result["review_count"] = len(rows)
    ids, reviewed_ids = [row["id"] for row in entries], [row.get("id") for row in rows]
    if any(not valid_id(value) for value in reviewed_ids):
        errors.append("Review IDs must be nonempty strings without edge whitespace")
        return result
    if len(set(reviewed_ids)) != len(reviewed_ids) or set(reviewed_ids) != set(ids):
        errors.append("Review must cover every original ID exactly once")
    main_id, reviewer_id = draft.get("main_agent_id"), review.get("reviewer_agent_id")
    if not valid_id(main_id) or not valid_id(reviewer_id) or main_id == reviewer_id:
        errors.append("Distinct real main/reviewer agent IDs must be recorded")
    if review.get("independent") is not True:
        errors.append("Independent review not recorded")
    try:
        if review.get("packet_sha256") != packet_hash(draft):
            errors.append("Review is for a different draft, decisions, evidence, or target format")
    except (TypeError, ValueError):
        errors.append("Draft must contain only finite JSON values")
    style = draft.get("style")
    if not isinstance(style, dict):
        errors.append("Target style must be an object")
        style = {}
    if not nonempty_string(style.get("name")) or style.get("selection") not in ("user_explicit", "user_no_requirement") or not has_sources(style.get("rules")):
        errors.append("Target format, actual user selection, and rule sources must be recorded")
    if style.get("selection") == "user_no_requirement":
        name = re.sub(r"\s+", "", str(style.get("name", ""))).replace("—", "-").replace("–", "-").upper()
        if name != "GB/T7714-2025":
            errors.append("Explicitly having no format requirement defaults only to GB/T 7714-2025")
    by_id = {row["id"]: row for row in rows}
    included_ids = {row["id"] for row in entries if row.get("decision") == "include"}
    for entry in entries:
        entry_id = entry["id"]
        row = by_id.get(entry_id)
        if row is None:
            continue
        if any(row.get(key) not in ("verified", "unresolved", "not_applicable") for key in ("identity", "metadata", "format")):
            errors.append(f"{entry_id}: every original needs explicit identity, metadata, and format review states")
        issues = row.get("issues")
        if not valid_issues(issues):
            errors.append(f"{entry_id}: review findings must be an explicit list with code and detail")
        if "original_issues" in row and not valid_issues(row["original_issues"]):
            errors.append(f"{entry_id}: original_issues must be a list with code and detail")
        for owner in (entry, row):
            if "sources" in owner and owner["sources"] != [] and not has_sources(owner["sources"]):
                errors.append(f"{entry_id}: sources must be a list of valid source objects")
        if "candidate_html" in entry and entry["candidate_html"] is not None and not nonempty_string(entry["candidate_html"]):
            errors.append(f"{entry_id}: candidate HTML must be a nonempty string or null")
        if entry.get("decision") == "include":
            if not nonempty_string(entry.get("candidate")):
                errors.append(f"{entry_id}: corrected candidate missing")
            if entry.get("evidence_status") != "verified" or not has_sources(entry.get("sources")):
                errors.append(f"{entry_id}: main verification incomplete")
            if (row.get("verdict") != "pass" or any(row.get(key) != "verified" for key in ("identity", "metadata", "format"))
                    or issues != [] or not has_sources(row.get("sources"))):
                errors.append(f"{entry_id}: independent review has blocking or unverified findings")
            released.append(entry_id)
        elif entry.get("decision") in ("unresolved", "needs_user"):
            if (entry.get("candidate") is not None or entry.get("candidate_html") is not None
                    or row.get("verdict") != entry["decision"] or not issues
                    or row.get("identity") == row.get("metadata") == row.get("format") == "verified"):
                errors.append(f"{entry_id}: unresolved reference is not clearly withheld")
            pending.append(entry_id)
        elif entry.get("decision") == "duplicate":
            target = entry.get("duplicate_of")
            if (entry.get("candidate") is not None or entry.get("candidate_html") is not None
                    or entry.get("evidence_status") != "verified" or not has_sources(entry.get("sources"))
                    or not isinstance(target, str) or target not in included_ids or row.get("verdict") != "duplicate"
                    or row.get("duplicate_of") != target or row.get("identity") != "verified"
                    or row.get("metadata") != "verified" or row.get("format") not in ("verified", "not_applicable")
                    or issues != [] or not has_sources(row.get("sources"))):
                errors.append(f"{entry_id}: duplicate work/version mapping not verified")
            duplicates.append(entry_id)
        else:
            errors.append(f"{entry_id}: invalid decision")
    order = draft.get("bibliography_order", released)
    if (not isinstance(order, list) or any(not valid_id(value) for value in order)
            or len(order) != len(released) or set(order) != set(released)):
        errors.append("Bibliography order must cover included IDs exactly once")
    errors.extend(artifact_errors(draft, artifact_root))
    passed = not errors
    result.update(structural_checks_passed=passed, complete=passed and not pending,
                  released_ids=order if passed else [], pending_ids=pending, duplicate_ids=duplicates)
    return result


def read_json(path):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError("Nonfinite JSON value: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs, parse_constant=constant)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    packet = commands.add_parser("packet", help="Create blind input and seal the entire draft")
    packet.add_argument("--draft", required=True)
    packet.add_argument("--output")
    check = commands.add_parser("check", help="Check coverage, full draft digest and artifact bytes")
    check.add_argument("--draft", required=True)
    check.add_argument("--review", required=True)
    args = parser.parse_args(argv)
    try:
        draft = read_json(args.draft)
        if args.command == "packet":
            result = make_packet(draft)
            result["packet_sha256"] = packet_hash(draft)
        else:
            result = check_release(draft, read_json(args.review), Path(args.draft).resolve().parent)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.command == "packet" and args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0 if args.command == "packet" or result["structural_checks_passed"] else 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        print(json.dumps({"structural_checks_passed": False, "errors": [str(error)]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
