from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
from vnext_common import ROOT,DATA,PREVIEW,DOCS,CURRENT_JST,read_csv,parse_data_js,validate_rows,sha256
from issue_manifest import load_manifest
from runtime_gate import validate_runtime_issue

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--csv',default=str(DATA/'products.csv')); ap.add_argument('--skip-artifacts',action='store_true'); ap.add_argument('--skip-dom',action='store_true'); ap.add_argument('--gate-mode',choices=['release','runtime'],default=None); args=ap.parse_args()
    path=Path(args.csv); rows=read_csv(path)
    manifest=load_manifest()
    mode=args.gate_mode or ('runtime' if manifest.get('gate_mode')=='runtime' else 'release')
    r=validate_rows(rows,CURRENT_JST,mode=='release'); errors=list(r['errors'])
    runtime=None
    if mode=='runtime':
        runtime=validate_runtime_issue(rows,manifest); errors.extend(runtime['errors'])
    artifacts={}
    if not args.skip_artifacts:
        canon=DATA/'products.csv'; pub=DATA/'products_publish.csv'; pjs=PREVIEW/'data.js'; djs=DOCS/'data.js'
        req=[canon,pub,pjs,djs]
        missing=[str(x) for x in req if not x.exists()]
        if missing: errors.append('missing_artifacts='+','.join(missing))
        else:
            cr=read_csv(canon); pr=read_csv(pub); pp=parse_data_js(pjs)['products']; dp=parse_data_js(djs)['products']
            counts=[len(cr),len(pr),len(pp),len(dp)]
            if len(set(counts))!=1: errors.append(f'artifact_count_mismatch={counts}')
            if cr!=pr or cr!=pp or cr!=dp: errors.append('artifact_content_mismatch')
            if pjs.read_bytes()!=djs.read_bytes(): errors.append('preview_docs_data_js_mismatch')
            if (PREVIEW/'index.html').read_bytes()!=(DOCS/'index.html').read_bytes() or (PREVIEW/'app.js').read_bytes()!=(DOCS/'app.js').read_bytes() or (PREVIEW/'date_utils.js').read_bytes()!=(DOCS/'date_utils.js').read_bytes(): errors.append('preview_docs_shell_mismatch')
            artifacts={'counts':counts,'sha256':{str(x.relative_to(ROOT)):sha256(x) for x in req}}
    dom=None
    if not args.skip_dom and not args.skip_artifacts and not errors:
        p=subprocess.run([sys.executable,str(ROOT/'src'/'dom_gate.py')],capture_output=True,text=True)
        try: dom=json.loads(p.stdout.strip().splitlines()[-1])
        except Exception: dom={'pass':False,'stdout':p.stdout,'stderr':p.stderr}
        if p.returncode!=0 or not dom.get('pass'): errors.append('dom_gate_failed')
    result={'pass':not errors,'day':CURRENT_JST,'gate_mode':mode,'rows':len(rows),'counts':r['counts'],'active_counts':r['active_counts'],'errors':errors,'row_validation':r,'runtime_validation':runtime,'artifacts':artifacts,'dom':dom}
    out=ROOT/'reports'/'final_display_gate_vnext.json'; out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
