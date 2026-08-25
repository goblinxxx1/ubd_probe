"""Capture-recapture (Chao1) coverage estimation for discovery saturation.

Pure functions, no I/O. Chao1 lower-bounds the total number of *discoverable*
domains from the frequency of singletons (домен побачений рівно 1 раз) and
doubletons (рівно 2 рази). Ідея з екології (оцінка чисельності виду), адаптована
для оцінки, скільки бізнес-доменів ще лишилось знайти пошуком.

ЗАСТЕРЕЖЕННЯ (best-practice): Chao1 — НИЖНЯ МЕЖА і припускає ВИПАДКОВИЙ семплінг.
Наш пошук ТАРГЕТОВАНИЙ (грід), тож абсолютне число зсунуте — використовувати ЛИШЕ
як DIRECTIONAL gauge (тренд сатурації в часі), НЕ гейтити тверді рішення на його
абсолютному значенні. При f2==0 і малому f1 оцінка нестабільна (bias-corrected форма
пом'якшує, не усуває)."""


def chao1(observed: int, f1: int, f2: int) -> float:
    """Оцінка-нижня-межа загальної кількості різних доменів.

    observed = скільки різних доменів уже бачили; f1 = бачені рівно раз;
    f2 = бачені рівно двічі. При f2==0 — bias-corrected форма."""
    if observed <= 0:
        return 0.0
    if f2 > 0:
        return observed + (f1 * f1) / (2.0 * f2)
    return observed + (f1 * (f1 - 1)) / 2.0


def saturation(observed: int, f1: int, f2: int) -> float:
    """Частка вже відкритого домен-всесвіту в [0,1]. 1.0 = нема чого шукати."""
    est = chao1(observed, f1, f2)
    if est <= 0:
        return 1.0
    return min(1.0, observed / est)
