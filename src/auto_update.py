from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
import requests
from PIL import Image
from io import BytesIO
from vnext_common import ROOT,DATA,CURRENT_JST,read_csv,write_csv,sha256
from source_discovery import discover_live
from issue_manifest import load_manifest,build_manifest,write_manifest

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142 Safari/537.36'
PUBLIC=[DATA/'products.csv',DATA/'products_publish.csv',ROOT/'preview'/'data.js',ROOT/'docs'/'data.js',DATA/'current_issue_manifest.json']

def hashes(): return {str(p):sha256(p) for p in PUBLIC if p.exists()}

def fetch_group_images(discovery:dict,cache:Path)->dict:
    ses=requests.Session(); ses.headers.update({'User-Agent':UA}); cache.mkdir(parents=True,exist_ok=True)
    for g in discovery['groups']:
        local=[]
        for i,u in enumerate(g.get('images',[])):
            r=ses.get(u,headers={'Referer':g['page_url']},timeout=(15,60)); r.raise_for_status(); b=r.content
            im=Image.open(BytesIO(b)); im.verify()
            if len(b)<10000: raise ValueError('implausibly small image')
            # Include content hash so same URL with replaced image is still a new source.
            content_hash=hashlib.sha256(b).hexdigest()
            name=content_hash[:20]+'.jpg'; (cache/name).write_bytes(b)
            local.append({'source_index':i,'cache_filename':name,'content_sha256':content_hash})
        # Strengthen discovery fingerprint with the downloaded image content hashes.
        g['local_images']=local
        g['fingerprint']=hashlib.sha256((g.get('fingerprint','')+'|'+'|'.join(x['content_sha256'] for x in local)).encode()).hexdigest()
    return discovery

def fingerprints_match(current:dict,discovery:dict)->bool:
    old={g.get('store_id'):g.get('fingerprint') for g in current.get('groups',[]) if g.get('store_id')}
    new={g.get('store_id'):g.get('fingerprint') for g in discovery.get('groups',[]) if g.get('store_id')}
    return bool(old) and old==new and all(new.values())

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--simulate-new-issue-failure',action='store_true'); a=ap.parse_args()
    before=hashes()
    if a.simulate_new_issue_failure:
        bad=DATA/'staging'/'auto_failure.csv'; rows=[dict(r) for r in read_csv(DATA/'products.csv')]
        # Simulate corrupt extraction evidence without using a product-count floor.
        rows[0]['price_in_tax_yen']='0'
        write_csv(bad,rows,list(rows[0].keys()))
        p=subprocess.run([sys.executable,str(ROOT/'src'/'promotion.py'),'--staging',str(bad)],cwd=ROOT,capture_output=True,text=True)
        after=hashes(); ok=p.returncode!=0 and before==after
        print(json.dumps({'pass':ok,'mode':'simulated_new_issue_failure','promotion_rc':p.returncode,'public_unchanged':before==after},ensure_ascii=False)); return 0 if ok else 1
    d=discover_live()
    if not d['pass']:
        print(json.dumps({'pass':False,'status':'discovery_failed_public_preserved','errors':d['errors'],'public_unchanged':before==hashes()},ensure_ascii=False)); return 2

    # Download current originals before deciding unchanged so a same-URL image replacement
    # is detected by content hash, not only by date range / URL.
    runtime=DATA/'runtime_cache'; d=fetch_group_images(d,runtime)
    current=load_manifest()
    if fingerprints_match(current,d):
        p=subprocess.run([sys.executable,str(ROOT/'src'/'final_display_gate.py')],cwd=ROOT,capture_output=True,text=True)
        if p.returncode==0:
            print(json.dumps({'pass':True,'status':'current_issue_unchanged','day':CURRENT_JST},ensure_ascii=False)); return 0

    man=DATA/'runtime_source_manifest.json'; man.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    cand=DATA/'staging'/'runtime_candidates.csv'; report_path=DATA/'staging'/'runtime_extraction_report.json'
    p=subprocess.run([sys.executable,str(ROOT/'src'/'extract_runtime_candidates.py'),'--manifest',str(man),'--cache-dir',str(runtime),'--out',str(cand),'--report',str(report_path)],cwd=ROOT,capture_output=True,text=True)
    if p.returncode!=0:
        print(json.dumps({'pass':False,'status':'extraction_failed_public_preserved','public_unchanged':before==hashes(),'stderr':p.stderr[-1000:]},ensure_ascii=False)); return 3
    report=json.loads(report_path.read_text(encoding='utf-8'))
    issue=build_manifest(d,report,'runtime'); issue_tmp=DATA/'staging'/'current_issue_manifest.json'; write_manifest(issue,issue_tmp)
    # Public canonical is CURRENT issue data only. Historical rows are not mixed into the live site.
    prom=subprocess.run([sys.executable,str(ROOT/'src'/'promotion.py'),'--staging',str(cand),'--gate-mode','runtime','--issue-manifest',str(issue_tmp)],cwd=ROOT,capture_output=True,text=True)
    if prom.returncode!=0:
        print(json.dumps({'pass':False,'status':'candidate_gate_failed_public_preserved','public_unchanged':before==hashes(),'promotion':prom.stdout[-1600:]},ensure_ascii=False)); return 4
    print(json.dumps({'pass':True,'status':'updated_current_issue','candidate_rows':report.get('rows'),'date_buttons':issue.get('date_buttons')},ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
