#!/usr/bin/env python3
"""Check review coverage and release consistency; not bibliographic truth."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def make_packet(draft):
    packet = {"schema_version": 1, "style": draft.get("style"),
              "entries": [{**{"id": row.get("id"), "original": row.get("original"),
                              "candidate": row.get("candidate")},
                           **({"candidate_html": row["candidate_html"]} if "candidate_html" in row else {})}
                          for row in draft.get("entries", [])]}
    if "presentation" in draft:
        packet["presentation"] = draft["presentation"]
    return packet


def packet_hash(draft):
    payload = json.dumps(make_packet(draft), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def has_sources(rows):
    return isinstance(rows, list) and bool(rows) and all(
        isinstance(row, dict) and nonempty_string(row.get("url") or row.get("path")) and nonempty_string(row.get("locator"))
        for row in rows
    )


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def check_release(draft, review):
    errors, released, pending = [], [], []
    entries = draft.get("entries", [])
    rows = review.get("rows", [])
    ids = [row.get("id") for row in entries]
    reviewed_ids = [row.get("id") for row in rows]
    if draft.get("schema_version") != 1 or not entries:
        errors.append("Draft must have schema_version 1 and at least one original entry")
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        errors.append("Every original entry needs a unique nonempty string ID")
    if len(set(reviewed_ids)) != len(reviewed_ids) or set(reviewed_ids) != set(ids):
        errors.append("Review must cover every original ID exactly once")
    main_id, reviewer_id = draft.get("main_agent_id"), review.get("reviewer_agent_id")
    if not isinstance(main_id, str) or not main_id or not isinstance(reviewer_id, str) or not reviewer_id or main_id == reviewer_id:
        errors.append("Distinct real main/reviewer agent IDs must be recorded")
    if review.get("independent") is not True:
        errors.append("Independent review not recorded")
    if review.get("packet_sha256") != packet_hash(draft):
        errors.append("Review is for a different draft or target format")
    style = draft.get("style") or {}
    if not nonempty_string(style.get("name")) or style.get("selection") not in ("user_explicit", "user_no_requirement") or not has_sources(style.get("rules")):
        errors.append("Target format, actual user selection, and rule sources must be recorded")
    if style.get("selection") == "user_no_requirement":
        normalized_name = re.sub(r"\s+", "", str(style.get("name", ""))).replace("—", "-").replace("–", "-").upper()
        if normalized_name != "GB/T7714-2025":
            errors.append("Explicitly having no format requirement defaults only to GB/T 7714-2025")
    if "presentation" in draft and not isinstance(draft["presentation"], dict):
        errors.append("Presentation settings must be an object when provided")
    by_id = {row.get("id"): row for row in rows}
    included_ids = {row.get("id") for row in entries if row.get("decision") == "include"}
    for entry in entries:
        entry_id = entry.get("id")
        row = by_id.get(entry_id)
        if not isinstance(entry.get("original"), str) or not entry["original"].strip():
            errors.append(f"{entry_id}: original reference missing")
        if row is None:
            continue
        if any(row.get(key) not in ("verified", "unresolved", "not_applicable") for key in ("identity", "metadata", "format")):
            errors.append(f"{entry_id}: every original needs explicit identity, metadata, and format review states")
        issues = row.get("issues")
        if not isinstance(issues, list) or any(not isinstance(issue, dict) or not nonempty_string(issue.get("code"))
                                              or not nonempty_string(issue.get("detail")) for issue in issues):
            errors.append(f"{entry_id}: review findings must be an explicit list with code and detail")
        if "candidate_html" in entry and entry["candidate_html"] is not None and not nonempty_string(entry["candidate_html"]):
            errors.append(f"{entry_id}: candidate HTML must be a nonempty string or null")
        if entry.get("decision") == "include":
            if not isinstance(entry.get("candidate"), str) or not entry["candidate"].strip():
                errors.append(f"{entry_id}: corrected candidate missing")
            if entry.get("evidence_status") != "verified" or not has_sources(entry.get("sources")):
                errors.append(f"{entry_id}: main verification incomplete")
            if (row.get("verdict") != "pass" or any(row.get(key) != "verified" for key in ("identity", "metadata", "format"))
                    or row.get("issues") != [] or not has_sources(row.get("sources"))):
                errors.append(f"{entry_id}: independent review has blocking or unverified findings")
            released.append(entry_id)
        elif entry.get("decision") in ("unresolved", "needs_user"):
            if (entry.get("candidate") is not None or entry.get("candidate_html") is not None
                    or row.get("verdict") not in ("unresolved", "needs_user") or not issues):
                errors.append(f"{entry_id}: unresolved reference is not clearly withheld")
            pending.append(entry_id)
        elif entry.get("decision") == "duplicate":
            if (entry.get("candidate") is not None or entry.get("candidate_html") is not None
                    or entry.get("evidence_status") != "verified" or not has_sources(entry.get("sources"))
                    or entry.get("duplicate_of") not in included_ids or row.get("verdict") != "duplicate"
                    or row.get("duplicate_of") != entry.get("duplicate_of") or row.get("identity") != "verified"
                    or row.get("metadata") != "verified" or row.get("issues") != []
                    or not has_sources(row.get("sources"))):
                errors.append(f"{entry_id}: duplicate work/version mapping not verified")
        else:
            errors.append(f"{entry_id}: invalid decision")
    passed = not errors
    return {"structural_checks_passed": passed, "complete": passed and not pending,
            "original_count": len(ids), "review_count": len(reviewed_ids),
            "released_ids": released if passed else [], "pending_ids": pending, "errors": errors,
            "scope": "Coverage and version consistency only; inspect genuine delegation and source evidence separately."}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    packet = commands.add_parser("packet", help="Create review input without main conclusions")
    packet.add_argument("--draft", required=True)
    packet.add_argument("--output")
    check = commands.add_parser("check", help="Check coverage, draft digest, and blocking findings")
    check.add_argument("--draft", required=True)
    check.add_argument("--review", required=True)
    args = parser.parse_args(argv)
    try:
        draft = read_json(args.draft)
        if args.command == "packet":
            result = make_packet(draft)
            result["packet_sha256"] = packet_hash(draft)
        else:
            result = check_release(draft, read_json(args.review))
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.command == "packet" and args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0 if args.command == "packet" or result["structural_checks_passed"] else 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        print(json.dumps({"structural_checks_passed": False, "errors": [str(error)]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
