from __future__ import annotations
import cv2, numpy as np, pytesseract, re, os
from collections import Counter

os.environ.setdefault("OMP_THREAD_LIMIT","1")

PRICE_OCR_VERSION = "hybrid-price-v1.9.2"


def _red_mask(img):
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
    return cv2.bitwise_or(
        cv2.inRange(hsv,np.array([0,90,55]),np.array([22,255,255])),
        cv2.inRange(hsv,np.array([155,90,55]),np.array([179,255,255]))
    )


def _read_group(mask,group,H,W):
    x1=min(c[0] for c in group);y1=min(c[1] for c in group)
    x2=max(c[0]+c[2] for c in group);y2=max(c[1]+c[3] for c in group)
    roi=mask[max(0,y1-4):min(H,y2+4),max(0,x1-4):min(W,x2+4)]
    roi=cv2.resize(roi,None,fx=6,fy=6,interpolation=cv2.INTER_NEAREST)
    roi=cv2.bitwise_not(roi)
    reads=[]
    for psm in (7,8,13):
        s=pytesseract.image_to_string(
            roi,lang="eng",
            config=f"--psm {psm} -c tessedit_char_whitelist=0123456789",
            timeout=12
        ).strip()
        reads.append(re.sub(r"\D","",s))
    vals=[s for s in reads if s.isdigit() and 2<=len(s)<=4]
    if not vals:
        return [x1,y1,x2,y2],None,reads
    for s in vals:
        if len(s)==3 and any(len(t)==4 and t.startswith(s) for t in vals):
            return [x1,y1,x2,y2],int(s),reads
    cnt=Counter(vals);top=max(cnt.values())
    tied=[s for s,n in cnt.items() if n==top]
    tied.sort(key=lambda s:(abs(len(s)-3),len(s)))
    return [x1,y1,x2,y2],int(tied[0]),reads


def detect_red_price_anchors(img):
    H,W=img.shape[:2]
    mask=_red_mask(img)
    n,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
    comps=[]
    for i in range(1,n):
        x,y,w,h,area=map(int,stats[i][:5])
        if (
            area>=max(12,int(H*W*0.000015)) and
            2<=w<=max(80,int(W*.09)) and
            max(15,int(H*.018))<=h<=max(70,int(H*.10))
        ):
            comps.append((x,y,w,h,area,i))

    rows=[]
    for c in sorted(comps,key=lambda z:(z[1],z[0])):
        for row in rows:
            cy=np.median([r[1]+r[3]/2 for r in row])
            ch=np.median([r[3] for r in row])
            if abs((c[1]+c[3]/2)-cy)<=max(4,ch*.18) and abs(c[3]-ch)<=max(5,ch*.30):
                row.append(c);break
        else:
            rows.append([c])

    groups=[]
    for row in rows:
        row=sorted(row,key=lambda z:z[0]);cur=[]
        med_h=np.median([r[3] for r in row])
        for c in row:
            gap=c[0]-(cur[-1][0]+cur[-1][2]) if cur else 0
            if cur and gap>max(12,med_h*.55):
                if len(cur)>=2:groups.append(cur)
                cur=[]
            cur.append(c)
        if len(cur)>=2:groups.append(cur)

    out=[]
    for g in groups:
        bbox,val,reads=_read_group(mask,g,H,W)
        if val is None:continue
        if 20<=val<=99:
            x1=bbox[0];yc=(bbox[1]+bbox[3])/2
            mh=np.median([c[3] for c in g]); ids={c[5] for c in g}
            cand=[]
            for c in comps:
                if c[5] in ids:continue
                right=c[0]+c[2];cy=c[1]+c[3]/2
                if 0<=x1-right<=max(10,mh*.35) and abs(cy-yc)<=max(7,mh*.25) and .78*mh<=c[3]<=1.25*mh:
                    cand.append((x1-right,c))
            if cand:
                cand.sort(key=lambda z:z[0])
                nb,nv,nreads=_read_group(mask,sorted([cand[0][1]]+g,key=lambda z:z[0]),H,W)
                if nv is not None and 100<=nv<=999:
                    bbox,val,reads=nb,nv,nreads
        if 20<=val<=9999 and (bbox[3]-bbox[1])>=max(16,int(H*.018)):
            out.append({"bbox":bbox,"value":val,"reads":reads,"source":"red","confidence":1.0})
    ded=[]
    for d in sorted(out,key=lambda z:(z["bbox"][1],z["bbox"][0])):
        bx=d["bbox"];cx=(bx[0]+bx[2])/2;cy=(bx[1]+bx[3])/2
        if any(
            q["value"]==d["value"] and
            abs(cx-(q["bbox"][0]+q["bbox"][2])/2)<max(12,W*.015) and
            abs(cy-(q["bbox"][1]+q["bbox"][3])/2)<max(10,H*.015)
            for q in ded
        ):
            continue
        ded.append(d)
    return ded


