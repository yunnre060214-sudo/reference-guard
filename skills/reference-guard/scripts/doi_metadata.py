#!/usr/bin/env python3
"""Retrieve DOI registry records. Records and cache hits are not citation verification."""
# SPDX-License-Identifier: AGPL-3.0-or-later
import argparse
import copy
import datetime
import hashlib
import json
import math
import re
import socket
import sys
import tempfile
import time
from http.client import HTTPException
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

MAX_BYTES = 4 * 1024 * 1024
USER_AGENT = "reference-guard/2.0 (public bibliographic metadata reader)"
REGISTRIES = (("Crossref", "https://api.crossref.org/works/"),
              ("DataCite", "https://api.datacite.org/dois/"))


def normalize_doi(value):
    if not isinstance(value, str):
        raise ValueError("DOI must be a string")
    value = value.strip()
    if value.lower().startswith("doi:"):
        value = value[4:].strip()
    if value.lower().startswith(("http://", "https://")):
        parsed = urlsplit(value)
        if (parsed.hostname not in ("doi.org", "dx.doi.org") or parsed.username
                or parsed.password or parsed.port not in (None, 80, 443)):
            raise ValueError("Expected a DOI name or doi.org URL")
        if parsed.query or parsed.fragment:
            raise ValueError("Encode literal DOI ?/# characters in URLs; remove tracking parameters")
        value = unquote(parsed.path.lstrip("/"))
    if not re.fullmatch(r"10\.\d{4,9}/[^\s\x00-\x1f\x7f]+", value):
        raise ValueError("Invalid DOI syntax; supply the exact identifier without citation punctuation")
    return value


def record_digest(record):
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def extract_record(payload, registry):
    if not isinstance(payload, dict) or payload.get("errors"):
        raise ValueError("Registry returned an error or invalid response envelope")
    if registry == "Crossref":
        if payload.get("status") != "ok" or payload.get("message-type") != "work":
            raise ValueError("Crossref response is not a successful work record")
        record = payload["message"]
        identifiers = {"record_doi": record.get("DOI")} if isinstance(record, dict) else {}
    else:
        resource = payload["data"]
        if not isinstance(resource, dict) or resource.get("type") != "dois":
            raise ValueError("DataCite response is not a DOI resource")
        record = resource["attributes"]
        identifiers = {"record_doi": record.get("doi"), "resource_id": resource.get("id")} if isinstance(record, dict) else {}
    if not isinstance(record, dict) or not identifiers:
        raise ValueError("Registry response lacks a DOI record")
    for identifier in identifiers.values():
        normalize_doi(identifier)
    return record, identifiers


