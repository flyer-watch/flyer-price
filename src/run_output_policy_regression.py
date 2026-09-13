from __future__ import annotations
import csv, json, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from output_policy import apply_output_policy, is_household_good


def read_rows(path):
    with Path(path).open('r',encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    for r in rows:
        for k,v in list(r.items()):
            if v=='': r[k]=None
        for k in ('price_ex_tax_yen','price_in_tax_yen','tax_rate'):
            if r.get(k) not in (None,''):
                try: r[k]=float(r[k])
                except (TypeError,ValueError): pass
    return rows


def main():
    synthetic=[
      {'store_id':'s','sale_start':'2026-09-11','sale_end':'2026-09-11','product_name':'食品A','specification':'1個','price_ex_tax_yen':100.9,'price_in_tax_yen':108.9,'tax_rate':0.08,'category':'食品'},
      dict(store_id='s',sale_start='2026-09-11',sale_end='2026-09-11',product_name='食品A',specification='1個',price_ex_tax_yen=100.9,price_in_tax_yen=108.9,tax_rate=0.08,category='食品'),
      {'store_id':'s','sale_start':'2026-09-11','sale_end':'2026-09-11','product_name':'食品B','specification':'','price_ex_tax_yen':199.9,'price_in_tax_yen':None,'tax_rate':0.08,'category':'食品'},
      {'store_id':'s','sale_start':'2026-09-11','sale_end':'2026-09-11','product_name':'食品C','specification':'','price_ex_tax_yen':199.9,'price_in_tax_yen':214.9,'tax_rate':0.08,'category':'食品'},
      {'store_id':'s','sale_start':'2026-09-11','sale_end':'2026-09-11','product_name':'価格なし','specification':'','price_ex_tax_yen':None,'price_in_tax_yen':None,'tax_rate':0.08,'promotion':'20%OFF','category':'食品'},
      {'store_id':'s','sale_start':'2026-09-11','sale_end':'2026-09-11','product_name':'0円誤検出','specification':'','price_ex_tax_yen':0,'price_in_tax_yen':0,'tax_rate':0.08,'category':'食品'},
      {'store_id':'s','sale_start':'2026-09-11','sale_end':'2026-09-11','product_name':'キッチンペーパー','specification':'','price_ex_tax_yen':200,'price_in_tax_yen':220,'tax_rate':0.10,'category':'日用品'},
    ]
    out=apply_output_policy(synthetic)
    real=read_rows(ROOT/'data'/'local_beta_products.csv')
    real_out=apply_output_policy(real)
    keys=[(r.get('store_id'),r.get('sale_start'),r.get('sale_end'),r.get('product_name'),r.get('specification'),r.get('price_in_tax_yen')) for r in real_out]
    checks={
      'dedupe':sum(1 for r in out if r.get('product_name')=='食品A')==1,
      'percent_only_excluded':not any(r.get('product_name')=='価格なし' for r in out),
      'household_excluded':not any(is_household_good(r) for r in out),
      'floor_given_inc':next(r for r in out if r.get('product_name')=='食品A')['price_in_tax_yen']==108,
      'calc_and_floor_inc':next(r for r in out if r.get('product_name')=='食品B')['price_in_tax_yen']==214,
      'zero_price_excluded':not any(r.get('product_name')=='0円誤検出' for r in out),
      'real_53_to_49':len(real)==53 and len(real_out)==49,
      'real_no_household':not any(is_household_good(r) for r in real_out),
      'real_all_included_integer':all(isinstance(r.get('price_in_tax_yen'),int) for r in real_out),
      'real_no_duplicates':len(keys)==len(set(keys)),
      'real_all_positive':all((r.get('price_in_tax_yen') or 0)>0 for r in real_out),
    }
    rep={'version':'v1.9','checks':checks,'synthetic_output':out,'real_input':len(real),'real_output':len(real_out),'pass':all(checks.values())}
    p=ROOT/'reports'/'output_policy_v1_9.json'
    p.write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pass':rep['pass'],'real_input':len(real),'real_output':len(real_out),'checks':checks},ensure_ascii=False))
    raise SystemExit(0 if rep['pass'] else 1)

if __name__=='__main__': main()
