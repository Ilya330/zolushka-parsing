#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка YML/XML фида (формат — как у dasmart-parser, его принимают Prom.ua/
Rozetka) из разобранных товаров zolushka.com.ua.

У поставщика нет числовых ID категорий (только текстовые breadcrumbs на
странице товара) — строим свои синтетические ID по уникальным путям
категорий и проставляем родителя по префиксу пути.
"""

import os
from datetime import datetime
from xml.sax.saxutils import escape

SHOP_NAME = os.environ.get("SHOP_NAME", "zolushka")
SHOP_COMPANY = os.environ.get("SHOP_COMPANY", "Попелюшка")
SHOP_URL = os.environ.get("SHOP_URL", "https://zolushka.com.ua")
CURRENCY = os.environ.get("CURRENCY", "UAH")


def _esc(s):
    return escape(str(s), {'"': "&quot;"})


def _cdata(s):
    return "<![CDATA[" + str(s).replace("]]>", "]]&gt;") + "]]>"


def assign_category_ids(products):
    """Вернуть (categories, products с проставленным categoryId).

    categories: [{"id","parent","name"}]. ID — по порядку появления
    уникального пути (1, 2, 3…), родитель — ID пути на уровень выше.
    """
    path_id = {}
    categories = []

    def ensure(path):
        if not path:
            return None
        if path in path_id:
            return path_id[path]
        parent_id = ensure(path[:-1])
        new_id = str(len(categories) + 1)
        path_id[path] = new_id
        categories.append({"id": new_id, "parent": parent_id or "", "name": path[-1]})
        return new_id

    for p in products:
        cat_id = ensure(tuple(p.get("category_path") or []))
        p["categoryId"] = cat_id or ""

    return categories, products


def build_xml(categories, products):
    out = ['<?xml version="1.0" encoding="UTF-8"?>']
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    out.append(f'<yml_catalog date="{date}">')
    out.append("<shop>")
    out.append(f"<name>{_esc(SHOP_NAME)}</name>")
    out.append(f"<company>{_esc(SHOP_COMPANY)}</company>")
    out.append(f"<url>{_esc(SHOP_URL)}</url>")
    out.append(f'<currencies><currency id="{CURRENCY}" rate="1"/></currencies>')

    out.append("<categories>")
    for c in categories:
        parent = f' parentId="{_esc(c["parent"])}"' if c.get("parent") else ""
        out.append(
            f'<category id="{_esc(c["id"])}"{parent}>{_esc(c["name"])}</category>'
        )
    out.append("</categories>")

    out.append("<offers>")
    for p in products:
        available = "true" if p.get("available") else "false"
        out.append(f'<offer id="{_esc(p.get("id", ""))}" available="{available}">')

        out.append(f"<url>{_esc(p['url'])}</url>")
        if p.get("price") not in ("", None):
            out.append(f"<price>{_esc(p['price'])}</price>")
        if p.get("opt_price"):
            out.append(f"<vendorprice>{_esc(p['opt_price'])}</vendorprice>")
        out.append(f"<currencyId>{_esc(p.get('currency') or CURRENCY)}</currencyId>")
        if p.get("categoryId"):
            out.append(f"<categoryId>{_esc(p['categoryId'])}</categoryId>")
        for u in p.get("images", []):
            out.append(f"<picture>{_esc(u)}</picture>")
        if p.get("vendor"):
            out.append(f"<vendor>{_esc(p['vendor'])}</vendor>")
        if p.get("vendorCode"):
            out.append(f"<vendorCode>{_esc(p['vendorCode'])}</vendorCode>")
        if p.get("name"):
            out.append(f"<name>{_cdata(p['name'])}</name>")
        if p.get("description"):
            out.append(f"<description>{_cdata(p['description'])}</description>")
        if p.get("quantity") not in ("", None):
            out.append(f"<quantity_in_stock>{_esc(p['quantity'])}</quantity_in_stock>")
        for pn, pv in p.get("characteristics", {}).items():
            out.append(f'<param name="{_esc(pn)}">{_esc(pv)}</param>')
        out.append("</offer>")

    out.append("</offers>")
    out.append("</shop>")
    out.append("</yml_catalog>")
    return "\n".join(out)


def write_feed(products, path):
    """Проставить categoryId и записать фид. Вернуть (path, categories)."""
    categories, products = assign_category_ids(products)
    xml = build_xml(categories, products)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    return path, categories
