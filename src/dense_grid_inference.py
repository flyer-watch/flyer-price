from __future__ import annotations
import numpy as np, cv2, pytesseract, re

def cluster_price_rows(anchors,H):
    pts=[]
    for a in anchors:
        b=a["bbox"];pts.append({**a,"cx":(b[0]+b[2])/2,"cy":(b[1]+b[3])/2})
    rows=[]
    tol=max(18,H*.06)
    for p in sorted(pts,key=lambda z:(z["cy"],z["cx"])):
        for row in rows:
            med=float(np.median([q["cy"] for q in row]))
            if abs(p["cy"]-med)<=tol:
                row.append(p);break
        else:
            rows.append([p])
    for row in rows:row.sort(key=lambda z:z["cx"])
    rows.sort(key=lambda r:float(np.median([q["cy"] for q in r])))
    return rows

def infer_dense_cells(img,anchors,header_fraction=.11):
    """
    Infer dense flyer cells from price anchors plus actual grid separators.

    Important: flyer prices are usually right-aligned inside a cell, so
    midpoints between price centers are biased and can cut product names.
    Real vertical/horizontal rules are preferred whenever they exist.
    """
    H,W=img.shape[:2]
    rows=cluster_price_rows(anchors,H)
    row_y=[float(np.median([q["cy"] for q in r])) for r in rows]

    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,50,150)
    lines=cv2.HoughLinesP(
        edges,1,np.pi/180,threshold=max(28,int(min(H,W)*.035)),
        minLineLength=max(30,int(min(H,W)*.10)),maxLineGap=12
    )

    sep_y=[]
    sep_x=[]
    if lines is not None:
        for x1,y1,x2,y2 in lines[:,0]:
            length=((x2-x1)**2+(y2-y1)**2)**.5
            if abs(y2-y1)<=3 and abs(x2-x1)>=W*.20:
                sep_y.append((int((y1+y2)/2),float(length)))
            if abs(x2-x1)<=3 and abs(y2-y1)>=H*.10:
                sep_x.append((int((x1+x2)/2),float(length)))

    def cluster_lines(items,tol=5):
        groups=[]
        for pos,length in sorted(items):
            if not groups or abs(pos-np.median([x[0] for x in groups[-1]]))>tol:
                groups.append([(pos,length)])
            else:
                groups[-1].append((pos,length))
        return [
            (int(round(np.median([x[0] for x in g]))),max(x[1] for x in g))
            for g in groups
        ]

    sep_y=cluster_lines(sep_y,5)
    sep_x=cluster_lines(sep_x,5)

    # Detect a saturated top banner and start product cells below it.
    # If no banner is present, retain the caller's header_fraction fallback.
    top_bound=int(H*header_fraction)
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
    satmask=cv2.inRange(hsv[:,:,1],70,255)
    cnts,_=cv2.findContours(satmask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    header_bottoms=[]
    for c in cnts:
        x,y,w,h=cv2.boundingRect(c)
        fill=float((satmask[y:y+h,x:x+w]>0).mean()) if w*h else 0.0
        if y<=H*.15 and w>=W*.28 and h>=max(22,H*.035) and h<=H*.20 and fill>=.40:
            header_bottoms.append(y+h)
    if header_bottoms:
        top_bound=max(top_bound,min(max(header_bottoms)+4,int(H*.25)))

    # Horizontal row bounds: prefer actual long rules between price rows.
    ybounds=[top_bound]
    for a,b in zip(row_y[:-1],row_y[1:]):
        candidates=[(y,length) for y,length in sep_y if a<y<b]
        if candidates:
            target=a+(b-a)*.20
            max_len=max(length for y,length in candidates)
            strong=[(y,length) for y,length in candidates if length>=max_len*.60]
            boundary=min(strong,key=lambda t:abs(t[0]-target))[0]
        else:
            boundary=int(a+(b-a)*.20)
        ybounds.append(int(boundary))
    ybounds.append(H)

    cells=[]
    for ri,row in enumerate(rows):
        xs=[q["cx"] for q in row]
        xbounds=[0]
        for a,b in zip(xs[:-1],xs[1:]):
            candidates=[(x,length) for x,length in sep_x if a<x<b]
            if candidates:
                # Repeated grid rules are longer/stronger than character strokes.
                max_len=max(length for x,length in candidates)
                strong=[(x,length) for x,length in candidates if length>=max_len*.60]
                # If more than one remains, the true divider tends to be the
                # strongest line; ties use the candidate nearest the midpoint.
                mid=(a+b)/2
                strong.sort(key=lambda t:(-t[1],abs(t[0]-mid)))
                boundary=strong[0][0]
            else:
                boundary=int((a+b)/2)
            xbounds.append(int(boundary))
        xbounds.append(W)

        # Ensure monotonic unique bounds. Bad Hough duplicates fall back locally.
        for i in range(1,len(xbounds)-1):
            if xbounds[i]<=xbounds[i-1]+5 or xbounds[i]>=xbounds[i+1]-5:
                xbounds[i]=int((xs[i-1]+xs[i])/2)

        for ci,q in enumerate(row):
            cells.append({
                "row":ri,"col":ci,"price":q["value"],
                "anchor_bbox":q["bbox"],
                "x1":xbounds[ci],"y1":ybounds[ri],
                "x2":xbounds[ci+1],"y2":ybounds[ri+1]
            })
    return cells

def full_image_tokens(img):
    data=pytesseract.image_to_data(
        img,lang="jpn+eng",config="--psm 11",
        output_type=pytesseract.Output.DATAFRAME,timeout=45
    )
    data=data[(data.conf>=10)&data.text.notna()&(data.text.astype(str).str.strip()!="")].copy()
    data["cx"]=data["left"]+data["width"]/2
    data["cy"]=data["top"]+data["height"]/2
    return data

def associate_name_near_anchor(cell,tokens):
    # Main product name is normally above the price and within the inferred cell.
    b=cell["anchor_bbox"];ay=(b[1]+b[3])/2
    sub=tokens[
        (tokens.cx>=cell["x1"])&(tokens.cx<cell["x2"])&
        (tokens.cy>=cell["y1"])&(tokens.cy<ay-5)
    ].sort_values(["top","left"])
    # Prefer strings containing Japanese/letters and suppress price/spec-only lines.
    parts=[]
    for txt in sub.text.astype(str):
        t=txt.strip()
        if not t:continue
        if re.fullmatch(r"[\d\s.,/%+×xX\-~〜～円]+",t):continue
        if re.search(r"[一-龥ぁ-んァ-ヶA-Za-z]",t):
            parts.append(t)
    return " ".join(parts[:8])


def recover_dense_names(img,cells,dictionary,min_score=50,min_margin=8):
    """
    Dense-grid name recovery using the shared numeric-aware resolver.
    Numeric siblings (3連/4連, 1.4mm/1.6mm, etc.) are never collapsed
    unless the OCR contains evidence for the specific numeric variant.
    Unknown variants remain ocr_unverified.
    """
    from name_resolution import resolve_name

    tokens=full_image_tokens(img)
    results=[]
    H,W=img.shape[:2]

    for cell in cells:
        text=associate_name_near_anchor(cell,tokens)
        candidates=[]

        base=resolve_name(text,dictionary,min_score=min_score,min_margin=min_margin)
        candidates.append({
            "resolution":base,"text":text,"stage":"full_image"
        })

        # Weak, ambiguous, or unverified cells receive targeted local OCR.
        if base["status"]!="dictionary_resolved" or base["score"]<78:
            x1=max(0,int(cell["x1"]));y1=max(0,int(cell["y1"]))
            x2=min(W,int(cell["x2"]));y2=min(H,int(cell["y2"]))
            crop=img[y1:y2,x1:x2]

            if crop.size:
                for scale in (3,4):
                    up=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
                    gray=cv2.cvtColor(up,cv2.COLOR_BGR2GRAY)
                    _,_,red_channel=cv2.split(up)
                    for vname,v in (("gray",gray),("red_channel",red_channel)):
                        for psm in (6,11):
                            try:
                                txt=pytesseract.image_to_string(
                                    v,lang="jpn+eng",config=f"--psm {psm}",timeout=12
                                ).strip()
                            except Exception:
                                txt=""
                            if not txt:
                                continue
                            rr=resolve_name(txt,dictionary,min_score=min_score,min_margin=min_margin)
                            candidates.append({
                                "resolution":rr,"text":txt,
                                "stage":f"local_{vname}_psm{psm}_x{scale}"
                            })

        # Prefer a safely resolved candidate; otherwise keep the highest-score
        # unverified OCR text rather than forcing a dictionary item.
        candidates.sort(
            key=lambda z:(
                1 if z["resolution"]["status"]=="dictionary_resolved" else 0,
                z["resolution"]["score"],
                z["resolution"]["margin"]
            ),
            reverse=True
        )
        chosen=candidates[0]
        rr=chosen["resolution"]

        results.append({
            **cell,
            "product_name":rr["name"],
            "name_status":rr["status"],
            "name_score":float(rr["score"]),
            "name_margin":float(rr["margin"]),
            "name_stage":chosen["stage"],
            "ocr_text":chosen["text"],
            "name_reason":rr.get("reason","")
        })
    return results
