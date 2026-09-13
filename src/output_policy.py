from __future__ import annotations
import math, re, unicodedata
from typing import Iterable

from price_policy import floor_yen, tax_included_from_ex_tax

HOUSEHOLD_CATEGORIES = {
    "日用品", "日用雑貨", "生活用品", "生活雑貨", "家庭用品", "ホーム用品",
    "洗剤", "紙製品", "衛生用品", "掃除用品", "キッチン用品",
}


def _norm(v) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(v or ""))).lower()


def is_household_good(row: dict) -> bool:
    """Category-first household exclusion.

    Product-name heuristics are deliberately conservative and only cover clear
    household classes. This prevents a missing/weak category from silently
    exposing obvious paper/cleaning/toiletry products while avoiding broad
    10%-tax based filtering (which would wrongly remove non-household items).
    """
    cat=_norm(row.get("category"))
    if cat in {_norm(x) for x in HOUSEHOLD_CATEGORIES}:
        return True

    name=_norm(row.get("product_name"))
    clear_markers=(
        "キッチンペーパー", "トイレットペーパー", "ティッシュペーパー",
        "ボックスティッシュ", "洗濯洗剤", "食器用洗剤", "台所用洗剤",
        "衣料用洗剤", "柔軟剤", "漂白剤", "住居用洗剤", "ハミガキ",
        "歯磨き", "歯ブラシ", "シャンプー", "コンディショナー",
        "ボディソープ", "ハンドソープ",
    )
    if any(m in name for m in clear_markers):
        return True
    # Major laundry/dishwashing brand wording often omits the generic "洗剤".
    if any(m in name for m in ("アリエール", "ボールド", "トップクリアリキッド", "ジョイ除菌")):
        return True
    return False


def normalize_output_row(row: dict) -> dict | None:
    out=dict(row)
    ex=floor_yen(out.get("price_ex_tax_yen"))
    inc=floor_yen(out.get("price_in_tax_yen"))
    rate=out.get("tax_rate")

    # A real yen price is mandatory. Percentage-only/no-price panels have no
    # numeric yen price and are therefore excluded here even if upstream OCR
    # found other numeric text.
    if inc is None and ex is not None and rate not in (None, ""):
        try:
            inc=tax_included_from_ex_tax(ex,float(rate))
        except (TypeError,ValueError):
            inc=None
    if inc is None or inc <= 0:
        return None
    if ex is not None and ex < 0:
        return None

    out["price_ex_tax_yen"]=ex
    out["price_in_tax_yen"]=inc
    if is_household_good(out):
        return None
    return out


def dedupe_products(rows: Iterable[dict]) -> list[dict]:
    out=[]; seen=set()
    for raw in rows:
        row=normalize_output_row(raw)
        if row is None:
            continue
        key=(
            _norm(row.get("store_id")),
            str(row.get("sale_start") or ""),
            str(row.get("sale_end") or ""),
            _norm(row.get("product_name")),
            _norm(row.get("specification")),
            row.get("price_in_tax_yen"),
        )
        if key in seen:
            continue
        seen.add(key); out.append(row)
    return out


def apply_output_policy(rows: Iterable[dict]) -> list[dict]:
    return dedupe_products(rows)
