from __future__ import annotations
import math, cv2, numpy as np, pandas as pd, pytesseract
from name_resolution import resolve_name

def _contact_sheet(jobs, cols=5, slot_w=500, slot_h=180):
    rows=math.ceil(len(jobs)/cols) if jobs else 1
    sheet=np.full((rows*slot_h,cols*slot_w,3),255,np.uint8)
    bounds=[]
    for i,j in enumerate(jobs):
        crop=j["crop"]
        maxw,maxh=slot_w-18,slot_h-18
        scale=min(maxw/max(1,crop.shape[1]),maxh/max(1,crop.shape[0]))
        nw=max(1,int(crop.shape[1]*scale));nh=max(1,int(crop.shape[0]*scale))
        rs=cv2.resize(crop,(nw,nh),interpolation=cv2.INTER_CUBIC)
        rr=i//cols;cc=i%cols
        ox=cc*slot_w+(slot_w-nw)//2
        oy=rr*slot_h+(slot_h-nh)//2
        sheet[oy:oy+nh,ox:ox+nw]=rs
        bounds.append((cc*slot_w,rr*slot_h,(cc+1)*slot_w,(rr+1)*slot_h))
    return sheet,bounds

def _ocr_sheet(sheet):
    gray=cv2.cvtColor(sheet,cv2.COLOR_BGR2GRAY)
    clahe=cv2.createCLAHE(clipLimit=1.6,tileGridSize=(12,12)).apply(gray)
    dfs=[]
    for vname,v in (("gray",gray),("clahe",clahe)):
        df=pytesseract.image_to_data(
            v,lang="jpn+eng",config="--psm 11",
            output_type=pytesseract.Output.DATAFRAME,timeout=45
        )
        df=df[(df.conf>=0)&df.text.notna()&(df.text.astype(str).str.strip()!="")].copy()
        df["cx"]=df.left+df.width/2
        df["cy"]=df.top+df.height/2
        df["variant"]=vname
        dfs.append(df)
    return pd.concat(dfs,ignore_index=True) if dfs else pd.DataFrame()

def _text_for_slot(df,bounds,variant):
    x1,y1,x2,y2=bounds
    sub=df[
        (df.variant==variant)&
        (df.cx>=x1)&(df.cx<x2)&(df.cy>=y1)&(df.cy<y2)
    ].sort_values(["top","left"])
    return " ".join(sub.text.astype(str).tolist())

def _targeted_fallback(crop,dictionary,min_score,min_margin):
    attempts=[]
    # Start with the combinations that fixed the hardest Comodi synthetic cell.
    variants_plan=[
        (5,"otsu",11),(7,"otsu",11),
        (5,"otsu",6),(6,"otsu",6),
        (5,"gray",6),(6,"clahe",6),(7,"gray",11)
    ]
    for scale,vname,psm in variants_plan:
        up=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
        gray=cv2.cvtColor(up,cv2.COLOR_BGR2GRAY)
        if vname=="gray":
            v=gray
        elif vname=="clahe":
            v=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(gray)
        else:
            v=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
        try:
            txt=pytesseract.image_to_string(v,lang="jpn+eng",config=f"--psm {psm}",timeout=12).strip()
        except Exception:
            txt=""
        if not txt:
            continue
        rr=resolve_name(txt,dictionary,min_score=min_score,min_margin=min_margin)
        attempts.append((rr,txt,scale,vname,psm))
        if rr["status"]=="dictionary_resolved":
            return {
                "resolution":rr,"text":txt,
                "stage":f"targeted_{vname}_psm{psm}_x{scale}",
                "attempt_count":len(attempts)
            }
    if attempts:
        attempts.sort(key=lambda x:(x[0]["score"],x[0]["margin"]),reverse=True)
        rr,txt,scale,vname,psm=attempts[0]
        return {
            "resolution":rr,"text":txt,
            "stage":f"targeted_{vname}_psm{psm}_x{scale}",
            "attempt_count":len(attempts)
        }
    return {
        "resolution":{"name":"","status":"ocr_unverified","score":0.0,"margin":0.0,"reason":"no_ocr"},
        "text":"","stage":"targeted_failed","attempt_count":0
    }

def batch_resolve_jobs(jobs,min_score=40,min_margin=4):
    """
    jobs:
      crop: image of one inferred product cell/name zone
      dictionary: allowed verified names for that region
      expected/id/context: optional metadata

    Strategy:
      1. two OCR calls total for all jobs via contact sheet,
      2. unresolved jobs only -> limited targeted OCR,
      3. never force unresolved text into dictionary.
    """
    if not jobs:
        return {"results":[],"metrics":{"jobs":0,"batch_ocr_calls":0,"targeted_jobs":0,"targeted_attempts":0}}

    sheet,bounds=_contact_sheet(jobs)
    df=_ocr_sheet(sheet)
    results=[]
    targeted_jobs=0
    targeted_attempts=0

    for j,b in zip(jobs,bounds):
        candidates=[]
        for vn in ("gray","clahe"):
            text=_text_for_slot(df,b,vn)
            rr=resolve_name(text,j["dictionary"],min_score=min_score,min_margin=min_margin)
            candidates.append({
                "resolution":rr,"text":text,"stage":f"batch_{vn}"
            })
        candidates.sort(
            key=lambda z:(1 if z["resolution"]["status"]=="dictionary_resolved" else 0,
                          z["resolution"]["score"],z["resolution"]["margin"]),
            reverse=True
        )
        chosen=candidates[0]

        if chosen["resolution"]["status"]!="dictionary_resolved":
            targeted_jobs+=1
            fb=_targeted_fallback(j["crop"],j["dictionary"],min_score,min_margin)
            targeted_attempts+=fb["attempt_count"]
            options=[chosen,fb]
            options.sort(
                key=lambda z:(1 if z["resolution"]["status"]=="dictionary_resolved" else 0,
                              z["resolution"]["score"],z["resolution"]["margin"]),
                reverse=True
            )
            chosen=options[0]

        meta={k:v for k,v in j.items() if k not in ("crop","dictionary")}
        results.append({
            **meta,
            "product_name":chosen["resolution"]["name"],
            "name_status":chosen["resolution"]["status"],
            "name_score":float(chosen["resolution"]["score"]),
            "name_margin":float(chosen["resolution"]["margin"]),
            "ocr_text":chosen["text"],
            "name_stage":chosen["stage"],
            "name_reason":chosen["resolution"].get("reason","")
        })

    return {
        "results":results,
        "metrics":{
            "jobs":len(jobs),
            "batch_ocr_calls":2,
            "targeted_jobs":targeted_jobs,
            "targeted_attempts":targeted_attempts
        },
        "contact_sheet":sheet
    }
