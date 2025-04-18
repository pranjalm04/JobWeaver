from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
def normalize_url(href,base_url):

    if not href:
        return None
    if href.startswith("#"):
        return None
    full_url = urljoin(base_url, href.strip())
    parsed = urlparse(full_url)
    netloc = parsed.netloc.lower()
    fragment = ''
    query = parsed.query
    if query:
        params = parse_qs(query)
        tracking_params = ['utm_source', 'utm_medium', 'utm_campaign', 'ref', 'fbclid']
        for param in tracking_params:
            if param in params:
                del params[param]
        query = urlencode(params, doseq=True) if params else ''
    normalized = urlunparse((
        parsed.scheme,
        netloc,
        parsed.path.rstrip('/') or '/',  # Normalize trailing slash
        parsed.params,
        query,
        fragment
    ))
    return normalized
def url_diff(parent_url,child_url):
    parsed_parent = urlparse(parent_url)
    parsed_child = urlparse(child_url)
    parent_path = parsed_parent.path.rstrip("/")
    child_path = parsed_child.path.rstrip("/")
    if not child_path.startswith(parent_path):
        return None
    relative = child_path[len(parent_path):]
    return relative.lstrip("/") or "/"