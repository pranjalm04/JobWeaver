def normalize_url(href,base_url):
    from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
    if not href:
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
