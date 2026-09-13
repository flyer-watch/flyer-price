from __future__ import annotations
import fcntl,json,subprocess,sys,time
from pathlib import Path
from vnext_common import ROOT,DATA,sha256

REPORT=ROOT/'reports'/'DISTRIBUTION_RELEASE_GATE_vnext.json'
PUBLIC=[DATA/'products.csv',DATA/'products_publish.csv',ROOT/'preview'/'data.js',ROOT/'docs'/'data.js',DATA/'current_issue_manifest.json']

def run(label,cmd,expect=0,timeout=180):
    t=time.time()
    try:
        p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
        rc=p.returncode; out=p.stdout or ''; err=p.stderr or ''
    except subprocess.TimeoutExpired as e:
        rc=124
        out=(e.stdout or '') if isinstance(e.stdout,str) else ((e.stdout or b'').decode('utf-8','replace') if e.stdout else '')
        err=(e.stderr or '') if isinstance(e.stderr,str) else ((e.stderr or b'').decode('utf-8','replace') if e.stderr else '')
    row={'label':label,'pass':rc==expect,'rc':rc,'seconds':round(time.time()-t,2),'stdout_tail':out[-1800:],'stderr_tail':err[-1800:]}
    print(json.dumps(row,ensure_ascii=False),flush=True)
    return row

def hashes():
    return {str(p.relative_to(ROOT)):sha256(p) for p in PUBLIC if p.exists()}

def main():
    lock=(ROOT/'.distribution_gate.lock').open('w')
    try: fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps({'pass':False,'error':'distribution_gate_already_running'},ensure_ascii=False)); return 73
    steps=[]
    steps.append(run('1_python_syntax',[sys.executable,'-m','py_compile',*map(str,sorted((ROOT/'src').glob('*.py')))]))
    steps.append(run('2_legacy_quick_regressions',[sys.executable,str(ROOT/'src'/'run_local_regressions.py')],timeout=120))
    steps.append(run('3_restore_verified_release',[sys.executable,str(ROOT/'src'/'promotion.py'),'--staging',str(DATA/'staging'/'products.csv')],timeout=120))
    base=hashes()
    s4=run('4_auto_update_fail_closed',[sys.executable,str(ROOT/'src'/'auto_update.py'),'--simulate-new-issue-failure'],timeout=60)
    s4['public_unchanged']=hashes()==base; s4['pass']=s4['pass'] and s4['public_unchanged']; steps.append(s4)
    steps.append(run('5_source_discovery_fixture',[sys.executable,str(ROOT/'src'/'source_discovery.py'),'--fixture-test'],timeout=45))
    steps.append(run('6_no_count_floor_regression',[sys.executable,str(ROOT/'src'/'run_no_count_floor_regression.py')],timeout=45))
    steps.append(run('7_continuous_future_issue_regression',[sys.executable,str(ROOT/'src'/'run_continuous_update_regression.py')],timeout=180))
    steps.append(run('8_final_display_dom_gate',[sys.executable,str(ROOT/'src'/'final_display_gate.py')],timeout=120))
    passed=all(x.get('pass',False) for x in steps)
    result={'version':'vNext-continuous-20260913g-source-accuracy','pass':passed,'steps':steps,'public_sha256':hashes(),'third_party_originals_required_for_distribution_gate':False}
    REPORT.parent.mkdir(exist_ok=True); REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pass':passed,'failed':[x['label'] for x in steps if not x.get('pass')],'report':str(REPORT)},ensure_ascii=False))
    return 0 if passed else 1
if __name__=='__main__': raise SystemExit(main())
