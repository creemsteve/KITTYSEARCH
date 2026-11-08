import io
import json
import socket
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import Mock, patch

import kittysearch as core
import kittysearch_models as models
import kittysearch_pages as pages


class ReviewingModel:
    def __init__(self, fail_first=False):
        self.calls = []
        self.fail_first = fail_first

    def tokenize(self, value):
        # Deliberately conservative tokenizer to exercise small-context splits.
        return list(range((len(value) + 2) // 3))

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        if "text" in kwargs["response_format"]["schema"]["properties"]:
            return {"choices": [{"message": {"content": json.dumps({"text": "A usable finding [1]."})}}]}
        if self.fail_first and len(self.calls) == 1:
            return {"choices": [{"message": {"content": "{}"}}]}
        entries = json.loads(kwargs["messages"][-1]["content"].split("\nResults: ", 1)[1])
        reviews = []
        for entry in entries:
            useful = "USEFUL ANSWER" in entry.get("page_excerpt", "")
            reviews.append(dict(id=entry["id"], relevance=95 if useful else 20,
                                quality=90 if useful else 30, ai_generated=False, confidence=0,
                                reason="Found usable answer" if useful else "No answer in this passage",
                                summary="Useful answer from this passage" if useful else "No answer supplied in this passage"))
        return {"choices": [{"message": {"content": json.dumps({"results": reviews})}}]}


def page_response(raw, content_type="text/html; charset=utf-8"):
    response = io.BytesIO(raw)
    response.headers = Message()
    response.headers["Content-Type"] = content_type
    response.geturl = lambda: "https://example.org/final"
    return response


class PageRetrievalTests(unittest.TestCase):
    def fetch(self, raw, limit=6000, kind="text/html; charset=utf-8"):
        opener = Mock()
        opener.open.return_value = page_response(raw, kind)
        with patch.object(pages, "check_url"), patch.object(pages.urllib.request, "build_opener", return_value=opener):
            return pages.fetch_page("https://example.org", limit, 10, core.DEFAULTS)

    def test_html_extracts_prose_and_excludes_nested_hidden_and_navigation(self):
        raw = b'''<html><head><script>bad script</script><style>bad style</style></head>
        <body><nav><div>bad menu</div></nav><main><h1>Result</h1>
        <p>Useful &amp; readable <strong>answer</strong>.</p>
        <div hidden><p>bad hidden</p></div><p aria-hidden="true">bad aria</p>
        <div style="display: none">bad inline</div><p>Final evidence</p></main>
        <footer>bad footer</footer></body></html>'''
        result = self.fetch(raw)
        self.assertNotIn("bad", result["text"])
        self.assertIn("Useful & readable", result["text"])
        self.assertIn("Final evidence", result["text"])
        self.assertFalse(result["truncated"])
        self.assertEqual(result["url"], "https://example.org/final")

    def test_depth_limits_and_response_byte_limit(self):
        raw = ("Evidence " * 4000).encode()
        for depth in ("page", "deep"):
            result = self.fetch(raw, pages.DEPTHS[depth], "text/plain")
            self.assertEqual(len(result["text"]), pages.DEPTHS[depth])
            self.assertTrue(result["truncated"])
        with patch.object(pages, "MAX_BYTES", 100):
            result = self.fetch(b"x" * 300, kind="text/plain")
        self.assertEqual(len(result["text"]), 100)
        self.assertTrue(result["truncated"])

    def test_unsupported_empty_and_unrecognized_charset(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            self.fetch(b"%PDF", kind="application/pdf")
        with self.assertRaisesRegex(ValueError, "No readable"):
            self.fetch(b"<script>only script</script>")
        self.assertEqual(self.fetch(b"readable", kind="text/plain; charset=unknown-encoding")["text"], "readable")

    def test_unsafe_urls_and_private_dns_are_not_requested(self):
        for url in ("file:///secret", "https://user:pass@example.org", "http://127.0.0.1", "http://[::1]", "http://example.org"):
            with self.subTest(url=url), patch.object(pages.socket, "getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]):
                with self.assertRaises(ValueError):
                    pages.check_url(url, core.DEFAULTS)

    def test_redirects_obey_domain_filters_before_resolving(self):
        handler = pages.PageRedirect(dict(core.DEFAULTS, allowed_domains=["example.org"]))
        request = pages.urllib.request.Request("https://example.org")
        with patch.object(pages.socket, "getaddrinfo") as resolve:
            with self.assertRaisesRegex(ValueError, "domain filters"):
                handler.redirect_request(request, None, 302, "redirect", {}, "https://blocked.org")
        resolve.assert_not_called()

    def test_snippets_do_not_fetch_or_reuse_previous_page_text(self):
        items = [{"url": "https://example.org", "kitty_page_text": "old page"}]
        with patch.object(pages, "fetch_page") as fetch:
            pages.retrieve_pages(items, core.DEFAULTS)
        fetch.assert_not_called()
        self.assertNotIn("kitty_page_text", items[0])


class DepthReviewTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(directory.cleanup)
        patcher = patch.object(core, "data_dir", return_value=Path(directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cfg = dict(core.DEFAULTS, model_path="fake.gguf", search_depth="deep")
        self.item = {"title": "Source", "url": "https://example.org", "content": "Uninformative preview"}

    def search(self, model, fetch):
        with patch.object(core, "get_local_model", return_value=model), patch.object(core, "http_json", return_value={"results": [self.item]}), patch.object(pages, "fetch_page", side_effect=fetch), patch.object(core.overview, "synthesize", return_value=None):
            return core.search("find the answer", self.cfg)

    def test_later_page_content_reaches_model_and_improves_result(self):
        text = "Irrelevant introduction. " * 300 + "USEFUL ANSWER"
        model = ReviewingModel()
        result = self.search(model, lambda *args: dict(text=text, url=self.item["url"], truncated=False))
        item = result["results"][0]
        self.assertEqual(item["kitty_page_reviewed_chars"], len(text))
        self.assertEqual(item["kitty_relevance"], 95)
        self.assertEqual(item["kitty_reasons"], ["Found usable answer"])
        self.assertGreater(len(model.calls), 1)
        self.assertEqual(result["pages_retrieved"], 1)
        self.assertIsNone(result["model_error"])

    def test_small_context_and_unicode_cover_every_character_without_overflow(self):
        self.cfg.update(model_context=2048, kitty_mode=True)
        text = "中文\\\" café\n" * 500
        model = ReviewingModel()
        result = self.search(model, lambda *args: dict(text=text, url=self.item["url"], truncated=True))
        excerpts = []
        for call in model.calls:
            tokens = sum(len(model.tokenize(message["content"].encode())) for message in call["messages"])
            self.assertLessEqual(tokens + call["max_tokens"] + 192, 2048)
            if "\nResults: " not in call["messages"][-1]["content"]:
                continue
            entry = json.loads(call["messages"][-1]["content"].split("\nResults: ", 1)[1])[0]
            excerpts.append(entry["page_excerpt"])
        self.assertEqual("".join(excerpts), text)
        self.assertEqual(result["results"][0]["kitty_page_reviewed_chars"], len(text))

    def test_partial_page_reviews_report_coverage(self):
        text = "Intro " * 600 + "USEFUL ANSWER"
        result = self.search(ReviewingModel(fail_first=True), lambda *args: dict(text=text, url=self.item["url"], truncated=False))
        self.assertIn("Page review incomplete", result["model_error"])
        self.assertLess(result["results"][0]["kitty_page_reviewed_chars"], len(text))
        self.assertTrue(result["analyzed"])

    def test_failed_page_retrieval_reviews_snippet_and_keeps_result(self):
        result = self.search(ReviewingModel(), TimeoutError("timed out"))
        self.assertEqual(result["page_errors"], 1)
        self.assertEqual(result["pages_retrieved"], 0)
        self.assertIn("timed out", result["results"][0]["kitty_page_error"])
        self.assertTrue(result["results"][0]["kitty_ai_reviewed"])

    def test_missing_model_does_not_contact_result_sites(self):
        with patch.object(core, "get_local_model", side_effect=RuntimeError("model unavailable")), patch.object(pages, "fetch_page") as fetch:
            with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                core.analyze_with_local_model("query", [self.item], self.cfg)
        fetch.assert_not_called()

    def test_filters_and_result_limit_apply_before_retrieval(self):
        items = [dict(self.item, url="https://blocked.org"), self.item, dict(self.item, url="https://extra.org")]
        cfg = dict(self.cfg, blocked_domains=["blocked.org"], results=1)
        with patch.object(core, "http_json", return_value={"results": items}), patch.object(core, "get_local_model", return_value=ReviewingModel()), patch.object(pages, "fetch_page", return_value=dict(text="USEFUL ANSWER", url=self.item["url"], truncated=False)) as fetch:
            core.search("query", cfg)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[0], self.item["url"])

    def test_depth_persists_defaults_and_rejects_invalid_values(self):
        home = core.data_dir()
        for depth in pages.DEPTHS:
            models.save_settings(home, dict(core.automatic_config(), search_depth=depth))
            self.assertEqual(core.automatic_config()["search_depth"], depth)
        for invalid in (None, True, 2, "invalid"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                models.save_settings(home, dict(core.automatic_config(), search_depth=invalid))
        saved = json.loads((home / "desktop-model.json").read_text())
        del saved["search_depth"]
        (home / "desktop-model.json").write_text(json.dumps(saved))
        self.assertEqual(core.automatic_config()["search_depth"], "snippets")


if __name__ == "__main__":
    unittest.main()
