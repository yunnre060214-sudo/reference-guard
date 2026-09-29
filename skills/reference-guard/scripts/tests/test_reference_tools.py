"""Behavior tests: rendering, DOI response identity, and review coverage.

Expectations concern observable output and rejected releases, not skill wording.
"""
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
NODE = os.environ.get("REFERENCE_GUARD_TEST_NODE") or shutil.which("node")


def load_script(name):
    path = ROOT / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(NODE, "Node.js is required for formatting tests")
class FormatTests(unittest.TestCase):
    def render(self, items, style="gbt2025"):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "items.json"
            source.write_text(json.dumps(items), encoding="utf-8")
            return subprocess.run(
                [NODE, str(ROOT / "scripts" / "format_bibliography.cjs"),
                 "--input", str(source), "--style", style],
                capture_output=True, text=True,
            )

    def journal(self, **changes):
        # Deliberately synthetic formatting input; it is not a source record.
        item = {
            "id": "format-fixture", "type": "article-journal",
            "title": "A test of bibliographic formatting",
            "author": [{"family": n, "given": g} for n, g in
                       [("Alpha", "Ada"), ("Beta", "Ben"),
                        ("Gamma", "Cam"), ("Delta", "Dan")]],
            "container-title": "Example Journal", "volume": "12", "issue": "3",
            "page": "101-109", "issued": {"date-parts": [[2024]]},
        }
        item.update(changes)
        return item

    def test_gbt2025_journal_fields_and_three_author_truncation(self):
        result = self.render([self.journal()])
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = json.loads(result.stdout)["entries"][0]
        self.assertIn("[J]", entry["text"])
        self.assertIn("2024，12（3）：101-109", entry["text"])
        self.assertIn("Alpha A，Beta B，Gamma C，等", entry["text"])
        self.assertNotIn("Delta", entry["text"])

    def test_preprint_is_pp_and_never_a_journal(self):
        item = self.journal(type="article", publisher="arXiv", URL="https://example.org/fixture",
                            accessed={"date-parts": [[2026, 9, 28]]})
        for key in ("container-title", "volume", "issue", "page"):
            item.pop(key)
        result = self.render([item])
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = json.loads(result.stdout)["entries"][0]["text"]
        self.assertIn("[PP/OL]", entry)
        self.assertIn("arXiv", entry)
        self.assertIn("[2026-09-28]", entry)
        self.assertNotIn("[J", entry)

    def test_apa_all_four_authors_and_italics_survive_html(self):
        result = self.render([self.journal()], "apa7")
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = json.loads(result.stdout)["entries"][0]
        self.assertIn("Delta, D.", entry["text"])
        self.assertNotIn("[J]", entry["text"])
        self.assertIn("<i>Example Journal</i>", entry["html"])

    def test_ieee_has_numeric_label_and_volume_and_issue(self):
        result = self.render([self.journal()], "ieee")
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = json.loads(result.stdout)["entries"][0]["text"]
        self.assertIn("[1]", entry)
        self.assertIn("vol. 12", entry)
        self.assertIn("no. 3", entry)
        self.assertNotIn("[J]", entry)

    def test_duplicate_ids_rejected_instead_of_silently_dropping_a_row(self):
        result = self.render([self.journal(), self.journal(title="Different work")])
        self.assertNotEqual(result.returncode, 0)

    def test_no_date_is_invented_when_metadata_has_none(self):
        item = self.journal()
        item.pop("issued")
        result = self.render([item])
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = json.loads(result.stdout)["entries"][0]["text"]
        self.assertNotIn("2026", entry)
        self.assertNotIn("2024", entry)

    def test_access_date_is_not_used_as_estimated_publication_year(self):
        for kind in ("book", "report"):
            with self.subTest(kind=kind):
                item = {"id": "undated", "type": kind, "title": "Synthetic undated item",
                        "URL": "https://example.org/undated", "accessed": {"date-parts": [[2026, 9, 28]]}}
                result = self.render([item])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("2026", json.loads(result.stdout)["entries"][0]["text"])

    def test_known_archive_pages_are_preserved(self):
        item = {"id": "archive", "type": "manuscript", "title": "Synthetic archive item",
                "archive": "Fixture Archive", "archive-place": "Fixture City",
                "archive_location": "F-001", "issued": {"date-parts": [[1931, 11, 7]]}, "page": "3-6"}
        result = self.render([item])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1931-11-07：3-6", json.loads(result.stdout)["entries"][0]["text"])

    def test_report_form_is_explicit_and_controls_date_precision(self):
        base = {"id": "report", "type": "report", "title": "Synthetic report",
                "publisher": "Fixture Publisher", "publisher-place": "Fixture City",
                "issued": {"date-parts": [[2023, 12, 28]]}}
        standalone = self.render([dict(base, **{"publication-form": "standalone"})])
        book = self.render([dict(base, **{"publication-form": "book"})])
        self.assertEqual(standalone.returncode, 0, standalone.stderr)
        self.assertEqual(book.returncode, 0, book.stderr)
        standalone_text = json.loads(standalone.stdout)["entries"][0]["text"]
        book_text = json.loads(book.stdout)["entries"][0]["text"]
        self.assertIn("2023-12-28", standalone_text)
        self.assertNotIn("Fixture Publisher", standalone_text)
        self.assertIn("Fixture Publisher，2023", book_text)
        self.assertNotIn("2023-12-28", book_text)

    def test_publisher_alone_cannot_choose_a_report_publication_form(self):
        item = {"id": "report", "type": "report", "title": "Synthetic report",
                "publisher": "Fixture Publisher", "issued": {"date-parts": [[2023, 12, 28]]}}
        result = self.render([item])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("publication-form", result.stderr)

    def test_evidenced_estimated_year_keeps_its_brackets(self):
        item = {"id": "estimated", "type": "book", "title": "Synthetic dated book",
                "publisher": "Fixture Publisher", "issued": {"date-parts": [[1936]], "circa": True}}
        result = self.render([item])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[1936]", json.loads(result.stdout)["entries"][0]["text"])

    def test_estimated_journal_year_keeps_brackets_in_each_date_path(self):
        dated = self.journal(issued={"date-parts": [[1936]], "circa": True})
        online = copy.deepcopy(dated)
        online.pop("volume")
        online.pop("issue")
        available = copy.deepcopy(online)
        available["issued"] = {"date-parts": [[1937]]}
        available["available-date"] = {"date-parts": [[1936]], "circa": True}
        for item in (dated, online, available):
            with self.subTest(item=item):
                result = self.render([item])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("[1936]", json.loads(result.stdout)["entries"][0]["text"])

    def test_preprint_version_label_is_not_duplicated(self):
        for version in ("7", "V7", "v7"):
            with self.subTest(version=version):
                item = {"id": "preprint", "type": "article", "title": "Synthetic preprint",
                        "version": version, "publisher": "Fixture Repository",
                        "issued": {"date-parts": [[2023, 8, 2]]},
                        "accessed": {"date-parts": [[2026, 9, 29]]}, "URL": "https://example.org/preprintv7"}
                result = self.render([item])
                self.assertEqual(result.returncode, 0, result.stderr)
                text = json.loads(result.stdout)["entries"][0]["text"]
                self.assertIn("V7.", text)
                self.assertNotIn("VV7", text)
                self.assertNotIn("Vv7", text)

    def test_doi_only_online_item_warns_that_access_path_is_missing(self):
        item = self.journal(DOI="10.5555/fixture-only")
        result = self.render([item])
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "candidate_only")
        self.assertTrue(any("URL" in warning for warning in output["warnings"]))

    def test_gbt_standard_number_missing_is_not_silently_ignored(self):
        item = {"id": "standard", "type": "standard", "title": "Synthetic unnamed-number standard",
                "issued": {"date-parts": [[2025]]}}
        result = self.render([item])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any("number" in warning for warning in json.loads(result.stdout)["warnings"]))


class ReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_script("review_gate")
        self.draft = {
            "schema_version": 1, "main_agent_id": "/root",
            "style": {"name": "GB/T 7714—2025", "selection": "user_no_requirement",
                      "rules": [{"url": "https://example.org/standard", "locator": "8.5"}]},
            "entries": [
                {"id": "R1", "original": "Original reference", "decision": "include",
                 "candidate": "Corrected reference", "evidence_status": "verified",
                 "sources": [{"url": "https://example.org/paper", "locator": "article record"}]},
                {"id": "R2", "original": "Ambiguous original", "decision": "needs_user",
                 "candidate": None, "evidence_status": "unresolved", "sources": []},
            ],
        }
        self.review = {
            "reviewer_agent_id": "/root/adversary", "independent": True,
            "packet_sha256": self.tool.packet_hash(self.draft),
            "rows": [
                {"id": "R1", "verdict": "pass", "identity": "verified",
                 "metadata": "verified", "format": "verified", "issues": [],
                 "sources": [{"url": "https://example.org/paper", "locator": "reopened record"}]},
                {"id": "R2", "verdict": "needs_user", "identity": "unresolved",
                 "metadata": "unresolved", "format": "not_applicable",
                 "issues": [{"code": "identity_ambiguous", "detail": "Two possible works"}],
                 "sources": []},
            ],
        }

    def test_full_coverage_allows_only_verified_subset_and_labels_partial(self):
        result = self.tool.check_release(self.draft, self.review)
        self.assertTrue(result["structural_checks_passed"], result)
        self.assertFalse(result["complete"])
        self.assertEqual(result["released_ids"], ["R1"])
        self.assertEqual(result["pending_ids"], ["R2"])

    def test_omitted_unresolved_original_is_not_full_review(self):
        self.review["rows"].pop()
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_main_agent_cannot_certify_its_own_review(self):
        self.review["reviewer_agent_id"] = "/root"
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_changed_final_text_invalidates_earlier_review(self):
        self.draft["entries"][0]["candidate"] += " DOI:incorrect"
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_format_unverifiable_cannot_pass_despite_truthful_metadata(self):
        self.review["rows"][0]["format"] = "unverifiable"
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_a_blocking_finding_prevents_release(self):
        self.review["rows"][0]["issues"] = [{"code": "doi_mismatch", "detail": "DOI is for a different work"}]
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_blind_packet_does_not_contain_main_agent_conclusions_or_ledger(self):
        packet = self.tool.make_packet(self.draft)
        row = packet["entries"][0]
        self.assertEqual(row["original"], "Original reference")
        self.assertEqual(row["candidate"], "Corrected reference")
        self.assertNotIn("decision", row)
        self.assertNotIn("evidence_status", row)
        self.assertNotIn("sources", row)

    def test_duplicate_review_rows_cannot_hide_unreviewed_entry(self):
        self.review["rows"] = [self.review["rows"][0], self.review["rows"][0]]
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_incomplete_metadata_is_not_released_even_with_reviewer_pass(self):
        self.draft["entries"][0]["evidence_status"] = "unresolved"
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_duplicate_with_a_blocking_issue_cannot_be_merged(self):
        entry = self.draft["entries"][1]
        entry.update(decision="duplicate", duplicate_of="R1", evidence_status="verified",
                     sources=copy.deepcopy(self.draft["entries"][0]["sources"]))
        row = self.review["rows"][1]
        row.update(verdict="duplicate", duplicate_of="R1", identity="verified", metadata="verified",
                   format="not_applicable", issues=[], sources=copy.deepcopy(self.review["rows"][0]["sources"]))
        self.assertTrue(self.tool.check_release(self.draft, self.review)["complete"])
        row["issues"] = [{"code": "version_conflict", "severity": "blocking", "detail": "Versions differ"}]
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_no_requirement_cannot_silently_default_to_apa(self):
        self.draft["style"]["name"] = "APA 7"
        self.review["packet_sha256"] = self.tool.packet_hash(self.draft)
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_source_locator_and_address_must_be_nonempty_strings(self):
        self.draft["entries"][0]["sources"] = [{"url": {"fake": "value"}, "locator": ["fake"]}]
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_unresolved_entry_still_needs_explicit_review_states(self):
        self.review["rows"][1] = {"id": "R2", "verdict": "needs_user"}
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_changed_candidate_html_invalidates_the_review(self):
        self.draft["entries"][0]["candidate_html"] = "<i>Corrected reference</i>"
        self.review["packet_sha256"] = self.tool.packet_hash(self.draft)
        self.draft["entries"][0]["candidate_html"] = "Corrected reference"
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])

    def test_changed_presentation_invalidates_the_review(self):
        self.draft["presentation"] = {"hanging-indent": True}
        self.review["packet_sha256"] = self.tool.packet_hash(self.draft)
        self.draft["presentation"]["hanging-indent"] = False
        self.assertFalse(self.tool.check_release(self.draft, self.review)["structural_checks_passed"])


class DoiTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_script("doi_metadata")
        self.payload = {"status": "ok", "message-type": "work", "message": {
            "DOI": "10.1038/s41586-021-03819-2",
            "title": ["Highly accurate protein structure prediction with AlphaFold"],
            "author": [{"family": "Jumper", "given": "John"}],
            "container-title": ["Nature"], "volume": "596", "issue": "7873",
            "page": "583-589", "type": "journal-article",
            "published-print": {"date-parts": [[2021, 8, 26]]},
            "published-online": {"date-parts": [[2021, 7, 15]]},
        }}

    def response(self, payload):
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    def test_record_found_is_not_claimed_to_match_input_citation(self):
        with mock.patch.object(self.tool, "urlopen", return_value=self.response(self.payload)):
            result = self.tool.fetch_doi("https://doi.org/10.1038/s41586-021-03819-2")
        self.assertEqual(result["status"], "record_found")
        self.assertNotIn("verified", result)
        self.assertEqual(result["record"]["title"], self.payload["message"]["title"])
        self.assertEqual(result["record"]["published-print"]["date-parts"], [[2021, 8, 26]])
        self.assertEqual(result["record"]["published-online"]["date-parts"], [[2021, 7, 15]])

    def test_mismatched_registry_response_is_not_accepted(self):
        self.payload["message"]["DOI"] = "10.1038/nature14539"
        with mock.patch.object(self.tool, "urlopen", return_value=self.response(self.payload)):
            result = self.tool.fetch_doi("10.1038/s41586-021-03819-2")
        self.assertEqual(result["status"], "response_mismatch")

    def test_registry_404_never_claims_universal_nonexistence(self):
        error = HTTPError("https://api.crossref.org/works/10.5555/absent", 404, "Not Found", {}, None)
        with mock.patch.object(self.tool, "urlopen", side_effect=error):
            result = self.tool.fetch_doi("10.5555/absent")
        self.assertEqual(result["status"], "not_found_in_registries")
        self.assertNotIn("nonexistent", json.dumps(result))

    def test_network_failure_is_an_access_failure_not_a_fake_reference(self):
        with mock.patch.object(self.tool, "urlopen", side_effect=URLError("connection timed out")):
            result = self.tool.fetch_doi("10.1038/s41586-021-03819-2")
        self.assertEqual(result["status"], "access_failed")

    def test_malformed_crossref_record_is_reported_without_crashing(self):
        for malformed in (None, [], "unexpected-string"):
            with self.subTest(record_type=type(malformed).__name__):
                payload = dict(self.payload, message=malformed)
                with mock.patch.object(self.tool, "urlopen", return_value=self.response(payload)):
                    result = self.tool.fetch_doi("10.1038/s41586-021-03819-2")
                self.assertEqual(result["status"], "access_failed")
                self.assertNotIn("record", result)

    def test_malformed_datacite_record_after_404_is_not_claimed_absent(self):
        error = HTTPError("https://api.crossref.org/works/x", 404, "Not Found", {}, None)
        for malformed in (None, [], "unexpected-string"):
            with self.subTest(record_type=type(malformed).__name__):
                payload = {"data": {"id": "10.48550/arxiv.1706.03762", "type": "dois", "attributes": malformed}}
                with mock.patch.object(self.tool, "urlopen", side_effect=[error, self.response(payload)]):
                    result = self.tool.fetch_doi("10.48550/arXiv.1706.03762")
                self.assertEqual(result["status"], "access_failed")
                self.assertNotEqual(result["status"], "not_found_in_registries")

    def test_crossref_error_or_wrong_resource_envelope_is_not_a_record(self):
        for changes in ({"status": "failed", "message-type": "error"}, {"message-type": "member"}):
            with self.subTest(changes=changes):
                payload = dict(self.payload, **changes)
                with mock.patch.object(self.tool, "urlopen", return_value=self.response(payload)):
                    result = self.tool.fetch_doi("10.1038/s41586-021-03819-2")
                self.assertEqual(result["status"], "access_failed")

    def test_datacite_error_type_and_envelope_id_must_not_be_accepted(self):
        error = HTTPError("https://api.crossref.org/works/x", 404, "Not Found", {}, None)
        base = {"data": {"id": "10.48550/arxiv.1706.03762", "type": "dois",
                         "attributes": {"doi": "10.48550/arXiv.1706.03762"}}}
        bad_payloads = [dict(copy.deepcopy(base), errors=[{"title": "Upstream error"}]),
                        copy.deepcopy(base), copy.deepcopy(base)]
        bad_payloads[1]["data"]["type"] = "clients"
        bad_payloads[2]["data"]["id"] = "10.1038/nature14539"
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                with mock.patch.object(self.tool, "urlopen", side_effect=[error, self.response(payload)]):
                    result = self.tool.fetch_doi("10.48550/arXiv.1706.03762")
                self.assertIn(result["status"], ("access_failed", "response_mismatch"))
                self.assertNotIn("record", result)

    def test_datacite_record_can_follow_a_crossref_404(self):
        error = HTTPError("https://api.crossref.org/works/x", 404, "Not Found", {}, None)
        payload = {"data": {"id": "10.48550/arxiv.1706.03762", "type": "dois", "attributes": {
            "doi": "10.48550/arXiv.1706.03762", "titles": [{"title": "Attention Is All You Need"}],
            "creators": [{"name": "Vaswani, Ashish"}], "publicationYear": 2017,
            "publisher": "arXiv", "types": {"resourceTypeGeneral": "Preprint"},
        }}}
        with mock.patch.object(self.tool, "urlopen", side_effect=[error, self.response(payload)]):
            result = self.tool.fetch_doi("10.48550/arXiv.1706.03762")
        self.assertEqual(result["status"], "record_found")
        self.assertEqual(result["registry"], "DataCite")
        self.assertEqual(result["record"]["publicationYear"], 2017)


if __name__ == "__main__":
    unittest.main()
