from __future__ import annotations
import re
import cv2, numpy as np, pytesseract
from product_dictionary_matcher import dictionary_score, normalize_japanese
from rapidfuzz.fuzz import ratio


def detect_bullet_columns(img, y_min_ratio=0.28, y_max_ratio=0.86):
    """Detect repeated filled bullet markers used by flyer product lists.

    The detector does not know product coordinates/names. It looks for small,
    near-circular dark components whose x positions repeat vertically.
    """
    H,W=img.shape[:2]
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    mask=(gray<80).astype(np.uint8)*255
    n,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
    pts=[]
    for i in range(1,n):
        x,y,w,h,area=map(int,stats[i,:5])
        fill=area/(w*h) if w*h else 0.0
        if not (int(H*y_min_ratio)<=y<=int(H*y_max_ratio)):
            continue
        if 5<=w<=11 and 5<=h<=11 and 28<=area<=90 and fill>=0.65:
            pts.append({'x':x,'y':y,'w':w,'h':h,'cx':x+w/2,'cy':y+h/2,'fill':fill})

    clusters=[]
    for p in sorted(pts,key=lambda q:q['cx']):
        hit=None
        for c in clusters:
            if abs(p['cx']-c['cx'])<=5:
                hit=c; break
        if hit is None:
            clusters.append({'cx':p['cx'],'points':[p]})
        else:
            hit['points'].append(p)
            hit['cx']=sum(q['cx'] for q in hit['points'])/len(hit['points'])
    clusters=[c for c in clusters if len(c['points'])>=3]
    for c in clusters:
        c['points']=sorted(c['points'],key=lambda q:q['y'])
    return sorted(clusters,key=lambda c:c['cx'])


def _safe_ocr(image, psm=6):
    try:
        return pytesseract.image_to_string(image,lang='jpn+eng',config=f'--psm {psm}',timeout=30).strip()
    except Exception:
        return ''


def _ocr_local_variants(crop, profile="base"):
    """Return a small, runtime-bounded set of OCR views.

    ``base`` deliberately keeps the old one-call behavior. ``difficult`` is
    reserved for long-gap/last rows where product images or wrapping make the
    base OCR unreliable. ``column`` uses two grayscale segmentation modes.
    """
    if crop is None or crop.size==0:
        return []
    scale=3.0 if profile=="column" else 3.5
    up=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
    gray=cv2.cvtColor(up,cv2.COLOR_BGR2GRAY)
    otsu=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    jobs=[]
    if profile=="base":
        jobs=[("otsu_p6",otsu,6)]
    elif profile=="difficult":
        jobs=[("gray_p6",gray,6),("otsu_p6",otsu,6),("gray_p11",gray,11)]
    elif profile=="column":
        jobs=[("gray_p6",gray,6),("gray_p11",gray,11)]
    else:
        jobs=[("otsu_p6",otsu,6)]
    out=[]
    for label,im,psm in jobs:
        text=_safe_ocr(im,psm)
        if text:
            out.append((label,text))
    seen=set(); uniq=[]
    for label,text in out:
        key=re.sub(r"\s+"," ",text).strip()
        if key and key not in seen:
            seen.add(key); uniq.append((label,text))
    return uniq


def _normalize_records(candidate_names, candidate_records=None):
    if candidate_records is None:
        return [{'name':str(n),'specification':''} for n in candidate_names]
    out=[]
    for r in candidate_records:
        if isinstance(r,str):
            out.append({'name':r,'specification':''})
        else:
            name=str(r.get('name') or r.get('product_name') or '')
            if not name:
                continue
            out.append({'name':name,'specification':str(r.get('specification') or r.get('spec') or '')})
    return out


def _spec_key(spec):
    # Keep Japanese semantic words; pure units/quantities are intentionally
    # weak because many products share them (100g当り, 1コ, etc.).
    return normalize_japanese(spec)


