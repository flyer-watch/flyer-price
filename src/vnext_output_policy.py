from __future__ import annotations
import re, unicodedata
from typing import Iterable
from price_policy import floor_yen, tax_included_from_ex_tax

def _norm(v)->str:
    return re.sub(r"\s+","",unicodedata.normalize("NFKC",str(v or ""))).lower()

def normalize_output_row(row:dict)->dict|None:
    out=dict(row)
    ex=floor_yen(out.get("price_ex_tax_yen")); inc=floor_yen(out.get("price_in_tax_yen")); rate=out.get("tax_rate")
    if inc is None and ex is not None and rate not in (None,""):
        try: inc=tax_included_from_ex_tax(ex,float(rate))
        except (TypeError,ValueError): inc=None
    if inc is None or inc<=0: return None
    if ex is not None and ex<0: return None
    out["price_ex_tax_yen"]=ex; out["price_in_tax_yen"]=inc
    return out

def apply_output_policy(rows:Iterable[dict])->list[dict]:
    out=[]; seen=set()
    for raw in rows:
        row=normalize_output_row(raw)
        if row is None: continue
        key=(_norm(row.get("store_id")),str(row.get("sale_start") or ""),str(row.get("sale_end") or ""),_norm(row.get("product_name")),_norm(row.get("specification")),row.get("price_in_tax_yen"))
        if key in seen: continue
        seen.add(key); out.append(row)
    return out
