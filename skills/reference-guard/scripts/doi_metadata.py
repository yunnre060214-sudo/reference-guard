#!/usr/bin/env python3
"""Read DOI registry records, without certifying a supplied citation."""
import argparse
import datetime
import json
import re
import socket
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

MAX_BYTES = 4 * 1024 * 1024
USER_AGENT = "reference-guard/1.0 (public bibliographic metadata reader)"


def normalize_doi(value):
    value = value.strip()
    if value.lower().startswith("doi:"):
        value = value[4:].strip()
    if value.lower().startswith(("http://", "https://")):
        parsed = urlsplit(value)
        if parsed.hostname not in ("doi.org", "dx.doi.org"):
            raise ValueError("Expected a DOI name or doi.org URL")
        value = unquote(parsed.path.lstrip("/"))
    if not re.fullmatch(r"10\.\d{4,9}/[^\s\x00-\x1f\x7f]+", value):
        raise ValueError("Invalid DOI syntax; supply the exact identifier without citation punctuation")
    return value


def fetch_doi(value, timeout=20):
    doi = normalize_doi(value)
    attempts = []
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for registry, base in (("Crossref", "https://api.crossref.org/works/"),
                           ("DataCite", "https://api.datacite.org/dois/")):
        url = base + quote(doi, safe="")
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("Registry response exceeded the size limit")
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("errors"):
                raise ValueError("Registry returned an error or invalid response envelope")
            if registry == "Crossref":
                if payload.get("status") != "ok" or payload.get("message-type") != "work":
                    raise ValueError("Crossref response is not a successful work record")
                record = payload["message"]
            else:
                resource = payload["data"]
                if not isinstance(resource, dict) or resource.get("type") != "dois":
                    raise ValueError("DataCite response is not a DOI resource")
                record = resource["attributes"]
            if not isinstance(record, dict):
                raise ValueError("Registry response lacks a DOI record")
            actual_doi = record.get("DOI" if registry == "Crossref" else "doi")
            if not isinstance(actual_doi, str):
                raise ValueError("Registry response lacks a DOI record")
            identifiers = {"record_doi": actual_doi}
            if registry == "DataCite":
                identifiers["resource_id"] = resource.get("id")
            for field, identifier in identifiers.items():
                if not isinstance(identifier, str):
                    raise ValueError("Registry response lacks an identifier")
                if normalize_doi(identifier).casefold() != doi.casefold():
                    return {"doi": doi, "status": "response_mismatch", "registry": registry,
                            "record_doi": actual_doi, "mismatched_field": field,
                            "response_identifier": identifier, "source_url": url, "fetched_at": fetched_at,
                            "attempts": attempts}
            return {"doi": doi, "status": "record_found", "registry": registry,
                    "source_url": url, "fetched_at": fetched_at, "record": record,
                    "attempts": attempts,
                    "scope": "Registry record only; compare the proposed citation and publication version separately."}
        except HTTPError as error:
            attempts.append({"registry": registry, "source_url": url, "http_status": error.code})
            if error.code == 404:
                continue
            return {"doi": doi, "status": "access_failed", "fetched_at": fetched_at,
                    "attempts": attempts, "error": str(error)}
        except (URLError, TimeoutError, socket.timeout, OSError, ValueError, KeyError, TypeError) as error:
            attempts.append({"registry": registry, "source_url": url, "error": str(error)})
            return {"doi": doi, "status": "access_failed", "fetched_at": fetched_at,
                    "attempts": attempts, "error": str(error)}
    return {"doi": doi, "status": "not_found_in_registries", "fetched_at": fetched_at,
            "attempts": attempts,
            "scope": "No record retrieved from these public registry endpoints; not proof that the work does not exist."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dois", nargs="+", help="Exact DOI names or doi.org URLs")
    parser.add_argument("--timeout", type=float, default=20, help="Seconds per registry request")
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 60:
        parser.error("--timeout must be greater than 0 and at most 60")
    results = []
    for value in args.dois:
        try:
            results.append(fetch_doi(value, args.timeout))
        except ValueError as error:
            results.append({"input": value, "status": "invalid_input", "error": str(error)})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(row["status"] == "record_found" for row in results) else 1


if __name__ == "__main__":
    sys.exit(main())
