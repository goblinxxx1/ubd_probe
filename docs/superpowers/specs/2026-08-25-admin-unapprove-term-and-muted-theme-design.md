# Адмінка: «повернути в кандидати» approved-терміни + приглушена тема

**Дата:** 2026-08-25
**Гілка:** `feat/admin-unapprove-term-and-muted-theme`

Два незалежні дрібні адмін-запити в одному треку.

## Фіча 1 — видалити слово зі схвалених термінів пошуку (approved → pending)

**Проблема:** схвалені (approved) query-терміни годують пошуковий грід краулера (краулер щоб 6 год перечитує їх з `/api/internal/query-terms/approved` → `runner.py:121`). Зараз у [admin/src/views/QueryTermsView.vue] для `status === 'approved'` НЕМА жодної дії — не можна прибрати помилково-схвалене слово.

**Рішення (обрано користувачем):** approved → **pending** (повернути в чергу кандидатів). Слово виходить з гріду на найближчому 6-год рефреші; лишається кандидатом на повторний аудит; оборотно (можна знову затвердити). Крауле-код НЕ чіпаємо — він уже сам віддає лише approved.

- **Backend:** новий ендпоінт `POST /api/admin/query-terms/{term_id}/to-pending` → `query_term_crud.to_pending(db, term_id)` (уже існує, reuse; ставить status=pending, чистить reviewed_by/reviewed_at). Response `QueryTermOut`. Не чіпаємо наявний `unreject` (він для rejected-вкладки, той самий crud).
- **Admin API:** `toPending(id)` у [admin/src/api/queryTerms.js].
- **Admin UI:** у QueryTermsView для `row.status === 'approved'` — кнопка **«Повернути в кандидати»** (та сама мова, що для rejected) → `toPending` + toast + reload.

**Тести:**
- backend ([backend/tests/test_query_terms_admin.py]): POST to-pending на approved-термін → 200, status=pending, reviewed_by/at очищені; `list_approved_terms` більше його не містить.
- admin ([admin/tests/views/QueryTermsView.test.js]): approved-рядок показує кнопку, клік викликає `toPending` і reload.

## Фіча 2 — приглушити тон адмінки (темніші поверхні)

**Запит:** зробити світлі поверхні ~вполовину темніше; посилання не чіпати; семантичні статуси лишити. Рівень зафіксовано користувачем інтерактивним прев'ю.

**Ключова знахідка:** наші токени фарбують лише хром (sidebar/topbar/body — [AdminLayout.vue], [global.less]). Контент — Element Plus компоненти (таблиці/картки/інпути/дропдауни) — малює власним білим через `--el-bg-color`/`--el-fill-color-blank`/тощо. Тож треба перекрити й нейтральні EP-змінні, інакше будуть білі таблиці на грейжевому тлі.

### Палітра (зафіксована)

[admin/src/styles/variables.less] — нові значення (решта рядків без змін):
```
@bg:         #BAB6AB;   // було #FAFAF9
@surface:    #CAC6BC;   // було #FFFFFF
@brand:      #AB7D38;   // було #E0982A
@divider:    #A49F93;   // було #E7E5E0
@nav-muted:  #4D4941;   // було #6E6A5E
@meta-muted: #575146;   // було #6A6355
@cream:      #C5B9A0;   // було #F5F1E8
@row-hover:  #C5B9A0;   // було #FCF5EA
```
НЕ чіпати: `@text #14110A`, `@link #8A5A1E` (користувач просив лишити посилання), `@dark #211D16`, `@heading-weight`, ширини, брейкпоінти.

### Element Plus тема

[admin/src/styles/element-theme.less] — рампа primary з нового акценту + нові перекриття нейтралей:
```
--el-color-primary:          #AB7D38;
--el-color-primary-light-3:  #B49360;
--el-color-primary-light-5:  #BAA17A;
--el-color-primary-light-7:  #C1B094;
--el-color-primary-light-8:  #C4B7A2;
--el-color-primary-light-9:  #C5B9A0;   // = @row-hover/@cream
--el-color-primary-dark-2:   #8B6429;

--el-bg-color:               #CAC6BC;   // картки, тіло таблиці
--el-bg-color-page:          #BAB6AB;
--el-bg-color-overlay:       #D0CCC3;   // дропдауни/тултіпи (трохи світліше = елевація)
--el-fill-color-blank:       #CAC6BC;   // фон інпутів/клітин
--el-fill-color:             #BEB9AE;
--el-fill-color-light:       #C3BFB4;
--el-fill-color-lighter:     #C6C2B8;
--el-fill-color-extra-light: #C9C5BB;
--el-fill-color-dark:        #B7B2A7;
--el-fill-color-darker:      #B2ADA2;
--el-border-color:           #A49F93;
--el-border-color-light:     #ADA89C;
--el-border-color-lighter:   #B4AFA3;
--el-border-color-extra-light:#BBB6AA;
--el-border-color-dark:      #9A958A;
--el-border-color-darker:    #928D81;
--el-text-color-primary:     #14110A;
--el-text-color-regular:     #2A261D;
--el-text-color-secondary:   #575146;
--el-text-color-placeholder: #6E6A5E;
--el-text-color-disabled:    #8A8578;
```
**НЕ чіпати** семантичні `--el-color-success/warning/danger/info*` — статуси лишаються скануваними (наявне рішення теми).

### Перевірка
- `npm run build` (обов'язково — ловить scoped-Less помилки; Vitest НЕ ловить — [[ubd-ui-redesign]]).
- Ребілд admin-контейнера. Візуал звіряє користувач (браузер-панель не дістає host-localhost — [[ubd-preview-surfaces]]); палітру вже підтверджено інтерактивним прев'ю.

## Поза скоупом (свідомо)
- Public-фронт (:8080) — не чіпаємо, лише admin.
- Семантичні статус-кольори EP.
- Крауле-код (approved-терміни вже читаються live).
