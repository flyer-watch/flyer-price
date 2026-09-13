from __future__ import annotations
import re, cv2, numpy as np, pytesseract
from temporal_rules import parse_temporal_text, resolve_scope

DATEISH=re.compile(r"\d{1,2}\s*/\s*\d{1,2}")

def _ocr_df(img):
    """General sparse OCR for ordinary dark-on-light date labels."""
    df=pytesseract.image_to_data(
        img,lang="jpn+eng",config="--psm 11",
        output_type=pytesseract.Output.DATAFRAME,timeout=45
    )
    return df[(df.conf>=20)&df.text.notna()&(df.text.astype(str).str.strip()!="")].copy()

def _normalize_date_ocr(text:str)->str:
    """
    Repair only narrow, date-specific OCR confusions.
    Examples observed in color headers:
      979(水)限り -> 9/9(水)限り
      9/9ぐ11    -> 9/9〜11
      9/9て11    -> 9/9〜11
    The repairs are deliberately context-restricted so price text is untouched.
    """
    t=(text or "").strip()
    # Slash occasionally becomes "7" between two single date digits, but only
    # when followed by a weekday marker.  979(水) -> 9/9(水).
    t=re.sub(r"(?<!\d)(\d)7(\d)(?=\([月火水木金土日水]\))",r"\1/\2",t)
    # Range dash/tilde can become Japanese glyphs on colored backgrounds.
    t=re.sub(r"(?<=\d)[ぐてて〜～](?=\d)", "〜", t)
    return t

def _color_header_anchors(img,page_start,page_end,year=2026):
    """
    Find saturated rectangular banners (green/blue/red headers) and OCR them
    separately.  This is important because white text on colored backgrounds
    often disappears from whole-page PSM11 OCR.
    """
    H,W=img.shape[:2]
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
    sat=hsv[:,:,1]
    mask=cv2.inRange(sat,70,255)

    # RETR_LIST intentionally exposes filled banner rectangles even when a
    # colored page border connects them into a larger outer contour.
    cnts,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    rects=[]
    for c in cnts:
        x,y,w,h=cv2.boundingRect(c)
        area=w*h
        if (
            w>=max(120,int(W*.10)) and
            h>=max(28,int(H*.025)) and
            h<=int(H*.18) and
            area>=H*W*.003
        ):
            # Filled banners have high saturation over much of the rectangle.
            roi=mask[y:y+h,x:x+w]
            fill=float((roi>0).mean()) if roi.size else 0.0
            if fill>=0.45:
                rects.append((x,y,w,h,fill))

    # Remove near-duplicate contours.
    ded_rects=[]
    for r in sorted(rects,key=lambda z:(z[1],z[0],-z[2]*z[3])):
        x,y,w,h,fill=r
        if any(abs(x-q[0])<8 and abs(y-q[1])<8 and abs(w-q[2])<12 and abs(h-q[3])<12 for q in ded_rects):
            continue
        ded_rects.append(r)

    anchors=[]
    for x,y,w,h,fill in ded_rects:
        crop=img[y:y+h,x:x+w]
        gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        chsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
        # Explicit white-text mask is often best on green/blue banners.
        white=cv2.inRange(chsv,np.array([0,0,150]),np.array([179,115,255]))
        variants=[("orig",crop),("gray",gray),("white",white)]

        candidates=[]
        for vname,v in variants:
            for psm in (7,6):
                try:
                    txt=pytesseract.image_to_string(
                        v,lang="jpn+eng",config=f"--psm {psm}",timeout=15
                    ).strip()
                except Exception:
                    txt=""
                if not txt:
                    continue
                norm=_normalize_date_ocr(txt)
                rules=parse_temporal_text(norm,year)
                if any(r.get("start_date") for r in rules):
                    resolved=resolve_scope(page_start,page_end,rules)
                    conf=max((r.get("confidence",0.0) for r in rules if r.get("start_date")),default=0.0)
                    candidates.append({
                        "text":txt,"normalized":norm,"rules":rules,
                        "resolved":resolved,"confidence":conf,
                        "variant":vname,"psm":psm
                    })

        if not candidates:
            continue
        # Prefer the parser's confidence, then a text containing slash/range.
        candidates.sort(
            key=lambda z:(z["confidence"], "/" in z["normalized"], "〜" in z["normalized"], len(z["normalized"])),
            reverse=True
        )
        best=candidates[0]
        anchors.append({
            "cx":x+w/2,"cy":y+h/2,
            "token":best["text"],"context":best["normalized"],
            "resolved":best["resolved"],
            "source":"color_header",
            "bbox":[x,y,x+w,y+h],
            "ocr_candidates":[
                {"text":c["text"],"normalized":c["normalized"],"variant":c["variant"],"psm":c["psm"]}
                for c in candidates
            ]
        })
    return anchors

def _long_lines(img):
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,50,150)
    H,W=gray.shape
    lines=cv2.HoughLinesP(edges,1,np.pi/180,threshold=max(40,int(min(H,W)*.05)),
                         minLineLength=int(min(H,W)*.30),maxLineGap=12)
    vert=[];horiz=[]
    if lines is not None:
        for x1,y1,x2,y2 in lines[:,0]:
            if abs(x2-x1)<=4 and abs(y2-y1)>=H*.35:
                vert.append((int((x1+x2)/2),abs(y2-y1)))
            if abs(y2-y1)<=4 and abs(x2-x1)>=W*.25:
                horiz.append((int((y1+y2)/2),abs(x2-x1)))
    return vert,horiz

