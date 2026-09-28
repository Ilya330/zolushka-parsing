#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Русскоязычные назва/опис/характеристики — отдельный снимок {vendorCode: {...}},
обновляемый реже основного прогона (fetch_ru_content.py): контент почти не
меняется, ежедневно его пересобирать незачем — это удваивало бы время
основного прогона без пользы.
"""

import json
import os

RU_CONTENT_PATH = os.environ.get(
    "RU_CONTENT_PATH", os.path.join(os.path.dirname(__file__), "ru_content.json")
)


def load(path=RU_CONTENT_PATH):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge(products, ru_map):
    """Проставить p["name_ru"]/["description_ru"]/["characteristics_ru"]."""
    matched = 0
    for p in products:
        r = ru_map.get(p.get("vendorCode", ""))
        if r:
            p["name_ru"] = r.get("name_ru", "")
            p["description_ru"] = r.get("description_ru", "")
            p["characteristics_ru"] = r.get("characteristics_ru", {})
            matched += 1
    return matched
