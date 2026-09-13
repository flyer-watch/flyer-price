from __future__ import annotations
import math
from typing import Optional

def floor_yen(value) -> Optional[int]:
    if value is None:
        return None
    try:
        x=float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x):
        return None
    return math.floor(x)

def tax_included_from_ex_tax(price_ex_tax, tax_rate: float) -> Optional[int]:
    base=floor_yen(price_ex_tax)
    if base is None:
        return None
    return math.floor(base*(1.0+float(tax_rate)))

def normalize_price_pair(price_ex_tax=None, price_in_tax=None):
    return floor_yen(price_ex_tax), floor_yen(price_in_tax)

def infer_tax_rate(price_ex_tax, price_in_tax, allowed=(0.08,0.10)):
    ex=floor_yen(price_ex_tax)
    inc=floor_yen(price_in_tax)
    if ex is None or inc is None:
        return None
    for rate in allowed:
        if tax_included_from_ex_tax(ex, rate)==inc:
            return rate
    return None
