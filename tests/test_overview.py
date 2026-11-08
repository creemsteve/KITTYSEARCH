import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kittysearch as core
import kittysearch_overview as overview
from test_local_model import FakeModel, response, review


def overview_response(text, sources=None):
    if sources is None:
        sources = sorted(overview.citations(text), key=int)
    return {"choices": [{"message": {"content": json.dumps({"text": text, "sources": sources})}}]}


class SynthesisModel:
    def __init__(self):
        self.calls = []

    def tokenize(self, value):
        return range((len(value) + 2) // 3)

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        notes = json.loads(kwargs["messages"][-1]["content"])["findings"]
        ids = sorted({s for note in notes for s in note["sources"]}, key=int)
        return overview_response("Findings are limited to the supplied content. " + " ".join(f"[{s}]" for s in ids))


class OverviewTests(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(home.cleanup)
        patcher = patch.object(core, "data_dir", return_value=Path(home.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cfg = dict(core.DEFAULTS, model_path="fake.gguf")
        self.items = [{"title": "First", "url": "https://example.org/a", "content": "First finding"},
                      {"title": "Second", "url": "https://example.org/b", "content": "Second finding"}]

    def search(self, model, items=None):
        with patch.object(core, "get_local_model", return_value=model), patch.object(core, "http_json", return_value={"results": self.items if items is None else items}):
            return core.search("query", self.cfg)

    def test_search_keeps_page_summaries_and_cited_overview_after_ranking(self):
        model = FakeModel([response([review(0, relevance=10, summary="First finding"),
                                     review(1, relevance=90, summary="Second finding")]),
                           overview_response("First finding [1]. Second finding [2].")])
        data = self.search(model)
        self.assertIsNone(data["overview_error"])
        self.assertEqual(data["overview"]["reviewed"], 2)
        self.assertEqual(data["results"][0]["kitty_source_id"], "2")
        self.assertEqual(data["results"][0]["kitty_summary"], "Second finding")
        self.assertEqual(data["overview"]["sources"][0]["url"], self.items[0]["url"])
        findings = json.loads(model.calls[-1]["messages"][-1]["content"])["findings"]
        self.assertEqual([n["text"] for n in findings], ["First finding", "Second finding"])
        self.assertEqual(findings[0]["basis"], "search snippet")

    def test_synthesis_failure_does_not_discard_valid_reviews(self):
        for answer in (overview_response("Unsupported [99]."), overview_response("No citations."),
                       overview_response(""), {"choices": []},
                       {"choices": [{"message": {"content": '{"text":'}, "finish_reason": "length"}]}):
            with self.subTest(answer=answer):
                data = self.search(FakeModel([response([review(0), review(1)]), answer]))
                self.assertTrue(data["analyzed"])
                self.assertTrue(all(i["kitty_ai_reviewed"] for i in data["results"]))
                self.assertIsNone(data["model_error"])
                self.assertIsNone(data["overview"])
                self.assertIn("General overview unavailable", data["overview_error"])

    def test_structured_sources_become_citations_when_model_omits_inline_markers(self):
        data = self.search(FakeModel([response([review(0), review(1)]),
                                     overview_response("Combined knowledge.", ["1", "2"])]))
        self.assertEqual(data["overview"]["text"], "Combined knowledge. [1] [2]")

    def test_no_model_or_empty_results_skip_synthesis(self):
        with patch.object(overview, "synthesize") as synthesize:
            self.cfg["model_path"] = ""
            self.assertIsNone(self.search(FakeModel([]))["overview"])
            self.cfg["model_path"] = "fake.gguf"
            self.assertIsNone(self.search(FakeModel([]), [])["overview"])
        synthesize.assert_not_called()

    def test_partial_reviews_only_contribute_known_findings(self):
        data = self.search(FakeModel([response([review(1)]), overview_response("Second page finding [2].")]))
        self.assertEqual((data["overview"]["reviewed"], data["overview"]["total"]), (1, 2))
        self.assertEqual([s["id"] for s in data["overview"]["sources"]], ["2"])
        self.assertIn("reviewed 1 of 2", data["model_error"])

    def test_many_unicode_findings_reduce_within_small_context(self):
        items = self.items * 25
        reviews = {str(i): review(i, summary="中文 findings with qualifications. " * 12) for i in range(50)}
        model = SynthesisModel()
        cfg = dict(self.cfg, model_context=2048, kitty_mode=True)
        result = overview.synthesize("query", items, reviews, cfg, model, core.KITTY_MODE_DIRECTIVE)
        self.assertEqual(result["reviewed"], 50)
        self.assertEqual(len(result["sources"]), 50)
        self.assertGreater(len(model.calls), 1)
        for call in model.calls:
            tokens = sum(len(model.tokenize(m["content"].encode())) for m in call["messages"])
            self.assertLessEqual(tokens + call["max_tokens"] + 192, 2048)
            self.assertIn("untrusted data", call["messages"][0]["content"])
            self.assertIn(core.KITTY_MODE_DIRECTIVE, call["messages"][0]["content"])

    def test_insufficient_context_reports_error_without_inference(self):
        model = SynthesisModel()
        with self.assertRaisesRegex(ValueError, "context"):
            overview.synthesize("query", self.items, {"0": review(0)}, dict(self.cfg, model_context=200), model)
        self.assertEqual(model.calls, [])

    def test_invalid_page_summaries_are_rejected(self):
        for summary in (None, 7, "", " " * 20, "x" * 501):
            with self.subTest(summary=summary), patch.object(core, "get_local_model", return_value=FakeModel([response([review(0, summary=summary)])])):
                with self.assertRaisesRegex(ValueError, "no valid reviews"):
                    core.analyze_with_local_model("query", self.items[:1], self.cfg)


if __name__ == "__main__":
    unittest.main()
