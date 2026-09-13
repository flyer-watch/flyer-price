from __future__ import annotations
import argparse, json, hashlib, sys, subprocess, tempfile, time
from pathlib import Path
import requests, cv2, numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from generic_price_detector import detect_price_anchors, PRICE_OCR_VERSION

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142 Safari/537.36"


def detect_price_anchors_isolated(image_path:Path,profile:dict,timeout_sec:float=55.0,max_attempts:int=2):
    errors=[]
    for attempt in range(1,max_attempts+1):
        with tempfile.TemporaryDirectory(prefix='price_detect_') as td:
            out=Path(td)/'result.json'
            cmd=[sys.executable,str(HERE/'price_detect_worker.py'),str(image_path),json.dumps(profile,ensure_ascii=False),str(out)]
            try:
                p=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                errors.append(f'attempt {attempt}: timeout after {timeout_sec}s')
                time.sleep(2.0)
                continue
            if p.returncode==0 and out.exists():
                return json.loads(out.read_text(encoding='utf-8'))
            errors.append(f'attempt {attempt}: returncode={p.returncode}, output={out.exists()}')
            time.sleep(1.0)
    raise TimeoutError(f'price detection worker failed after {max_attempts} attempts: {image_path.name}: {errors}')


def multiset_recall(expected,actual):
    rem=list(actual);matched=0
    for e in expected:
        if e in rem:
            rem.remove(e);matched+=1
    return matched/len(expected) if expected else 1.0,matched,rem


