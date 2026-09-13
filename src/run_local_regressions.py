from __future__ import annotations
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'; REPORTS=ROOT/'reports'


def run(label,args,timeout=120,quiet=False):
    t=time.time()
    try:
        if quiet:
            p=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=timeout)
            stdout_tail=''; stderr_tail=''
        else:
            p=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=timeout)
            stdout_tail=p.stdout[-1600:]; stderr_tail=p.stderr[-1600:]
        rc=p.returncode; reason=None
    except subprocess.TimeoutExpired:
        rc=124; stdout_tail=''; stderr_tail=f'timeout after {timeout}s'; reason='timeout'
    row={'label':label,'returncode':rc,'pass':rc==0,'seconds':round(time.time()-t,2),'stdout_tail':stdout_tail,'stderr_tail':stderr_tail}
    if reason: row['reason']=reason
    print(json.dumps({'step':label,'pass':row['pass'],'seconds':row['seconds']},ensure_ascii=False),flush=True)
    return row


def report_check(label,name,key='pass'):
    p=REPORTS/name
    if not p.exists():
        row={'label':label,'pass':False,'reason':'missing_report','report':name,'seconds':0.0}
    else:
        try:
            d=json.loads(p.read_text(encoding='utf-8'))
            row={'label':label,'pass':bool(d.get(key)),'report':name,'seconds':0.0}
        except Exception as e:
            row={'label':label,'pass':False,'reason':f'bad_json:{e}','report':name,'seconds':0.0}
    print(json.dumps({'step':label,'pass':row['pass'],'seconds':0.0},ensure_ascii=False),flush=True)
    return row


def main():
    ap=argparse.ArgumentParser(description='Network-free functional regression for flyer_pdca v1.9.3.')
    ap.add_argument('--full',action='store_true',help='Regenerate expensive local OCR regressions instead of validating committed reports.')
    a=ap.parse_args(); results=[]

    results.append(run('python_syntax',['-m','py_compile',*map(str,sorted(SRC.glob('*.py')))]))
    results.append(run('source_provenance_regression',[SRC/'run_source_provenance_regression.py']))
    results.append(run('recognition_fingerprint_regression',[SRC/'run_recognition_fingerprint_regression.py']))
    results.append(run('output_policy',[SRC/'run_output_policy_regression.py']))
    results.append(run('build_preview_docs',[SRC/'build_preview.py']))
    results.append(run('remote_manifest_dry',[SRC/'remote_regression.py','--dry-run','--report',REPORTS/'remote_regression_manifest_validation_v1_9.json']))
    results.append(run('remote_cache_inventory',[SRC/'list_remote_cache_requirements.py']))
    results.append(run('preview_docs_ui',[SRC/'run_preview_regression.py']))

    if a.full:
        results.append(run('life_0909_uniform_e2e',[SRC/'run_life_0909_uniform_e2e.py'],timeout=100,quiet=True))
        results.append(run('life_0909_decoy_safety',[SRC/'run_life_0909_decoy_safety.py'],timeout=100,quiet=True))
        results.append(run('product_association_positive_negative',[SRC/'run_original_e2e_runner_regression.py'],timeout=100,quiet=True))
    else:
        results.append(report_check('life_0909_uniform_e2e_current','life_0909_uniform_e2e_v1_9_3.json'))
        results.append(report_check('life_0909_decoy_safety_current','life_0909_uniform_children_decoy_safety_v1_9_3.json'))
        results.append(report_check('product_association_positive_negative_current','original_product_e2e_runner_regression_v1_9.json'))

    local_pass=all(r.get('pass',False) for r in results)
    rep={'version':'v1.9.3','mode':'full' if a.full else 'quick','local_regression_pass':local_pass,'steps':results}
    (REPORTS/'local_regressions_v1_9.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'version':'v1.9.3','mode':rep['mode'],'local_regression_pass':local_pass,'steps':len(results)},ensure_ascii=False))
    raise SystemExit(0 if local_pass else 1)

if __name__=='__main__': main()
