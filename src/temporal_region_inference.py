from __future__ import annotations
import cv2, numpy as np, pytesseract, re
from datetime import date

DATE_TOKEN_RE=re.compile(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)")

def detect_explicit_date_tokens(img,year=2026):
    data=pytesseract.image_to_data(
        img,lang="jpn+eng",config="--psm 11",
        output_type=pytesseract.Output.DATAFRAME,timeout=40
    )
    data=data[(data.conf>=25)&data.text.notna()]
    out=[]
    for _,r in data.iterrows():
        txt=str(r.text).strip()
        m=DATE_TOKEN_RE.search(txt)
        if not m:
            continue
        mo,da=map(int,m.groups())
        try:
            dt=date(year,mo,da).isoformat()
        except ValueError:
            continue
        out.append({
            "date":dt,"text":txt,"confidence":float(r.conf)/100.0,
            "bbox":[int(r.left),int(r.top),int(r.left+r.width),int(r.top+r.height)],
            "cx":float(r.left+r.width/2),"cy":float(r.top+r.height/2)
        })
    return out

def detect_long_separators(img):
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,50,150)
    H,W=gray.shape
    lines=cv2.HoughLinesP(
        edges,1,np.pi/180,threshold=max(40,int(min(H,W)*.05)),
        minLineLength=int(min(H,W)*.35),maxLineGap=12
    )
    vert=[];horiz=[]
    if lines is not None:
        for x1,y1,x2,y2 in lines[:,0]:
            if abs(x2-x1)<=4 and abs(y2-y1)>=H*.35:
                vert.append((int((x1+x2)/2),abs(y2-y1)))
            if abs(y2-y1)<=4 and abs(x2-x1)>=W*.35:
                horiz.append((int((y1+y2)/2),abs(x2-x1)))
    return vert,horiz

def infer_comodi_nested_regions(img,page_start,page_end):
    """
    Comodi-like page:
    - page period is the default scope.
    - explicit M/D labels create single-day overrides.
    - a strong full-height vertical separator divides day panels from
      the default-period dense catalog.
    """
    H,W=img.shape[:2]
    tokens=detect_explicit_date_tokens(img)
    vert,horiz=detect_long_separators(img)

    # Prefer a vertical separator around 30-55% of width.
    candidates=[x for x,length in vert if W*.25<=x<=W*.60]
    if candidates:
        # mode-ish/median suppresses double-edge line detection
        split_x=int(np.median(candidates))
    else:
        split_x=int(W*.40)

    left_dates=sorted(
        [t for t in tokens if t["cx"]<split_x],
        key=lambda t:t["cy"]
    )
    # Dedup same date/nearby.
    ded=[]
    for t in left_dates:
        if ded and t["date"]==ded[-1]["date"] and abs(t["cy"]-ded[-1]["cy"])<30:
            continue
        ded.append(t)
    left_dates=ded

    regions=[]
    if left_dates:
        ys=[0]
        for a,b in zip(left_dates[:-1],left_dates[1:]):
            # Prefer a real long horizontal separator between adjacent
            # explicit date panels. Midpoint is only a fallback.
            sep_candidates=[(y,length) for y,length in horiz if a["cy"]<y<b["cy"]]
            if sep_candidates:
                # Longest line first; if several are the same border's
                # double edges, their median is stable.
                max_len=max(length for y,length in sep_candidates)
                strong=[y for y,length in sep_candidates if length>=max_len*.90]
                boundary=int(np.median(strong))
            else:
                boundary=int((a["cy"]+b["cy"])/2)
            ys.append(boundary)
        ys.append(H)
        for i,t in enumerate(left_dates):
            regions.append({
                "region_id":f"day_{i+1}",
                "x1":0,"y1":ys[i],"x2":split_x,"y2":ys[i+1],
                "sale_start":t["date"],"sale_end":t["date"],
                "date_source":"explicit_ocr"
            })
    else:
        regions.append({
            "region_id":"left_default","x1":0,"y1":0,"x2":split_x,"y2":H,
            "sale_start":page_start,"sale_end":page_end,
            "date_source":"page_default"
        })

    regions.append({
        "region_id":"right_default","x1":split_x,"y1":0,"x2":W,"y2":H,
        "sale_start":page_start,"sale_end":page_end,
        "date_source":"page_default"
    })
    return {"split_x":split_x,"date_tokens":tokens,"regions":regions}

def assign_point_scope(x,y,regions):
    hits=[r for r in regions if r["x1"]<=x<r["x2"] and r["y1"]<=y<r["y2"]]
    if not hits:
        return None
    # explicit date region wins over default if overlapping
    hits.sort(key=lambda r:0 if r["date_source"]=="explicit_ocr" else 1)
    return hits[0]
