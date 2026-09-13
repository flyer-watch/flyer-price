from __future__ import annotations
import re, collections
from rapidfuzz.fuzz import partial_ratio

def normalize_japanese(s):
    s=str(s or "").replace("／","/").replace("　","")
    s=re.sub(r"\s+","",s)
    return re.sub(r"[（）()\[\]【】「」『』<>〈〉《》:：;；,，.。/\\\-ー_・0-9a-zA-Z]+","",s)

def character_coverage(name,text):
    a=collections.Counter(normalize_japanese(name))
    b=collections.Counter(normalize_japanese(text))
    den=sum(a.values())
    return 0.0 if den==0 else 100.0*sum(min(v,b[k]) for k,v in a.items())/den

def dictionary_score(name,text):
    a=normalize_japanese(name); b=normalize_japanese(text)
    if not a or not b:
        return 0.0
    ordered=float(partial_ratio(a,b))
    coverage=character_coverage(name,text)
    return 0.35*ordered+0.65*coverage

def match_product_dictionary(text,names):
    ranks=sorted(
        ({"name":n,"score":dictionary_score(n,text),
          "coverage":character_coverage(n,text),
          "partial":float(partial_ratio(normalize_japanese(n),normalize_japanese(text))) if normalize_japanese(text) else 0.0}
         for n in names),
        key=lambda x:x["score"], reverse=True
    )
    return ranks
