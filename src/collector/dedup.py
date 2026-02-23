from __future__ import annotations

import hashlib
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def canonicalize_url(url: str) -> str:
    """Normalize a URL for dedup: lowercase host, strip fragments, sort params, drop tracking."""
    p = urlparse(url)
    # lowercase scheme + host
    scheme = p.scheme.lower()
    netloc = p.netloc.lower().rstrip(".")
    # strip www prefix
    if netloc.startswith("www."):
        netloc = netloc[4:]
    # strip fragment
    # sort query params, drop common tracking params
    drop_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "fbclid", "gclid", "ref", "source", "mc_cid", "mc_eid",
    }
    params = parse_qs(p.query, keep_blank_values=False)
    filtered = {k: v for k, v in sorted(params.items()) if k.lower() not in drop_params}
    query = urlencode(filtered, doseq=True)
    # strip trailing slash from path
    path = p.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", query, ""))


def url_hash(url: str) -> str:
    """SHA-256 hash of canonicalized URL."""
    canonical = canonicalize_url(url)
    return hashlib.sha256(canonical.encode()).hexdigest()


def content_hash(text: str) -> str:
    """SHA-256 hash of normalized content for content-level dedup."""
    # Collapse whitespace for stable hashing
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode()).hexdigest()
