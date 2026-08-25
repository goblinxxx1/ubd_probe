# Розгортання UBD на віддаленому сервері (VPS / хмара)

**Для кого:** людина, що піднімає проєкт на «чистому» Linux-сервері (VPS, хмарна ВМ, виділений хост) — не на локальній машині.
**Що отримаєш наприкінці:** робочий стек у Docker (публічний сайт + адмінка + API + БД + краулер із локальним LLM-суддею), доступний за доменом через HTTPS, з автобекапами БД.

Для локального запуску й щоденної розробки дивись натомість [RUN.md](../RUN.md) та [README-docker.md](../README-docker.md). Для викату лише нового коду краулера на вже піднятий стек — [runbook-redeploy-crawler.md](runbook-redeploy-crawler.md).

---

## 0. Що саме розгортаємо

Один Linux-сервер, увесь стек у Docker Compose. Сервіси діляться на дві групи:

| Група | Сервіси | Профіль | Коли потрібні |
|---|---|---|---|
| **Базова** (сайт) | `db`, `db-backup`, `backend`, `public`, `admin`, `adminer` | *(без профілю — стартують завжди)* | Завжди |
| **Краулер** (пошук офферів) | `crawler`, `llama`, `searxng`, `fixture` | `crawler` | Лише якщо потрібне автонаповнення офферами |

- **`backend`** — FastAPI. При першому старті САМ виконує міграції БД і сидинг (створює адмін-акаунт із `SEED_ADMIN_*`). Нічого руками мігрувати не треба.
- **`public`** / **`admin`** — статичні Vue-фронти на nginx; кожен усередині проксить `/api` на `backend` через docker-мережу. Тобто фронтам НЕ треба знати зовнішню адресу API.
- **`llama`** — локальна LLM `Qwen2.5-7B` (llama.cpp), суддя релевантності краулера. **Важить у памʼяті ~6 ГБ** і сам качає ~4.4 ГБ ваг при першому старті. Це найважчий сервіс.
- **`db`** — MySQL 8. Порт назовні **не публікується** (тільки в docker-мережі).
- **`adminer`** — веб-UI до БД. ⚠️ За замовчуванням публікується на `:8888` — на сервері це треба закрити (див. розділ 6).

### Вимоги до сервера

| Сценарій | RAM | CPU | Диск | ОС |
|---|---|---|---|---|
| **Повний стек** (з краулером + `llama`) | **8 ГБ** | 4 vCPU | 40 ГБ SSD | Ubuntu 22.04/24.04 LTS |
| **Тільки сайт** (без профілю `crawler`) | 2 ГБ | 1–2 vCPU | 20 ГБ SSD | Ubuntu 22.04/24.04 LTS |

> `llama` рахує на CPU — під час роботи судді буде помітне навантаження на ядра. Якщо сервер слабкий або офферам-пошук не потрібен — просто не піднімай профіль `crawler` (усі інструкції нижче це враховують).

---

## 1. Підготовка сервера

Виконуй під користувачем з `sudo`. Приклади — для Ubuntu.

### 1.1. Оновити систему і поставити Docker

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
```

Це ставить Docker Engine + плагін `docker compose`. Перевір:

```bash
docker --version && docker compose version
```

### 1.2. Дозволити запускати docker без sudo (опційно, зручно)

```bash
sudo usermod -aG docker $USER
```

Після цього **вийди і зайди в SSH заново**, щоб зміна групи застосувалась.

### 1.3. Базовий фаєрвол

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

> ⚠️ **Дуже важливо:** сам по собі `ufw` **НЕ** захищає порти, які публікує Docker. Docker додає власні правила `iptables`, що спрацьовують раніше за `ufw`, тож контейнер, опублікований на `0.0.0.0:8080`, буде доступний з інтернету навіть при `ufw deny`. Тому нижче (розділ 6) ми прив'язуємо всі порти застосунку до `127.0.0.1` і виставляємо назовні лише reverse-proxy на 80/443. Не покладайся на `ufw` як на єдиний захист.

---

## 2. Отримати код

```bash
git clone <URL-репозиторію> ubd
cd ubd
git checkout main
```

Далі всі команди виконуються з кореня репозиторію (`.../ubd`).

---

## 3. Секрети та налаштування (`.env`)

Секрети зберігаються у файлах `.env`, які **не потрапляють у git** (`.gitignore`). Їх треба створити на сервері вручну.

### 3.1. Кореневий `.env` (обовʼязково)

Це головний файл — з нього compose бере паролі, ключі й порти для базового стеку.

```bash
cp .env.example .env
```

Згенеруй **сильні** значення (не лишай приклади!) і впиши їх у `.env`:

```bash
openssl rand -base64 24   # → MYSQL_ROOT_PASSWORD
openssl rand -hex 32      # → JWT_SECRET
openssl rand -hex 24      # → CRAWLER_API_KEY
```

Відредагуй `.env`:

```ini
MYSQL_ROOT_PASSWORD=<згенероване>
JWT_SECRET=<згенероване>
CRAWLER_API_KEY=<згенероване>          # має збігатися з crawler/.env (розділ 3.2)
SEED_ADMIN_EMAIL=you@example.com
SEED_ADMIN_PASSWORD=<надійний пароль адміна>

