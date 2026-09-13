from __future__ import annotations
import json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
 js=(ROOT/'preview'/'data.js').read_text(encoding='utf-8').strip()
 m=re.fullmatch(r'window\.FLYER_DATA=(.*);',js,flags=re.S)
 if not m: raise SystemExit('bad data.js wrapper')
 data=json.loads(m.group(1)); rows=data['products']
 stores=sorted({r['store_id'] for r in rows})
 node="require('./preview/date_utils.js'); console.log(JSON.stringify(globalThis.FLYER_DATE_UTILS.isoDates('2026-09-09','2026-09-11')));"
 p=subprocess.run(['node','-e',node],cwd=ROOT,capture_output=True,text=True)
 dates=json.loads(p.stdout.strip()) if p.returncode==0 and p.stdout.strip() else None
 index=(ROOT/'preview'/'index.html').read_text(encoding='utf-8')
 app=(ROOT/'preview'/'app.js').read_text(encoding='utf-8')
 checks={
  'node_available_and_date_utils_runs':p.returncode==0,
  'jst_safe_date_sequence':dates==['2026-09-09','2026-09-10','2026-09-11'],
  'date_utils_loaded_before_app':index.find('date_utils.js')!=-1 and index.find('date_utils.js')<index.find('app.js'),
  'stores_are_data_driven':'const storeMap=new Map()' in app and 'comodi_sakuragawa' not in app,
  'no_empty_store_tab_source':stores==['life_hikawadai','ok_kamiitabashi'],
  'meta_v1_9':data.get('meta',{}).get('version')=='local-beta-v1.9',
  'docs_files_match_preview':all((ROOT/'docs'/n).exists() and (ROOT/'docs'/n).read_bytes()==(ROOT/'preview'/n).read_bytes() for n in ('index.html','app.js','date_utils.js','data.js')),
  'row_count_49':len(rows)==49,
  'all_prices_integer_positive':all(isinstance(r.get('price_in_tax_yen'),int) and r['price_in_tax_yen']>0 for r in rows),
  'no_household_category':all(r.get('category')!='日用品' for r in rows),
 }
 rep={'version':'v1.9','stores':stores,'date_test':dates,'checks':checks,'pass':all(checks.values())}
 (ROOT/'reports'/'preview_regression_v1_9.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(rep,ensure_ascii=False))
 raise SystemExit(0 if rep['pass'] else 1)
if __name__=='__main__':main()
