from __future__ import annotations
import argparse, json, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'; REPORTS=ROOT/'reports'


def run(label,args):
    t=time.time()
    p=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,capture_output=True,text=True)
    row={'step':label,'pass':p.returncode==0,'returncode':p.returncode,'seconds':round(time.time()-t,2),'stdout_tail':p.stdout[-2400:],'stderr_tail':p.stderr[-2400:]}
    print(json.dumps({k:row[k] for k in ('step','pass','seconds')},ensure_ascii=False),flush=True)
    return row


def write_report(rows,failed_step=None):
    gate={}
    gp=REPORTS/'release_gate_v1_9.json'
    if gp.exists():
        try: gate=json.loads(gp.read_text(encoding='utf-8'))
        except Exception: gate={}
    passed=(failed_step is None and all(r['pass'] for r in rows) and bool(gate.get('github_release_ready')))
    rep={'version':'v1.9.3','pass':passed,'github_release_ready':bool(gate.get('github_release_ready')),'failed_step':failed_step,'steps':rows}
    (REPORTS/'original_release_validation_v1_9.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8')
    return rep


def main():
    ap=argparse.ArgumentParser(description='Complete reproducible release validation for flyer_pdca v1.9.3.')
    ap.add_argument('--skip-fetch',action='store_true',help='Use already fetched/provenanced original cache.')
    ap.add_argument('--full-functional',action='store_true',help='Regenerate expensive local OCR regressions before the real-image gates.')
    a=ap.parse_args(); rows=[]

    rows.append(run('local_functional_regressions',[SRC/'run_local_regressions.py'] + (['--full'] if a.full_functional else [])))
    if not rows[-1]['pass']:
        rep=write_report(rows,'local_functional_regressions'); print(json.dumps({'pass':False,'github_release_ready':rep['github_release_ready']},ensure_ascii=False)); raise SystemExit(1)

    if not a.skip_fetch:
        rows.append(run('fetch_original_images',[SRC/'fetch_original_images.py']))
        if not rows[-1]['pass']:
            rep=write_report(rows,'fetch_original_images'); print(json.dumps({'pass':False,'github_release_ready':rep['github_release_ready']},ensure_ascii=False)); raise SystemExit(1)

    steps=[
      ('verify_source_provenance',[SRC/'run_source_provenance_check.py']),
      ('original_price_anchor_regression',[SRC/'remote_regression.py','--offline-cache-only','--report',REPORTS/'remote_regression_offline_cache_v1_9.json']),
      ('original_product_e2e',[SRC/'run_original_product_e2e.py','--report',REPORTS/'original_product_e2e_v1_9.json']),
      ('release_gate',[SRC/'run_release_gate.py']),
    ]
    failed=None
    for label,args in steps:
        rows.append(run(label,args))
        if not rows[-1]['pass']:
            failed=label; break
    rep=write_report(rows,failed)
    print(json.dumps({'pass':rep['pass'],'github_release_ready':rep['github_release_ready'],'failed_step':failed,'steps':len(rows)},ensure_ascii=False))
    raise SystemExit(0 if rep['pass'] else 1)

if __name__=='__main__': main()
