from crawler.learn.labeler import label_item
from crawler.models import RawItem


def _item(url, has_schema=False):
    return RawItem(source_id=1, platform="website", key="k",
                   text="Знижка 20%", url=url, has_offer_schema=has_schema)


def test_pass_label_and_positive_anchor():
    rec = label_item(_item("https://shop.ua/sale", has_schema=True), True)
    assert rec.label == "pass"
    assert rec.host == "shop.ua"
    assert rec.pos_anchor is True
    assert rec.neg_anchor is False


def test_negative_anchor_from_blocklist():
    rec = label_item(_item("https://nv.ua/news"), False)
    assert rec.label == "fail"
    assert rec.neg_anchor is True
