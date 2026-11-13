"""Synthetic, offline adversarial tests. Fixture agent IDs are not real reviews."""
# SPDX-License-Identifier: AGPL-3.0-or-later
import copy
import datetime
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from http.client import IncompleteRead, BadStatusLine
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import doi_metadata as doi
import reference_guard as workflow
import review_gate as gate


def materials():
    source = [{"url": "https://example.org/synthetic", "locator": "Synthetic fixture, not real evidence"}]
    draft = {"schema_version": 2, "main_agent_id": "synthetic-main",
             "style": {"name": "APA 7", "selection": "user_explicit", "rules": copy.deepcopy(source)},
             "entries": [{"id": "R1", "original": "Synthetic original", "candidate": "Exact candidate, punctuation intact.",
                          "decision": "include", "evidence_status": "verified", "sources": copy.deepcopy(source)}]}
    review = {"reviewer_agent_id": "synthetic-reviewer", "independent": True,
              "packet_sha256": gate.packet_hash(draft), "rows": [{"id": "R1", "identity": "verified", "metadata": "verified",
              "format": "verified", "verdict": "pass", "issues": [], "sources": copy.deepcopy(source)}]}
    return draft, review


def payload(identifier="10.5555/synthetic"):
    return {"status": "ok", "message-type": "work", "message": {"DOI": identifier,
            "title": ["Synthetic title"], "author": [{"family": "Alpha", "given": "Ada"}],
            "published-print": {"date-parts": [[2024]]}, "published-online": {"date-parts": [[2023]]}}}


def response(data):
    return io.BytesIO(json.dumps(data).encode())


