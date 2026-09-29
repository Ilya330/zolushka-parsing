#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Снимок опт-цен — читает куку УЖЕ авторизованной сессии (вход на сайте
защищён reCAPTCHA, программно мы туда не логинимся) и переобходит товарные
страницы, вытаскивая цену той же микроразметкой schema.org, что и основной
парсер. Список (Артикул, URL) берём прямо из уже заполненной Google-таблицы
(лист «Zolushka») — не пересобираем каталог заново.

Кука рано или поздно протухнет — --check тогда явно скажет об этом (в CI
это должно уронить job с понятной причиной, а не тихо оставить старые цены).

Как получить куку:
  1. Зайдите на https://zolushka.com.ua/ в обычном браузере и залогиньтесь
     (email/пароль от аккаунта, которому provider дал доступ к опт-ценам).
  2. DevTools -> Network -> любой запрос к zolushka.com.ua -> заголовки
     запроса -> скопировать целиком значение заголовка Cookie.
  3. Локально: вставить строкой в session_cookie.txt рядом со скриптом
     (файл в .gitignore). В GitHub Actions: обновить секрет
     ZOLUSHKA_SESSION_COOKIE тем же значением.

Запуск:
  python3 fetch_opt_prices.py --check          # только проверить, залогинены ли мы
  python3 fetch_opt_prices.py --limit 10        # пробный прогон, печатает сравнение с розницей
  python3 fetch_opt_prices.py                   # полный прогон -> opt_prices.json
"""

import argparse
import json
import os
import re
import sys
import time

import parse_zolushka as pz
import run_zolushka
import zolushka_to_sheets as zts

HERE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.environ.get(
    "ZOLUSHKA_SESSION_COOKIE_FILE", os.path.join(HERE, "session_cookie.txt")
)
OUT_PATH = os.path.join(HERE, "opt_prices.json")


def load_session_cookie():
    # в GitHub Actions значение приходит секретом напрямую, без файла
    env_cookie = os.environ.get("ZOLUSHKA_SESSION_COOKIE")
    if env_cookie:
        return env_cookie.strip()
    if not os.path.exists(COOKIE_FILE):
        sys.exit(
            f"Нет {COOKIE_FILE} и не задан ZOLUSHKA_SESSION_COOKIE. "
            "Залогиньтесь на сайте в обычном браузере, скопируйте заголовок "
            "Cookie целиком и сохраните его туда (см. docstring этого файла)."
        )
    with open(COOKIE_FILE, encoding="utf-8") as f:
        return f.read().strip()


def load_products():
    """[(vendorCode, url, price), ...] прямо из таблицы (лист «Zolushka»)."""
    gc = run_zolushka.gspread_client()
    sh = gc.open_by_key(zts.TARGET_SHEET_ID)
    ws = sh.worksheet(zts.WORKSHEET)
    rows = ws.get_all_values()[1:]
    code_i = zts.HEADERS.index("Артикул")
    price_i = zts.HEADERS.index("Ціна")
    url_i = zts.HEADERS.index("URL")
    return [(r[code_i], r[url_i], r[price_i]) for r in rows if r[url_i]]


def check_logged_in(cookie):
    """Грубая эвристика: если на /profile/ всё ещё форма логина — не вошли."""
    body = pz.fetch(pz.BASE + "/profile/", extra_headers={"Cookie": cookie})
    has_login_form = 'action="/security/login/"' in body
    return not has_login_form, body


def fetch_price(url, cookie):
    body = pz.fetch(url, extra_headers={"Cookie": cookie})
    m = re.search(r'itemprop="price"\s+content="([^"]*)"', body)
    return m.group(1) if m else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="только проверить логин")
    ap.add_argument("--limit", type=int, default=0, help="ограничить число товаров")
    args = ap.parse_args()

    cookie = load_session_cookie()

    print("Проверяю сессию (/profile/)...", flush=True)
    ok, _ = check_logged_in(cookie)
    print("  похоже, что залогинены:", ok, flush=True)
    if not ok:
        sys.exit(
            "ОШИБКА: кука не похожа на авторизованную (страница входа всё "
            "ещё показывается) — сессия протухла. Обновите куку (см. "
            "docstring) и повторите. [код выхода ненулевой специально, "
            "чтобы CI пометил прогон красным]"
        )
    if args.check:
        return

    print("Читаю список товаров из таблицы...", flush=True)
    products = load_products()
    if args.limit:
        products = products[:args.limit]
    print(f"Товаров для сверки: {len(products)}", flush=True)

    opt = {}
    diffs = 0
    for i, (code, url, retail_price) in enumerate(products, 1):
        try:
            price = fetch_price(url, cookie)
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(products)}] ошибка {url}: {e}", flush=True)
            continue
        if price:
            opt[code] = price
            if price != retail_price:
                diffs += 1
        if args.limit:
            print(f"  {code}: роздрібна={retail_price!r} "
                  f"з кукою={price!r}", flush=True)
        elif i % 500 == 0:
            print(f"  {i}/{len(products)}", flush=True)
        time.sleep(0.3)

    print(f"Готово: {len(opt)} цен, отличаются от розницы: {diffs}", flush=True)
    if not args.limit:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(opt, f, ensure_ascii=False, indent=2)
        print(f"Записано в {OUT_PATH} — закоммитьте его, чтобы прогон "
              f"подхватил свежие опт-цены.", flush=True)
    elif diffs == 0:
        print("ВНИМАНИЕ: ни одна цена не отличается от розничной — либо "
              "аккаунту ещё не открыли опт (см. /opt-dropshipping/), либо "
              "опт-цена показывается не в этом же поле. Не запускайте полный "
              "прогон, пока не разберётесь.", flush=True)


if __name__ == "__main__":
    main()