def _ocr_observation(img,target_h:int,mode:str):
    H,W=img.shape[:2]
    scale=float(target_h)/H
    small=cv2.resize(img,(max(1,int(round(W*scale))),target_h),interpolation=cv2.INTER_AREA)
    if mode in {"digits","digits_otsu"}:
        work=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
        if mode=="digits_otsu":
            _,work=cv2.threshold(work,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        lang="eng";config="--psm 11 -c tessedit_char_whitelist=0123456789"
    else:
        work=small;lang="jpn+eng";config="--psm 11"
    data=pytesseract.image_to_data(
        work,lang=lang,config=config,
        output_type=pytesseract.Output.DICT,timeout=10
    )
    inv=1.0/scale
    tokens=[]
    for i,text in enumerate(data.get("text",[])):
        text=" ".join(str(text).split())
        if not text:continue
        try:conf=float(data["conf"][i])
        except Exception:conf=-1.0
        if conf<0:continue
        x=float(data["left"][i])*inv;y=float(data["top"][i])*inv
        w=float(data["width"][i])*inv;h=float(data["height"][i])*inv
        tokens.append({
            "text":text,"confidence":conf,
            "bbox":[int(round(x)),int(round(y)),int(round(x+w)),int(round(y+h))],
            "scaled_height":int(data["height"][i]),"target_height":target_h,"mode":mode,
        })
    return tokens



def _tiled_digit_observation(img,target_h:int,rows:int=2,cols:int=2,overlap:float=.06):
    H,W=img.shape[:2];out=[]
    for ry in range(rows):
        for cx in range(cols):
            xa=int(cx*W/cols);xb=int((cx+1)*W/cols);ya=int(ry*H/rows);yb=int((ry+1)*H/rows)
            px=int((W/cols)*overlap);py=int((H/rows)*overlap)
            x1=max(0,xa-px);x2=min(W,xb+px);y1=max(0,ya-py);y2=min(H,yb+py)
            tile=img[y1:y2,x1:x2];th,tw=tile.shape[:2];scale=float(target_h)/th
            small=cv2.resize(tile,(max(1,int(round(tw*scale))),target_h),interpolation=cv2.INTER_AREA)
            work=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
            try:
                data=pytesseract.image_to_data(work,lang="eng",config="--psm 11 -c tessedit_char_whitelist=0123456789",output_type=pytesseract.Output.DICT,timeout=8)
            except RuntimeError:
                continue
            inv=1.0/scale
            for i,text in enumerate(data.get("text",[])):
                text=" ".join(str(text).split())
                if not text:continue
                try:conf=float(data["conf"][i])
                except Exception:conf=-1.0
                if conf<0:continue
                xx=x1+float(data["left"][i])*inv;yy=y1+float(data["top"][i])*inv
                ww=float(data["width"][i])*inv;hh=float(data["height"][i])*inv
                out.append({"text":text,"confidence":conf,"bbox":[int(round(xx)),int(round(yy)),int(round(xx+ww)),int(round(yy+hh))],"scaled_height":int(data["height"][i]),"target_height":target_h,"mode":"digits_tiled"})
    return out

def _candidate_values(text:str,max_concat_digits:int=8):
    """Generate conservative alternate hypotheses from one OCR word.

    Flyers often merge main price + tiny tax/yen glyphs into one digit run
    (e.g. 298 -> 2985). Alternatives are retained only for short merged runs.
    """
    s=str(text).replace(",","").replace(" ","")
    vals=[]
    for m in re.finditer(r"\d+",s):
        ds=m.group()
        if 2<=len(ds)<=4:
            vals.append(int(ds))
        if len(ds)==4 and ds[-1] in "56":
            vals.append(int(ds[:3]))
        if 5<=len(ds)<=int(max_concat_digits):
            # Merged OCR often concatenates a true 3- or 4-digit shelf price
            # with a tiny tax/yen glyph. Keep sliding hypotheses for broad
            # recall only; association anchors remain based on direct values.
            for i in range(len(ds)-2):
                vals.append(int(ds[i:i+3]))
            if len(ds)<=6:
                for i in range(len(ds)-3):
                    v4=int(ds[i:i+4])
                    # Auxiliary 4-digit hypotheses from merged runs are kept
                    # conservative: grocery high-ticket prices are typically
                    # quoted in 10-yen units. Direct 4-digit OCR is unaffected.
                    if v4>=1000 and v4%10==0:
                        vals.append(v4)
    # Common edge confusions observed on flyer price fonts. These are alternate
    # hypotheses only and never replace the direct OCR reading.
    m=re.match(r"^[sS](\d{2})(?!\d)",s)
    if m:vals.append(int("2"+m.group(1)))
    m=re.match(r"^[Bb](\d{2})(?!\d)",s)
    if m:vals.append(int("8"+m.group(1)))
    out=[]
    for v in vals:
        if 20<=v<=9999 and v not in out:out.append(v)
    return out


def _direct_value(text:str):
    runs=re.findall(r"\d{2,4}",str(text).replace(",",""))
    if not runs:return None
    ds=max(runs,key=len)
    try:v=int(ds)
    except Exception:return None
    return v if 20<=v<=9999 else None


def _dedupe_value_spatial(items,H,W):
    out=[]
    for d in sorted(items,key=lambda z:(z["bbox"][1],z["bbox"][0],z["value"])):
        b=d["bbox"];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
        if any(
            q["value"]==d["value"] and
            abs(cx-(q["bbox"][0]+q["bbox"][2])/2)<max(10,W*.012) and
            abs(cy-(q["bbox"][1]+q["bbox"][3])/2)<max(10,H*.012)
            for q in out
        ):continue
        out.append(d)
    return out


def _dedupe_location(items,H,W):
    out=[]
    # Prefer red, then higher-confidence OCR token, then larger bbox height.
    items=sorted(items,key=lambda d:(0 if d.get("source")=="red" else 1,-float(d.get("confidence",0)),-(d["bbox"][3]-d["bbox"][1])))
    for d in items:
        b=d["bbox"];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
        if any(
            abs(cx-(q["bbox"][0]+q["bbox"][2])/2)<max(12,W*.012) and
            abs(cy-(q["bbox"][1]+q["bbox"][3])/2)<max(10,H*.012)
            for q in out
        ):continue
        out.append(d)
    return sorted(out,key=lambda z:(z["bbox"][1],z["bbox"][0]))


def default_profile():
    return {"mode":"red_only","include_red":True}


def detect_price_anchors(img,profile=None):
    """Return broad recall anchors + high-trust association anchors.

    profile is data-driven by flyer layout. `broad_anchors` are used only for
    price-recall validation; `association_anchors` are intentionally narrower
    and are used to partition product-name cells.
    """
    profile={**default_profile(),**(profile or {})}
    mode=profile.get("mode","red_only")
    H,W=img.shape[:2]
    broad=[];strong=[];observations=[];name_tokens=[]
    if profile.get("include_red",True):
        red=detect_red_price_anchors(img)
        broad.extend(red);strong.extend(red)
    if mode!="hybrid_ocr":
        return {"version":PRICE_OCR_VERSION,"broad_anchors":_dedupe_value_spatial(broad,H,W),"association_anchors":_dedupe_location(strong,H,W),"name_tokens":[],"observations":[]}

    specs=[]
    for h in profile.get("jpn_heights",[900]):specs.append((int(h),"jpn"))
    for h in profile.get("digit_heights",[1500]):specs.append((int(h),"digits"))
    for h in profile.get("otsu_digit_heights",[]):specs.append((int(h),"digits_otsu"))
    min_ratio=float(profile.get("min_token_height_ratio",.01))
    max_concat=int(profile.get("max_concat_digits",8))
    strong_ratio=float(profile.get("association_min_height_ratio",.008))
    strong_conf=float(profile.get("association_min_confidence",10))

    first_jpn=True
    for target_h,ocr_mode in specs:
        try:
            tokens=_ocr_observation(img,target_h,ocr_mode)
            observations.append({"target_height":target_h,"mode":ocr_mode,"token_count":len(tokens),"status":"ok"})
        except RuntimeError as e:
            observations.append({"target_height":target_h,"mode":ocr_mode,"token_count":0,"status":"timeout","error":str(e)})
            continue
        if ocr_mode=="jpn" and first_jpn:
            name_tokens=tokens
            first_jpn=False
        for t in tokens:
            if t["scaled_height"]>=target_h*min_ratio:
                for val in _candidate_values(t["text"],max_concat):
                    broad.append({"bbox":t["bbox"],"value":val,"source":f"ocr_{ocr_mode}_{target_h}","confidence":t["confidence"],"raw_text":t["text"]})
            if ocr_mode=="jpn" and target_h==int(profile.get("jpn_heights",[900])[0]) and t["scaled_height"]>=target_h*strong_ratio and t["confidence"]>=strong_conf:
                val=_direct_value(t["text"])
                if val is not None:
                    strong.append({"bbox":t["bbox"],"value":val,"source":f"ocr_assoc_{target_h}","confidence":t["confidence"],"raw_text":t["text"]})
    tile_h=int(profile.get("tiled_digit_height",0) or 0)
    if tile_h>0:
        rows=int(profile.get("tile_rows",2));cols=int(profile.get("tile_cols",2));overlap=float(profile.get("tile_overlap",.06));tile_ratio=float(profile.get("tile_min_token_height_ratio",.008))
        tokens=_tiled_digit_observation(img,tile_h,rows,cols,overlap)
        observations.append({"target_height":tile_h,"mode":"digits_tiled","token_count":len(tokens),"tiles":rows*cols})
        for t in tokens:
            if t["scaled_height"]>=tile_h*tile_ratio:
                for val in _candidate_values(t["text"],max_concat):
                    broad.append({"bbox":t["bbox"],"value":val,"source":f"ocr_digits_tiled_{tile_h}","confidence":t["confidence"],"raw_text":t["text"]})
    return {
        "version":PRICE_OCR_VERSION,
        "broad_anchors":_dedupe_value_spatial(broad,H,W),
        "association_anchors":_dedupe_location(strong,H,W),
        "name_tokens":name_tokens,
        "observations":observations,
    }


def extract_name_ocr_tokens(img,target_h=700):
    """Reusable low-resolution Japanese/English OCR tokens in original-image coordinates."""
    return _ocr_observation(img,int(target_h),"jpn")
