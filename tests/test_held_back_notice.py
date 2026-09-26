"""A cited section that is in the source but not searchable gets a notice.

The notice names the section. It does not hide or change results.
"""
from pathlib import Path
import tempfile
import unittest

from lawindex.retrieval import SearchFilters
from lawindex.search import Snapshot, candidate_section_keys


class HeldBackNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Snapshot()

    def codes(self, result):
        return [notice["code"] for notice in result["notices"]]

    def section_notice(self, result):
        notices = [notice for notice in result["notices"] if notice["code"] == "section_not_indexed"]
        self.assertEqual(len(notices), 1)
        return notices[0]

    def test_held_back_key_gives_the_notice(self):
        labels = self.s.source_keys["contract-1872"]
        self.assertEqual(labels["contract-1872:73"], "73")
        self.assertNotIn("contract-1872:73", {key.casefold() for key in self.s.records})
        title = self.s.acts["contract-1872"]["title"]
        expected = (f"Section 73 of {title} exists in the source but is not searchable yet. "
                    "Open the source PDF to read it.")
        by_title = self.s.search("The Indian Contract Act, 1872 section 73")
        self.assertEqual(by_title["trace"]["act_filters"], ["contract-1872"])
        self.assertEqual(self.section_notice(by_title)["message"], expected)
        by_filter = self.s.search("section 73", filters=SearchFilters(act="contract-1872"))
        self.assertEqual(self.section_notice(by_filter)["message"], expected)

    def test_admitted_section_gives_no_notice(self):
        self.assertIn("contract-1872:75", self.s.records)
        result = self.s.search("The Indian Contract Act, 1872 section 75")
        self.assertNotIn("section_not_indexed", self.codes(result))
        self.assertTrue(any(item["key"] == "contract-1872:75" for item in result["results"]))

    def test_section_not_in_the_source_gives_no_notice(self):
        self.assertNotIn("contract-1872:999", self.s.source_keys["contract-1872"])
        result = self.s.search("The Indian Contract Act, 1872 section 999")
        self.assertNotIn("section_not_indexed", self.codes(result))

    def test_missing_candidate_file_gives_no_notice_and_no_error(self):
        missing = self.s.root / "data/phase3/candidates/not-a-real-act.json"
        self.assertFalse(missing.exists())
        self.assertIsNone(candidate_section_keys(missing))
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "contract-1872.json"
            bad.write_text("{not json")
            self.assertIsNone(candidate_section_keys(bad))
            bad.write_text("[]")
            self.assertIsNone(candidate_section_keys(bad))
            bad.write_text('{"candidates": [{"key": "contract-1872:73", "body_text": "not kept"}]}')
            kept = candidate_section_keys(bad)
            self.assertEqual(kept, {"contract-1872:73": "73"})
        saved = self.s.source_keys.pop("contract-1872")
        self.addCleanup(self.s.source_keys.__setitem__, "contract-1872", saved)
        result = self.s.search("The Indian Contract Act, 1872 section 73")
        self.assertNotIn("section_not_indexed", self.codes(result))
        self.assertIn("results", result)

    def test_results_are_still_returned_when_the_notice_fires(self):
        query = "The Indian Contract Act, 1872 section 73"
        with_notice = self.s.search(query)
        self.assertIn("section_not_indexed", self.codes(with_notice))
        saved = self.s.source_keys.pop("contract-1872")
        self.addCleanup(self.s.source_keys.__setitem__, "contract-1872", saved)
        without = self.s.search(query)
        self.assertEqual([item["key"] for item in with_notice["results"]],
                         [item["key"] for item in without["results"]])
        self.assertEqual(with_notice["total"], without["total"])
        self.assertEqual(with_notice["trace"]["final_order"], without["trace"]["final_order"])
        self.assertNotIn("section_not_indexed", self.codes(without))


if __name__ == "__main__":
    unittest.main()