def _context_near(df,cx,cy,W,H):
    sub=df[
        (df.left+df.width>=max(0,cx-W*.10))&
        (df.left<=min(W,cx+W*.28))&
        (df.top+df.height>=max(0,cy-H*.035))&
        (df.top<=min(H,cy+H*.055))
    ].sort_values(["top","left"])
    return "".join(sub.text.astype(str).tolist())

def _dedupe_anchors(anchors,split_x):
    """
    Color-banner OCR should win over weaker whole-page OCR if both refer to the
    same visual header.
    """
    anchors=sorted(
        anchors,
        key=lambda a:(
            a["cx"]>=split_x,
            a["cy"],
            0 if a.get("source")=="color_header" else 1
        )
    )
    ded=[]
    for a in anchors:
        duplicate=None
        for i,q in enumerate(ded):
            if abs(a["cx"]-q["cx"])<80 and abs(a["cy"]-q["cy"])<45:
                duplicate=i;break
        if duplicate is None:
            ded.append(a)
        else:
            q=ded[duplicate]
            if a.get("source")=="color_header" and q.get("source")!="color_header":
                ded[duplicate]=a
    return ded

def infer_partitioned_regions(img,page_start,page_end,year=2026):
    H,W=img.shape[:2]
    df=_ocr_df(img)
    vert,horiz=_long_lines(img)
    vc=[(x,l) for x,l in vert if W*.25<x<W*.75]
    split_x=int(np.median([x for x,l in vc])) if vc else int(W*.5)

    anchors=[]
    # Ordinary OCR anchors.
    for _,r in df.iterrows():
        txt=str(r.text)
        if not DATEISH.search(txt):
            continue
        cx=float(r.left+r.width/2);cy=float(r.top+r.height/2)
        context=_context_near(df,cx,cy,W,H)
        rules=parse_temporal_text(context,year)
        if not any(x.get("start_date") for x in rules):
            rules=parse_temporal_text(txt,year)
        if not any(x.get("start_date") for x in rules):
            continue
        resolved=resolve_scope(page_start,page_end,rules)
        anchors.append({
            "cx":cx,"cy":cy,"token":txt,"context":context,
            "resolved":resolved,"source":"general_ocr"
        })

    # White-on-color banner anchors.
    anchors.extend(_color_header_anchors(img,page_start,page_end,year))
    anchors=_dedupe_anchors(anchors,split_x)

    regions=[]
    for lane_id,(lx1,lx2) in enumerate(((0,split_x),(split_x,W))):
        lane=[a for a in anchors if lx1<=a["cx"]<lx2]
        lane.sort(key=lambda a:a["cy"])
        if not lane:
            regions.append({
                "region_id":f"lane{lane_id}_default",
                "x1":lx1,"y1":0,"x2":lx2,"y2":H,
                "sale_start":page_start,"sale_end":page_end,
                "date_source":"page_default"
            })
            continue

        bounds=[0]
        for a,b in zip(lane[:-1],lane[1:]):
            cand=[(y,l) for y,l in horiz if a["cy"]<y<b["cy"]]
            if cand:
                max_len=max(l for y,l in cand)
                strong=[(y,l) for y,l in cand if l>=max_len*.65]

                # If the lower anchor came from a colored banner, the true
                # section boundary is usually the long rule immediately
                # ABOVE that banner.  Choosing a geometric midpoint would
                # accidentally select internal product-grid lines.
                bbox=b.get("bbox")
                if bbox:
                    banner_top=bbox[1]
                    before=[(y,l) for y,l in strong if y<=banner_top+3]
                    if before:
                        boundary=max(before,key=lambda t:t[0])[0]
                    else:
                        target=banner_top
                        boundary=min(strong,key=lambda t:abs(t[0]-target))[0]
                else:
                    mid=(a["cy"]+b["cy"])/2
                    boundary=min(strong,key=lambda t:abs(t[0]-mid))[0]
            else:
                bbox=b.get("bbox")
                if bbox:
                    boundary=max(int(a["cy"]+1),int(bbox[1]-1))
                else:
                    boundary=int((a["cy"]+b["cy"])/2)
            bounds.append(int(boundary))
        bounds.append(H)

        for i,a in enumerate(lane):
            r=a["resolved"]
            regions.append({
                "region_id":f"lane{lane_id}_{i}",
                "x1":lx1,"y1":bounds[i],"x2":lx2,"y2":bounds[i+1],
                "sale_start":r["sale_start"],"sale_end":r["sale_end"],
                "time_start":r.get("time_start",""),"time_end":r.get("time_end",""),
                "date_source":r["date_source"],"context":a["context"],
                "anchor_source":a.get("source","")
            })
    return {"split_x":split_x,"anchors":anchors,"regions":regions}

def assign(x,y,regions):
    hits=[r for r in regions if r["x1"]<=x<r["x2"] and r["y1"]<=y<r["y2"]]
    return hits[0] if hits else None
