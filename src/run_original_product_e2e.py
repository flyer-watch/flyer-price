from __future__ import annotations
import argparse, hashlib, json, re, sys, os
from pathlib import Path
import cv2, numpy as np, pytesseract

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src';sys.path.insert(0,str(SRC))
from generic_price_detector import detect_price_anchors, extract_name_ocr_tokens, PRICE_OCR_VERSION
from remote_regression import multiset_recall, file_sha256
from dense_grid_inference import cluster_price_rows

os.environ.setdefault('OMP_THREAD_LIMIT','1')

JP_RE=re.compile(r'[一-龥ぁ-んァ-ヶA-Za-z]')
PRICEISH_RE=re.compile(r'^[\s\d.,/%+×xX\-~〜～円税込本体価格]+$')


def cache_name(url:str)->str:return hashlib.sha256(url.encode()).hexdigest()[:20]+'.jpg'

def decode(path:Path):
    a=np.frombuffer(path.read_bytes(),np.uint8);img=cv2.imdecode(a,cv2.IMREAD_COLOR)
    if img is None:raise ValueError(f'decode failed: {path.name}')
    return img


def _name_tokens_from_raw(raw):
    out=[]
    for t in raw:
        text=' '.join(str(t.get('text','')).split())
        conf=float(t.get('confidence',-1))
        if conf<5 or not text or PRICEISH_RE.fullmatch(text) or not JP_RE.search(text):continue
        b=t['bbox'];out.append({'text':text,'cx':(b[0]+b[2])/2,'cy':(b[1]+b[3])/2,'top':b[1],'left':b[0]})
    return out

GENERIC_TOKENS={
    '販売','特売','商品','定番','水曜','月曜','火曜','木曜','金曜','土曜','日曜','フェア','限り','より','税込','税抜','本体価格','本体','価格','当り','あたり','パック','バック','各','円','お買得','お買い得','コーナー'
}

def _normalized_evidence(texts):
    joined=''.join(re.sub(r'[\s・/／()（）\[\]【】]+','',str(t)) for t in texts)
    joined=re.sub(r'\d+(?:[.,]\d+)?(?:kg|g|ml|l|L|個|本|枚|袋|パック|入|連|束|玉|尾|切|食)?','',joined,flags=re.I)
    for term in sorted(GENERIC_TOKENS|{'100g当り','100gあたり','1パック','パック当り','当りパック'},key=len,reverse=True):joined=joined.replace(term,'')
    joined=re.sub(r'[円%％税込税抜本体価格]+','',joined);joined=re.sub(r'[^一-龥ぁ-んァ-ヶA-Za-z]','',joined)
    return joined

def _has_specific_name(texts):
    e=_normalized_evidence(texts);jp=len(re.findall(r'[一-龥ぁ-んァ-ヶ]',e));latin=len(re.findall(r'[A-Za-z]',e))
    return jp>=2 or latin>=4


def anchor_cells(anchors,H,W):
    rows=cluster_price_rows(anchors,H);row_starts=[0]
    for prev in rows[:-1]:row_starts.append(int(max(q['bbox'][3] for q in prev)+2))
    row_ends=row_starts[1:]+[H];cells=[]
    for ri,row in enumerate(rows):
        xs=[q['cx'] for q in row];xbounds=[0]+[int((a+b)/2) for a,b in zip(xs[:-1],xs[1:])]+[W]
        for ci,a in enumerate(row):cells.append({'anchor':a,'x1':xbounds[ci],'x2':xbounds[ci+1],'y1':row_starts[ri],'y2':row_ends[ri]})
    return cells


def name_text_for_cell(img,cell,tokens,allow_local_fallback=True):
    H,W=img.shape[:2];a=cell['anchor'];b=a['bbox'];ay1=int(b[1]);ah=max(1,b[3]-b[1]);ty=max(int(cell['y1']),int(ay1-max(H*.15,ah*4.5)))
    nearby=[t for t in tokens if cell['x1']+2<=t['cx']<=cell['x2']-2 and ty<=t['cy']<=ay1-2]
    nearby.sort(key=lambda z:(z['top'],z['left']));texts=[t['text'] for t in nearby[:14]]
    has_name=_has_specific_name(texts); evidence=_normalized_evidence(texts)
    jp0=len(re.findall(r'[一-龥ぁ-んァ-ヶ]',evidence)); latin0=len(re.findall(r'[A-Za-z]',evidence))
    if allow_local_fallback and not has_name and (jp0>=1 or latin0>=2):
        x1=max(0,int(cell['x1'])+2);x2=min(W,int(cell['x2'])-2);y1=max(0,int(ty));y2=max(y1+1,min(H,int(ay1)-2))
        crop=img[y1:y2,x1:x2]
        if crop.size:
            work=cv2.resize(crop,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC)
            try:
                data=pytesseract.image_to_data(work,lang='jpn+eng',config='--psm 6',output_type=pytesseract.Output.DICT,timeout=8)
            except RuntimeError:
                data={'text':[],'conf':[]}
            local_texts=[]
            for i,t in enumerate(data.get('text',[])):
                t=' '.join(str(t).split())
                if not t: continue
                try: conf=float(data.get('conf',[])[i])
                except Exception: conf=-1
                if conf>=60: local_texts.append(t)
            if _has_specific_name(local_texts):
                texts=local_texts;has_name=True;evidence=_normalized_evidence(texts)
    return ' '.join(texts),has_name,evidence


