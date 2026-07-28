# Admin edit: links-синк + «Зберегти і опублікувати»

**Дата:** 2026-07-28
**Гілка:** `feat/admin-edit-links-sync-and-publish`
**Скоуп:** backend (`update_offer`) + admin (`OfferForm`/`OfferFormView`). Crawler/схема не чіпаємо.

## Проблема

1. **Правки посилань в адмінці не доходять до public.** Адмін-форма редагує поля «Сайт» (`site_url`) і «Сторінка новини» (`article_url`); `update_offer` (backend/app/crud/offer.py:198-221) робить `setattr` лише на **offer-колонки** і **ніколи не оновлює `offer_links`**. Public-картка (public/src/components/OfferCard.vue:8-14) рендерить `site_url`/`article_url` **з `offer.links`** (таблиця `offer_links`), а offer-колонки бере лише як фолбек, коли лінків нема. Оскільки крауловані офери мають рядок у `offer_links`, правки offer-колонок на public невидимі.
2. **Немає швидкого «зберегти + опублікувати»** зі сторінки редагування — треба зберегти, повернутись у чергу, тоді окремо опублікувати.

*(NB: `image_url` — offer-рівневе, картка бере його напряму (OfferCard.vue:7); правка видна після релоаду. Поза цим фіксом.)*

## Рішення

### Компонент A — `update_offer` синкає `offer_links` (backend/app/crud/offer.py)

Перед `setattr`-циклом запамʼятати старі `obj.site_url`, `obj.article_url`. Після застосування payload — якщо в payload є будь-що з `provider`/`site_url`/`article_url`, синкнути лінк(и):
- **0 лінків** → додати `OfferLink(provider=obj.provider, site_url=obj.site_url, article_url=obj.article_url)`.
- **1 лінк** → оновити його `provider`/`site_url`/`article_url` на нові offer-значення.
- **>1 лінк** → знайти лінк, де `link.site_url == old_site AND link.article_url == old_article` (той, що збігався зі СТАРими offer-значеннями), оновити його; якщо збігу нема — не чіпати жодного (крос-джерельні провайдер-лінки лишаються).

`OfferLink` імпортується локально (як у `create_offer`). Решта `update_offer` (валідація дат/знижки, категорії, canonical на зміну target_url) — без змін.

### Компонент B — кнопка «Зберегти і опублікувати» (admin)

- **`OfferForm.vue`:** `defineEmits(["submit","cancel","submit-publish"])`; `submitPublish()` — та сама валідація, що `submit()`, тоді `emit("submit-publish", buildOfferPayload(form))`. Computed `canPublish = props.initial?.id && props.initial?.status !== "published"`. У `.actions` додати `<el-button v-if="canPublish" type="success" @click="submitPublish">Зберегти і опублікувати</el-button>` (перед «Скасувати»).
- **`OfferFormView.vue`:** `@submit-publish="onSubmitPublish"`; `onSubmitPublish(payload)` → `await offers.update(id, payload)` → `await offers.publish(id)` → `ElMessage.success("Збережено та опубліковано")` → `router.push({name:"offers"})`. (`offers.publish` уже є.)

## Тести

- **backend (+):** update site_url на офері з 1 лінком → лінк оновлено (public-значення змінилось); update на мульти-лінк-офері оновлює лише той, що збігався зі старими, інші лишаються; update офера без лінків → лінк створено; наявні `test_update_*` (canonical-recompute, валідація) зелені.
- **admin (+):** OfferForm показує кнопку лише при `id && status!=='published'` і емітить `submit-publish` з payload; OfferFormView на `submit-publish` викликає `update` потім `publish`; + `npm run build`.

## Не-скоуп (YAGNI)

- `image_url`-синк (вже offer-рівневе, доходить до public).
- Публічний кеш/staleness (окремо, якщо підтвердиться).
- Дедуп сторінки на рівні `article_url` — окремий майбутній трек [[ubd-todo-page-level-offer-identity]].