def file_sha256(p:Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def download_image(session,item,cache_dir,offline_cache_only=False):
    url=item["url"];referer=item.get("referer","")
    key=hashlib.sha256(url.encode()).hexdigest()[:20]+".jpg"
    p=cache_dir/key
    if not p.exists():
        if offline_cache_only:
            raise FileNotFoundError(f"cache missing: {p.name}")
        r=session.get(url,headers={"Referer":referer},timeout=45)
        r.raise_for_status();p.write_bytes(r.content)
    data=np.frombuffer(p.read_bytes(),np.uint8)
    img=cv2.imdecode(data,cv2.IMREAD_COLOR)
    if img is None:raise ValueError(f"decode failed: {url}")
    return img,p


def dry_validate(manifest):
    errors=[];ids=set()
    for g in manifest.get("groups",[]):
        if g["id"] in ids:errors.append(f"duplicate id {g['id']}")
        ids.add(g["id"])
        if not g.get("images"):errors.append(f"no images {g['id']}")
        if not g.get("anchor_prices"):errors.append(f"no anchors {g['id']}")
        if not (0<g.get("minimum_recall",0)<=1):errors.append(f"bad threshold {g['id']}")
        pd=g.get('price_detector',{})
        if pd.get('mode') not in {None,'red_only','hybrid_ocr'}:errors.append(f"bad detector mode {g['id']}")
        for i in g.get("images",[]):
            if not i["url"].startswith("https://"):errors.append(f"non https {g['id']}")
    return {"pass":not errors,"errors":errors,"group_count":len(ids),"detector_version":PRICE_OCR_VERSION}


def _save_anchor_cache(anchor_cache_dir:Path,p:Path,profile:dict,result:dict):
    anchor_cache_dir.mkdir(parents=True,exist_ok=True)
    payload={
        'detector_version':PRICE_OCR_VERSION,'image_filename':p.name,'image_sha256':file_sha256(p),
        'profile':profile,'result':result,
    }
    q=anchor_cache_dir/(p.stem+'.json')
    q.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    return q


def _load_anchor_cache(anchor_cache_dir:Path,p:Path,profile:dict):
    q=anchor_cache_dir/(p.stem+'.json')
    if not q.exists():return None,q
    try:d=json.loads(q.read_text(encoding='utf-8'))
    except Exception:return None,q
    if d.get('detector_version')!=PRICE_OCR_VERSION:return None,q
    if d.get('profile')!=profile:return None,q
    if d.get('image_sha256')!=file_sha256(p):return None,q
    return d.get('result'),q


def run(manifest,cache_dir,offline_cache_only=False,anchor_cache_dir=None):
    s=requests.Session();s.headers.update({"User-Agent":UA,"Accept-Language":"ja-JP,ja;q=0.9,en;q=0.5"})
    cache_dir.mkdir(parents=True,exist_ok=True)
    if anchor_cache_dir is None:anchor_cache_dir=ROOT/'data'/'anchor_cache'
    groups=[]
    for g in manifest["groups"]:
        vals=[];files=[];errs=[];images=[]
        profile=g.get('price_detector',{'mode':'red_only','include_red':True})
        density_limit=float(profile.get('max_candidate_density_per_mp',80))
        density_ok=True
        for item in g["images"]:
            try:
                img,p=download_image(s,item,cache_dir,offline_cache_only=offline_cache_only)
                files.append(str(p))
                det,cache_path=_load_anchor_cache(Path(anchor_cache_dir),p,profile)
                cache_hit=det is not None
                if det is None:
                    det=detect_price_anchors_isolated(p,profile)
                    cache_path=_save_anchor_cache(Path(anchor_cache_dir),p,profile,det)
                anchors=det['broad_anchors'];vals.extend(x['value'] for x in anchors)
                H,W=img.shape[:2];mp=(H*W)/1_000_000.0;density=len(anchors)/mp if mp else 9999
                this_ok=density<=density_limit;density_ok=density_ok and this_ok
                images.append({
                    'cache_file':str(p),'anchor_cache':str(cache_path),'broad_anchor_count':len(anchors),
                    'association_anchor_count':len(det.get('association_anchors',[])),
                    'candidate_density_per_mp':round(density,3),'density_limit':density_limit,'density_pass':this_ok,
                    'observations':det.get('observations',[]),'anchor_cache_hit':cache_hit,
                })
            except Exception as e:
                errs.append(f"{type(e).__name__}: {e}")
        recall,matched,fp=multiset_recall(g["anchor_prices"],vals)
        passed=recall>=g["minimum_recall"] and not errs and density_ok
        groups.append({
            "id":g["id"],"expected_anchors":len(g["anchor_prices"]),"detected_prices":len(vals),
            "matched":matched,"recall":recall,"threshold":g["minimum_recall"],"pass":passed,
            "candidate_density_pass":density_ok,"errors":errs,"cache_files":files,"images":images,
            "unmatched_detection_sample":fp[:30]
        })
    return {"pass":all(g["pass"] for g in groups),"offline_cache_only":offline_cache_only,"detector_version":PRICE_OCR_VERSION,"groups":groups}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",default=str(ROOT/"fixtures"/"remote_regression_manifest.json"))
    ap.add_argument("--cache-dir",default=str(ROOT/"data"/"remote_cache"))
    ap.add_argument("--anchor-cache-dir",default=str(ROOT/"data"/"anchor_cache"))
    ap.add_argument("--dry-run",action="store_true")
    ap.add_argument("--group",action="append",default=[],help="Validate only selected group id(s)")
    ap.add_argument("--offline-cache-only",action="store_true",help="Never access network; use only URL-hash cache files")
    ap.add_argument("--report",default=str(ROOT/"reports"/"remote_regression_result.json"))
    a=ap.parse_args();manifest=json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    if a.group:
        wanted=set(a.group);manifest={**manifest,'groups':[g for g in manifest.get('groups',[]) if g.get('id') in wanted]}
    result=dry_validate(manifest) if a.dry_run else run(manifest,Path(a.cache_dir),offline_cache_only=a.offline_cache_only,anchor_cache_dir=Path(a.anchor_cache_dir))
    Path(a.report).parent.mkdir(parents=True,exist_ok=True)
    Path(a.report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result["pass"] else 1)

if __name__=="__main__":main()
