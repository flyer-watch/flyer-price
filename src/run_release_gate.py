from __future__ import annotations
import argparse, json, pathlib, subprocess, sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
REPORTS=ROOT/'reports'
sys.path.insert(0,str(ROOT/'src'))
from recognition_fingerprint import validate_recognition_fingerprint


def load(name):
    p=REPORTS/name
    if not p.exists(): return None
    try: return json.loads(p.read_text(encoding='utf-8'))
    except Exception: return None


def report_pass(name,key='pass'):
    d=load(name)
    if d is None: return {'pass':False,'reason':'missing_or_bad_report','report':name}
    return {'pass':bool(d.get(key)),'report':name}


def remote_group(report,group_id):
    if not report:return None
    return next((g for g in report.get('groups',[]) if g.get('id')==group_id),None)


def cache_gate(group):
    if group is None:return {'pass':False,'status':'missing_remote_group'}
    return {
        'pass':bool(group.get('pass')),
        'status':'original_cache_regression_ran',
        'recall':group.get('recall'),'threshold':group.get('threshold'),
        'candidate_density_pass':group.get('candidate_density_pass'),
        'errors':group.get('errors',[]),'cache_files':group.get('cache_files',[]),
    }


def product_gate(report,*ids):
    if not report:return {'pass':False,'status':'missing_product_e2e_report'}
    found={g.get('id'):g for g in report.get('groups',[])}
    gs=[found.get(i,{'id':i,'pass':False,'status':'missing_group'}) for i in ids]
    return {'pass':all(g.get('pass',False) for g in gs),'groups':gs}


def provenance_gate(report):
    if not report:return {'pass':False,'status':'missing_provenance_report'}
    return {'pass':bool(report.get('pass')),'status':report.get('status'),'required_count':report.get('required_count'),'valid_count':report.get('valid_count'),'provenance_path':report.get('provenance_path')}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',default=str(REPORTS/'release_gate_v1_9.json')); a=ap.parse_args()
    src_files=[str(p) for p in sorted((ROOT/'src').glob('*.py'))]
    syntax=subprocess.run([sys.executable,'-m','py_compile',*src_files],capture_output=True,text=True)
    fp9=validate_recognition_fingerprint(ROOT/'src',ROOT/'fixtures'/'recognition_source_fingerprint_v1_9.json')
    fp7=validate_recognition_fingerprint(ROOT/'src',ROOT/'fixtures'/'recognition_source_fingerprint_v1_7.json')
    expected_core_delta=(fp7.get('changed')==['generic_price_detector.py'] and not fp7.get('missing') and not fp7.get('unexpected'))

    temporal=load('temporal_rules_current_flyers_v1_1.json') or {}
    mixed=load('synthetic_comodi_mixed_v1_4.json') or {}; nested=load('synthetic_comodi_nested_v1_4.json') or {}
    checks={
      'python_syntax':{'pass':syntax.returncode==0,'stderr':syntax.stderr[-2000:]},
      'source_provenance_positive_negative_current':report_pass('source_provenance_regression_v1_9.json'),
      'recognition_fingerprint_positive_negative_current':report_pass('recognition_fingerprint_regression_v1_9.json'),
      'recognition_source_matches_v1_9_baseline':fp9,
      'v1_7_to_v1_9_core_delta_only_generic_price_detector':{'pass':expected_core_delta,'changed':fp7.get('changed',[]),'missing':fp7.get('missing',[]),'unexpected':fp7.get('unexpected',[])},
      'output_policy_current':report_pass('output_policy_v1_9.json'),
      'preview_docs_ui_current':report_pass('preview_regression_v1_9.json'),
      'remote_manifest_current':report_pass('remote_regression_manifest_validation_v1_9.json'),
      'life_0909_uniform_e2e_current':report_pass('life_0909_uniform_e2e_v1_9_3.json'),
      'life_0909_decoy_precision_current':report_pass('life_0909_uniform_children_decoy_safety_v1_9_3.json'),
      'product_association_positive_negative_current':report_pass('original_product_e2e_runner_regression_v1_9.json'),
      # The following logic is unchanged from v1.7; only generic_price_detector.py differs.
      'life_0910_names_inherited_unchanged_core':{'pass':bool((load('life_0910_names_v1_4.json') or {}).get('name_pass')),'report':'life_0910_names_v1_4.json'},
      'life_segmentation_inherited_unchanged_core':{'pass':bool((load('life_segmentation_regression_v1_4.json') or {}).get('segmentation_pass')),'report':'life_segmentation_regression_v1_4.json'},
      'numeric_name_resolution_inherited_unchanged_core':report_pass('numeric_name_resolution_v1_4.json'),
      'source_adapter_inherited_unchanged_core':report_pass('source_adapter_offline_v1_4.json'),
      'temporal_rules_inherited_unchanged_core':{'pass':bool(temporal.get('total')) and temporal.get('passed')==temporal.get('total') and bool((temporal.get('composite_date_time') or {}).get('pass')) and bool((temporal.get('start_date_parent_end') or {}).get('pass')) and bool((temporal.get('explicit_date_outside_parent') or {}).get('pass')),'report':'temporal_rules_current_flyers_v1_1.json','passed':temporal.get('passed'),'total':temporal.get('total')},
      'comodi_mixed_temporal_scope_inherited':{'pass':bool(mixed.get('scope_pass',False)),'report':'synthetic_comodi_mixed_v1_4.json'},
      'comodi_nested_temporal_scope_inherited':{'pass':bool(nested.get('scope_pass',False)),'report':'synthetic_comodi_nested_v1_4.json'},
    }

    remote=load('remote_regression_offline_cache_v1_9.json')
    product=load('original_product_e2e_v1_9.json')
    prov=provenance_gate(load('source_provenance_current_v1_9.json'))
    l9=cache_gate(remote_group(remote,'life_0909')); l12=cache_gate(remote_group(remote,'life_0912')); ok=cache_gate(remote_group(remote,'ok_0907')); com=cache_gate(remote_group(remote,'comodi_0909'))
    real={
      'original_source_provenance_integrity':prov,
      'life_original_price_anchor_regression':{'pass':l9['pass'] and l12['pass'],'groups':{'life_0909':l9,'life_0912':l12}},
      'ok_original_price_anchor_regression':ok,
      'comodi_original_price_anchor_regression':com,
      'life_original_product_extraction_e2e':product_gate(product,'life_0909','life_0912'),
      'ok_original_product_extraction_e2e':product_gate(product,'ok_0907'),
      'comodi_original_product_extraction_e2e':product_gate(product,'comodi_0909'),
    }
    functional=all(v.get('pass',False) for v in checks.values())
    ready=bool(functional and all(v.get('pass',False) for v in real.values()))
    blockers=[k for k,v in real.items() if not v.get('pass',False)]
    out={'version':'v1.9.3','checks':checks,'real_image_gates':real,'functional_regression_pass':functional,'github_release_ready':ready,'blocking_reasons':blockers,'interpretation':'v1.9 changes the generic price detector only in recognition core. That delta is covered by current real-image price regression and current positive/negative association regressions. GitHub release requires all functional and original-image gates to pass.'}
    pathlib.Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'functional_regression_pass':functional,'github_release_ready':ready,'blocking_reasons':blockers,'core_delta_from_v1_7':fp7.get('changed',[])},ensure_ascii=False))
    return 0 if ready else 1

if __name__=='__main__': raise SystemExit(main())
