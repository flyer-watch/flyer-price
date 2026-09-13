from __future__ import annotations
import json, shutil
from pathlib import Path
from vnext_common import ROOT,DATA,PREVIEW,DOCS,read_csv,write_csv,CURRENT_JST
from issue_manifest import PATH as ISSUE_MANIFEST

CANON=DATA/'products.csv'; PUB=DATA/'products_publish.csv'
rows=read_csv(CANON)
write_csv(PUB,rows,list(rows[0].keys()) if rows else [])
manifest={}
if ISSUE_MANIFEST.exists():
    manifest=json.loads(ISSUE_MANIFEST.read_text(encoding='utf-8'))
else:
    legacy=DATA/'verified_snapshot_manifest.json'
    if legacy.exists(): manifest=json.loads(legacy.read_text(encoding='utf-8'))
date_buttons=manifest.get('date_buttons') or sorted({r.get('sale_start','') for r in rows if r.get('sale_start') and r.get('sale_start')==r.get('sale_end')})
configured_stores=[{'store_id':g.get('store_id'),'label':f"{g.get('chain','')} {g.get('store_name','')}".strip()} for g in manifest.get('groups',[]) if g.get('store_id')]
payload={'meta':{'version':'vNext-source-accuracy-continuous','generated_jst':CURRENT_JST,'total':len(rows),'price_rule':'税込価格・小数点以下切り捨て','household_goods':'included_if_priced','date_filter':'single_day_only','date_buttons':date_buttons,'stores':configured_stores,'canonical':'data/products.csv'},'products':rows}
PREVIEW.mkdir(parents=True,exist_ok=True); DOCS.mkdir(parents=True,exist_ok=True)
data_js='window.FLYER_DATA='+json.dumps(payload,ensure_ascii=False,separators=(',',':'))+';\n'
(PREVIEW/'data.js').write_text(data_js,encoding='utf-8')
for name in ('index.html','app.js','date_utils.js'):
    shutil.copy2(PREVIEW/name,DOCS/name)
(DOCS/'data.js').write_text(data_js,encoding='utf-8')
print(json.dumps({'rows':len(rows),'canonical':str(CANON),'publish':str(PUB),'date_buttons':date_buttons},ensure_ascii=False))
