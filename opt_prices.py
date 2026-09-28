#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Опт-цены — отдельный снимок {vendorCode: цена}, обновляемый вручную
инструментом fetch_opt_prices.py (там же — почему это не часть основного
ежедневного прогона: вход защищён reCAPTCHA, автологин мы не делаем).
"""

import json
import os

OPT_PRICES_PATH = os.environ.get(
    "OPT_PRICES_PATH", os.path.join(os.path.dirname(__file__), "opt_prices.json")
)


def load(path=OPT_PRICES_PATH):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge(products, opt_map):
    """Проставить p["opt_price"] по vendorCode. Вернуть число сопоставленных."""
    matched = 0
    for p in products:
        v = opt_map.get(p.get("vendorCode", ""))
        if v:
            p["opt_price"] = v
            matched += 1
    return matched