# Краулер: 0 = один прохід і вихід; >0 = цикл кожні N секунд.
# Для живого сервера з автопошуком постав, напр., 10800 (кожні 3 год).
CRAWL_INTERVAL_SECONDS=10800

# Бекап БД раз на 48 год (172800 с) у ./backups на хості.
BACKUP_INTERVAL_SECONDS=172800

# Порти на хості (лишаємо як є — у розділі 6 замкнемо їх на 127.0.0.1).
BACKEND_PORT=8000
PUBLIC_PORT=8080
ADMIN_PORT=8082
```

> Адмін-акаунт (`SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`) створюється автоматично при першому старті backend. Постав одразу надійний пароль.

### 3.2. `crawler/.env` (лише якщо піднімаєш профіль `crawler`)

```bash
cp crawler/.env.example crawler/.env
```

Мінімум, що варто перевірити/поставити:

```ini
CRAWLER_API_KEY=<те саме значення, що в кореневому .env>
ACTIVE_DISCOVERY=true          # увімкнути активний пошук офферів
SEARCH_PROVIDERS=duckduckgo,searxng
```

- Суддя релевантності (`llama`) увімкнений за замовчуванням і сам ходить на `http://llama:8080` у docker-мережі — окремо налаштовувати не треба.
- У Docker `INTERNAL_API_URL` із цього файлу **ігнорується** — compose перекриває його на `http://backend:8000`. Не чіпай.
- Решта параметрів (антитротлінг пошуку, domain rating, лексикон) мають робочі дефолти — читай коментарі у `crawler/.env.example`, якщо треба тюнінг.

---

## 4. Збірка й перший запуск

### Варіант A — повний стек (сайт + краулер)

```bash
docker compose --profile crawler build
docker compose --profile crawler up -d
```

### Варіант B — тільки сайт (без краулера/llama)

```bash
docker compose build
docker compose up -d
```

**Що відбувається при першому старті:**
1. Піднімається `db`, чекає готовності.
2. `backend` виконує міграції (`alembic upgrade head`) і сидинг → створює адміна. Порядок гарантований healthcheck'ами.
3. `public`/`admin` стартують після готовності backend.
4. *(профіль crawler)* `llama` починає **качати ~4.4 ГБ ваг моделі** з HuggingFace у Docker-волюм `ubd-llama-models`. Це може тривати кілька хвилин; healthcheck має `start_period` 10 хв. Модель зберігається у волюмі й далі **не перекачується**.
5. *(профіль crawler)* `crawler` стартує після того, як backend став healthy.

---

## 5. Перевірка, що все живе

```bash
docker compose ps
```

Усі потрібні сервіси мають бути `Up` (а `db`, `backend`, `llama` — ще й `(healthy)`).

Швидка перевірка API (з самого сервера):

```bash
curl -fsS http://127.0.0.1:8000/api/health && echo OK
```

Якщо піднято краулер — перевір, що суддя відповідає:

```bash
docker compose exec -T crawler python -c "import urllib.request; print(urllib.request.urlopen('http://llama:8080/health', timeout=10).read().decode())"
# очікується: {"status":"ok"}
```

Логи краулера (мають бути `200 OK` на пошукові запити):

```bash
docker compose logs --tail=15 crawler
```

---

## 6. Доступ ззовні: HTTPS + закриття зайвих портів

Мета: назовні відкриті **тільки** `80`/`443` (reverse-proxy). Усі порти застосунку слухають лише `127.0.0.1`, тож недоступні з інтернету напряму (це і обходить проблему «Docker в обхід ufw» з розділу 1.3).

### 6.1. Замкнути порти застосунку на localhost

Відредагуй `docker-compose.yml` — додай префікс `127.0.0.1:` до кожної публікації порту:

```yaml
  backend:
    ports:
      - "127.0.0.1:${BACKEND_PORT:-8000}:8000"
  public:
    ports:
      - "127.0.0.1:${PUBLIC_PORT:-8080}:80"
  admin:
    ports:
      - "127.0.0.1:${ADMIN_PORT:-8082}:80"
  adminer:
    ports:
      - "127.0.0.1:8888:8080"      # доступ лише через SSH-тунель; або видали блок ports цілком
```

