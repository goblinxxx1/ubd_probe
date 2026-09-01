from pathlib import Path
from unittest import mock

import httpx

from crawler.fetchers.website import WebsiteFetcher

FIX = (Path(__file__).parent / "fixtures" / "website_offers.html").read_text(encoding="utf-8")


def _client():
    def handle(request):
        return httpx.Response(200, text=FIX)
    return httpx.Client(transport=httpx.MockTransport(handle))


def test_website_extracts_text_blocks_and_links():
    f = WebsiteFetcher(_client())
    items, new_key = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    texts = [i.text for i in items]
    assert any("Знижка 15%" in t for t in texts)
    assert any("музею" in t for t in texts)
    assert all(i.platform == "website" for i in items)
    # short "Коротко" block is filtered out
    assert not any(i.text.strip() == "Коротко" for i in items)
    # link captured
    assert any("t.me/coffeechan" in "".join(i.links) for i in items)
    assert new_key is not None


def test_website_no_duplicate_or_overlapping_blocks():
    # fixture has 2 real offers (nested <article><p>...) plus one filtered-out
    # short block; each offer must be emitted exactly once, not once per
    # matched ancestor/descendant pair.
    f = WebsiteFetcher(_client())
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert len(items) == 2
    keys = [i.key for i in items]
    assert len(keys) == len(set(keys))
    # the offer block that had a link still carries it
    discount_item = next(i for i in items if "Знижка 15%" in i.text)
    assert any("t.me/coffeechan" in link for link in discount_item.links)


def test_article_splits_into_paragraph_items():
    # A news <article> wrapping several <p> must emit ONE item PER paragraph,
    # not one merged giant block. This restores the "all trigger words in one
    # paragraph" rule: a donation-widget number ("250 грн") in one paragraph
    # must stay isolated from a discount-context word in another, so the
    # extractor can't fabricate a fixed-price offer from cross-paragraph noise.
    html = ('<html><body><article>'
            '<p>Знижка 15% для ветеранів на каву сьогодні у нас.</p>'
            '<p>Підтримайте редакцію: Разово Щомісяця 250 грн 500 грн Підтримати.</p>'
            '</article></body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://news.x/a"}, None)
    assert len(items) == 2
    promo = next(i for i in items if "Знижка 15%" in i.text)
    widget = next(i for i in items if "250 грн" in i.text)
    # the paragraphs are separate items — the number never shares text with the promo
    assert "250 грн" not in promo.text
    assert "Знижка 15%" not in widget.text


def test_article_paragraph_items_keep_ancestor_level_links():
    # A link that sits between paragraphs (direct child of <article>, sibling of
    # the <p>) must still ride along on the paragraph item, so per-paragraph
    # segmentation does not drop offer links.
    html = ('<html><body><article>'
            '<p>Знижка 15% для ветеранів на каву сьогодні у нас.</p>'
            '<a href="https://t.me/coffeechan">канал</a>'
            '</article></body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items
    promo = next(i for i in items if "Знижка 15%" in i.text)
    assert any("t.me/coffeechan" in link for link in promo.links)


def test_website_captures_site_name():
    html = ('<html><head><meta property="og:site_name" content="My Cafe">'
            '<title>t</title></head><body>'
            '<article><p>Знижка 15% для ветеранів на каву у нас.</p></article>'
            '</body></html>')
    def handle(request):
        return httpx.Response(200, text=html)
    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handle)))
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.site_name == "My Cafe" for i in items)


def test_website_never_raises_on_network_error():
    def boom(request):
        raise httpx.ConnectError("down")
    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(boom)))
    items, key = f.fetch({"id": 1, "url_or_handle": "http://x"}, "prev")
    assert items == [] and key == "prev"


def test_website_locality_from_jsonld():
    html = ('<html><head><script type="application/ld+json">'
            '{"@type":"Restaurant","address":{"@type":"PostalAddress",'
            '"addressLocality":"Львів"}}</script></head><body>'
            '<article><p>Знижка 15% для ветеранів на каву у нас сьогодні.</p>'
            '</article></body></html>')

    def handle(request):
        return httpx.Response(200, text=html)

    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handle)))
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.locality == "Львів" for i in items)


def test_website_locality_from_og_meta():
    html = ('<html><head><meta property="og:locality" content="Одеса"></head>'
            '<body><article><p>Знижка 15% для ветеранів на каву у нас сьогодні.'
            '</p></article></body></html>')

    def handle(request):
        return httpx.Response(200, text=html)

    f = WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handle)))
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.locality == "Одеса" for i in items)


