from __future__ import annotations
import cv2, numpy as np

def cluster_anchor_rows(anchors,H):
    pts=[]
    for a in anchors:
        b=a["bbox"]
        pts.append({
            **a,
            "cx":(b[0]+b[2])/2,
            "cy":(b[1]+b[3])/2
        })
    rows=[]
    tol=max(24,H*.12)
    for p in sorted(pts,key=lambda z:(z["cy"],z["cx"])):
        for row in rows:
            med=float(np.median([q["cy"] for q in row]))
            if abs(p["cy"]-med)<=tol:
                row.append(p)
                break
        else:
            rows.append([p])
    for row in rows:
        row.sort(key=lambda z:z["cx"])
    rows.sort(key=lambda r:float(np.median([q["cy"] for q in r])))
    return rows

def _horizontal_rules(img):
    H,W=img.shape[:2]
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,50,150)
    lines=cv2.HoughLinesP(
        edges,1,np.pi/180,
        threshold=max(35,int(W*.03)),
        minLineLength=int(W*.35),
        maxLineGap=12
    )
    ys=[]
    if lines is not None:
        for x1,y1,x2,y2 in lines[:,0]:
            if abs(y2-y1)<=3 and abs(x2-x1)>=W*.35:
                ys.append((int((y1+y2)/2),abs(x2-x1)))
    # cluster double-edge detections
    groups=[]
    for y,l in sorted(ys):
        if not groups or abs(y-np.median([q[0] for q in groups[-1]]))>5:
            groups.append([(y,l)])
        else:
            groups[-1].append((y,l))
    return [
        (float(np.mean([q[0] for q in g])),max(q[1] for q in g))
        for g in groups
    ]

def infer_irregular_price_cells(img,anchors):
    """
    Life-like daily strip with irregular product widths and occasional
    no-price discount panels.

    Price anchors are near the right side of each priced product cell.
    A large horizontal anchor gap indicates an intervening no-price panel.
    The following priced cells may vertically span more than one ordinary row.
    """
    H,W=img.shape[:2]
    rows=cluster_anchor_rows(anchors,H)
    if not rows:
        return []

    row_centers=[float(np.median([a["cy"] for a in row])) for row in rows]
    rules=_horizontal_rules(img)

    # Choose real horizontal rules between price rows.
    separators=[]
    for a,b in zip(row_centers[:-1],row_centers[1:]):
        candidates=[(y,l) for y,l in rules if a<y<b]
        if candidates:
            mid=(a+b)/2
            max_len=max(l for y,l in candidates)
            strong=[(y,l) for y,l in candidates if l>=max_len*.65]
            separators.append(min(strong,key=lambda t:abs(t[0]-mid))[0])
        else:
            separators.append((a+b)/2)

    # Bottom of daily block is usually a strong rule just below last row.
    bottom_candidates=[(y,l) for y,l in rules if y>row_centers[-1]]
    if bottom_candidates:
        target=H-max(18,H*.055)
        max_len=max(l for y,l in bottom_candidates)
        strong=[(y,l) for y,l in bottom_candidates if l>=max_len*.55]
        bottom=min(strong,key=lambda t:abs(t[0]-target))[0]
    else:
        bottom=float(H)

    cells=[]
    for ri,row in enumerate(rows):
        row_top=0.0 if ri==0 else separators[ri-1]
        row_bottom=bottom if ri==len(rows)-1 else separators[ri]

        gaps=[row[i]["cx"]-row[i-1]["cx"] for i in range(1,len(row))]
        med_gap=float(np.median(gaps)) if gaps else W*.15
        large_gap_threshold=max(W*.20,med_gap*1.80)

        prev=None
        tall_segment=False
        for ci,a in enumerate(row):
            if prev is None:
                left=max(0.0,a["cx"]-W*.165)
            else:
                gap=a["cx"]-prev["cx"]
                if gap>large_gap_threshold:
                    left=max(0.0,a["cx"]-W*.10)
                    tall_segment=True
                else:
                    left=prev["cx"]+W*.041

            right=min(float(W),a["cx"]+W*.050)
            top=row_top

            # If a large missing-price gap appears in the last anchor row,
            # following products often occupy a tall cell spanning the row above.
            if ri==len(rows)-1 and tall_segment and ri>=1:
                top=0.0 if ri==1 else separators[ri-2]

            cells.append({
                "id":f"r{ri}c{ci}",
                "row":ri,"col":ci,
                "price":a["value"],
                "anchor_bbox":a["bbox"],
                "anchor_x":a["cx"],"anchor_y":a["cy"],
                "x1":float(left),"y1":float(top),
                "x2":float(right),"y2":float(row_bottom)
            })
            prev=a
    return cells
