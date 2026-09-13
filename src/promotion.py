from __future__ import annotations
import argparse,json,shutil,subprocess,sys
from pathlib import Path
from vnext_common import ROOT,DATA,PREVIEW,DOCS,read_csv,validate_rows,CURRENT_JST
from issue_manifest import PATH as ISSUE_MANIFEST
from runtime_gate import validate_runtime_issue

PUBLIC=[DATA/'products.csv',DATA/'products_publish.csv',PREVIEW/'data.js',DOCS/'data.js']

def run(cmd):
    p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
    if p.returncode!=0: raise RuntimeError(f'command failed {cmd}: {p.stdout}\n{p.stderr}')
    return p

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--staging',default=str(DATA/'staging'/'products.csv'))
    ap.add_argument('--fault',choices=['after_canonical','after_build','after_gate'])
    ap.add_argument('--gate-mode',choices=['release','runtime'],default='release')
    ap.add_argument('--issue-manifest')
    args=ap.parse_args()
    staging=Path(args.staging); rows=read_csv(staging)
    structural=validate_rows(rows,CURRENT_JST,args.gate_mode=='release')
    errors=list(structural['errors'])
    new_manifest=None
    if args.gate_mode=='runtime':
        if not args.issue_manifest: errors.append('runtime promotion requires --issue-manifest')
        else:
            new_manifest=json.loads(Path(args.issue_manifest).read_text(encoding='utf-8'))
            rg=validate_runtime_issue(rows,new_manifest)
            errors.extend(rg['errors'])
    if errors:
        print(json.dumps({'pass':False,'phase':'pre_gate','errors':errors},ensure_ascii=False)); return 2
    targets=PUBLIC+([ISSUE_MANIFEST] if args.gate_mode=='runtime' else [])
    backup={p:(p.read_bytes() if p.exists() else None) for p in targets}
    try:
        DATA.mkdir(parents=True,exist_ok=True); shutil.copyfile(staging,DATA/'products.csv')
        if args.gate_mode=='runtime' and new_manifest is not None:
            ISSUE_MANIFEST.write_text(json.dumps(new_manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if args.fault=='after_canonical': raise RuntimeError('FAULT after_canonical')
        run([sys.executable,str(ROOT/'src'/'build_from_canonical.py')])
        if args.fault=='after_build': raise RuntimeError('FAULT after_build')
        gate=[sys.executable,str(ROOT/'src'/'final_display_gate.py')]
        if args.gate_mode=='runtime': gate+=['--gate-mode','runtime']
        run(gate)
        if args.fault=='after_gate': raise RuntimeError('FAULT after_gate')
        print(json.dumps({'pass':True,'rows':len(rows),'phase':'promoted','gate_mode':args.gate_mode},ensure_ascii=False)); return 0
    except Exception as e:
        for p,b in backup.items():
            if b is None:
                if p.exists(): p.unlink()
            else:
                p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b)
        print(json.dumps({'pass':False,'phase':'rollback','error':str(e)},ensure_ascii=False)); return 3
if __name__=='__main__': raise SystemExit(main())
