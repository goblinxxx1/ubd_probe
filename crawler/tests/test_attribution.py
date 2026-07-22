from crawler.discovery.attribution import attribute, build_page_ctx, PageCtx
from crawler.models import RawItem, SourceCandidate


def _item(text, url="https://biz.example/p", links=None, site_name=None):
    return RawItem(source_id=None, platform="website", key="k", text=text,
                   url=url, links=links or [], site_name=site_name)


def test_first_party_first_person():
    item = _item("У нас знижка 10% для УБД", site_name="Biz")
    ctx = build_page_ctx(SourceCandidate(name="Biz", type="website",
                                         url_or_handle="https://biz.example"), [item])
    a = attribute(item, ctx)
    assert a.is_first_party and a.provider == "Biz"
    assert a.suggest_type == "website"
    assert a.suggest_url_or_handle == "https://biz.example"


def test_third_party_external_link():
    item = _item("Заклад Кава дає 15% військовим",
                 links=["https://kava.example/menu"], site_name="Portal")
    ctx = PageCtx(cand_type="website", cand_name="Portal",
                  cand_url_or_handle="https://portal.example",
                  brand="Portal", host="portal.example", offer_block_count=9)
    a = attribute(item, ctx)
    assert not a.is_first_party
    assert a.provider == "kava.example"
    assert a.suggest_url_or_handle == "https://kava.example"


def test_generic_info_rejected():
    item = _item("Для УБД існують знижки по місту", site_name=None)
    ctx = PageCtx(cand_type="website", cand_name="Portal",
                  cand_url_or_handle="https://portal.example",
                  brand=None, host="portal.example", offer_block_count=9)
    assert attribute(item, ctx) is None


def test_single_business_page_first_party():
    item = _item("Знижка 10% ветеранам", site_name="Shop")
    ctx = PageCtx(cand_type="website", cand_name="Shop",
                  cand_url_or_handle="https://shop.example",
                  brand="Shop", host="shop.example", offer_block_count=1)
    a = attribute(item, ctx)
    assert a.is_first_party and a.provider == "Shop"


def test_rule3_two_blocks_no_longer_first_party():
    item = _item("Знижка 10% ветеранам", site_name="Shop")
    ctx = PageCtx(cand_type="website", cand_name="Shop",
                  cand_url_or_handle="https://shop.example",
                  brand="Shop", host="shop.example", offer_block_count=2)
    assert attribute(item, ctx) is None


def test_blocked_page_host_returns_none():
    item = _item("У нас знижка 10% для УБД", site_name="НВ Бізнес")
    ctx = PageCtx(cand_type="website", cand_name="НВ",
                  cand_url_or_handle="https://biz.nv.ua/x",
                  brand="НВ Бізнес", host="biz.nv.ua", offer_block_count=1)
    assert attribute(item, ctx) is None


def test_blocked_external_link_ignored():
    item = _item("Дивіться відео про знижки військовим",
                 links=["https://vm.tiktok.com/abc"], site_name="Portal")
    ctx = PageCtx(cand_type="website", cand_name="Portal",
                  cand_url_or_handle="https://portal.example",
                  brand="Portal", host="portal.example", offer_block_count=9)
    # tiktok link must not become a provider; nothing else qualifies → None
    assert attribute(item, ctx) is None


def test_telegram_channel_is_provider():
    item = _item("Знижка 25% сьогодні", url="https://t.me/kavachan/12")
    ctx = build_page_ctx(SourceCandidate(name="Kava Channel", type="telegram",
                                         url_or_handle="t.me/kavachan"), [item])
    a = attribute(item, ctx)
    assert a.is_first_party and a.provider == "Kava Channel"
    assert a.suggest_type == "telegram"
    assert a.suggest_url_or_handle == "t.me/kavachan"


def test_telegram_news_channel_rejected():
    item = _item("Розклад пар та стипендії", url="https://t.me/nau_info/753")
    ctx = build_page_ctx(SourceCandidate(name="КАІ • Корисна інфа", type="telegram",
                                         url_or_handle="https://t.me/nau_info"), [item])
    assert attribute(item, ctx) is None


def test_telegram_business_channel_attributed():
    item = _item("Знижка 10% для УБД", url="https://t.me/kava_lviv")
    ctx = build_page_ctx(SourceCandidate(name="Кав'ярня Львів", type="telegram",
                                         url_or_handle="https://t.me/kava_lviv"), [item])
    a = attribute(item, ctx)
    assert a is not None
    assert a.suggest_type == "telegram"


def _ctx(host="cafe.example", brand="Cafe", blocks=1, outbound=0):
    return PageCtx(cand_type="website", cand_name=brand,
                   cand_url_or_handle=f"https://{host}", brand=brand, host=host,
                   offer_block_count=blocks, outbound_host_count=outbound)


def _item2(text, url="https://cafe.example/p", links=None, is_article=False, business=False):
    return RawItem(source_id=None, platform="website", key="k", text=text, url=url,
                   links=links or [], is_article=is_article, has_business_schema=business)


def test_article_page_never_first_party_drops_without_outbound():
    it = _item2("Ми зібрали знижки для ветеранів", is_article=True)
    assert attribute(it, _ctx(host="blog.example", brand="Blog")) is None


def test_article_page_salvages_via_outbound_business_link():
    it = _item2("Знижка 20% для ветеранів", links=["https://realshop.ua/sale"], is_article=True)
    attr = attribute(it, _ctx(host="blog.example", brand="Blog"))
    assert attr is not None and attr.is_first_party is False
    assert attr.provider == "realshop.ua"


def test_business_landing_with_blogposting_and_business_schema_stays_first_party():
    it = _item2("Ми даємо знижку 20% для ветеранів", is_article=True, business=True)
    attr = attribute(it, _ctx(host="cafe.example", brand="Cafe"))
    assert attr is not None and attr.is_first_party is True


def test_aggregator_many_outbound_never_first_party():
    it = _item2("Ми зібрали знижки для ветеранів", links=["https://realshop.ua/sale"])
    attr = attribute(it, _ctx(host="portal.example", brand="Portal", outbound=5))
    assert attr is not None and attr.is_first_party is False and attr.provider == "realshop.ua"


def test_non_media_first_person_still_first_party():
    it = _item2("У нас знижка 20% для ветеранів", links=["https://ig.example/x"])
    attr = attribute(it, _ctx())
    assert attr is not None and attr.is_first_party is True   # outbound must NOT win here