> `adminer` після цього доступний тільки з самого сервера. Щоб зайти в нього з ноутбука — SSH-тунель: `ssh -L 8888:127.0.0.1:8888 user@сервер`, далі відкрий `http://localhost:8888`. У проді його краще взагалі не тримати піднятим.

Застосуй зміну:

```bash
docker compose --profile crawler up -d   # (або без --profile crawler для варіанту B)
```

### 6.2. Reverse-proxy з автоматичним HTTPS (Caddy)

Caddy сам отримує й оновлює сертифікати Let's Encrypt. Постав його **на хост** (не в Docker):

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Пропиши домени у `/etc/caddy/Caddyfile` (спрямуй A-записи цих доменів на IP сервера заздалегідь):

```caddyfile
shop.example.com {
    reverse_proxy 127.0.0.1:8080
}

admin.example.com {
    reverse_proxy 127.0.0.1:8082
}
```

```bash
sudo systemctl reload caddy
```

Готово: `https://shop.example.com` → публічний сайт, `https://admin.example.com` → адмінка, обидва по TLS. `backend` назовні не потрібен (фронти проксять `/api` всередині docker-мережі).

---

## 7. Бекапи БД

Сайдкар `db-backup` уже вмикається у базовому стеку: раз на `BACKUP_INTERVAL_SECONDS` (дефолт 48 год) робить `mysqldump` бази `ubd` у теку `./backups/` **на хості** (переживає навіть `docker compose down -v`).

- Перевірити, що бекапи зʼявляються: `ls -lh backups/`
- Відновити з бекапу:

  ```bash
  sh docker/backup/restore.sh backups/ubd_YYYYmmdd_HHMMSS.sql
  ```

  ⚠️ Відновлення **повністю заміщує** поточну базу `ubd`. Пароль скрипт бере з `./.env`.

> Порада: періодично копіюй теку `backups/` кудись поза сервером (інший хост / обʼєктне сховище) — локальний бекап не рятує від втрати самого сервера.

---

## 8. Оновлення (викат нового коду)

```bash
git pull
docker compose --profile crawler build      # або без --profile crawler
docker compose --profile crawler up -d
```

- `backend` при старті сам домігрує БД, якщо додались нові міграції.
- `llama` при цьому **не перекачує** модель (вона у волюмі) і навіть не пересоздається, якщо його конфіг не змінювався.
- Для викату лише краулера є коротший рунбук: [runbook-redeploy-crawler.md](runbook-redeploy-crawler.md).

---

## 9. Чек-лист безпеки (перед «бойовим» запуском)

- [ ] Усі секрети в `.env` — згенеровані, а не значення з `.env.example`.
- [ ] `SEED_ADMIN_PASSWORD` надійний; після першого входу пароль адміна змінено.
- [ ] Порти застосунку прив'язані до `127.0.0.1` (розділ 6.1) — перевір: `sudo ss -tlnp | grep -E ':8080|:8082|:8000|:8888'` має показувати `127.0.0.1`, а не `0.0.0.0`.
- [ ] `db` не публікується назовні (за замовчуванням так і є — переконайся, що не додав).
- [ ] `adminer` закритий (localhost-only або взагалі не піднятий).
- [ ] `ufw` активний, відкриті лише 22/80/443.
- [ ] HTTPS працює (Caddy видав сертифікати).
- [ ] Бекапи зʼявляються в `./backups/` і копіюються поза сервер.

---

## 10. Якщо щось не так

| Симптом | Що зробити |
|---|---|
| `backend` рестартиться / не `healthy` | `docker compose logs --tail=50 backend`. Часто — неправильний `DATABASE_URL`/пароль: звір `MYSQL_ROOT_PASSWORD` у `.env`. |
| `llama` довго `starting` при першому старті | Це нормально — качає ~4.4 ГБ. Дивись прогрес: `docker compose logs -f llama`. `start_period` — 10 хв. |
| Краулер живий, а суддя недоступний | Перевір `docker compose ps llama`. Після старту `llama` ~1 хв вантажить модель у памʼять. |
| Сайт відкривається, але дані не вантажаться (помилки `/api`) | Фронт живий, але не дістає backend. `docker compose logs --tail=30 backend`; перевір, що `backend` — `healthy`. |
| Порт застосунку видно з інтернету попри `ufw` | Ти не замкнув порт на `127.0.0.1` (розділ 6.1). Docker публікує в обхід `ufw`. |
| Домен не відкривається по HTTPS | Перевір A-запис домену → IP сервера; `sudo journalctl -u caddy -n 50`; порти 80/443 відкриті в `ufw` і в security-group хмари. |
| Мало памʼяті / `llama` вбиває OOM | Сервер < 8 ГБ. Або збільш RAM, або підіймай без профілю `crawler` (Варіант B). |
