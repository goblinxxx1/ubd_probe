"""Pre-walk «low-value host» гейт: відсіює НЕкомерційні хости ДО дорогого обходу.

Причина: `classify_candidate` віддає будь-який http-хост з видачі пошуку як
website-кандидата, а harvester повністю обходить кожного (robots+sitemap+BFS =
30-50 фетчів) перш ніж реєстр запише score 0. ~88% доменів дають 0 оферів. Цей
гейт вбиває структурно-безнадійні хости на вході, ще до витрати бюджету обходу.

Свідомо СТРУКТУРНИЙ (TLD/друга-мітка), а не список хостів: gov/edu/mil/int та
IDN-ccTLD ловляться без ручної курації. Мінімальний список глобальних платформ —
для чужих gTLD, що структурно не вирізняються (reddit/steam/...); розширювати його
має самонавчальний блокліст, а не цей файл."""

from crawler.util.hosts import bare_host

# Інституційні TLD/друга-мітка — ніколи не бізнес зі знижкою для УБД.
_INSTITUTIONAL_TLDS = {"gov", "edu", "mil", "int"}
_INSTITUTIONAL_SECOND_LEVEL = {"gov", "edu", "mil"}  # напр. edu.ua, gov.ua, mil.ua

# Глобальні неторгові платформи, що приходять як «website» з чужих gTLD і структурно
# не відрізняються від бізнесу. Тримати ВУЗЬКИМ; зростання — через learned-блокліст.
_GLOBAL_PLATFORMS = frozenset({
    "reddit.com", "kaggle.com", "wikimedia.org", "wikipedia.org",
    "steamcommunity.com", "steampowered.com", "teamfortress.com",
    "fliphtml5.com", "trip.com", "quora.com", "medium.com",
})


def is_low_value_host(value: str | None) -> bool:
    """True, якщо хост структурно не може бути джерелом офера (не витрачати обхід)."""
    host = bare_host(value)
    if not host or "." not in host:
        return False
    labels = host.split(".")
    tld = labels[-1]
    if tld in _INSTITUTIONAL_TLDS:
        return True
    if len(labels) >= 2 and labels[-2] in _INSTITUTIONAL_SECOND_LEVEL:
        return True     # *.edu.ua / *.gov.ua / *.mil.ua
    return any(host == p or host.endswith("." + p) for p in _GLOBAL_PLATFORMS)


# Новинні/медіа токени в мітці хоста — новинний сайт ніколи не дає знижку УБД.
# Підрядок (домени — ASCII-транслітом), бо патерн у дикому полі часто злитий:
# <місто/слово>news (rivnenews/lvivnews), <слово>-news (groza-news), або мітка news.
# Виміряно на живому корпусі (196 хостів): 0 бізнес-хостів зачеплено, 11 матчів —
# усі справжні новини. `zmi` НЕ беремо (колізить зі «zmina/зміни»).
_NEWS_TOKENS = ("news", "novyny", "gazeta", "visti", "pravda")

# TLD, що позначає медійний ресурс незалежно від мітки (новинні портали, журнали).
# .media — практично завжди медіа; перевірено 0 published-оферів на .media.
_MEDIA_TLDS = {"media"}


def is_news_host(value: str | None) -> bool:
    """True, якщо хост — новинний/медійний ресурс (не джерело офера УБД): новинний
    токен у мітці АБО медійний TLD (.media)."""
    host = bare_host(value)
    if not host:
        return False
    labels = host.split(".")
    if labels[-1] in _MEDIA_TLDS:
        return True
    return any(tok in label for label in labels for tok in _NEWS_TOKENS)