def _record_scorer(records):
    spec_counts={}
    for r in records:
        k=_spec_key(r.get('specification',''))
        if k:
            spec_counts[k]=spec_counts.get(k,0)+1

    def score(r,text):
        name_score=float(dictionary_score(r['name'],text))
        spec=str(r.get('specification') or '')
        sk=_spec_key(spec)
        spec_score=float(dictionary_score(spec,text)) if spec else 0.0
        # Specification can rescue a degraded product-name OCR only when it is
        # semantically distinctive in this candidate set. It can never create
        # a match from specification alone: at least modest name evidence is
        # required. This protects common quantity strings from forcing names.
        distinctive=bool(sk and len(sk)>=3 and spec_counts.get(sk,0)==1)
        fused=name_score
        if distinctive and name_score>=25.0 and spec_score>0:
            fused=max(fused,0.58*name_score+0.42*spec_score)
        return {
            'score':min(100.0,fused),
            'name_score':name_score,
            'spec_score':spec_score,
            'spec_distinctive':distinctive,
        }
    return score



def _similar_name_margin(records, scores, target, similarity_threshold=58.0):
    """Margin against near-name siblings only.

    Broad OCR regions legitimately contain many unrelated products, so global
    rank is not meaningful there. Near-duplicate dictionary entries *are*
    meaningful: a candidate must beat variants such as 小/大, むね/もも or
    バニラ/抹茶 before it can be accepted.
    """
    t=normalize_japanese(target)
    own=float(scores[target]['score'])
    siblings=[]
    for r in records:
        n=r['name']
        if n==target:
            continue
        nn=normalize_japanese(n)
        if t and nn and ratio(t,nn)>=similarity_threshold:
            siblings.append(float(scores[n]['score']))
    if not siblings:
        return 100.0
    return own-max(siblings)

def _rank_records(records, scorer, text):
    rows=[]
    for r in records:
        s=scorer(r,text)
        rows.append({'name':r['name'],**s})
    rows.sort(key=lambda z:z['score'],reverse=True)
    return rows


def _row_bounds(points, i, span, H):
    """Infer a text row window from bullets without product-specific coords."""
    j=min(len(points)-1,i+span-1)
    y1=max(0,int(points[i]['y']-8))
    if j+1<len(points):
        nxt=int(points[j+1]['y'])
        cur=int(points[j]['y'])
        gap=max(1,nxt-cur)
        # Stop before the next bullet instead of including it. The old +3px
        # rule contaminated long-gap rows with the following product/image.
        y2=max(y1+18,nxt-max(3,int(round(gap*0.10))))
    else:
        gaps=[points[k+1]['y']-points[k]['y'] for k in range(len(points)-1)]
        med=float(np.median(gaps)) if gaps else 40.0
        y2=min(H,int(points[j]['y']+max(65.0,1.7*med)))
    if y2-y1<18:
        y2=min(H,y1+24)
    return y1,min(H,y2)


