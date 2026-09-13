from __future__ import annotations
import json, sys
from pathlib import Path
import cv2
from generic_price_detector import detect_price_anchors


def main():
    if len(sys.argv)!=4:
        raise SystemExit('usage: price_detect_worker.py IMAGE PROFILE_JSON OUT_JSON')
    image_path=Path(sys.argv[1]); profile=json.loads(sys.argv[2]); out=Path(sys.argv[3])
    img=cv2.imread(str(image_path))
    if img is None: raise FileNotFoundError(image_path)
    result=detect_price_anchors(img,profile)
    out.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')

if __name__=='__main__': main()
