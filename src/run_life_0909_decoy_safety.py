from __future__ import annotations
import argparse,csv,json,sys,time
from pathlib import Path
import cv2
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from uniform_group_children import recover_uniform_children

DEFAULT_IMAGE=ROOT/'fixtures'/'uniform99_synthetic_v1_9_3.png'
DECOYS=[
 {'name':'国産りんご大玉','specification':'2個入'},
 {'name':'北海道低脂肪牛乳','specification':'1000ml'},
 {'name':'木綿豆腐','specification':'3個入'},
 {'name':'熟成ももハム','specification':'4枚入'},
 {'name':'冷凍そらまめ','specification':'250g'},
 {'name':'温泉たまご','specification':'10個入'},
 {'name':'焼きかまぼこ','specification':'5本入'},
 {'name':'加糖ヨーグルト','specification':'400g'},
]

def refs(path):
 with Path(path).open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
 return [r for r in rows if r.get('source_type')=='uniform99_synthetic']

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--image',default=str(DEFAULT_IMAGE))
 ap.add_argument('--candidates',default=str(ROOT/'fixtures'/'uniform99_synthetic_candidates_v1_9_3.csv'))
 ap.add_argument('--report',default=str(ROOT/'reports'/'life_0909_uniform_children_decoy_safety_v1_9_3.json'))
 a=ap.parse_args(); t=time.time()
 truth=refs(a.candidates)
 records=[{'name':r['product_name'],'specification':r.get('specification') or ''} for r in truth]+DECOYS
 names=[r['name'] for r in records]
 img=cv2.imread(a.image)
 if img is None: raise FileNotFoundError(a.image)
 res=recover_uniform_children(img,names,candidate_records=records)
 got=set(res['resolved'])
 expected=[r['product_name'] for r in truth]
 decoy_names=[r['name'] for r in DECOYS]
 missing=[n for n in expected if n not in got]
 false=[n for n in decoy_names if n in got]
 rep={
  'version':'v1.9.3','expected_count':len(expected),'decoy_count':len(decoy_names),
  'expected_resolved':len(expected)-len(missing),'missing_expected':missing,
  'false_positive_decoys':false,'elapsed_sec':round(time.time()-t,2),
  'pass':not missing and not false,
 }
 Path(a.report).write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(rep,ensure_ascii=False))
 raise SystemExit(0 if rep['pass'] else 1)
if __name__=='__main__': main()
