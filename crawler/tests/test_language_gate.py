from crawler.discovery.language_gate import LanguageGate


class NoWait:
    def wait(self, *a, **k):
        pass


class _Resp:
    def __init__(self, html):
        self.text = html
    def raise_for_status(self):
        pass


class _Client:
    def __init__(self, html):
        self._html = html
        self.gets = []
    def get(self, url, **kw):
        self.gets.append(url)
        return _Resp(self._html)


class _BoomClient:
    def get(self, url, **kw):
        raise RuntimeError("network down")


def _gate(html, client=None):
    return LanguageGate(client or _Client(html), NoWait())


EN_HTML = ('<html lang="en-US"><head>'
           '<link rel="alternate" hreflang="en" href="https://x/">'
           '<link rel="alternate" hreflang="fr" href="https://x/fr">'
           '</head><body>Free coloring pages for kids and adults to print and '
           'download in many themes animals nature mandalas</body></html>')


def test_english_homepage_with_no_uk_hreflang_is_foreign():
    g = _gate(EN_HTML)
    assert g.is_foreign("https://www.justcolor.net/", "justcolor.net", 0.0) is True


def test_ukrainian_homepage_is_not_foreign():
    html = ('<html lang="uk"><body>Знижки для військових та ветеранів у нашій '
            'мережі магазинів по всій Україні кожного дня</body></html>')
    assert _gate(html).is_foreign("https://shop.ua/", "shop.ua", 0.0) is False


def test_non_cyrillic_but_has_uk_hreflang_is_not_foreign():
    # a real multilingual UA site: English landing but a Ukrainian version exists
    html = ('<html lang="en"><head>'
            '<link rel="alternate" hreflang="uk-UA" href="https://x/uk">'
            '</head><body>Discounts for the military across all our stores every day</body></html>')
    assert _gate(html).is_foreign("https://x.com/", "x.com", 0.0) is False


def test_thin_content_is_not_foreign():
    # under min_alpha=15 letters → never block on lack of content
    assert _gate("<html><body>Hi</body></html>").is_foreign("https://x/", "x", 0.0) is False


def test_fetch_error_is_not_foreign():
    g = LanguageGate(_BoomClient(), NoWait())
    assert g.is_foreign("https://x/", "x", 0.0) is False


def test_rate_limiter_is_called_with_domain_and_delay():
    class RecWait:
        def __init__(self): self.calls = []
        def wait(self, domain, delay=None): self.calls.append((domain, delay))
    rl = RecWait()
    LanguageGate(_Client(EN_HTML), rl).is_foreign("https://justcolor.net/", "justcolor.net", 2.0)
    assert rl.calls == [("justcolor.net", 2.0)]
