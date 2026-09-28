#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Запись товаров zolushka.com.ua в нашу Google-таблицу `parsing_zolushka`."""

import json
import os

from sheets_util import write_sheet, CELL_LIMIT

TARGET_SHEET_ID = os.environ.get(
    "TARGET_SHEET_ID", "1jTGwSsHWo539yap0SVsgKkWgBW174U5I1bALk7vfqic"
)
WORKSHEET = os.environ.get("ZOLUSHKA_WORKSHEET", "Zolushka")

HEADERS = [
    "ID", "Артикул", "Назва", "Опис", "Характеристики", "Ціна", "Опт ціна",
    "Валюта", "Наявність", "Кількість", "Категорія", "Фото", "URL",
    "Назва (РУ)", "Опис (РУ)", "Характеристики (РУ)", "URL (РУ)",
]


def product_to_row(p):
    desc = p.get("description", "")
    if len(desc) > CELL_LIMIT:
        desc = desc[:CELL_LIMIT]
    chars = json.dumps(p.get("characteristics", {}), ensure_ascii=False)
    if len(chars) > CELL_LIMIT:
        chars = chars[:CELL_LIMIT]

    desc_ru = p.get("description_ru", "")
    if len(desc_ru) > CELL_LIMIT:
        desc_ru = desc_ru[:CELL_LIMIT]
    chars_ru = json.dumps(p.get("characteristics_ru", {}), ensure_ascii=False)
    if len(chars_ru) > CELL_LIMIT:
        chars_ru = chars_ru[:CELL_LIMIT]

    return [
        p.get("id", ""), p.get("vendorCode", ""), p.get("name", ""), desc, chars,
        p.get("price", ""), p.get("opt_price", ""), p.get("currency", ""),
        "так" if p.get("available") else "ні", p.get("quantity", ""),
        " > ".join(p.get("category_path") or []),
        ", ".join(p.get("images") or []),
        p.get("url", ""),
        p.get("name_ru", ""), desc_ru, chars_ru, p.get("ru_url", ""),
    ]


def write_all(gc, products, sheet_id=TARGET_SHEET_ID, title=WORKSHEET):
    sh = gc.open_by_key(sheet_id)
    rows = [product_to_row(p) for p in products]
    write_sheet(sh, title, HEADERS, rows)
    return len(rows)
