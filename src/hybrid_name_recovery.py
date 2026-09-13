from __future__ import annotations
import cv2, pandas as pd, pytesseract
from name_resolution import resolve_name
from batch_name_recovery import batch_resolve_jobs

def _full_image_tokens(img,scale=4):
    up=cv2.resize(img,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
    gray=cv2.cvtColor(up,cv2.COLOR_BGR2GRAY)
    df=pytesseract.image_to_data(
        gray,lang="jpn+eng",config="--psm 11",
        output_type=pytesseract.Output.DATAFRAME,timeout=45
    )
    df=df[(df.conf>=0)&df.text.notna()&(df.text.astype(str).str.strip()!="")].copy()
    df["cx"]=(df.left+df.width/2)/scale
    df["cy"]=(df.top+df.height/2)/scale
    return df

def _cell_text(tokens,cell):
    sub=tokens[
        (tokens.cx>=cell["x1"])&(tokens.cx<=cell["x2"])&
        (tokens.cy>=cell["y1"])&(tokens.cy<=cell["y2"])
    ].sort_values(["top","left"])
    return " ".join(sub.text.astype(str).tolist())

def recover_names_hybrid(img,cells,dictionary,min_score=42,min_margin=4):
    """
    1. One whole-flyer OCR pass.
    2. Keep safely resolved cells unchanged.
    3. Send unresolved cells only to 2-call batch OCR.
    4. Only remaining cells receive targeted local OCR.

    This prevents a good whole-page reading from being overwritten by a worse
    photo-heavy local OCR crop.
    """
    tokens=_full_image_tokens(img)
    results={}
    fallback=[]

    for i,cell in enumerate(cells):
        text=_cell_text(tokens,cell)
        rr=resolve_name(text,dictionary,min_score=min_score,min_margin=min_margin)
        item={**cell,
              "product_name":rr["name"],"name_status":rr["status"],
              "name_score":float(rr["score"]),"name_margin":float(rr["margin"]),
              "name_stage":"full_image","ocr_text":text,
              "name_reason":rr.get("reason","")}
        key=cell.get("id",i)
        if rr["status"]=="dictionary_resolved":
            results[key]=item
        else:
            x1=max(0,int(cell["x1"]));y1=max(0,int(cell["y1"]))
            x2=min(img.shape[1],int(cell["x2"]));y2=min(img.shape[0],int(cell["y2"]))
            fallback.append({
                "id":key,"crop":img[y1:y2,x1:x2],
                "dictionary":dictionary,
                "cell":cell
            })

    fb=batch_resolve_jobs(fallback,min_score=min_score,min_margin=min_margin)
    for r in fb["results"]:
        cell=r.pop("cell")
        key=r["id"]
        results[key]={**cell,**r}

    ordered=[]
    for i,cell in enumerate(cells):
        key=cell.get("id",i)
        ordered.append(results[key])

    return {
        "results":ordered,
        "metrics":{
            "cells":len(cells),
            "full_image_resolved":len(cells)-len(fallback),
            "fallback_jobs":len(fallback),
            **{f"fallback_{k}":v for k,v in fb["metrics"].items()}
        }
    }