def test_website_locality_absent_is_none():
    f = WebsiteFetcher(_client())
    items, _ = f.fetch({"id": 1, "url_or_handle": "http://x"}, None)
    assert items and all(i.locality is None for i in items)


def test_website_never_raises_on_parse_error():
    # The HTTP request/status succeed cleanly (real MockTransport response,
    # so client.get()/raise_for_status() don't themselves raise); the failure
    # is forced downstream, in HTML parsing. The fetcher must still swallow
    # it and preserve the previous cursor key rather than propagating.
    with mock.patch("crawler.fetchers.website.HTMLParser", side_effect=RuntimeError("boom")):
        items, key = WebsiteFetcher(_client()).fetch(
            {"id": 1, "url_or_handle": "http://x"}, "prev")
    assert items == [] and key == "prev"


def test_locality_from_microdata():
    from selectolax.parser import HTMLParser
    from crawler.fetchers.website import _extract_locality
    html = '<html><body><span itemprop="addressLocality">Київ</span></body></html>'
    assert _extract_locality(HTMLParser(html)) == "Київ"


def test_locality_from_contact_region():
    from selectolax.parser import HTMLParser
    from crawler.fetchers.website import _extract_locality
    html = ('<html><body><main><p>Знижка 15% для УБД</p></main>'
            '<footer><address>м. Вишневе, вул. Київська 1</address></footer>'
            '</body></html>')
    assert _extract_locality(HTMLParser(html)) == "Вишневе"


def test_offer_schema_flag_set(monkeypatch):
    from crawler.fetchers.website import WebsiteFetcher
    html = ('<html><body><article>'
            'Знижка 20% для ветеранів у кафе на розі, діє до 31.12'
            '<script type="application/ld+json">'
            '{"@type":"Offer","price":"100"}</script>'
            '</article></body></html>')

    class _Resp:
        text = html
        status_code = 200
        headers = {}
        def raise_for_status(self): pass

    class _Client:
        def get(self, url, follow_redirects=True, headers=None): return _Resp()

    items, _ = WebsiteFetcher(_Client()).fetch(
        {"id": 1, "url_or_handle": "http://shop.ua"}, None)
    assert items and items[0].has_offer_schema is True


def test_offer_schema_flag_not_set_for_incidental_word():
    from crawler.fetchers.website import WebsiteFetcher
    html = ('<html><body><article>'
            'Знижка 20% для ветеранів у кафе на розі, діє до 31.12'
            '<script type="application/ld+json">'
            # квотований "offer" у ЧУЖОМУ полі (не @type) — тригерив старий підрядковий
            # `"offer" in raw`, але новий regex прив'язаний до @type → має бути False
            '{"@type":"Article","category":"offer"}</script>'
            '</article></body></html>')

    class _Resp:
        text = html
        status_code = 200
        headers = {}
        def raise_for_status(self): pass

    class _Client:
        def get(self, url, follow_redirects=True, headers=None): return _Resp()

    items, _ = WebsiteFetcher(_Client()).fetch(
        {"id": 1, "url_or_handle": "http://shop.ua"}, None)
    assert items and items[0].has_offer_schema is False


def _fetcher_returning(html):
    def handle(request):
        return httpx.Response(200, text=html)
    return WebsiteFetcher(httpx.Client(transport=httpx.MockTransport(handle)))


# --- generic block segmentation: content can live in ANY structural container,
#     not only <p>/<li>/<article> ---

