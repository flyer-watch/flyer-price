from __future__ import annotations
import json,shutil,subprocess,sys,time,fcntl
from pathlib import Path
from vnext_common import ROOT,DATA,PREVIEW,DOCS,sha256,read_csv,write_csv

REPORT=ROOT/'reports'/'FINAL_RELEASE_GATE_vnext.json'
PUBLIC=[DATA/'products.csv',DATA/'products_publish.csv',PREVIEW/'data.js',DOCS/'data.js']

def run(label,cmd,expect=0,timeout=150):
    print(json.dumps({'stage_start':label,'timeout':timeout},ensure_ascii=False),flush=True)
    t=time.time()
    stdout=''; stderr=''
    try:
        p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
        ok=(p.returncode==expect); rc=p.returncode
        stdout=p.stdout or ''; stderr=p.stderr or ''
    except subprocess.TimeoutExpired as e:
        ok=False; rc=124
        stdout=(e.stdout or '') if isinstance(e.stdout,str) else ((e.stdout or b'').decode('utf-8','replace') if e.stdout else '')
        stderr=(e.stderr or '') if isinstance(e.stderr,str) else ((e.stderr or b'').decode('utf-8','replace') if e.stderr else '')
    row={'label':label,'pass':ok,'rc':rc,'seconds':round(time.time()-t,2),'stdout_tail':stdout[-2000:],'stderr_tail':stderr[-2000:] if rc!=124 else (stderr[-1500:]+f'\ntimeout {timeout}s')}
    print(json.dumps({'stage_end':label,'pass':ok,'rc':rc,'seconds':row['seconds']},ensure_ascii=False),flush=True)
    return row

def hashes(): return {str(p.relative_to(ROOT)):sha256(p) for p in PUBLIC}

def main():
    lock_path=ROOT/'.run_all_gates.lock'
    lock_file=lock_path.open('w')
    try:
        fcntl.flock(lock_file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps({'pass':False,'error':'run_all_gates_already_running','lock':str(lock_path)},ensure_ascii=False))
        return 73
    steps=[]
    # 1. Syntax for entire Python surface.
    steps.append(run('1_python_syntax',[sys.executable,'-m','py_compile',*map(str,sorted((ROOT/'src').glob('*.py')))]))
    # 2. Legacy quick regressions; recognition fingerprint proves the v1.9 core is unchanged.
    steps.append(run('2_legacy_quick_regressions',[sys.executable,str(ROOT/'src'/'run_local_regressions.py')],timeout=90))
    # Legacy preview build intentionally points at old beta data; immediately restore production release before any release check.
    steps.append(run('restore_verified_release_after_legacy',[sys.executable,str(ROOT/'src'/'promotion.py'),'--staging',str(DATA/'staging'/'products.csv')],timeout=90))
    # 3. Provenance integrity of development originals when that private cache is present.
    # Distribution ZIP intentionally excludes third-party flyer binaries, so absence
    # of that cache is an explicit SKIP rather than a release failure.
    prov=DATA/'remote_cache'/'source_provenance.json'
    if prov.exists():
        steps.append(run('3_original_source_provenance',[sys.executable,str(ROOT/'src'/'run_source_provenance_check.py')],timeout=45))
    else:
        steps.append({'label':'3_original_source_provenance','pass':True,'skipped':True,'reason':'third_party_originals_not_bundled_in_distribution'})
    # 4. Verified staging rows pass structural/provenance checks without any product-count floor.
    steps.append(run('4_staging_release_gate',[sys.executable,str(ROOT/'src'/'final_display_gate.py'),'--csv',str(DATA/'staging'/'products.csv'),'--skip-artifacts','--skip-dom'],timeout=45))
    # 5. Successful transactional promotion including real DOM.
    steps.append(run('5_transactional_promotion',[sys.executable,str(ROOT/'src'/'promotion.py'),'--staging',str(DATA/'staging'/'products.csv')],timeout=90))
    base=hashes()
    # 6. Bad staging is rejected before write, public hashes unchanged.
    bad=DATA/'staging'/'gate_negative.csv'; source=read_csv(DATA/'staging'/'products.csv'); badrows=[dict(r) for r in source]
    # Negative fixture is invalid because it contains an impossible zero price,
    # not because any store has "too few" products.
    badrows[0]['price_in_tax_yen']='0'
    write_csv(bad,badrows,list(source[0].keys()))
    s6=run('6_bad_staging_fail_closed',[sys.executable,str(ROOT/'src'/'promotion.py'),'--staging',str(bad)],expect=2,timeout=45)
    s6['public_unchanged']=(hashes()==base); s6['pass']=s6['pass'] and s6['public_unchanged']; steps.append(s6)
    # 7. Fault injection at all mutation phases, each must rollback byte-identically.
    faults=[]
    for f in ('after_canonical','after_build','after_gate'):
        before=hashes(); rr=run('fault_'+f,[sys.executable,str(ROOT/'src'/'promotion.py'),'--staging',str(DATA/'staging'/'products.csv'),'--fault',f],expect=3,timeout=90)
        rr['public_unchanged']=(hashes()==before); rr['pass']=rr['pass'] and rr['public_unchanged']; faults.append(rr)
    steps.append({'label':'7_fault_injection_rollback','pass':all(x['pass'] for x in faults),'cases':faults})
    # 8. Discovery parser regression + a simulated new-issue extraction failure must keep public release unchanged.
    d1=run('source_discovery_fixture',[sys.executable,str(ROOT/'src'/'source_discovery.py'),'--fixture-test'],timeout=30)
    before=hashes(); d2=run('auto_update_fail_closed',[sys.executable,str(ROOT/'src'/'auto_update.py'),'--simulate-new-issue-failure'],timeout=45); d2['public_unchanged']=(hashes()==before); d2['pass']=d2['pass'] and d2['public_unchanged']
    steps.append({'label':'8_auto_update_safety','pass':d1['pass'] and d2['pass'],'discovery':d1,'fail_closed':d2})
    # 9. Final release artifact and Chromium interaction gate.
    steps.append(run('9_final_display_dom_gate',[sys.executable,str(ROOT/'src'/'final_display_gate.py')],timeout=90))
    passed=all(s.get('pass',False) for s in steps)
    result={'version':'vNext-20260913g-source-accuracy','pass':passed,'stages':9,'steps':steps,'public_sha256':hashes() if all(p.exists() for p in PUBLIC) else {},'final_gate':json.loads((ROOT/'reports'/'final_display_gate_vnext.json').read_text(encoding='utf-8')) if (ROOT/'reports'/'final_display_gate_vnext.json').exists() else None}
    REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pass':passed,'stages':9,'failed':[s['label'] for s in steps if not s.get('pass')],'report':str(REPORT)},ensure_ascii=False))
    return 0 if passed else 1
if __name__=='__main__': raise SystemExit(main())