def recover_uniform_children(img, candidate_names, min_score=52.0, min_margin=5.0,
                             candidate_records=None, column_score=72.0):
    """Recover known child products under a common-price parent.

    Evidence is fused from:
      1) bullet-local row windows,
      2) two-row windows for wrapped maker/product text,
      3) broad bullet-column OCR.

    Candidate metadata may contain ``specification``. A distinctive spec is
    allowed to support a degraded name OCR only when there is already product-
    name evidence; common quantity strings never resolve a product by itself.
    """
    H,W=img.shape[:2]
    records=_normalize_records(candidate_names,candidate_records)
    names=[r['name'] for r in records]
    scorer=_record_scorer(records)
    cols=detect_bullet_columns(img)
    windows=[]

    # Local row evidence.
    for ci,c in enumerate(cols):
        pts=c['points']
        x1=max(0,int(c['cx']-8))
        x2=int(cols[ci+1]['cx']-8) if ci+1<len(cols) else W
        for i,p in enumerate(pts):
            for span in (1,2):
                y1,y2=_row_bounds(pts,i,span,H)
                # Extra OCR only on a single-row difficult region. Two-row
                # windows stay on the cheap base path.
                difficult=(span==1 and (y2-y1>=55 or i==len(pts)-1))
                profile='difficult' if difficult else 'base'
                for variant,text in _ocr_local_variants(img[y1:y2,x1:x2],profile=profile):
                    ranks=_rank_records(records,scorer,text)
                    if not ranks:
                        continue
                    top=ranks[0]
                    second=ranks[1]['score'] if len(ranks)>1 else 0.0
                    windows.append({
                        'kind':'local','column':ci,'row':i,'span':span,
                        'variant':variant,'bbox':[x1,y1,x2,y2],
                        'text':text,'top_name':top['name'],'top_score':top['score'],
                        'top_name_score':top['name_score'],'top_spec_score':top['spec_score'],
                        'margin':top['score']-second,
                        'scores':{z['name']:z for z in ranks},
                    })

    # Broad per-column OCR catches items whose tiny bullet row is too short or
    # whose bullet itself is partially lost. This remains layout-derived: x/y
    # bounds come only from detected bullet columns.
    column_windows=[]
    for ci,c in enumerate(cols):
        pts=c['points']
        x1=max(0,int(c['cx']-8))
        x2=int(cols[ci+1]['cx']-8) if ci+1<len(cols) else W
        gaps=[pts[k+1]['y']-pts[k]['y'] for k in range(len(pts)-1)]
        med=float(np.median(gaps)) if gaps else 40.0
        y1=max(0,int(pts[0]['y']-35))
        y2=min(H,int(pts[-1]['y']+max(75.0,1.9*med)))
        for variant,text in _ocr_local_variants(img[y1:y2,x1:x2],profile='column'):
            ranks=_rank_records(records,scorer,text)
            column_windows.append({
                'kind':'column','column':ci,'variant':variant,
                'bbox':[x1,y1,x2,y2],'text':text,
                'scores':{z['name']:z for z in ranks},
            })

    # Resolution policy. Local rank+margin is strongest. Broad-column evidence
    # may independently prove multiple products, therefore it is evaluated per
    # candidate rather than forcing only one top candidate per column.
    best={}
    evidence_by_name={n:[] for n in names}
    for w in windows:
        if w['top_score']>=min_score and w['margin']>=min_margin:
            n=w['top_name']
            e={k:v for k,v in w.items() if k!='scores'}
            evidence_by_name[n].append(e)
        # A two-row OCR window intentionally contains up to two products.
        # Do not throw away the second product merely because another genuine
        # product ranks first; require very strong candidate-specific evidence.
        if w.get('span')==2:
            for n,s in w['scores'].items():
                sibling_margin=_similar_name_margin(records,w['scores'],n)
                if s['score']>=82.0 and sibling_margin>=5.0:
                    evidence_by_name[n].append({
                        'kind':'local_multi','column':w['column'],'row':w['row'],
                        'span':w['span'],'variant':w['variant'],'bbox':w['bbox'],
                        'text':w['text'],'top_name':n,'top_score':s['score'],
                        'top_name_score':s['name_score'],'top_spec_score':s['spec_score'],
                        'margin':sibling_margin,
                    })

    # Keep medium column evidence temporarily so that two independent OCR
    # segmentations can form a consensus without globally lowering thresholds.
    medium_column={n:[] for n in names}
    for w in column_windows:
        for n,s in w['scores'].items():
            sibling_margin=_similar_name_margin(records,w['scores'],n)
            e={
                'kind':'column','column':w['column'],'variant':w['variant'],
                'bbox':w['bbox'],'text':w['text'],
                'top_name':n,'top_score':s['score'],
                'top_name_score':s['name_score'],'top_spec_score':s['spec_score'],
                'spec_distinctive':s['spec_distinctive'],'margin':sibling_margin,
            }
            if s['score']>=column_score and sibling_margin>=5.0:
                evidence_by_name[n].append(e)
            elif (s['name_score']>=45.0 and s['spec_distinctive'] and s['spec_score']>=70.0 and s['score']>=58.0 and sibling_margin>=5.0):
                # Distinctive specification rescue: product name still needs
                # substantial OCR support; specification cannot resolve alone.
                e['kind']='column_name_spec'
                evidence_by_name[n].append(e)
            elif s['score']>=60.0 and sibling_margin>=5.0:
                medium_column[n].append(e)

    for n,evs in medium_column.items():
        by_col={}
        for e in evs:
            by_col.setdefault(e['column'],[]).append(e)
        for ci,items in by_col.items():
            variants={e['variant'] for e in items}
            if len(variants)>=2:
                best_consensus=max(items,key=lambda e:e['top_score']).copy()
                best_consensus['kind']='column_consensus'
                best_consensus['consensus_variants']=sorted(variants)
                evidence_by_name[n].append(best_consensus)

    for n,evs in evidence_by_name.items():
        if not evs:
            continue
        evs.sort(key=lambda e:(e['top_score'], e.get('margin') or 0.0),reverse=True)
        best[n]=evs[0]

    return {
        'bullet_columns':cols,
        'windows':windows,
        'column_windows':column_windows,
        'resolved':best,
        'evidence_by_name':evidence_by_name,
    }