def test_bare_div_leaf_is_segmented():
    # The common real-world case (terraincognita military discount): the offer text
    # sits in a plain <div> with no <p>/<li>/<article> wrapper. It must be captured.
    html = ('<html><body><div>Для військових діє постійна знижка 10% '
            'за промокодом TERRA450 у нашому магазині.</div></body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://shop.ua/oplata"}, None)
    assert any("знижка 10%" in i.text for i in items)


def test_section_and_td_leaves_are_segmented():
    # <section> and <td> are structural containers too — text directly inside them
    # (no inner block) was invisible to the article/li/p-only selector.
    html = ('<html><body>'
            '<section>Ветеранам знижка 15% на все спорядження цього місяця.</section>'
            '<table><tr><td>Військовим знижка 20% за промокодом ARMY у нас.</td></tr></table>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://shop.ua/x"}, None)
    texts = " || ".join(i.text for i in items)
    assert "знижка 15%" in texts
    assert "знижка 20%" in texts


def test_inline_tags_do_not_split_a_block():
    # <b>/<a>/<span> inside a block must NOT become separate items — their text stays
    # merged into the single enclosing block leaf (they are inline, never boundaries).
    html = ('<html><body><div>Знижка <b>10%</b> для '
            '<a href="/vet">військових</a> та <span>ветеранів</span> завжди.'
            '</div></body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://shop.ua/x"}, None)
    merged = [i for i in items if "Знижка" in i.text]
    assert len(merged) == 1
    assert all(w in merged[0].text for w in ("10%", "військових", "ветеранів"))


def test_chrome_blocks_are_not_segmented():
    # Discount-looking text in nav/header/footer is site chrome, not an offer — drop it.
    html = ('<html><body>'
            '<nav><div>Знижки 10% для військових — меню магазину тут завжди.</div></nav>'
            '<footer><div>Знижка 5% ветеранам у футері нашого сайту сьогодні.</div></footer>'
            '<div>Знижка 25% для військових у головному блоці сторінки завжди.</div>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://shop.ua/x"}, None)
    texts = " || ".join(i.text for i in items)
    assert "25%" in texts            # main content kept
    assert "меню" not in texts       # nav dropped
    assert "футері" not in texts     # footer dropped


def test_wrapper_div_not_duplicated_over_inner_paragraph():
    # A <div> that only wraps a <p> must emit the inner leaf <p> exactly once, never
    # both the wrapper and the paragraph (no duplicate/overlapping blocks).
    html = ('<html><body><div class="wrap">'
            '<p>Знижка 15% для ветеранів на каву у нас сьогодні завжди.</p>'
            '</div></body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://shop.ua/x"}, None)
    assert len(items) == 1
    assert "Знижка 15%" in items[0].text


def test_news_article_schema_sets_is_article(monkeypatch):
    html = ('<html><head>'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"NewsArticle","headline":"Знижки для ветеранів"}'
            '</script></head><body>'
            '<article>Знижка 20% для ветеранів у місті детально розписана тут</article>'
            '</body></html>')
    f = _fetcher_returning(html)   # existing helper in this test module
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://news.example/a"}, None)
    assert items and items[0].is_article is True
    assert items[0].has_business_schema is False


def test_localbusiness_schema_sets_business_not_article(monkeypatch):
    html = ('<html><head>'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"LocalBusiness","name":"Кафе"}'
            '</script></head><body>'
            '<p>Знижка 20% для ветеранів у нас щодня протягом місяця</p>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://cafe.example"}, None)
    assert items and items[0].is_article is False
    assert items[0].has_business_schema is True


def test_tech_article_subtype_sets_is_article():
    html = ('<html><head>'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"TechArticle","headline":"Огляд"}'
            '</script></head><body>'
            '<article>Знижка 20% для ветеранів детально розписана тут</article>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://news.example/a"}, None)
    assert items and items[0].is_article is True
    assert items[0].has_business_schema is False


def test_report_type_sets_is_article():
    html = ('<html><head>'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"Report","headline":"Звіт"}'
            '</script></head><body>'
            '<p>Знижка 20% для ветеранів у місті протягом місяця</p>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://ngo.example/r"}, None)
    assert items and items[0].is_article is True


def test_og_type_article_sets_is_article():
    # News/blog CMSes routinely set og:type=article without any schema.org JSON-LD.
    # That must count as a media signal even though _has_article_schema is False.
    html = ('<html><head><meta property="og:type" content="article"></head>'
            '<body><p>Знижка 20% для ветеранів у місті детально розписана тут.</p>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://news.example/a"}, None)
    assert items and items[0].is_article is True
    assert items[0].has_business_schema is False


def test_og_type_website_is_not_article():
    # Plain business pages set og:type=website — must NOT be flagged media.
    html = ('<html><head><meta property="og:type" content="website"></head>'
            '<body><p>Знижка 20% для ветеранів у нашому магазині завжди діє тут.</p>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://shop.example"}, None)
    assert items and items[0].is_article is False


def test_dated_permalink_sets_is_article():
    # A /YYYY/MM/DD/ (or /YYYY/MM/) permalink is a news/blog convention; business
    # discount pages practically never carry dated permalinks.
    html = '<html><body><p>Безкоштовна автоцивілка для ветеранів уже цього року.</p></body></html>'
    f = _fetcher_returning(html)
    url = "https://kalush.informator.ua/2025/10/27/bezkoshtovna-avtoczyvilka-dlya-veteraniv"
    items, _ = f.fetch({"id": 1, "url_or_handle": url}, None)
    assert items and items[0].is_article is True


def test_dated_permalink_month_only_sets_is_article():
    html = '<html><body><p>Знижки для ветеранів у Вінниці цього місяця активно діють.</p></body></html>'
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://presspoint.in.ua/2020/04/slug-here"}, None)
    assert items and items[0].is_article is True


def test_business_url_with_numbers_is_not_dated_permalink():
    # A catalog/product path with numbers must not be mistaken for a dated permalink.
    html = '<html><body><p>Знижка 15% для ветеранів на це взуття у нашому магазині завжди.</p></body></html>'
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://shop.example/catalog/12345/item-99"}, None)
    assert items and items[0].is_article is False


def test_url_dated_permalink_helper():
    from crawler.fetchers.website import _url_dated_permalink
    assert _url_dated_permalink("https://x.ua/2026/08/08/383579_news")
    assert _url_dated_permalink("https://x.ua/uk/2026/08/08/slug")
    assert _url_dated_permalink("https://x.ua/2020/04/slug")
    assert not _url_dated_permalink("https://x.ua/catalog/12345")
    assert not _url_dated_permalink("https://x.ua/2020")          # year alone — not a permalink
    assert not _url_dated_permalink("https://x.ua/1234/56/78")    # not a plausible year
    assert not _url_dated_permalink("")


def test_site_tagline_prefers_header_then_footer_then_meta():
    from crawler.fetchers.website import _extract_site_tagline
    from selectolax.parser import HTMLParser
    header = HTMLParser('<div class="site-description">Хедер слоган</div>'
                        '<div class="tb-footer-desc">Футер опис</div>'
                        '<meta name="description" content="Мета опис">')
    assert _extract_site_tagline(header) == "Хедер слоган"
    footer = HTMLParser('<div class="tb-footer-desc">Футер опис бізнесу</div>'
                        '<meta name="description" content="Мета опис">')
    assert _extract_site_tagline(footer) == "Футер опис бізнесу"
    meta = HTMLParser('<meta name="description" content="Лише мета опис">')
    assert _extract_site_tagline(meta) == "Лише мета опис"
    assert _extract_site_tagline(HTMLParser('<div>нічого</div>')) is None


def test_site_tagline_capped_and_whitespace_normalized():
    from crawler.fetchers.website import _extract_site_tagline
    from selectolax.parser import HTMLParser
    long = "слово " * 60
    out = _extract_site_tagline(HTMLParser(f'<meta name="description" content="{long}">'))
    assert out is not None and len(out) <= 160 and "  " not in out


def test_fetch_puts_title_on_items():
    # Сирий <title> має потрапляти на RawItem окремо від site_name (яке
    # пріоритетно бере og:site_name) — is_directory_page читає саме сирий
    # заголовок з роздільником "сутність | бренд".
    html = ('<html><head><meta property="og:site_name" content="MY Help">'
            '<title>Знижка для Easy English | MY Help</title></head><body>'
            '<article><p>Знижка 10% для УБД у нас сьогодні завжди.</p></article>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://myhelp.com.ua/x"}, None)
    assert items and all(i.title == "Знижка для Easy English | MY Help" for i in items)
    assert items[0].site_name == "MY Help"     # og:site_name лишається пріоритетним для site_name


def test_fetch_puts_site_tagline_on_items():
    import httpx
    from crawler.fetchers.website import WebsiteFetcher
    html = ('<html><head><meta name="description" content="Опис магазину"></head>'
            '<body><p>Знижка 15% для ветеранів у нашому магазині завжди діє тут.</p></body></html>')
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=html))
    fetcher = WebsiteFetcher(httpx.Client(transport=transport))
    items, _ = fetcher.fetch({"id": 1, "url_or_handle": "https://biz.example"}, None)
    assert items and items[0].site_tagline == "Опис магазину"


# --- provider name from logo <img alt> ---

def test_extract_logo_alt_from_logo_scope():
    from crawler.fetchers.website import _extract_logo_alt
    from selectolax.parser import HTMLParser
    html = ('<header><a class="header__logo"><img src="/l.svg" alt="Terra Incognita"></a>'
            '</header><img src="/pay.svg" alt="Накладений платіж">')
    assert _extract_logo_alt(HTMLParser(html)) == "Terra Incognita"


def test_extract_logo_alt_ignores_non_logo_images():
    from crawler.fetchers.website import _extract_logo_alt
    from selectolax.parser import HTMLParser
    html = ('<body><img src="/pay.svg" alt="Накладений платіж">'
            '<img src="/m.svg" alt="Meest Пошта"></body>')
    assert _extract_logo_alt(HTMLParser(html)) is None


def test_extract_logo_alt_skips_generic_alt():
    from crawler.fetchers.website import _extract_logo_alt
    from selectolax.parser import HTMLParser
    for generic in ("logo", "Лого", "IMAGE", "Головна"):
        html = f'<div class="logo"><img alt="{generic}"></div>'
        assert _extract_logo_alt(HTMLParser(html)) is None, generic


def test_fetch_puts_logo_alt_on_items():
    html = ('<html><head><title>t</title></head><body>'
            '<header><div class="site-logo"><img src="/l.png" alt="Кафе Львів"></div>'
            '</header><p>Знижка 15% для ветеранів на каву у нас сьогодні завжди.</p>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://cafe.example"}, None)
    assert items and all(i.logo_alt == "Кафе Львів" for i in items)


# --- <link rel=canonical> carried on RawItem ---

def test_fetch_extracts_canonical_url():
    html = ('<html><head><link rel="canonical" href="https://shop.ua/offer">'
            '</head><body><div>Знижка 20% для військових у нашому магазині сьогодні</div>'
            '</body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://shop.ua/offer?utm=x"}, None)
    assert items and items[0].canonical_url == "https://shop.ua/offer"


def test_fetch_canonical_absent_is_none():
    html = ('<html><body><div>Знижка 20% для військових у нашому магазині сьогодні'
            '</div></body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://shop.ua/offer"}, None)
    assert items and items[0].canonical_url is None


def test_fetch_canonical_rejects_unsafe_scheme():
    html = ('<html><head><link rel="canonical" href="javascript:alert(1)">'
            '</head><body><div>Знижка 20% для військових у нашому магазині сьогодні'
            '</div></body></html>')
    f = _fetcher_returning(html)
    items, _ = f.fetch({"id": 1, "url_or_handle": "https://shop.ua/offer"}, None)
    assert items and items[0].canonical_url is None


# --- conditional GET (304) + 429/503 Retry-After host backoff ---

class _Resp:
    """Мінімальний httpx.Response-подібний обʼєкт для тестів статус-кодів/хедерів."""
    def __init__(self, text="", status=200, headers=None):
        self.text = text
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


from crawler.discovery.validator_store import ValidatorStore


def test_304_short_circuits_without_parsing(tmp_path):
    store = ValidatorStore(str(tmp_path / "v.json"))
    store.put("https://a.ua", etag='"v1"', last_modified=None)
    sent = {}
    class C:
        def get(self, url, follow_redirects=True, headers=None):
            sent.update(headers or {})
            return _Resp("", status=304, headers={"ETag": '"v1"'})
    items, key = WebsiteFetcher(C(), store=store).fetch(
        {"id": 1, "url_or_handle": "https://a.ua"}, "prev-key")
    assert sent.get("If-None-Match") == '"v1"'
    assert items == [] and key == "prev-key"          # nothing changed, cheap


def test_429_calls_throttle_sink_with_retry_after():
    hits = []
    class C:
        def get(self, url, follow_redirects=True, headers=None):
            return _Resp("", status=429, headers={"Retry-After": "42"})
    WebsiteFetcher(C(), throttle_sink=lambda host, s: hits.append((host, s))).fetch(
        {"id": 1, "url_or_handle": "https://a.ua/x"}, None)
    assert hits == [("a.ua", 42.0)]


def _html_client(html):
    def handle(request):
        return httpx.Response(200, text=html)
    return httpx.Client(transport=httpx.MockTransport(handle))


def test_detects_news_schema_and_feed():
    html = (
        '<html><head>'
        '<link rel="alternate" type="application/rss+xml" href="/feed/">'
        '<script type="application/ld+json">{"@type":"NewsArticle","headline":"x"}</script>'
        '</head><body><div>Громада підтримала мобілізованих захисників у місті сьогодні</div>'
        '</body></html>')
    items, _ = WebsiteFetcher(_html_client(html)).fetch({"id": 1, "url_or_handle": "http://p"}, None)
    assert items
    assert items[0].has_news_schema is True
    assert items[0].has_feed is True


def test_no_news_schema_or_feed_on_plain_page():
    html = ('<html><head><title>Магазин</title></head>'
            '<body><div>Знижка 20% для військових на весь асортимент сьогодні у нас</div></body></html>')
    items, _ = WebsiteFetcher(_html_client(html)).fetch({"id": 1, "url_or_handle": "http://p"}, None)
    assert items
    assert items[0].has_news_schema is False
    assert items[0].has_feed is False
