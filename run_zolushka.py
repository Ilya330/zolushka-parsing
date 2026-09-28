#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Оркестратор: каталог zolushka.com.ua -> zolushka_products.json +
public/feed.xml (для маркетплейса) + лист «Zolushka» в Google-таблице
`parsing_zolushka`.

Запуск:
  python3 run_zolushka.py                # полный прогон (~12 900 товаров)
  python3 run_zolushka.py --limit 50     # пробный прогон на 50 товарах
  python3 run_zolushka.py --no-sheets    # без записи в Google-таблицу
  python3 run_zolushka.py --no-feed      # без сборки public/feed.xml
"""

import argparse
import json
import os
import sys

import build_feed
import opt_prices
import parse_zolushka
import ru_content

HERE = os.path.dirname(os.path.abspath(__file__))
SA_JSON = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_JSON", os.path.join(HERE, "service_account.json")
)
OUT_JSON = os.environ.get(
    "ZOLUSHKA_OUT_JSON", os.path.join(HERE, "zolushka_products.json")
)
OUT_FEED = os.environ.get("OUT_FEED", os.path.join(HERE, "public", "feed.xml"))

_GC = None


def gspread_client():
    """Ленивая инициализация gspread-клиента (один на прогон).

    BackOffHTTPClient повторяет запрос при 408/429/5xx с растущей паузой.
    """
    global _GC
    if _GC is None:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(SA_JSON, scopes=scopes)
        _GC = gspread.authorize(creds, http_client=gspread.BackOffHTTPClient)
    return _GC


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sheets", action="store_true",
                    help="не писать в Google-таблицу")
    ap.add_argument("--no-feed", action="store_true",
                    help="не собирать public/feed.xml")
    ap.add_argument("--limit", type=int, default=0,
                    help="ограничить число товаров (для проверки)")
    args = ap.parse_args()

    out_json = OUT_JSON
    if args.limit and "ZOLUSHKA_OUT_JSON" not in os.environ:
        # тестовый прогон — не затирать боевой бэкап полного каталога
        root, ext = os.path.splitext(OUT_JSON)
        out_json = f"{root}.sample{ext}"

    print("Снимаю antibot-куку...", flush=True)
    parse_zolushka.get_cookie()

    print("Скачиваю sitemap...", flush=True)
    urls = parse_zolushka.list_product_urls()
    if args.limit:
        urls = urls[:args.limit]
    print(f"  товарных URL: {len(urls)}", flush=True)

    print("Разбор товарных страниц...", flush=True)
    products, errors = parse_zolushka.scrape_all(urls)
    print(f"  разобрано: {len(products)}, ошибок: {len(errors)}", flush=True)
    if errors:
        print("  примеры ошибок:", flush=True)
        for url, err in errors[:10]:
            print(f"    {url}: {err}", flush=True)
    if not products:
        print("ОШИБКА: 0 товаров — прерываю.", file=sys.stderr)
        sys.exit(1)

    opt_map = opt_prices.load()
    matched = opt_prices.merge(products, opt_map)
    print(f"  опт-цен подставлено: {matched} / {len(products)} "
          f"(снимок из opt_prices.json, обновляется вручную)", flush=True)

    ru_map = ru_content.load()
    ru_matched = ru_content.merge(products, ru_map)
    print(f"  рос. версий подставлено: {ru_matched} / {len(products)} "
          f"(снимок из ru_content.json, обновляется раз в неделю)", flush=True)

    # бэкап на диск ДО фида/таблицы — прогон может занять десятки минут,
    # сбой дальше не должен стоить всего разбора
    print(f"Сохраняю {out_json}...", flush=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    size = os.path.getsize(out_json)
    print(f"  {out_json} ({size / 1e6:.1f} МБ)", flush=True)

    if not args.no_feed:
        print("Сборка public/feed.xml...", flush=True)
        path, categories = build_feed.write_feed(products, OUT_FEED)
        print(f"  {path} ({os.path.getsize(path) / 1e6:.1f} МБ, "
              f"категорий: {len(categories)})", flush=True)

    if args.limit and not args.no_sheets:
        print("  --limit задан без --no-sheets: лист «Zolushka» тоже будет "
              "перезаписан урезанной выборкой!", flush=True)
    if not args.no_sheets:
        print("Запись в Google-таблицу (лист Zolushka)...", flush=True)
        import zolushka_to_sheets
        n = zolushka_to_sheets.write_all(gspread_client(), products)
        print(f"  записано товаров: {n}", flush=True)
    print("Готово.", flush=True)


if __name__ == "__main__":
    main()
