from __future__ import annotations
import csv, json, shutil
from pathlib import Path
from output_policy import apply_output_policy

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data'/'local_beta_products.csv'
OUT_CSV=ROOT/'data'/'local_beta_products_filtered.csv'
OUT_JS=ROOT/'preview'/'data.js'
DOCS=ROOT/'docs'

with SRC.open('r',encoding='utf-8-sig',newline='') as f:
    rows=list(csv.DictReader(f))

# Normalize empty CSV fields and numeric values before the shared policy.
for r in rows:
    for k,v in list(r.items()):
        if v=='': r[k]=None
    for k in ('price_ex_tax_yen','price_in_tax_yen'):
        if r.get(k) not in (None,''):
            try: r[k]=float(r[k])
            except ValueError: pass
    if r.get('tax_rate') not in (None,''):
        try: r['tax_rate']=float(r['tax_rate'])
        except ValueError: pass

filtered=apply_output_policy(rows)
fields=list(rows[0].keys()) if rows else []
with OUT_CSV.open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
    w.writeheader(); w.writerows(filtered)

payload={
    'meta':{
        'version':'local-beta-v1.9',
        'total':len(filtered),
        'price_rule':'税込価格・小数点以下切り捨て',
        'household_goods':'excluded',
    },
    'products':filtered,
}
OUT_JS.write_text('window.FLYER_DATA='+json.dumps(payload,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
DOCS.mkdir(parents=True,exist_ok=True)
for name in ('index.html','app.js','date_utils.js','data.js'):
    shutil.copy2(ROOT/'preview'/name,DOCS/name)
print(json.dumps({'input_rows':len(rows),'output_rows':len(filtered),'excluded':len(rows)-len(filtered),'csv':str(OUT_CSV),'js':str(OUT_JS),'docs':str(DOCS)},ensure_ascii=False))
