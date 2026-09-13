from __future__ import annotations
import re, unicodedata, collections
from rapidfuzz.fuzz import partial_ratio

PUNCT_RE = re.compile(r"[\s（）()\[\]【】「」『』<>〈〉《》:：;；,，。/\\\-ー_・]+")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
NUM_UNIT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(連|mm|cm|ml|l|g|kg|枚|個|コ|袋|本|巻|組|カン|缶|パック|本入|袋入)",
    re.I
)

def nfkc(s):
    return unicodedata.normalize("NFKC", str(s or "")).lower()

def normalize_full(s):
    s=nfkc(s)
    # keep digits and decimal point; remove punctuation except decimal dot
    s=PUNCT_RE.sub("",s)
    s=re.sub(r"(?<!\d)\.(?!\d)","",s)
    return s

def normalize_text_only(s):
    s=normalize_full(s)
    s=NUM_RE.sub("",s)
    return s

def numeric_signatures(s):
    """
    Strong signatures keep both number and nearby unit/suffix:
      3連, 1.6mm, 900ml.
    If no such signature exists, retain standalone numbers so that
    商品1 / 商品2 can still be distinguished in ambiguous sibling groups.
    """
    raw=nfkc(s)
    strong=[]
    for n,u in NUM_UNIT_RE.findall(raw):
        strong.append(f"{n}{u.lower()}")
    if strong:
        return tuple(dict.fromkeys(strong))
    return tuple(dict.fromkeys(NUM_RE.findall(raw)))

def text_coverage(candidate, ocr):
    A=collections.Counter(normalize_text_only(candidate))
    B=collections.Counter(normalize_text_only(ocr))
    den=sum(A.values())
    return 0.0 if not den else 100.0*sum(min(v,B[k]) for k,v in A.items())/den

def full_coverage(candidate, ocr):
    A=collections.Counter(normalize_full(candidate))
    B=collections.Counter(normalize_full(ocr))
    den=sum(A.values())
    return 0.0 if not den else 100.0*sum(min(v,B[k]) for k,v in A.items())/den

def base_score(candidate, ocr):
    a=normalize_full(candidate)
    b=normalize_full(ocr)
    ta=normalize_text_only(candidate)
    tb=normalize_text_only(ocr)
    if not a or not b:
        return 0.0
    ordered_full=float(partial_ratio(a,b))
    ordered_text=float(partial_ratio(ta,tb)) if ta and tb else 0.0
    return (
        0.30*ordered_full +
        0.20*ordered_text +
        0.25*full_coverage(candidate,ocr) +
        0.25*text_coverage(candidate,ocr)
    )

def skeleton(s):
    """Used only to detect dictionary siblings that differ mainly by numbers."""
    return normalize_text_only(s)

def sibling_groups(names):
    groups={}
    for n in names:
        groups.setdefault(skeleton(n),[]).append(n)
    return groups

def signature_support(candidate, ocr):
    c=numeric_signatures(candidate)
    if not c:
        return 1.0

    raw=nfkc(ocr)
    o_full=normalize_full(ocr)
    o_numbers=set(NUM_RE.findall(raw))
    hits=0

    for sig in c:
        # Strong number+unit signatures such as 3連 / 1.6mm / 900ml
        # normally appear as a contiguous normalized phrase. Tesseract may
        # reverse the reading order of a nearby number and suffix in dense
        # flyer layouts (for example "連 3" for "3連"). Accept that
        # local reversal only when the SAME number and SAME unit are adjacent;
        # this keeps the unknown-variant veto intact (4連 never proves 3連).
        if re.search(r"[a-zA-Zぁ-んァ-ヶ一-龥]", sig):
            norm_sig=normalize_full(sig)
            matched=norm_sig in o_full
            if not matched:
                m=re.fullmatch(r"(\d+(?:\.\d+)?)(.+)", norm_sig)
                if m:
                    number,unit=m.groups()
                    matched=(unit+number) in o_full
            if matched:
                hits+=1
        else:
            # Standalone numeric variants must match an exact numeric token.
            # "1" must NOT be considered present merely because the price is 199.
            if sig in o_numbers:
                hits+=1
    return hits/len(c)

def rank_dictionary(ocr_text, names):
    groups=sibling_groups(names)
    rows=[]
    for n in names:
        score=base_score(n,ocr_text)
        sigs=numeric_signatures(n)
        support=signature_support(n,ocr_text)
        siblings=groups.get(skeleton(n),[])
        ambiguous_numeric_group=(
            len(siblings)>1 and
            len({numeric_signatures(x) for x in siblings})>1
        )

        veto=False
        adjustment=0.0

        # Safety rule: any dictionary item that itself contains a meaningful
        # numeric signature must have OCR evidence for that signature.
        # This applies even when there is no numeric sibling currently stored
        # in the dictionary. Otherwise an unseen "4連" could be silently
        # rewritten to the only known "3連".
        if sigs and support<=0:
            veto=True
            adjustment-=40.0
        elif sigs and support>0:
            # Numeric evidence is especially useful inside sibling groups.
            adjustment+=(18.0 if ambiguous_numeric_group else 8.0)*support

        final=max(0.0,min(100.0,score+adjustment))
        rows.append({
            "name":n,
            "score":final,
            "base_score":score,
            "numeric_signatures":list(sigs),
            "signature_support":support,
            "numeric_sibling_group":ambiguous_numeric_group,
            "veto":veto,
        })
    rows.sort(key=lambda x:(x["veto"] is False,x["score"],x["signature_support"]),reverse=True)
    return rows

def resolve_name(ocr_text, names, min_score=50.0, min_margin=8.0):
    ranks=rank_dictionary(ocr_text,names)
    if not ranks:
        return {
            "name":str(ocr_text or "").strip(),
            "status":"ocr_unverified",
            "score":0.0,"margin":0.0,
            "reason":"empty_dictionary"
        }

    viable=[r for r in ranks if not r["veto"]]
    if not viable:
        top=ranks[0]
        return {
            "name":str(ocr_text or "").strip(),
            "status":"ocr_unverified",
            "score":top["score"],"margin":0.0,
            "reason":"numeric_variant_not_evidenced",
            "top_candidates":ranks[:3],
        }

    top=viable[0]
    second=viable[1]["score"] if len(viable)>1 else 0.0
    margin=top["score"]-second

    # If multiple numeric siblings exist and OCR supports none uniquely,
    # do not force a known variant.
    if top["numeric_sibling_group"] and top["signature_support"]<=0:
        return {
            "name":str(ocr_text or "").strip(),
            "status":"ocr_unverified",
            "score":top["score"],"margin":margin,
            "reason":"ambiguous_numeric_sibling",
            "top_candidates":viable[:3],
        }

    if top["score"]>=min_score and margin>=min_margin:
        return {
            "name":top["name"],
            "status":"dictionary_resolved",
            "score":top["score"],"margin":margin,
            "reason":"score_and_margin",
            "top_candidates":viable[:3],
        }

    return {
        "name":str(ocr_text or "").strip(),
        "status":"ocr_unverified",
        "score":top["score"],"margin":margin,
        "reason":"insufficient_score_or_margin",
        "top_candidates":viable[:3],
    }
