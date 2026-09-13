from __future__ import annotations
import argparse,hashlib,json,re,sys,unicodedata
from pathlib import Path
import cv2,numpy as np
from generic_price_detector import detect_price_anchors,extract_name_ocr_tokens
from run_original_product_e2e import _name_tokens_from_raw,anchor_cells,name_text_for_cell
from price_policy import tax_included_from_ex_tax
from vnext_output_policy import apply_output_policy
from vnext_common import ROOT,write_csv,is_household_name
from partitioned_temporal_regions import infer_partitioned_regions,assign as assign_partitioned
from temporal_region_inference import infer_comodi_nested_regions,assign_point_scope

GENERIC=('税込','税抜','本体','価格','限り','販売','お買得','お買い得','当り','あたり','より','チラシ','ポイント','クーポン','店舗','特売','セール')

def decode(p:Path):
    a=np.frombuffer(p.read_bytes(),np.uint8); return cv2.imdecode(a,cv2.IMREAD_COLOR)

def clean_name(text:str)->str:
    parts=[]
    for raw in re.split(r'\s+',unicodedata.normalize('NFKC',text or '')):
        t=raw.strip('・/／()（）[]【】<>「」『』:：,，.。')
        if len(t)<2 or len(t)>42: continue
        if any(x in t for x in GENERIC): continue
        if re.fullmatch(r'[\d.,%％+\-〜~円]+',t): continue
        if re.search(r'\d{1,4}(?:g|kg|ml|L|個|本|枚|袋|入|パック|束|尾|切)$',t,re.I): continue
        if not re.search(r'[一-龥ぁ-んァ-ヶA-Za-z]',t): continue
        bad=sum(ch in '□■●▲▼※★☆→←' for ch in t)
        if bad: continue
        parts.append(t)
    if not parts: return ''
    # Product labels tend to be the longest specific OCR fragment in the local panel.
    parts=sorted(set(parts),key=lambda s:(len(s),s),reverse=True)
    return parts[0]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--manifest',required=True); ap.add_argument('--cache-dir',required=True); ap.add_argument('--out',required=True); ap.add_argument('--report'); a=ap.parse_args()
    manifest=json.loads(Path(a.manifest).read_text(encoding='utf-8')); cache=Path(a.cache_dir); rows=[]; stats={}; daily_dates=set()
    for g in manifest.get('groups',[]):
        if not g.get('ok'): continue
        for imeta in g.get('local_images',[]):
            p=cache/imeta['cache_filename']; img=decode(p)
            if img is None: continue
            # Layout-adaptive detection: red price glyphs are common but are not
            # assumed. Hybrid OCR adds black/other-colour numeric anchors and
            # Japanese name tokens. This deliberately avoids fixed per-layout
            # coordinates or product-count expectations.
            profile={
                'mode':'hybrid_ocr','include_red':True,
                'jpn_heights':[900],'digit_heights':[1300],
                'otsu_digit_heights':[],'association_min_confidence':8,
                'association_min_height_ratio':0.007,
            }
            det=detect_price_anchors(img,profile); anchors=det.get('association_anchors',[])
            st=stats.setdefault(g['store_id'],{'images':0,'price_anchors':0,'candidate_rows':0,'pages':[]}); st['images']+=1; st['price_anchors']+=len(anchors)
            page_stat={'source_index':imeta.get('source_index'),'cache_filename':imeta.get('cache_filename'),'price_anchors':len(anchors),'raw_candidate_rows':0,'ocr_observations':det.get('observations',[])}
            st['pages'].append(page_stat)
            raw=det.get('name_tokens') or extract_name_ocr_tokens(img,900); tokens=_name_tokens_from_raw(raw)
            year=int(str(g.get('sale_start','2026'))[:4] or 2026)
            try:
                if g.get('store_id')=='comodi_sakuragawa':
                    temporal=infer_comodi_nested_regions(img,g['sale_start'],g['sale_end'])
                    regions=temporal.get('regions',[])
                    for z in regions:
                        if z.get('sale_start') and z.get('sale_start')==z.get('sale_end'): daily_dates.add(z['sale_start'])
                    scope_for=lambda x,y: assign_point_scope(x,y,regions)
                else:
                    temporal=infer_partitioned_regions(img,g['sale_start'],g['sale_end'],year=year)
                    regions=temporal.get('regions',[])
                    for z in regions:
                        if z.get('sale_start') and z.get('sale_start')==z.get('sale_end'): daily_dates.add(z['sale_start'])
                    scope_for=lambda x,y: assign_partitioned(x,y,regions)
            except Exception:
                regions=[]
                scope_for=lambda x,y: None
            for cell in anchor_cells(anchors,*img.shape[:2]):
                txt,has,_=name_text_for_cell(img,cell,tokens,allow_local_fallback=True)
                if not has: continue
                name=clean_name(txt)
                if not name: continue
                ex=int(cell['anchor']['value'])
                if ex<=0 or ex>10000: continue
                household=is_household_name(name)
                tax_rate=0.10 if household else 0.08
                inc=tax_included_from_ex_tax(ex,tax_rate)
                a0=cell['anchor']; b=a0.get('bbox') or [a0.get('cx',0),a0.get('cy',0),a0.get('cx',0),a0.get('cy',0)]
                cx=float(a0.get('cx',(b[0]+b[2])/2)); cy=float(a0.get('cy',(b[1]+b[3])/2))
                scope=scope_for(cx,cy) or {}
                sale_start=scope.get('sale_start') or g['sale_start']; sale_end=scope.get('sale_end') or g['sale_end']
                src=g['images'][imeta['source_index']]
                rows.append({'store_id':g['store_id'],'chain':g['chain'],'store_name':g['store_name'],'sale_start':sale_start,'sale_end':sale_end,'product_name':name,'specification':'','price_ex_tax_yen':ex,'price_in_tax_yen':inc,'tax_rate':tax_rate,'promotion':'','category':('日用品' if household else '食品'),'availability_rule':scope.get('availability_rule',''),'scope_level':scope.get('date_source','page_default'),'source_type':'runtime_local_ocr','validation_status':'auto_strict','source_url':src,'source_image':imeta['cache_filename'],'source_fingerprint':g.get('fingerprint',''),'verification_note':'automatic local OCR candidate with temporal scope'})
                page_stat['raw_candidate_rows']+=1
    rows=apply_output_policy(rows)
    # Stronger de-dupe by store/name/price to prevent repeated OCR fragments.
    out=[]; seen=set()
    for r in rows:
        k=(r['store_id'],re.sub(r'\s+','',r['product_name']),r['price_in_tax_yen'])
        if k in seen: continue
        seen.add(k); out.append(r)
    for r in out:
        stats.setdefault(r['store_id'],{'images':0,'price_anchors':0,'candidate_rows':0,'pages':[]})['candidate_rows']+=1
        if r.get('sale_start') and r.get('sale_start')==r.get('sale_end'): daily_dates.add(r['sale_start'])
    for sid,st in stats.items():
        by_image={}
        for r in out:
            if r.get('store_id')==sid:
                by_image[r.get('source_image','')]=by_image.get(r.get('source_image',''),0)+1
        for pg in st.get('pages',[]):
            pg['candidate_rows']=by_image.get(pg.get('cache_filename',''),0)
            pg['unresolved_price_evidence']=max(0,int(pg.get('price_anchors') or 0)-int(pg.get('candidate_rows') or 0))
    fields=list(out[0].keys()) if out else ['store_id','chain','store_name','sale_start','sale_end','product_name','specification','price_ex_tax_yen','price_in_tax_yen','tax_rate','promotion','category','availability_rule','scope_level','source_type','validation_status','source_url','source_image','source_fingerprint','verification_note']
    write_csv(Path(a.out),out,fields)
    report={'rows':len(out),'counts':{sid:sum(r['store_id']==sid for r in out) for sid in set(r['store_id'] for r in out)},'stores':stats,'daily_dates':sorted(daily_dates)}
    if a.report: Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__': main()
