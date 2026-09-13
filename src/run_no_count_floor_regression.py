from __future__ import annotations
import json
from vnext_common import validate_rows
from runtime_gate import validate_runtime_issue

def row(day='2026-09-20'):
    return {
        'store_id':'belx_itabashi_nakadai','chain':'スーパーベルクス','store_name':'板橋中台店',
        'sale_start':day,'sale_end':day,'product_name':'検証商品','specification':'1個',
        'price_ex_tax_yen':'100','price_in_tax_yen':'108','tax_rate':'0.08','promotion':'','category':'食品',
        'availability_rule':'','scope_level':'source_evidence','source_type':'runtime_local_ocr',
        'validation_status':'auto_strict','source_url':'https://example.invalid/flyer.jpg',
        'source_image':'fixture.jpg','source_fingerprint':'fp','verification_note':'count-floor regression'
    }

def main():
    # One published product and zero products active on the chosen day are both
    # legitimate. Count alone must never fail release.
    rows=[row('2026-09-20')]
    structural=validate_rows(rows,day='2026-09-19',require_gates=True)
    manifest={
        'groups':[{'store_id':'belx_itabashi_nakadai','images':['https://example.invalid/flyer.jpg'],'fingerprint':'fp'}],
        'extraction':{'stores':{'belx_itabashi_nakadai':{'images':1,'price_anchors':1,'candidate_rows':1}}}
    }
    runtime=validate_runtime_issue(rows,manifest)
    result={'pass':bool(structural.get('pass') and runtime.get('pass') and structural.get('active_counts',{}).get('belx_itabashi_nakadai',0)==0),
            'structural':structural,'runtime':runtime,'assertion':'one total row / zero active rows is allowed when source evidence is valid'}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
