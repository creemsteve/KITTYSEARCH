import json
import unittest
from unittest.mock import patch

import kittysearch as core


def response(reviews):
    return {"choices": [{"message": {"content": json.dumps({"results": reviews})}}]}


def review(idx, **changes):
    result = {"id": str(idx), "relevance": 80, "quality": 70,
              "ai_generated": False, "confidence": 0, "reason": "Relevant snippet"}
    result.update(changes)
    return result


class FakeModel:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.answers)


class LocalReviewTests(unittest.TestCase):
    def setUp(self):
        self.items = [{"title": "A", "url": "https://example.org", "content": "snippet"} for _ in range(3)]
        self.cfg = dict(core.DEFAULTS, model_path="granite.gguf")

    def test_batches_and_validates_reviews(self):
        model = FakeModel([response([review(0), review(1), review(2)]), response([review(2)])])
        with patch.object(core, "get_local_model", return_value=model):
            result = core.analyze_with_local_model("query", self.items, self.cfg)
        self.assertEqual(set(result), {"0", "1", "2"})
        self.assertEqual(len(model.calls), 2)
        self.assertIn("untrusted data", model.calls[0]["messages"][0]["content"])
        self.assertEqual(model.calls[0]["response_format"], {"type": "json_object"})

    def test_kitty_mode_directive_applies_to_every_batch_and_can_be_disabled(self):
        answers = [response([review(0), review(1)]), response([review(2)])]
        model = FakeModel(answers * 2)
        cfg = dict(self.cfg, kitty_mode=True)
        with patch.object(core, "get_local_model", return_value=model):
            result = core.analyze_with_local_model("query", self.items, cfg)
            cfg["kitty_mode"] = False
            core.analyze_with_local_model("query", self.items, cfg)
        self.assertEqual(set(result), {"0", "1", "2"})
        for call in model.calls[:2]:
            self.assertEqual(call["messages"][0], {"role": "system", "content": core.KITTY_MODE_DIRECTIVE})
            self.assertIn("therian catgirl", call["messages"][0]["content"])
            self.assertEqual(call["messages"][1]["role"], "user")
            self.assertIn("untrusted data", call["messages"][1]["content"])
            self.assertEqual(call["response_format"], {"type": "json_object"})
        for call in model.calls[2:]:
            self.assertEqual(len(call["messages"]), 1)
            self.assertEqual(call["messages"][0]["role"], "user")

    def test_invalid_types_and_unknown_ids_are_rejected(self):
        model = FakeModel([response([review(0, ai_generated="false"), review(99)]),
                           response([review(2, relevance=101)])])
        with patch.object(core, "get_local_model", return_value=model):
            with self.assertRaisesRegex(ValueError, "no valid reviews"):
                core.analyze_with_local_model("query", self.items, self.cfg)

    def test_partial_reviews_fall_back_and_are_reported(self):
        model = FakeModel([response([review(0)]), response([])])
        with patch.object(core, "get_local_model", return_value=model), patch.object(core, "http_json", return_value={"results": self.items}):
            result = core.search("query", self.cfg)
        self.assertTrue(result["analyzed"])
        self.assertIn("reviewed 1 of 3", result["model_error"])
        self.assertEqual(sum(item["kitty_ai_reviewed"] for item in result["results"]), 1)

    def test_model_failure_uses_lexical_ranking(self):
        with patch.object(core, "get_local_model", side_effect=RuntimeError("runtime unavailable")), patch.object(core, "http_json", return_value={"results": self.items}):
            result = core.search("query", self.cfg)
        self.assertFalse(result["analyzed"])
        self.assertEqual(result["model_error"], "runtime unavailable")
        self.assertTrue(all(not item["kitty_ai_reviewed"] for item in result["results"]))

    def test_unsupported_model_authorship_claim_is_not_a_flag(self):
        claim = review(0, ai_generated=True, confidence=100, reason="This looks generated")
        with patch.object(core, "analyze_with_local_model", return_value={"0": claim}), patch.object(core, "http_json", return_value={"results": self.items[:1]}):
            result = core.search("query", self.cfg)
        self.assertFalse(result["results"][0]["kitty_ai_generated"])

    def test_empty_results_do_not_load_model(self):
        with patch.object(core, "get_local_model") as get_model:
            self.assertEqual(core.analyze_with_local_model("query", [], self.cfg), {})
            get_model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
