from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse


def normalize_url(href: str | None, base_url: str) -> str | None:
    if not href:
        return None
    if href.startswith("#"):
        return None
    full_url = urljoin(base_url, href.strip())
    parsed = urlparse(full_url)
    netloc = parsed.netloc.lower()
    fragment = ""
    query = parsed.query
    if query:
        params = parse_qs(query)
        tracking_params = ["utm_source", "utm_medium", "utm_campaign", "ref", "fbclid"]
        for param in tracking_params:
            if param in params:
                del params[param]
        query = urlencode(params, doseq=True) if params else ""
    normalized = urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path.rstrip("/") or "/",
            parsed.params,
            query,
            fragment,
        )
    )
    return normalized


def url_diff(parent_url: str, child_url: str) -> str | None:
    parsed_parent = urlparse(parent_url)
    parsed_child = urlparse(child_url)
    parent_path = parsed_parent.path.rstrip("/")
    child_path = parsed_child.path.rstrip("/")
    if not child_path.startswith(parent_path):
        return None
    relative = child_path[len(parent_path) :]
    return relative.lstrip("/") or "/"
