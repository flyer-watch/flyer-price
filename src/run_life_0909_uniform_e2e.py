from __future__ import annotations
import argparse, csv, json, sys, time
from pathlib import Path
import cv2

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from uniform_price_detector import detect_common_large_price
from uniform_group_children import recover_uniform_children
from price_policy import tax_included_from_ex_tax
from output_policy import apply_output_policy

DEFAULT_IMAGE=ROOT/'fixtures'/'uniform99_synthetic_v1_9_3.png'
DEFAULT_TEMPLATES=ROOT/'fixtures'/'uniform99_synthetic_digit_templates_v1_9_3.npz'


def read_reference_candidates(path: Path):
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    rows=[r for r in rows if r.get('source_type')=='uniform99_synthetic']
    return rows


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--image',default=str(DEFAULT_IMAGE))
    ap.add_argument('--templates',default=str(DEFAULT_TEMPLATES))
    ap.add_argument('--candidates',default=str(ROOT/'fixtures'/'uniform99_synthetic_candidates_v1_9_3.csv'))
    ap.add_argument('--report',default=str(ROOT/'reports'/'life_0909_uniform_e2e_v1_9_3.json'))
    args=ap.parse_args()

    t0=time.time()
    refs=read_reference_candidates(Path(args.candidates))
    candidate_names=[r['product_name'] for r in refs]
    candidate_records=[{'name':r['product_name'],'specification':r.get('specification') or ''} for r in refs]
    img=cv2.imread(args.image)
    if img is None:
        raise FileNotFoundError(args.image)

    parent=detect_common_large_price(args.image,args.templates)
    children=recover_uniform_children(img,candidate_names,candidate_records=candidate_records)
    resolved=set(children['resolved'])

    parent_ok=(parent.get('status')=='common_price_detected' and parent.get('value')==99 and parent.get('scope_level')=='product_group')
    ex_price=parent.get('value') if parent_ok else None
    in_price=tax_included_from_ex_tax(ex_price,0.08) if ex_price is not None else None

    # Reference rows provide candidate metadata only. Detected price fields are
    # deliberately overwritten by the parent common-price detector.
    emitted=[]
    for r in refs:
        if r['product_name'] not in resolved:
            continue
        emitted.append({
            'store_id':r.get('store_id'), 'chain':r.get('chain'), 'store_name':r.get('store_name'),
            'sale_start':r.get('sale_start'), 'sale_end':r.get('sale_end'),
            'product_name':r.get('product_name'), 'specification':r.get('specification'),
            'price_ex_tax_yen':ex_price, 'price_in_tax_yen':in_price, 'tax_rate':0.08,
            'promotion':f'均一本体価格{ex_price}円' if ex_price is not None else None,
            'category':r.get('category'), 'availability_rule':r.get('availability_rule'),
            'scope_level':'product_group_child', 'source_type':'uniform99_e2e_detected',
            'validation_status':'detected',
        })

    filtered=apply_output_policy(emitted)
    names=[r['product_name'] for r in filtered]
    expected_names=[r['product_name'] for r in refs]
    missing=[n for n in expected_names if n not in names]
    duplicates=len(names)-len(set(names))
    price_ok=bool(filtered) and all(r.get('price_ex_tax_yen')==99 and r.get('price_in_tax_yen')==106 for r in filtered)
    periods_ok=bool(filtered) and all(r.get('sale_start')=='2026-09-09' and r.get('sale_end')=='2026-09-11' for r in filtered)
    child_ok=(len(resolved)==len(refs) and len(refs)>0 and not missing)
    output_ok=(len(filtered)==len(refs) and duplicates==0 and price_ok and periods_ok)
    passed=bool(parent_ok and child_ok and output_ok)

    report={
        'version':'v1.9.3',
        'input_image':str(Path(args.image).resolve()),
        'candidate_metadata_source':str(Path(args.candidates).resolve()),
        'candidate_price_fields_used_for_detection':False,
        'parent':parent,
        'parent_pass':parent_ok,
        'expected_children':len(refs),
        'resolved_children':len(resolved),
        'missing_children':missing,
        'children_pass':child_ok,
        'output_rows_before_policy':len(emitted),
        'output_rows_after_policy':len(filtered),
        'duplicate_count':duplicates,
        'all_prices_99_ex_106_in':price_ok,
        'all_sale_periods_2026_09_09_to_09_11':periods_ok,
        'output_policy_pass':output_ok,
        'elapsed_sec':round(time.time()-t0,2),
        'pass':passed,
        'rows':filtered,
    }
    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('parent_pass','expected_children','resolved_children','children_pass','output_rows_after_policy','all_prices_99_ex_106_in','output_policy_pass','elapsed_sec','pass')},ensure_ascii=False))
    raise SystemExit(0 if passed else 1)

if __name__=='__main__':
    main()
