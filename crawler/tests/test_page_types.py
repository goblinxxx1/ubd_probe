from crawler.discovery import promo_lexicon as pl


# --- INCLUDE by URL slug ---
def test_veteran_slugs_are_target():
    for u in ("https://s.ua/viyskovym", "https://s.ua/dlya-veteraniv",
              "https://s.ua/zsu", "https://s.ua/army-discount",
              "https://s.ua/%D0%B2%D1%96%D0%B9%D1%81%D1%8C%D0%BA%D0%BE%D0%B2%D0%B8%D0%BC"):
        assert pl.page_is_target(u) is True, u


def test_info_slugs_are_target():
    for u in ("https://s.ua/kontakty", "https://s.ua/contact",
              "https://s.ua/dostavka-i-oplata", "https://s.ua/delivery",
              "https://s.ua/about", "https://s.ua/pro-nas",
              "https://s.ua/loyalty", "https://s.ua/bonus",
              "https://s.ua/faq", "https://s.ua/korysna-informaciya"):
        assert pl.page_is_target(u) is True, u


def test_promo_slugs_still_target():
    assert pl.page_is_target("https://s.ua/promo") is True
    assert pl.page_is_target("https://s.ua/akcii") is True
    assert pl.page_is_target("https://s.ua/rozprodazh") is True


def test_sale_hot_no_longer_match_product_slugs():
    # real terraincognita product slugs that stole the page_cap budget via sale/hot
    assert pl.page_is_target("https://terraincognita.com.ua/chereviki-salewa-ms-mtn-397/") is False
    assert pl.page_is_target("https://terraincognita.com.ua/termos-hot-and-cold-stuff-0-75-l/") is False
    # the real veteran-discount page (payment/delivery) is still targeted
    assert pl.page_is_target("https://terraincognita.com.ua/oplata-dostavka/") is True


# --- INCLUDE by anchor text (opaque URL) ---
def test_anchor_text_makes_opaque_url_target():
    assert pl.page_is_target("https://s.ua/page/12",
                             "Знижка для військовослужбовців") is True
    assert pl.page_is_target("https://s.ua/p2", "Корисна інформація") is True
    assert pl.page_is_target("https://s.ua/p3", "Випадковий текст") is False


# --- EXCLUDE wins over INCLUDE ---
def test_exclude_beats_include():
    assert pl.page_is_target("https://s.ua/product/sale-shoes") is False
    assert pl.page_is_target("https://s.ua/koshyk") is False
    assert pl.page_is_target("https://s.ua/blog/znizhka-viyskovym") is False
    assert pl.is_excluded("https://s.ua/product/1") is True
    assert pl.is_excluded("https://s.ua/about") is False


# --- neutral ---
def test_neutral_is_not_target():
    assert pl.page_is_target("https://s.ua/random/page") is False


# --- no false positives from substring matching ---
def test_no_substring_false_positives():
    assert pl.page_is_target("https://pharmacy.ua/catalog") is False   # 'army' vs pharmacy
    assert pl.page_is_target("https://s.ua/help/how") is False         # '/p/' vs '/help/'
    assert pl.page_is_target("https://s.ua/vintage") is False          # 'tag' vs vintage


def test_exclude_tokens_no_substring_collisions():
    # EXCLUDE hard-prunes (skip + no traverse) — must not misfire on legit paths.
    assert pl.is_excluded("https://s.ua/border-crossing") is False     # '/order' not 'order'
    assert pl.is_excluded("https://s.ua/basketball-shoes") is False    # 'basket' removed
    assert pl.is_excluded("https://s.ua/research-center") is False     # '/search' not 'search'
    assert pl.is_excluded("https://s.ua/order/history") is True        # '/order' still excluded
    assert pl.is_excluded("https://s.ua/search?q=x") is True           # '/search' still excluded
    assert pl.is_excluded("https://s.ua/company-profile") is False     # '/profile' not 'profile'
    assert pl.is_excluded("https://s.ua/club-registration") is False   # '/register' not 'register'
    assert pl.is_excluded("https://s.ua/profile/edit") is True         # '/profile' still excluded
    assert pl.is_excluded("https://s.ua/register") is True             # '/register' still excluded


# --- seed gate ---
def test_seed_is_target_root_always():
    assert pl.seed_is_target("https://s.ua") is True          # empty path
    assert pl.seed_is_target("https://s.ua/") is True         # '/'


def test_seed_is_target_path_gated():
    assert pl.seed_is_target("https://s.ua/kontakty") is True
    assert pl.seed_is_target("https://s.ua/product/1") is False