def retry_delay(headers, attempt):
    raw = (headers or {}).get("Retry-After", "")
    try:
        delay = float(raw)
    except (ValueError, TypeError):
        try:
            delay = (parsedate_to_datetime(raw) - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            delay = 2 ** attempt
    return max(0, min(delay, 30)) if math.isfinite(delay) else 30


def fetch_doi(value, timeout=20, *, retries=0, mailto=None):
    doi = normalize_doi(value)
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 60:
        raise ValueError("timeout must be greater than 0 and at most 60")
    if type(retries) is not int or not 0 <= retries <= 3:
        raise ValueError("retries must be 0..3")
    if mailto and (not isinstance(mailto, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", mailto)):
        raise ValueError("mailto must be an email address")
    attempts, outcomes = [], []
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for registry, base in REGISTRIES:
        url = base + quote(doi, safe="")
        request = Request(url, headers={"User-Agent": USER_AGENT + ("; mailto:" + mailto if mailto else ""), "Accept": "application/json"})
        for attempt in range(retries + 1):
            trace = {"registry": registry, "source_url": url, "attempt": attempt + 1}
            try:
                with urlopen(request, timeout=timeout) as response:
                    raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("Registry response exceeded the size limit")
                payload = json.loads(raw.decode("utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
                record, identifiers = extract_record(payload, registry)
                for field, identifier in identifiers.items():
                    if normalize_doi(identifier).casefold() != doi.casefold():
                        return {"doi": doi, "status": "response_mismatch", "registry": registry,
                                "record_doi": identifiers["record_doi"], "mismatched_field": field,
                                "response_identifier": identifier, "source_url": url,
                                "fetched_at": fetched_at, "attempts": attempts + [trace]}
                trace["status"] = "record_found"
                return {"doi": doi, "status": "record_found", "registry": registry,
                        "source_url": url, "fetched_at": fetched_at, "record": record,
                        "record_sha256": record_digest(record), "attempts": attempts + [trace],
                        "scope": "Registry record only; compare citation fields and publication version separately."}
            except HTTPError as error:
                trace["http_status"] = error.code
                attempts.append(trace)
                if error.code == 404:
                    outcomes.append("not_found")
                    break
                if (error.code == 429 or 500 <= error.code < 600) and attempt < retries:
                    time.sleep(retry_delay(error.headers, attempt))
                    continue
                outcomes.append("failed")
                break
            except (URLError, TimeoutError, socket.timeout, OSError, HTTPException) as error:
                trace["error"] = str(error)
                attempts.append(trace)
                if attempt < retries:
                    time.sleep(min(2 ** attempt, 30))
                    continue
                outcomes.append("failed")
                break
            except (ValueError, KeyError, TypeError) as error:
                trace["error"] = str(error)
                attempts.append(trace)
                outcomes.append("failed")
                break
    absent = outcomes == ["not_found", "not_found"]
    return {"doi": doi, "status": "not_found_in_registries" if absent else "access_failed",
            "fetched_at": fetched_at, "attempts": attempts,
            "scope": "No record retrieved from these endpoints; not proof that the work does not exist."}


def cached_fetch(value, *, cache_dir=None, offline=False, max_age=86400, **options):
    doi = normalize_doi(value)
    cache_path, cache_note = None, None
    if cache_dir:
        cache_path = Path(cache_dir) / (hashlib.sha256(doi.casefold().encode()).hexdigest() + ".json")
        try:
            if cache_path.stat().st_size > MAX_BYTES:
                raise ValueError("Cache exceeds size limit")
            row = json.loads(cache_path.read_text(encoding="utf-8"))
            stamp = datetime.datetime.fromisoformat(row["fetched_at"])
            age = (datetime.datetime.now(datetime.timezone.utc) - stamp).total_seconds()
            actual = row["record"].get("DOI" if row["registry"] == "Crossref" else "doi")
            if (row["registry"] not in dict(REGISTRIES) or row["status"] != "record_found"
                    or normalize_doi(row["doi"]).casefold() != doi.casefold()
                    or normalize_doi(actual).casefold() != doi.casefold()
                    or record_digest(row["record"]) != row["record_sha256"] or not 0 <= age <= max_age):
                raise ValueError("Cache identity, integrity or age check failed")
            row["cache"] = {"hit": True, "age_seconds": round(age, 3), "offline": offline}
            return row
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            cache_note = str(error)
    if offline:
        return {"doi": doi, "status": "cache_miss", "cache": {"hit": False, "offline": True},
                "error": cache_note or "No cache directory supplied; no network requests made"}
    row = fetch_doi(doi, **options)
    row["cache"] = {"hit": False, "offline": False}
    if cache_path and row["status"] == "record_found":
        temp = None
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache_path.parent, delete=False) as handle:
                temp = Path(handle.name)
                json.dump(row, handle, ensure_ascii=False, allow_nan=False)
            temp.replace(cache_path)
        except OSError as error:
            row["cache"]["write_error"] = str(error)
        finally:
            if temp:
                temp.unlink(missing_ok=True)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dois", nargs="*", help="Exact DOI names or doi.org URLs")
    parser.add_argument("--input", help="UTF-8 file, one exact DOI per nonempty line")
    parser.add_argument("--output", help="JSON output file (default: stdout)")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--retries", type=int, default=2, help="Additional attempts per registry, 0..3")
    parser.add_argument("--mailto", help="Optional contact email sent to registry APIs")
    parser.add_argument("--cache-dir", help="Opt-in local cache of positive registry responses")
    parser.add_argument("--max-age", type=float, default=86400, help="Maximum cache age in seconds")
    parser.add_argument("--offline", action="store_true", help="Read valid cache only; never access the network")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 60:
        parser.error("--timeout must be greater than 0 and at most 60")
    if not 0 <= args.retries <= 3 or not math.isfinite(args.max_age) or args.max_age < 0:
        parser.error("--retries must be 0..3 and --max-age finite and nonnegative")
    try:
        values = args.dois + ([line.strip() for line in Path(args.input).read_text(encoding="utf-8-sig").splitlines() if line.strip()] if args.input else [])
        if not values:
            parser.error("Supply DOI arguments or --input")
        results, seen = [], {}
        for value in values:
            try:
                key = normalize_doi(value).casefold()
                if key not in seen:
                    seen[key] = cached_fetch(value, timeout=args.timeout, retries=args.retries, mailto=args.mailto,
                                             cache_dir=args.cache_dir, offline=args.offline, max_age=args.max_age)
                row = copy.deepcopy(seen[key])
                row["input"] = value
                results.append(row)
            except ValueError as error:
                results.append({"input": value, "status": "invalid_input", "error": str(error)})
        rendered = json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0 if all(row["status"] == "record_found" for row in results) else 1
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "input_output_error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
