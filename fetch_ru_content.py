#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сбор русскоязычных назва/опис/характеристики по ru_url. Список (Артикул,
URL (РУ)) берём прямо из уже заполненной Google-таблицы (лист «Zolushka») —
НЕ пересобираем каталог заново: он и так обновляется ежедневным
run_zolushka.py, а этот прогон должен быть независимым и не дублировать
полный обход сайта.

Отдельный, более редкий прогон, а не часть ежедневного: контент почти не
меняется, а его сбор удваивает число запросов к сайту.

Запуск:
  python3 fetch_ru_content.py --limit 50   # пробный прогон
  python3 fetch_ru_content.py              # полный -> ru_content.json
"""

import argparse
import concurrent.futures
import json
import os

import parse_zolushka as pz
import run_zolushka
import zolushka_to_sheets as zts

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "ru_content.json")


def load_ru_urls():
    """[(vendorCode, ru_url), ...] из колонок «Артикул»/«URL (РУ)» таблицы."""
    gc = run_zolushka.gspread_client()
    sh = gc.open_by_key(zts.TARGET_SHEET_ID)
    ws = sh.worksheet(zts.WORKSHEET)
    rows = ws.get_all_values()[1:]
    code_i = zts.HEADERS.index("Артикул")
    ru_url_i = zts.HEADERS.index("URL (РУ)")
    return [(r[code_i], r[ru_url_i]) for r in rows if r[ru_url_i]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print("Читаю список URL (РУ) из таблицы...", flush=True)
    pairs = load_ru_urls()
    print(f"  найдено: {len(pairs)}", flush=True)
    if args.limit:
        pairs = pairs[:args.limit]

    def worker(code_url):
        code, url = code_url
        return code, pz.parse_ru_fields(pz.fetch(url))

    ru_map = {}
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=pz.WORKERS) as ex:
        futures = {ex.submit(worker, cu): cu for cu in pairs}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            code, url = futures[fut]
            try:
                code, fields = fut.result()
                ru_map[code] = fields
            except Exception as e:  # noqa: BLE001
                errors.append((url, str(e)))
            done += 1
            if done % 200 == 0 or done == len(pairs):
                print(f"  {done}/{len(pairs)} (ошибок: {len(errors)})", flush=True)

    print(f"Готово: {len(ru_map)} товаров, ошибок: {len(errors)}", flush=True)
    if not args.limit:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(ru_map, f, ensure_ascii=False, indent=2)
        print(f"Записано в {OUT_PATH} — закоммитьте, чтобы прогон подхватил.",
              flush=True)


if __name__ == "__main__":
    main()
