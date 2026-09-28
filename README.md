# zolushka-parsing

Самообновляемый XML/YML-фид каталога **zolushka.com.ua** («Попелюшка»,
дитячі товари, движок Horoshop) для маркетплейсов (Prom.ua/Rozetka), плюс
копия тех же данных в Google-таблице `parsing_zolushka`.

Обновляется автоматически через GitHub Actions **1 раз в сутки, в 06:00 по
Києву**, результат публикуется на GitHub Pages. Почему не 5×/сутки, как у
dasmart, — см. «Тайминг и частота» ниже.

Отдельный проект от `dasmart-parser` — общего кода между ними нет.

## Файлы

| Файл | Назначение |
|---|---|
| `parse_zolushka.py` | Antibot-кука, список товарных URL из sitemap, разбор карточки, пул потоков + доповтор упавших |
| `build_feed.py` | Синтетические ID категорий из breadcrumbs + сборка `public/feed.xml` |
| `opt_prices.py` | Чтение снимка опт-цен `opt_prices.json` (обновляется вручную, см. ниже) |
| `fetch_opt_prices.py` | Ручной инструмент: опт-цены с авторизованной сессией (кука — руками) |
| `sheets_util.py` | Запись листа в Google-таблицу (clear + запись чанками) |
| `zolushka_to_sheets.py` | Формирование строк и запись листа «Zolushka» |
| `run_zolushka.py` | Оркестратор: скрапинг → `zolushka_products.json` → `public/feed.xml` → таблица |
| `.github/workflows/update.yml` | Расписание 1×/сутки + деплой на Pages + keepalive |

## Какие поля собираются

Со страницы товара, без единого лишнего запроса — ID и артикул, ціна,
наявність и кількість, категорія — все из встроенной микроразметки
schema.org и breadcrumbs, без хрупкого парсинга текста:

| Поле | Источник на странице |
|---|---|
| `id` | `<meta itemprop="mpn">` — внутренний числовой ID (не путать с артикулом) |
| `vendorCode` (артикул) | `<meta itemprop="sku">` |
| `name` | `<h1>` |
| `description` | `.product-description .text` **с HTML-розміткою як є** (не в текст) |
| `characteristics` | таблиця `.product-features__table` (пари ключ/значення) |
| `vendor` (бренд) | характеристика «Бренд», якщо є |
| `price` / `currency` | `<meta itemprop="price"/priceCurrency">` — роздрібна ціна |
| `opt_price` | окремий снімок `opt_prices.json` (див. «Опт-ціни» нижче) — НЕ зі сторінки анонімно |
| `available` | `<link itemprop="availability" href=".../InStock|OutOfStock">` |
| `quantity` | `data-max` у лічильника кількості біля кнопки «купити» (реальний залишок) |
| `images` | усі `data-href` галереї (`.gallery__link.j-gallery-zoom`) — це «zoom»-якість, більша за прев'ю, і чесна (не розтягнута) |
| `category_path` | breadcrumbs (`schema.org/BreadcrumbList`), без «Головна» і без самого товару |

Список товарних URL — не з категорій (там сітка товарів підвантажується
ajax-віджетом, `Disallow`-нутим у `robots.txt`), а з
`content/export/zolushka.com.ua/catalog-sitemap.xml` (~12 900 товарних URL
без урахування `/ru/`-дублів).

## Антибот

Без cookie `challenge_passed` сервер замість сторінки віддає скрипт:
імітація busy-wait і `document.cookie = "challenge_passed=" + <хэш>` +
`location.reload()`. Хэш **не залежить від IP/сесії** — читаємо його прямо
з тіла цього скрипту звичайним HTTP-запитом, без браузера. Значення іноді
змінюється між прогонами, тому не хардкодимо, а знімаємо заново на початку
і переснімаємо при виявленні непройденого челенджу посеред прогону.

## Опт-ціни: чому це окремий ручний крок

Вхід на сайт (`/security/login/`) захищений **справжньою reCAPTCHA** — не
тим тривіальним антиботом вище. Обходити чи автоматично розв'язувати
CAPTCHA ми не будемо в жодному вигляді, навіть для власного акаунта.
Тому опт-ціни — не частина щоденного автопрогону, а окремий ручний крок:

1. Заходите на `https://zolushka.com.ua/` у звичайному браузері, логінитесь
   (обліковка з доступом до опт-цін — умови на `/opt-dropshipping/`: перше
   замовлення від 10 000 грн і від 10 одиниць, далі опт діє півроку).
2. DevTools → Network → будь-який запит до zolushka.com.ua → заголовки
   запиту → копіюєте значення заголовка `Cookie` цілком.
3. Вставляєте цей рядок у `session_cookie.txt` поруч зі скриптами (файл у
   `.gitignore`, нікуди не комітиться).
4. `python3 fetch_opt_prices.py --check` — перевірка, що сесія робоча.
5. `python3 fetch_opt_prices.py --limit 10` — пробний прогін, друкує
   порівняння роздрібної ціни й ціни з кукою. **Це не перевірено на
   реальній сесії** (програмний логін заблокований капчею, побачити
   автентифіковану сторінку можна тільки руками) — якщо жодна з 10 цін не
   відрізняється від роздрібної, значить опт показується не в цьому ж полі
   (чи акаунту ще не відкрили опт) і код `fetch_price()` потрібно буде
   підправити під те, що реально прийде.
6. Якщо все ок — `python3 fetch_opt_prices.py` (повний прогін) і
   закомітити оновлений `opt_prices.json` — тільки після цього щоденний
   автопрогін підхопить свіжі опт-ціни (сам він кукою не користується).

Кука сесії рано чи пізно протухне — тоді кроки 1-4 повторити.

## Тайминг і частота

Повний прохід усіх ~12 900 товарів займає **70-90 хвилин** і 28.09.2026 вже
одного разу спіймав `429 Too Many Requests` під кінець годинного прогону
(51 товар — доловлені повільним повтором, тепер це робиться автоматично
всередині `parse_zolushka.scrape_all`). Гонити його 5×/добу, як у dasmart,
означало б 6-7.5 годин навантаження на чужий сервер щодня — вирішили
обмежитися **1 разом на добу**.

## Локальний запуск

```bash
pip3 install -r requirements.txt
python3 run_zolushka.py --limit 50 --no-sheets   # пробний прогін, без запису в таблицю
python3 run_zolushka.py                          # повний каталог (~70-90 хв) + feed.xml + лист «Zolushka»
```

Потрібен `service_account.json` поруч (той самий сервіс-акаунт, що й у
`dasmart-parser`, підключений і до цієї таблиці теж).

Python з python.org на macOS не бачить кореневі сертифікати
(`CERTIFICATE_VERIFY_FAILED`) — тоді
`export SSL_CERT_FILE=$(python3 -m certifi)` або «Install Certificates.command».

## Розгортання в GitHub (один раз)

```bash
gh repo create zolushka-parsing --public --source=. --remote=origin --push
gh secret set GOOGLE_SERVICE_ACCOUNT_JSON < service_account.json
```

Потім у репозиторії: **Settings → Pages → Source: GitHub Actions**.
Запустити вручну: **Actions → Update feed → Run workflow**.

Готове посилання фіда: `https://<логін>.github.io/zolushka-parsing/feed.xml` —
його вказуєте в імпорті Prom.ua / Rozetka.

## Джерела / призначення

- **Каталог постачальника:** `https://zolushka.com.ua/` (sitemap, без параметрів середовища).
- **Наша таблиця:** `TARGET_SHEET_ID` (`1jTGwSsHWo539yap0SVsgKkWgBW174U5I1bALk7vfqic`,
  таблиця `parsing_zolushka`), лист `ZOLUSHKA_WORKSHEET` (за замовчуванням «Zolushka»).
  Розшарена на той самий сервіс-акаунт, що й `dasmart-parser`.

## Нотатки

- **Зеркалювання постачальника.** Лист і фід повністю перезбираються щоразу;
  товари, що зникли з sitemap постачальника, зникають і в нас.
- **Правило 60 днів.** GitHub вимикає розклад у публічному репозиторії без
  комітів 60 днів — джоб `keepalive` після 50 днів тиші робить порожній
  коміт (той самий урок, що й у dasmart-parser, 24.08.2026).
- Якщо постачальник змінить структуру sitemap/картки товару — перевірити
  `parse_zolushka.list_product_urls` і `parse_zolushka.parse_product`.
