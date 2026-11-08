"""Search preferences, SearXNG request parameters, and local domain filtering."""
from __future__ import annotations

import ipaddress
import re
import urllib.parse
from typing import Any


SEARCH_DEFAULTS = {
    "engines": [], "categories": ["general"], "language": "all", "safesearch": 1,
    "allowed_domains": [], "blocked_domains": [],
}


def names(value: Any, label: str) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[,\n]", value)
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a comma-separated list of names.")
    result = []
    for item in value:
        item = item.strip()
        if not item:
            continue
        if any(ord(char) < 32 or char == "," for char in item):
            raise ValueError(f"Invalid {label.lower()} name: {item!r}.")
        if item not in result:
            result.append(item)
    return result


def domain_name(value: str) -> str:
    value = value.strip().rstrip(".").lower()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Enter domains such as example.org, without URLs, paths, ports, or wildcards.") from exc
    if len(value) > 253 or not value or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in value.split(".")
    ):
        raise ValueError("Enter domains such as example.org, without URLs, paths, ports, or wildcards.")
    return value


def normalize_options(settings: dict[str, Any]) -> dict[str, Any]:
    engines = names(settings.get("engines", []), "Engines")
    categories = names(settings.get("categories", ["general"]), "Categories")
    if not categories:
        raise ValueError("Choose at least one search category, such as general.")
    language = settings.get("language", "all")
    if not isinstance(language, str):
        raise ValueError("Enter a language code such as all, en, or en-US.")
    language = language.strip().replace("_", "-").lower()
    if language not in ("all", "auto") and not re.fullmatch(r"[a-z]{2,3}(?:-[a-z]{2})?", language):
        raise ValueError("Enter a language code such as all, en, or en-US.")
    if "-" in language:
        first, region = language.split("-")
        language = first + "-" + region.upper()
    safesearch = settings.get("safesearch", 1)
    if isinstance(safesearch, bool) or str(safesearch) not in ("0", "1", "2"):
        raise ValueError("Select SafeSearch Off, Moderate, or Strict.")
    result = {"engines": engines, "categories": categories, "language": language, "safesearch": int(safesearch)}
    for key in ("allowed_domains", "blocked_domains"):
        result[key] = list(dict.fromkeys(domain_name(item) for item in names(settings.get(key, []), "Domains")))
    return result


def server_options(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or not isinstance(config.get("engines"), list):
        raise ValueError("The server did not return an engine list from /config.")
    engines = {}
    for engine in config["engines"]:
        if not isinstance(engine, dict) or not isinstance(engine.get("name"), str):
            continue
        name = engine["name"]
        if names([name], "Engines") != [name]:
            continue
        categories = names(engine.get("categories", []), "Categories")
        engines[name] = {"name": name, "categories": categories, "enabled": bool(engine.get("enabled", True))}
    categories = names(config.get("categories", []), "Categories")
    categories = list(dict.fromkeys(categories + [category for engine in engines.values() for category in engine["categories"]]))
    return {"engines": engines, "categories": categories}


def request_parameters(query: str, options: dict[str, Any], catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    # SearXNG's !engine/:language syntax overrides form parameters. Keep the
    # saved engine/category/language choices authoritative for this client.
    if any(part.startswith("!") for part in query.split()):
        raise ValueError("Choose engines and categories in SearXNG settings instead of using ! shortcuts.")
    if any(part.startswith(":") for part in query.split()):
        raise ValueError("Choose the search language in SearXNG settings instead of using :language shortcuts.")
    params = {"q": query, "format": "json", "language": options["language"], "safesearch": options["safesearch"]}
    engines = options["engines"]
    categories = options["categories"]
    if catalog is not None:
        unknown_categories = set(categories) - set(catalog["categories"])
        if unknown_categories:
            raise ValueError("Unknown search categories on this server: " + ", ".join(sorted(unknown_categories)))
    if engines:
        if catalog is None:
            raise ValueError("Could not verify the selected engines. Load engines from the SearXNG server and try again.")
        unknown = set(engines) - set(catalog["engines"])
        if unknown:
            raise ValueError("Unknown search engines on this server: " + ", ".join(sorted(unknown)))
        engines = [name for name in engines if set(catalog["engines"][name]["categories"]) & set(categories)]
        if not engines:
            raise ValueError("None of the selected engines supports the selected search categories.")
        params["engines"] = ",".join(engines)
        # Do not send categories with an explicit engine list: SearXNG would
        # append other engines belonging to those categories (parse_generic).
    else:
        params["categories"] = ",".join(categories)
    return params


def domain_matches(host: str, domain: str) -> bool:
    try:
        ipaddress.ip_address(domain)
        return host == domain
    except ValueError:
        return host == domain or host.endswith("." + domain)


def filter_results(items: list[Any], options: dict[str, Any]) -> list[dict[str, Any]]:
    allowed, blocked = options["allowed_domains"], options["blocked_domains"]
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if allowed or blocked:
            try:
                url = urllib.parse.urlsplit(item.get("url", ""))
                if url.scheme not in ("http", "https") or not url.hostname:
                    continue
                host = domain_name(url.hostname)
            except (ValueError, TypeError, AttributeError):
                continue
            if any(domain_matches(host, domain) for domain in blocked):
                continue
            if allowed and not any(domain_matches(host, domain) for domain in allowed):
                continue
        result.append(item)
    return result