def _load_detection_cache(cache_path:Path,image_path:Path,profile:dict):
    if not cache_path.exists():return None
    try:d=json.loads(cache_path.read_text(encoding='utf-8'))
    except Exception:return None
    if d.get('detector_version')!=PRICE_OCR_VERSION:return None
    if d.get('image_sha256')!=file_sha256(image_path):return None
    if d.get('profile')!=profile:return None
    return d.get('result')


def evaluate_group(g,cache_dir:Path,anchor_cache_dir:Path,min_name_coverage:float,allow_local_fallback:bool=True):
    files=[];missing=[];images=[]
    for it in g.get('images',[]):
        p=cache_dir/cache_name(it['url'])
        if not p.exists():missing.append(p.name);continue
        try:images.append((decode(p),p))
        except Exception as e:return {'id':g['id'],'pass':False,'status':'decode_error','errors':[str(e)]}
        files.append(str(p))
    if missing:return {'id':g['id'],'pass':False,'status':'blocked_missing_original_cache','missing_count':len(missing),'missing_files':missing,'cache_files':files}

    profile=g.get('price_detector',{'mode':'red_only','include_red':True});values=[];assoc=[];image_rows=[]
    for img,p in images:
        det=_load_detection_cache(anchor_cache_dir/(p.stem+'.json'),p,profile)
        cache_hit=det is not None
        if det is None:det=detect_price_anchors(img,profile)
        broad=det.get('broad_anchors',[]);anchors=det.get('association_anchors',[])
        raw_names=det.get('name_tokens',[])
        if not raw_names:raw_names=extract_name_ocr_tokens(img,int(profile.get('name_ocr_height',700)))
        tokens=_name_tokens_from_raw(raw_names);cells=anchor_cells(anchors,*img.shape[:2]) if anchors else []
        values.extend(a['value'] for a in broad);good=0
        for cell in cells:
            a=cell['anchor'];txt,has_name,evidence=name_text_for_cell(img,cell,tokens,allow_local_fallback=allow_local_fallback);good+=int(has_name)
            assoc.append({'image':p.name,'price':a['value'],'bbox':a['bbox'],'cell':[cell['x1'],cell['y1'],cell['x2'],cell['y2']],'name_text':txt,'name_evidence':evidence,'has_name':has_name,'source':a.get('source')})
        image_rows.append({'image':p.name,'anchor_cache_hit':cache_hit,'broad_anchor_count':len(broad),'association_anchor_count':len(anchors),'name_token_count':len(tokens),'name_hits':good})
    recall,matched,fp=multiset_recall(g.get('anchor_prices',[]),values)
    name_count=sum(1 for a in assoc if a['has_name']);coverage=name_count/len(assoc) if assoc else 0.0
    passed=(recall>=float(g.get('minimum_recall',1.0)) and coverage>=min_name_coverage and bool(assoc))
    return {
        'id':g['id'],'pass':passed,'status':'original_product_association_ran','detector_version':PRICE_OCR_VERSION,
        'price_recall':recall,'price_threshold':g.get('minimum_recall'),'expected_anchor_count':len(g.get('anchor_prices',[])),
        'detected_anchor_count':len(values),'matched_anchor_count':matched,'association_anchor_count':len(assoc),
        'name_association_count':name_count,'name_association_total':len(assoc),'name_coverage':coverage,'name_coverage_threshold':min_name_coverage,
        'cache_files':files,'images':image_rows,'local_fallback_enabled':allow_local_fallback,'unmatched_detection_sample':fp[:30],'association_sample':assoc[:40],
    }


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',default=str(ROOT/'fixtures'/'remote_regression_manifest.json'));ap.add_argument('--cache-dir',default=str(ROOT/'data'/'remote_cache'));ap.add_argument('--anchor-cache-dir',default=str(ROOT/'data'/'anchor_cache'));ap.add_argument('--report',default=str(ROOT/'reports'/'original_product_e2e_v1_9.json'));ap.add_argument('--min-name-coverage',type=float,default=.55);ap.add_argument('--local-fallback',action='store_true',help='Enable expensive per-cell OCR fallback. Off by default for real-image release validation.');a=ap.parse_args()
    manifest=json.loads(Path(a.manifest).read_text(encoding='utf-8'))
    groups=[evaluate_group(g,Path(a.cache_dir),Path(a.anchor_cache_dir),a.min_name_coverage,allow_local_fallback=a.local_fallback) for g in manifest.get('groups',[])]
    out={'version':'v1.9','detector_version':PRICE_OCR_VERSION,'pass':all(g.get('pass',False) for g in groups),'groups':groups,'interpretation':'Broad anchors validate price recall; narrower association anchors partition product-name cells. Exact-name correctness remains protected by local/synthetic ground-truth regressions.'}
    Path(a.report).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pass':out['pass'],'groups':[{'id':g['id'],'pass':g.get('pass'),'price_recall':g.get('price_recall'),'name_coverage':g.get('name_coverage'),'assoc':g.get('association_anchor_count')} for g in groups]},ensure_ascii=False))
    raise SystemExit(0 if out['pass'] else 1)
if __name__=='__main__':main()
