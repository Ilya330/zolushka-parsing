#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрапинг zolushka.com.ua («Попелюшка», движок Horoshop): ID, артикул, назва,
опис (з HTML-розміткою), ціна, наявність, кількість, фото, категорія,
характеристики.

Список товарних URL берём из sitemap (content/export/.../catalog-sitemap.xml):
на страницах категорий сетка товаров подгружается ajax-виджетом
(Disallow'нутым в robots.txt), в статическом HTML её нет — а вот сама
товарная карточка отдаётся сервером целиком, без JS (ID/артикул/цена/
наявність — из микроразметки schema.org, категория — из breadcrumbs).

Антибот у поставщика: без cookie `challenge_passed` сервер вместо страницы
отдаёт крошечный скрипт — busy-wait для вида, затем
`document.cookie = "challenge_passed=" + <захардкоженный хэш>` и reload.
Хэш проверен: не зависит от IP/сессии, но иногда меняется между прогонами —
поэтому не хардкодим его, а снимаем заново и обновляем при обнаружении
непройденного челленджа посреди прогона.

Опт-цена сюда НЕ входит: вход на сайт защищён настоящей reCAPTCHA, её мы не
обходим ни в каком виде. Опт-цены — отдельный ручной инструмент
(fetch_opt_prices.py) с куки сессии, которую пользователь снимает сам после
логина в обычном браузере.
"""

import concurrent.futures
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from xml.etree import ElementTree as ET

BASE = "https://zolushka.com.ua"
SITEMAP_URL = f"{BASE}/content/export/zolushka.com.ua/catalog-sitemap.xml"
UA = "Mozilla/5.0 (compatible; dasmart-parser/1.0; +supplier-catalog-scan)"
WORKERS = int(os.environ.get("ZOLUSHKA_WORKERS", "6"))

_cookie = None
_cookie_lock = threading.Lock()


def _fetch_challenge_hash():
    req = urllib.request.Request(BASE + "/", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    m = re.search(r'defaultHash\s*=\s*"([a-f0-9]+)"', body)
    if not m:
        raise RuntimeError("не нашёл defaultHash — сайт мог поменять антибот-проверку")
    return m.group(1)


def get_cookie(refresh=False):
    global _cookie
    with _cookie_lock:
        if _cookie is None or refresh:
            _cookie = _fetch_challenge_hash()
        return _cookie


def fetch(url, tries=4, extra_headers=None):
    """GET с challenge-кукой; на просроченную куку — обновить и повторить.

    На 429 ждём дольше обычного (см. заметку в README про 51 упавший товар
    на полном прогоне) — этого не было, когда retry был короче.
    """
    last = None
    for i in range(tries):
        cookie = f"challenge_passed={get_cookie()}"
        headers = {"User-Agent": UA}
        if extra_headers:
            headers.update(extra_headers)
        if "Cookie" in (extra_headers or {}):
            # антибот-кука обязана быть свежей — не даём чужой Cookie её затереть
            headers["Cookie"] = f"{cookie}; {extra_headers['Cookie']}"
        else:
            headers["Cookie"] = cookie
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            time.sleep((15 if e.code == 429 else 2) * (i + 1))
            continue
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
            continue
        if len(body) < 2000 and "defaultHash" in body:
            get_cookie(refresh=True)
            continue
        return body
    if last is None:
        last = RuntimeError(f"{url}: антибот-челлендж не пройден за {tries} попыток")
    raise last


def list_product_urls():
    """Товарные URL из sitemap (украинская версия, без /ru/-дублей)."""
    xml = fetch(SITEMAP_URL)
    root = ET.fromstring(xml)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text.strip() for loc in root.findall(".//s:loc", ns)]
    return [u for u in urls if "/ru/" not in u]


def _meta_content(page_html, itemprop):
    m = re.search(rf'itemprop="{itemprop}"\s+content="([^"]*)"', page_html)
    if m:
        return html.unescape(m.group(1))
    # порядок атрибутов у Horoshop не всегда одинаков
    m = re.search(rf'content="([^"]*)"\s+itemprop="{itemprop}"', page_html)
    return html.unescape(m.group(1)) if m else ""


def _extract_category_path(page_html):
    m = re.search(r'<nav class="breadcrumbs".*?</nav>', page_html, re.S)
    if not m:
        return []
    names = re.findall(r'itemprop="name">([^<]*)</span>', m.group(0))
    names = [html.unescape(n).strip() for n in names]
    # первая крошка — "Головна", последняя — сам товар (дублирует h1)
    return names[1:-1]


def _extract_images(page_html):
    hrefs = re.findall(
        r'class="gallery__link j-gallery-zoom[^"]*"\s+data-href="([^"]+)"',
        page_html,
    )
    out = []
    for h in hrefs:
        h = html.unescape(h)
        if h.startswith("/"):
            h = BASE + h
        if h not in out:
            out.append(h)
    return out


def _extract_quantity(page_html):
    m = re.search(r'class="[^"]*j-product-counter[^"]*"[^>]*>', page_html)
    if not m:
        return ""
    tag = m.group(0)
    dm = re.search(r'data-max="(\d+)"', tag)
    return dm.group(1) if dm else ""


def parse_product(page_html, url):
    m = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, re.S)
    name = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""

    desc = ""
    m = re.search(
        r'<div class="product-description[^"]*"[^>]*>\s*'
        r'<div class="text">(.*?)</div>\s*</div>',
        page_html, re.S,
    )
    if m:
        desc = re.sub(r"<script.*?</script>", "", m.group(1), flags=re.S).strip()

    features = {}
    m = re.search(
        r'<table class="product-features__table">(.*?)</table>', page_html, re.S
    )
    if m:
        rows = re.findall(
            r'<th[^>]*product-features__cell--h[^>]*>(.*?)</th>\s*'
            r'<td[^>]*>(.*?)</td>',
            m.group(1), re.S,
        )
        for k, v in rows:
            k = re.sub(r"<[^>]+>", " ", k)
            v = re.sub(r"<[^>]+>", " ", v)
            k = html.unescape(re.sub(r"\s+", " ", k)).strip()
            v = html.unescape(re.sub(r"\s+", " ", v)).strip()
            if k:
                features[k] = v

    m = re.search(r'itemprop="availability"\s+href="[^"]*/(InStock|OutOfStock)"', page_html)
    # нет микроразметки — считаем как отсутствие в наличии (как у dasmart)
    available = m.group(1) == "InStock" if m else False

    return {
        "url": url,
        "id": _meta_content(page_html, "mpn"),
        "vendorCode": _meta_content(page_html, "sku"),
        "name": name,
        "description": desc,
        "characteristics": features,
        "vendor": features.get("Бренд", ""),
        "price": _meta_content(page_html, "price"),
        "currency": _meta_content(page_html, "priceCurrency") or "UAH",
        "available": available,
        "quantity": _extract_quantity(page_html),
        "images": _extract_images(page_html),
        "category_path": _extract_category_path(page_html),
    }


def _scrape_batch(urls, workers):
    products = []
    errors = []
    total = len(urls)

    def worker(url):
        return parse_product(fetch(url), url)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(worker, u): u for u in urls}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            url = futures[fut]
            try:
                products.append(fut.result())
            except Exception as e:  # noqa: BLE001
                errors.append((url, str(e)))
            done += 1
            if done % 200 == 0 or done == total:
                print(f"  {done}/{total} (ошибок: {len(errors)})", flush=True)
    return products, errors


def scrape_all(urls, workers=WORKERS):
    """Разобрать все товарные страницы. Вернуть (products, errors).

    Пул потоков + автоматический медленный последовательный доповтор для
    упавших URL (на полном прогоне 28.09.2026 часть запросов падала по 429
    под конец часового прогона — без этого повтора набор остаётся неполным,
    и раньше это приходилось разгребать вручную).
    """
    products, errors = _scrape_batch(urls, workers)
    if not errors:
        return products, errors

    retry_urls = [u for u, _ in errors]
    print(f"  доповтор {len(retry_urls)} упавших URL медленно, по одному...", flush=True)
    get_cookie(refresh=True)
    still_failed = []
    for i, u in enumerate(retry_urls, 1):
        try:
            products.append(parse_product(fetch(u, tries=5), u))
        except Exception as e:  # noqa: BLE001
            still_failed.append((u, str(e)))
        time.sleep(2)
        if i % 20 == 0 or i == len(retry_urls):
            print(f"    доповтор {i}/{len(retry_urls)}", flush=True)
    return products, still_failed


if __name__ == "__main__":  # быстрая локальная проверка на паре товаров
    urls = list_product_urls()
    print(f"товарных URL: {len(urls)}")
    sample = urls[:3]
    prods, errs = scrape_all(sample, workers=3)
    print(json.dumps(prods, ensure_ascii=False, indent=2))
    print("ошибок:", errs)
