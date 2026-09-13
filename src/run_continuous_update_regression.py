from __future__ import annotations
import csv,json,os,subprocess,sys
from collections import defaultdict
from pathlib import Path
from vnext_common import ROOT,DATA,PREVIEW,DOCS,read_csv,write_csv,sha256

PUBLIC=[DATA/'products.csv',DATA/'products_publish.csv',PREVIEW/'data.js',DOCS/'data.js',DATA/'current_issue_manifest.json']

def snap(): return {p:(p.read_bytes() if p.exists() else None) for p in PUBLIC}
def restore(b):
    for p,v in b.items():
        if v is None:
            if p.exists(): p.unlink()
        else:
            p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(v)
def hashes(): return {str(p.relative_to(ROOT)):sha256(p) for p in PUBLIC if p.exists()}

def main():
    backup=snap(); base_hash=hashes(); env={**os.environ,'FLYER_JST_DATE':'2026-09-14'}
    try:
        rows=read_csv(DATA/'products.csv'); by=defaultdict(list)
        for r in rows: by[r['store_id']].append(dict(r))
        groups=[]; report={'rows':0,'counts':{},'stores':{},'daily_dates':['2026-09-14','2026-09-15','2026-09-16']}; future=[]
        meta={
          'life_hikawadai':('life','ライフ','氷川台店'),
          'ok_kamiitabashi':('ok','オーケー','上板橋店'),
          'comodi_sakuragawa':('comodi','コモディイイダ','食彩館桜川店'),
          'belx_itabashi_nakadai':('belx','スーパーベルクス','板橋中台店')}
        for sid,(gid,chain,store) in meta.items():
            fp='future-'+gid+'-fingerprint'
            sample=[dict(by[sid][i % len(by[sid])]) for i in range(10)]
            for i,r in enumerate(sample):
                # Keep synthetic future rows unique even for a newly added store with a small seed set.
                r['specification']=(str(r.get('specification') or '')+f' [future-regression-{i}]').strip()
                r['sale_start']='2026-09-14' if i<3 else '2026-09-14'
                r['sale_end']='2026-09-14' if i<3 else '2026-09-16'
                r['source_fingerprint']=fp; r['source_url']=f'https://example.invalid/{gid}/future.jpg'; r['source_image']=f'{gid}-future.jpg'; r['validation_status']='auto_strict'; r['source_type']='runtime_local_ocr'
                future.append(r)
            groups.append({'id':gid,'store_id':sid,'chain':chain,'store_name':store,'page_url':f'https://example.invalid/{gid}','sale_start':'2026-09-14','sale_end':'2026-09-16','images':[f'https://example.invalid/{gid}/future.jpg'],'fingerprint':fp})
            report['counts'][sid]=10; report['stores'][sid]={'images':1,'price_anchors':20,'candidate_rows':10}
        report['rows']=len(future)
        stage=DATA/'staging'/'continuous_future.csv'; write_csv(stage,future,list(future[0].keys()))
        issue={'version':'current-issue-manifest-v2','as_of_jst':'2026-09-14','gate_mode':'runtime','groups':groups,'date_buttons':['2026-09-14','2026-09-15','2026-09-16'],'extraction':report}
        issue_path=DATA/'staging'/'continuous_future_manifest.json'; issue_path.write_text(json.dumps(issue,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        p=subprocess.run([sys.executable,str(ROOT/'src'/'promotion.py'),'--staging',str(stage),'--gate-mode','runtime','--issue-manifest',str(issue_path)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
        if p.returncode!=0: raise RuntimeError('future promotion failed: '+p.stdout[-1200:]+p.stderr[-1200:])
        got=read_csv(DATA/'products.csv')
        if len(got)!=40 or any(r['source_fingerprint'].startswith('future-') is False for r in got): raise RuntimeError('old issue rows survived future promotion')
        payload=(DOCS/'data.js').read_text(encoding='utf-8')
        if '2026-09-14' not in payload or '2026-09-16' not in payload: raise RuntimeError('future date buttons not rebuilt')
        # Fault injection must restore both public data and current issue manifest.
        promoted_hash=hashes()
        p2=subprocess.run([sys.executable,str(ROOT/'src'/'promotion.py'),'--staging',str(stage),'--gate-mode','runtime','--issue-manifest',str(issue_path),'--fault','after_build'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
        if p2.returncode==0 or hashes()!=promoted_hash: raise RuntimeError('runtime rollback failed')
        result={'pass':True,'future_rows':len(got),'date_buttons':['2026-09-14','2026-09-15','2026-09-16'],'old_rows_survived':False,'runtime_rollback_byte_identical':True}
        print(json.dumps(result,ensure_ascii=False)); return 0
    except Exception as e:
        print(json.dumps({'pass':False,'error':repr(e)},ensure_ascii=False)); return 1
    finally:
        restore(backup)
        for q in (DATA/'staging'/'continuous_future.csv', DATA/'staging'/'continuous_future_manifest.json'):
            try: q.unlink()
            except FileNotFoundError: pass

if __name__=='__main__': raise SystemExit(main())
