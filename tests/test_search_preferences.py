import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

import kittysearch as core
import kittysearch_searxng as preferences


SERVER_CONFIG = {
    "categories": ["general", "news", "images"],
    "engines": [
        {"name": "chosen engine", "categories": ["general", "news"], "enabled": True},
        {"name": "other engine", "categories": ["general"], "enabled": True},
        {"name": "pictures", "categories": ["images"], "enabled": False},
    ],
}


class SearchPreferenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.directory.cleanup)
        patcher = patch.object(core, "data_dir", return_value=Path(self.directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_old_settings_migrate_without_losing_connection(self):
        saved = {"searxng_mode": "external", "searxng_url": "https://example.org", "timeout": 24}
        (core.data_dir() / "desktop-searxng.json").write_text(json.dumps(saved), encoding="utf-8")
        cfg = core.automatic_config()
        self.assertEqual(cfg["timeout"], 24)
        self.assertEqual(cfg["categories"], ["general"])
        self.assertEqual(cfg["safesearch"], 1)

    def test_all_preferences_persist_and_normalize(self):
        saved = core.save_searxng_settings({
            "searxng_mode": "external", "searxng_url": "https://example.org", "timeout": 20,
            "engines": "chosen engine, pictures, chosen engine", "categories": "general, images",
            "language": "PT_br", "safesearch": "2", "allowed_domains": "EXAMPLE.ORG., bücher.de",
            "blocked_domains": "ads.example.org\ntracking.example.org",
        })
        cfg = core.automatic_config()
        for key in preferences.SEARCH_DEFAULTS:
            self.assertEqual(cfg[key], saved[key])
        self.assertEqual(cfg["language"], "pt-BR")
        self.assertEqual(cfg["allowed_domains"], ["example.org", "xn--bcher-kva.de"])
        self.assertEqual(cfg["engines"], ["chosen engine", "pictures"])

    def test_invalid_preferences_are_rejected(self):
        invalid = [
            {"categories": ""}, {"categories": [None]}, {"engines": 12}, {"engines": ["a,b"]},
            {"safesearch": True}, {"safesearch": 3}, {"safesearch": "strict"},
            {"language": "english"}, {"language": None}, {"language": "en?engines=other"},
            *({"blocked_domains": value} for value in ("https://example.org", "example.org/path", "*.example.org",
                                                       "example.org:80", "bad..org", "example.org@evil.org", "-bad.org")),
        ]
        for options in invalid:
            with self.subTest(options=options), self.assertRaises(ValueError):
                preferences.normalize_options(options)

    def test_explicit_engines_do_not_expand_to_other_category_engines(self):
        options = preferences.normalize_options({"engines": "chosen engine,pictures", "categories": "news"})
        params = preferences.request_parameters("heat pumps", options, preferences.server_options(SERVER_CONFIG))
        self.assertEqual(params["engines"], "chosen engine")
        self.assertNotIn("categories", params)
        self.assertEqual(params["safesearch"], 1)

    def test_unknown_or_incompatible_engine_selection_never_falls_back(self):
        catalog = preferences.server_options(SERVER_CONFIG)
        for values in ({"engines": "typo"}, {"engines": "pictures", "categories": "news"}, {"categories": "typo"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                preferences.request_parameters("query", preferences.normalize_options(values), catalog)

    def test_query_shortcuts_cannot_override_preferences(self):
        for query in ("!other query", "!!g query", "query !!", ":fr query", "query !news"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                preferences.request_parameters(query, preferences.normalize_options({}))

    def test_domain_matching_handles_subdomains_boundaries_idna_and_precedence(self):
        urls = ["https://example.org/a", "https://www.example.org/a", "https://ads.example.org/a",
                "https://x.ads.example.org/a", "https://notexample.org/a", "https://example.org.evil.org/a",
                "https://BÜCHER.de/a", "https://xn--bcher-kva.de/a", "https://EXAMPLE.ORG./a",
                "http://example.org@evil.org", "file:///example.org/a", "http://[broken", None]
        items = [{"url": url} for url in urls] + [None]
        options = preferences.normalize_options({"allowed_domains": "example.org, bücher.de", "blocked_domains": "ads.example.org"})
        kept = preferences.filter_results(items, options)
        self.assertEqual([item["url"] for item in kept], [urls[index] for index in (0, 1, 6, 7, 8)])

    def test_block_list_without_allow_list_keeps_other_domains(self):
        options = preferences.normalize_options({"blocked_domains": "example.org"})
        kept = preferences.filter_results([{"url": "https://sub.example.org"}, {"url": "https://other.org"}], options)
        self.assertEqual(kept, [{"url": "https://other.org"}])

    def test_ip_filters_match_only_the_address(self):
        options = preferences.normalize_options({"allowed_domains": "127.0.0.1, ::1"})
        kept = preferences.filter_results([{"url": "http://127.0.0.1/a"}, {"url": "http://x.127.0.0.1/a"}, {"url": "http://[::1]/a"}], options)
        self.assertEqual(len(kept), 2)

    def test_search_sends_saved_options_and_filters_before_limit_and_model_review(self):
        cfg = dict(core.DEFAULTS, engines=["chosen engine"], categories=["news"], language="es",
                   safesearch=2, blocked_domains=["blocked.org"], results=1)
        responses = [SERVER_CONFIG, {"results": [{"url": "https://blocked.org", "title": "blocked"},
                                                 {"url": "https://good.org", "title": "allowed"}]}]
        with patch.object(core, "http_json", side_effect=responses) as request, patch.object(core, "analyze_with_local_model", return_value={}) as review:
            result = core.search("query", cfg)
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(request.call_args_list[1].args[0]).query)
        self.assertEqual(params["engines"], ["chosen engine"])
        self.assertNotIn("categories", params)
        self.assertEqual(params["language"], ["es"])
        self.assertEqual(params["safesearch"], ["2"])
        self.assertEqual([item["url"] for item in review.call_args.args[1]], ["https://good.org"])
        self.assertEqual(result["domain_filtered"], 1)
        self.assertEqual(len(result["results"]), 1)

    def test_unknown_engine_aborts_before_search_request(self):
        with patch.object(core, "http_json", return_value=SERVER_CONFIG) as request:
            with self.assertRaisesRegex(ValueError, "Unknown search engines"):
                core.search("query", dict(core.DEFAULTS, engines=["missing"]))
        self.assertEqual(request.call_count, 1)
        self.assertTrue(request.call_args.args[0].endswith("/config"))

    def test_default_category_and_explicit_safe_search_off_are_sent(self):
        with patch.object(core, "http_json", return_value={"results": []}) as request:
            core.search("query", dict(core.DEFAULTS, safesearch=0))
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(request.call_args.args[0]).query)
        self.assertEqual(params["categories"], ["general"])
        self.assertEqual(params["safesearch"], ["0"])
        self.assertNotIn("engines", params)


if __name__ == "__main__":
    unittest.main()
