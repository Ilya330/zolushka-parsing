#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Общая запись листа в Google-таблицу (полная перезапись, чанками)."""

CELL_LIMIT = 50000   # лимит символов в ячейке Google Sheets
CHUNK = 400          # строк за один запрос update


def write_sheet(sh, title, headers, rows):
    """Полностью перезаписать лист `title` в открытой таблице `sh`."""
    try:
        ws = sh.worksheet(title)
    except Exception:  # noqa: BLE001  WorksheetNotFound
        ws = sh.add_worksheet(title=title, rows=len(rows) + 10, cols=len(headers))
    ws.clear()
    ws.resize(rows=max(len(rows) + 1, 2), cols=len(headers))

    table = [headers] + rows
    r = 1
    for i in range(0, len(table), CHUNK):
        chunk = table[i:i + CHUNK]
        ws.update(range_name=f"A{r}", values=chunk, value_input_option="RAW")
        r += len(chunk)
    try:
        ws.freeze(rows=1)
    except Exception:  # noqa: BLE001
        pass
