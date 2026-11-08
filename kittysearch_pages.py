"""Bounded, read-only retrieval of search-result page text."""
from __future__ import annotations

import ipaddress
import socket
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

import kittysearch_searxng as searxng

DEPTHS = {"snippets": 0, "page": 6_000, "deep": 24_000}
DEPTH_LABELS = {"Snippets": "snippets", "Page (6,000 characters)": "page", "Deep (24,000 characters)": "deep"}
MAX_BYTES = 2_000_000


def validate_depth(value):
    if not isinstance(value, str) or value not in DEPTHS:
        raise ValueError("Search depth must be Snippets, Page or Deep.")
    return value


class PageText(HTMLParser):
    """Keep visible prose, excluding common navigation and executable markup."""
    ignored = {"script", "style", "noscript", "template", "nav", "header", "footer", "svg", "form"}
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (tag in self.ignored or "hidden" in attrs or attrs.get("aria-hidden") == "true"
                  or "display:none" in attrs.get("style", "").replace(" ", "").lower())
        if tag not in self.void:
            self.stack.append((tag, hidden or bool(self.stack and self.stack[-1][1])))
        if not self.stack or not self.stack[-1][1]:
            if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "section", "article", "tr"}:
                self.parts.append("\n")

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if not self.stack or not self.stack[-1][1]:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if not self.stack or not self.stack[-1][1]:
            self.parts.append(data)

    def text(self):
        return "\n".join(line for part in "".join(self.parts).splitlines() if (line := " ".join(part.split())))


def check_url(url, options):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or any(c.isspace() or ord(c) < 32 for c in url)):
        raise ValueError("Only public HTTP/HTTPS pages without credentials can be retrieved.")
    if not searxng.filter_results([{"url": url}], options):
        raise ValueError("Page or redirect excluded by domain filters.")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
        raise ValueError("Local and private network pages are not retrieved.")


class PageRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, options):
        super().__init__()
        self.options = options

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, self.options)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_page(url, limit, timeout, options):
    check_url(url, options)
    opener = urllib.request.build_opener(PageRedirect(options))
    request = urllib.request.Request(url, headers={"User-Agent": "KITTYSEARCH/0.1.0", "Accept": "text/html,text/plain", "Accept-Encoding": "identity"})
    deadline = time.monotonic() + timeout
    with opener.open(request, timeout=timeout) as response:
        if response.headers.get("Content-Encoding", "identity").lower() not in ("", "identity"):
            raise ValueError("Unsupported response encoding; using the search snippet.")
        kind = response.headers.get_content_type()
        if kind not in ("text/html", "application/xhtml+xml", "text/plain"):
            raise ValueError("Unsupported page type; only HTML and plain text are read.")
        chunks = []
        size = 0
        while size <= MAX_BYTES:
            if time.monotonic() > deadline:
                raise TimeoutError("Page retrieval timed out.")
            chunk = response.read(min(65_536, MAX_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        raw = b"".join(chunks)
        charset = response.headers.get_content_charset() or "utf-8"
        try:
            text = raw[:MAX_BYTES].decode(charset, errors="replace")
        except LookupError:
            text = raw[:MAX_BYTES].decode("utf-8", errors="replace")
        if kind != "text/plain":
            parser = PageText()
            parser.feed(text)
            text = parser.text()
        else:
            text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if not text.strip():
            raise ValueError("No readable page text found (the page may require JavaScript or a login).")
        return {"text": text[:limit], "url": response.geturl(), "truncated": len(text) > limit or size > MAX_BYTES}


def retrieve_pages(items, cfg):
    for item in items:
        for key in list(item):
            if key.startswith("kitty_page_"):
                del item[key]
    limit = DEPTHS[validate_depth(cfg.get("search_depth", "snippets"))]
    if not limit or not items:
        return
    options = searxng.normalize_options(cfg)
    def retrieve(item):
        try:
            page = fetch_page(str(item.get("url", "")), limit, min(20, int(cfg.get("timeout", 20))), options)
            item.update(kitty_page_text=page["text"], kitty_page_url=page["url"],
                        kitty_page_truncated=page["truncated"], kitty_page_error="", kitty_page_reviewed_chars=0)
        except Exception as exc:
            item.update(kitty_page_error=str(exc), kitty_page_text="", kitty_page_reviewed_chars=0)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(retrieve, items))