class DoiV2Tests(unittest.TestCase):
    def test_truncated_http_responses_retry_and_do_not_crash_batch(self):
        for error in (IncompleteRead(b'{"status":'), BadStatusLine('bogus')):
            with self.subTest(error=type(error).__name__), mock.patch.object(doi, "urlopen", side_effect=[error, response(payload())]), mock.patch.object(doi.time, "sleep"):
                self.assertEqual(doi.fetch_doi("10.5555/synthetic", retries=1)["status"], "record_found")

    def test_normalization_preserves_meaningful_suffix_punctuation(self):
        self.assertEqual(doi.normalize_doi("DOI: 10.5555/A.(B)"), "10.5555/A.(B)")
        self.assertEqual(doi.normalize_doi("https://doi.org/10.5555%2FA%23B"), "10.5555/A#B")

    def test_invalid_doi_inputs_are_rejected(self):
        for value in (None, [], "", "https://evil.test/10.5555/x", "https://doi.org@evil.test/10.5555/x",
                      "https://doi.org/10.5555/x?utm=yes", "https://doi.org/10.5555/x#fragment", "10.5555/a\nb"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                doi.normalize_doi(value)

    def test_retry_429_honors_bounded_retry_after(self):
        error = HTTPError("https://api.crossref.org", 429, "Rate limited", {"Retry-After": "2"}, None)
        with mock.patch.object(doi, "urlopen", side_effect=[error, response(payload())]) as fetch, mock.patch.object(doi.time, "sleep") as sleep:
            result = doi.fetch_doi("10.5555/synthetic", retries=1)
        self.assertEqual(result["status"], "record_found")
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(2)
        self.assertEqual(len(result["attempts"]), 2)

    def test_retry_after_parses_dates_and_caps_nonfinite_or_huge_values(self):
        self.assertEqual(doi.retry_delay({"Retry-After": "9999"}, 0), 30)
        self.assertEqual(doi.retry_delay({"Retry-After": "inf"}, 0), 30)
        self.assertEqual(doi.retry_delay({"Retry-After": "bad"}, 2), 4)
        self.assertEqual(doi.retry_delay({"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}, 0), 0)

    def test_transient_failure_falls_back_to_other_registry(self):
        data = {"data": {"id": "10.5555/synthetic", "type": "dois", "attributes": {"doi": "10.5555/synthetic"}}}
        with mock.patch.object(doi, "urlopen", side_effect=[URLError("offline"), response(data)]):
            result = doi.fetch_doi("10.5555/synthetic")
        self.assertEqual(result["registry"], "DataCite")
        self.assertEqual(result["status"], "record_found")

    def test_partial_404_plus_access_error_is_never_global_not_found(self):
        error = HTTPError("https://api.crossref.org", 404, "Not found", {}, None)
        with mock.patch.object(doi, "urlopen", side_effect=[error, URLError("offline")]):
            result = doi.fetch_doi("10.5555/synthetic")
        self.assertEqual(result["status"], "access_failed")

    def test_positive_cache_is_reused_offline_with_original_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(doi, "urlopen", return_value=response(payload())):
                live = doi.cached_fetch("10.5555/synthetic", cache_dir=directory)
            with mock.patch.object(doi, "urlopen", side_effect=AssertionError("Network used")):
                cached = doi.cached_fetch("10.5555/SYNTHETIC", cache_dir=directory, offline=True)
            self.assertEqual(cached["fetched_at"], live["fetched_at"])
            self.assertTrue(cached["cache"]["hit"])

    def test_tampered_cache_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(doi, "urlopen", return_value=response(payload())):
                doi.cached_fetch("10.5555/synthetic", cache_dir=directory)
            path = next(Path(directory).glob("*.json"))
            row = json.loads(path.read_text())
            row["record"]["title"] = ["Changed"]
            path.write_text(json.dumps(row))
            with mock.patch.object(doi, "urlopen", side_effect=AssertionError("Network used")):
                self.assertEqual(doi.cached_fetch("10.5555/synthetic", cache_dir=directory, offline=True)["status"], "cache_miss")

    def test_stale_cache_and_network_failure_do_not_return_stale_record(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(doi, "urlopen", return_value=response(payload())):
                doi.cached_fetch("10.5555/synthetic", cache_dir=directory)
            with mock.patch.object(doi, "urlopen", side_effect=URLError("failed")):
                row = doi.cached_fetch("10.5555/synthetic", cache_dir=directory, max_age=0)
            self.assertEqual(row["status"], "access_failed")
            self.assertNotIn("record", row)

    def test_offline_without_cache_never_uses_network(self):
        with mock.patch.object(doi, "urlopen", side_effect=AssertionError("Network used")):
            self.assertEqual(doi.cached_fetch("10.5555/synthetic", offline=True)["status"], "cache_miss")

    def test_batch_deduplicates_requests_but_preserves_each_input_row(self):
        with mock.patch.object(doi, "fetch_doi", return_value={"doi": "10.5555/a", "status": "record_found"}) as fetch, mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            code = doi.main(["10.5555/A", "https://doi.org/10.5555/a", "bad", "--retries", "0"])
        self.assertEqual(fetch.call_count, 1)
        rows = json.loads(output.getvalue())
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2]["status"], "invalid_input")
        self.assertEqual(code, 1)

    def test_bad_limits_fail_before_network(self):
        for options in ({"timeout": float("nan")}, {"retries": 4}, {"mailto": "bad\nheader"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                doi.fetch_doi("10.5555/synthetic", **options)


class GateV2Tests(unittest.TestCase):
    def test_missing_original_from_initialized_inventory_is_blocked(self):
        draft, review = materials()
        draft["input"] = {"entry_count": 2, "originals_sha256": gate.originals_hash(draft["entries"])}
        review["packet_sha256"] = gate.packet_hash(draft)
        self.assertFalse(gate.check_release(draft, review)["complete"])
        draft["input"]["entry_count"] = 1
        draft["entries"][0]["original"] = "Altered after intake"
        review["packet_sha256"] = gate.packet_hash(draft)
        self.assertFalse(gate.check_release(draft, review)["complete"])

    def test_bad_historical_issues_fail_before_export_directory_creation(self):
        draft, review = materials()
        for value in (None, "bad", [None], [{"code": "missing_detail"}]):
            review["rows"][0]["original_issues"] = value
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "release"
                with self.assertRaises(ValueError):
                    workflow.export_release(draft, review, output)
                self.assertFalse(output.exists())

    def test_all_release_inputs_are_sealed(self):
        for mutate in (lambda d: d["entries"][0].update(decision="needs_user"),
                       lambda d: d["entries"][0]["sources"][0].update(locator="changed"),
                       lambda d: d["entries"][0].update(duplicate_of="R2"),
                       lambda d: d.update(bibliography_order=["R1"]),
                       lambda d: d.update(main_agent_id="another-main")):
            draft, review = materials()
            mutate(draft)
            with self.subTest(draft=draft):
                self.assertFalse(gate.check_release(draft, review)["structural_checks_passed"])

    def test_packet_is_blind_but_digest_binds_hidden_fields(self):
        draft, _ = materials()
        self.assertNotIn("sources", gate.make_packet(draft)["entries"][0])
        old = gate.packet_hash(draft)
        draft["entries"][0]["sources"][0]["locator"] = "different evidence"
        self.assertNotEqual(gate.packet_hash(draft), old)

    def test_malformed_json_shapes_fail_without_traceback(self):
        for draft in (None, [], 7, {}, {"schema_version": True, "entries": [{}]},
                      {"schema_version": 2, "entries": [None]}, {"schema_version": 2, "entries": [{"id": [], "original": "x"}]}):
            with self.subTest(draft=draft):
                self.assertFalse(gate.check_release(draft, {})["structural_checks_passed"])
        draft, _ = materials()
        for review in (None, [], {}, {"rows": [None]}, {"rows": [{"id": []}]}):
            with self.subTest(review=review):
                self.assertFalse(gate.check_release(draft, review)["structural_checks_passed"])

    def test_blank_or_padded_agent_ids_are_rejected(self):
        for value in (" ", "synthetic-main ", [], None):
            draft, review = materials()
            review["reviewer_agent_id"] = value
            self.assertFalse(gate.check_release(draft, review)["structural_checks_passed"])

    def test_javascript_source_url_does_not_count_as_evidence(self):
        draft, review = materials()
        draft["entries"][0]["sources"][0]["url"] = "javascript:alert(1)"
        review["packet_sha256"] = gate.packet_hash(draft)
        self.assertFalse(gate.check_release(draft, review)["structural_checks_passed"])

    def test_artifact_bytes_are_checked_not_just_declared_digest(self):
        draft, review = materials()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "final.html"
            target.write_bytes(b"<i>Frozen</i>")
            draft["artifacts"] = [{"path": "final.html", "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}]
            review["packet_sha256"] = gate.packet_hash(draft)
            self.assertTrue(gate.check_release(draft, review, directory)["complete"])
            target.write_bytes(b"changed")
            self.assertFalse(gate.check_release(draft, review, directory)["structural_checks_passed"])

    def test_artifact_path_escape_is_rejected(self):
        draft, review = materials()
        draft["artifacts"] = [{"path": "../outside", "sha256": "0" * 64}]
        review["packet_sha256"] = gate.packet_hash(draft)
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(gate.check_release(draft, review, directory)["structural_checks_passed"])

    def test_duplicate_cannot_point_to_an_unresolved_or_duplicate_target(self):
        draft, review = materials()
        draft["entries"][0].update(decision="duplicate", candidate=None, duplicate_of="R1")
        review["rows"][0].update(verdict="duplicate", duplicate_of="R1", format="not_applicable")
        review["packet_sha256"] = gate.packet_hash(draft)
        self.assertFalse(gate.check_release(draft, review)["structural_checks_passed"])

    def test_output_order_is_frozen_and_must_cover_all_included_ids(self):
        draft, review = materials()
        draft["bibliography_order"] = ["R1", "R1"]
        review["packet_sha256"] = gate.packet_hash(draft)
        self.assertFalse(gate.check_release(draft, review)["structural_checks_passed"])

    def test_duplicate_json_keys_and_nonfinite_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for value in ('{"id":1,"id":2}', '{"x":NaN}', '{"x":Infinity}'):
                path.write_text(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    gate.read_json(path)


class WorkflowTests(unittest.TestCase):
    def test_init_preserves_multiline_originals_and_input_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(["第一条\n续行", "Second"]), encoding="utf-8")
            draft = workflow.initialize(path, "json", "test-main")
            self.assertEqual(draft["entries"][0]["original"], "第一条\n续行")
            self.assertEqual(draft["input"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(draft["style"]["selection"], "pending")
            self.assertTrue(all(row["candidate"] is None for row in draft["entries"]))

    def test_no_requirement_is_explicit_and_rules_are_never_invented(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text('["Original"]')
            draft = workflow.initialize(path, "json", "test-main", no_requirement=True)
            self.assertEqual(draft["style"]["name"], "GB/T 7714—2025")
            self.assertEqual(draft["style"]["rules"], [])

    def test_init_rejects_blank_references_and_ambiguous_line_wrapping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.txt"
            path.write_text("First\n\nSecond")
            with self.assertRaises(ValueError):
                workflow.initialize(path, "lines", "test-main")

    def test_audit_flags_wrong_title_and_keeps_publication_dates_distinct(self):
        with mock.patch.object(doi, "urlopen", return_value=response(payload())):
            metadata = doi.fetch_doi("10.5555/synthetic")
        report = workflow.audit([{"id": "R1", "title": "Wrong work", "DOI": "10.5555/synthetic", "issued": {"date-parts": [[2025]]}}], [metadata])
        codes = {row["code"] for row in report["entries"][0]["findings"]}
        self.assertTrue({"title_differs", "year_differs", "multiple_publication_years"} <= codes)
        self.assertEqual(report["status"], "diagnostic_only")

    def test_shared_dois_are_candidates_not_auto_merged(self):
        report = workflow.audit([{"id": "a", "DOI": "10.5555/A"}, {"id": "b", "DOI": "10.5555/a"}], [])
        self.assertEqual(report["duplicate_doi_groups"][0]["ids"], ["a", "b"])
        self.assertEqual(len(report["entries"]), 2)

    def test_non_doi_work_is_not_treated_as_fake(self):
        report = workflow.audit([{"id": "book", "title": "Synthetic book"}], [])
        self.assertEqual(report["entries"][0]["status"], "needs_non_doi_verification")

    def test_conflicting_metadata_is_not_silently_chosen(self):
        with mock.patch.object(doi, "urlopen", return_value=response(payload())):
            row = doi.fetch_doi("10.5555/synthetic")
        other = copy.deepcopy(row)
        other["record"]["title"] = ["Different title"]
        other["record_sha256"] = doi.record_digest(other["record"])
        report = workflow.audit([{"id": "R1", "DOI": row["doi"]}], [row, other])
        self.assertEqual(report["entries"][0]["findings"][0]["code"], "registry_records_conflict")

    def test_export_preserves_exact_text_and_records_hashes(self):
        draft, review = materials()
        draft["entries"][0]["candidate"] = "Frozen　text\nSecond line; [DOI]."
        review["packet_sha256"] = gate.packet_hash(draft)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            manifest = workflow.export_release(draft, review, output)
            self.assertEqual((output / "bibliography.txt").read_text(), draft["entries"][0]["candidate"] + "\n")
            self.assertEqual(manifest["files"]["bibliography.txt"], hashlib.sha256((output / "bibliography.txt").read_bytes()).hexdigest())
            self.assertEqual(gate.read_json(output / "release.json")["review"], review)
            with self.assertRaises(FileExistsError):
                workflow.export_release(draft, review, output)

    def test_export_blocks_modified_review_and_writes_no_release(self):
        draft, review = materials()
        draft["entries"][0]["candidate"] += " changed"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            with self.assertRaises(ValueError):
                workflow.export_release(draft, review, output)
            self.assertFalse(output.exists())

    def test_partial_export_is_explicit_and_preserves_pending_original(self):
        draft, review = materials()
        draft["entries"].append({"id": "R2", "original": "Unresolved original", "decision": "unresolved", "candidate": None})
        review["rows"].append({"id": "R2", "verdict": "unresolved", "identity": "unresolved", "metadata": "unresolved", "format": "not_applicable", "issues": [{"code": "no_source", "detail": "No accessible source"}]})
        review["packet_sha256"] = gate.packet_hash(draft)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            with self.assertRaises(ValueError):
                workflow.export_release(draft, review, output)
            manifest = workflow.export_release(draft, review, output, allow_partial=True)
            self.assertEqual(manifest["status"], "partial")
            self.assertIn("Unresolved original", (output / "report.md").read_text())
            self.assertNotIn("Unresolved original", (output / "bibliography.txt").read_text())

    def test_doctor_checks_every_manifest_asset(self):
        result = workflow.doctor()
        self.assertEqual(len(result["assets"]), 6)
        self.assertTrue(all(row["passed"] for row in result["assets"]))
        self.assertIn("Real independent subagent creation", result["requires_host_check"])


@unittest.skipUnless(os.environ.get("REFERENCE_GUARD_TEST_NODE") or shutil.which("node"), "Node required")
class FormatV2Tests(unittest.TestCase):
    def render(self, items, style="apa7"):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "items.json"
            source.write_text(json.dumps(items))
            return subprocess.run([os.environ.get("REFERENCE_GUARD_TEST_NODE") or shutil.which("node"), str(SCRIPTS / "format_bibliography.cjs"), "--input", str(source), "--style", style], capture_output=True, text=True)

    def test_alphabetical_output_order_maps_to_original_ids(self):
        result = self.render([{"id": "R1", "type": "book", "title": "Zed", "author": [{"family": "Zed"}]},
                              {"id": "R2", "type": "book", "title": "Alpha", "author": [{"family": "Alpha"}]}])
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["bibliography_order"], ["R2", "R1"])
        self.assertEqual([row["input_index"] for row in output["entries"]], [2, 1])

    def test_impossible_dates_names_and_urls_fail_before_rendering(self):
        changes = [{"issued": {"date-parts": [[2024, 13]]}}, {"issued": {"date-parts": [[2023, 2, 29]]}},
                   {"issued": {"date-parts": [[2024, 1, 0]]}}, {"author": "Unknown"},
                   {"author": [{"family": []}]}, {"URL": "javascript:alert(1)"}, {"id": " R1"}]
        for change in changes:
            with self.subTest(change=change):
                result = self.render([dict({"id": "R1", "type": "book", "title": "Synthetic"}, **change)])
                self.assertNotEqual(result.returncode, 0)

    def test_valid_leap_day_can_render(self):
        result = self.render([{"id": "R1", "type": "webpage", "title": "Synthetic", "issued": {"date-parts": [[2024, 2, 29]]}}])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bom_encoded_csl_input_can_render(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "items.json"
            source.write_text('[{"id":"R1","type":"book","title":"Synthetic"}]', encoding="utf-8-sig")
            result = subprocess.run([os.environ.get("REFERENCE_GUARD_TEST_NODE") or shutil.which("node"), str(SCRIPTS / "format_bibliography.cjs"), "--input", str(source), "--style", "apa7"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
