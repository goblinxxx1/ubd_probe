from crawler.util.text_lang import cyrillic_ratio, is_non_ukrainian


def test_cyrillic_ratio_pure():
    assert cyrillic_ratio("знижка військовим") == 1.0
    assert cyrillic_ratio("free wifi speed test") == 0.0
    assert cyrillic_ratio("") == 0.0


def test_english_page_is_non_ukrainian():
    assert is_non_ukrainian("Rotten Wifi speed test blog about internet quality 20% off") is True


def test_ukrainian_page_passes():
    assert is_non_ukrainian("Знижка 15% для військовослужбовців у нашій клініці") is False


def test_short_text_not_judged():
    # too few letters to judge — never drop a page for lack of content
    assert is_non_ukrainian("Home") is False
    assert is_non_ukrainian("404") is False
    assert is_non_ukrainian("") is False


def test_mostly_cyrillic_with_some_latin_passes():
    # a Ukrainian offer mentioning a Latin brand stays Ukrainian
    assert is_non_ukrainian("Знижка 20% на iPhone та Samsung для ветеранів") is False
