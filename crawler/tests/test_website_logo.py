"""Brand-logo extraction (JSON-LD Organization.logo first) + URL scheme safety.
Distinct from the card hero image (_extract_image / og:image chain)."""

from selectolax.parser import HTMLParser

from crawler.fetchers.website import _extract_logo, _safe_url


def _p(html):
    return HTMLParser(html)


def test_logo_from_jsonld_organization_string():
    html = ('<html><head><script type="application/ld+json">'
            '{"@context":"http://schema.org","@type":"Organization",'
            '"logo":"https://woodmallcinema.com/themes/woodmall/img/logo.svg"}'
            '</script></head><body></body></html>')
    assert _extract_logo(_p(html), "https://woodmallcinema.com/") == \
        "https://woodmallcinema.com/themes/woodmall/img/logo.svg"


def test_logo_from_jsonld_object_url_relative_resolved():
    html = ('<head><script type="application/ld+json">'
            '{"@type":"LocalBusiness","logo":{"url":"/img/logo.svg"}}'
            '</script></head>')
    assert _extract_logo(_p(html), "https://x.com/page") == "https://x.com/img/logo.svg"


def test_logo_from_jsonld_graph_and_list_type():
    html = ('<head><script type="application/ld+json">'
            '{"@graph":[{"@type":["WebSite","Thing"],'
            '"logo":"https://x.com/l.svg"}]}'
            '</script></head>')
    assert _extract_logo(_p(html), "https://x.com/") == "https://x.com/l.svg"


def test_logo_falls_back_to_logo_img_src():
    html = '<body><a class="brand-logo"><img class="logo" src="/brand.png"></a></body>'
    assert _extract_logo(_p(html), "https://x.com/") == "https://x.com/brand.png"


def test_logo_falls_back_to_apple_touch_icon():
    html = '<head><link rel="apple-touch-icon" href="/touch.png"></head>'
    assert _extract_logo(_p(html), "https://x.com/") == "https://x.com/touch.png"


def test_logo_none_when_absent():
    assert _extract_logo(_p("<body>no logo here</body>"), "https://x.com/") is None


def test_logo_rejects_dangerous_scheme_in_jsonld():
    html = ('<head><script type="application/ld+json">'
            '{"@type":"Organization","logo":"javascript:alert(1)"}'
            '</script></head>')
    assert _extract_logo(_p(html), "https://x.com/") is None


def test_logo_survives_malformed_jsonld():
    html = ('<head><script type="application/ld+json">{not valid json</script>'
            '<link rel="apple-touch-icon" href="/touch.png"></head>')
    assert _extract_logo(_p(html), "https://x.com/") == "https://x.com/touch.png"


def test_safe_url_allows_http_https_and_resolves_relative():
    assert _safe_url("https://x.com/p", "/a.svg") == "https://x.com/a.svg"
    assert _safe_url("https://x.com/p", "https://cdn.com/b.png") == "https://cdn.com/b.png"


def test_safe_url_rejects_non_http_schemes():
    assert _safe_url("https://x.com/", "javascript:alert(1)") is None
    assert _safe_url("https://x.com/", "data:image/svg+xml;base64,PHN2Zz4=") is None
    assert _safe_url("https://x.com/", "") is None
    assert _safe_url("https://x.com/", None) is None
