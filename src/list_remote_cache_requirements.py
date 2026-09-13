from __future__ import annotations
import argparse, json
from pathlib import Path
from source_provenance import cache_name, validate_source_provenance

ROOT=Path(__file__).resolve().parents[1]

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--manifest',default=str(ROOT/'fixtures'/'remote_regression_manifest.json'))
 ap.add_argument('--cache-dir',default=str(ROOT/'data'/'remote_cache'))
 ap.add_argument('--provenance',default=str(ROOT/'data'/'remote_cache'/'source_provenance.json'))
 ap.add_argument('--report',default=str(ROOT/'reports'/'remote_cache_requirements_v1_9.json'))
 a=ap.parse_args()
 manifest=json.loads(Path(a.manifest).read_text(encoding='utf-8'))
 cache=Path(a.cache_dir); items=[]
 for g in manifest.get('groups',[]):
  for im in g.get('images',[]):
   fn=cache_name(im['url']); p=cache/fn
   items.append({'group_id':g['id'],'url':im['url'],'referer':im.get('referer',''),'cache_filename':fn,'cache_path':str(p),'present':p.exists()})
 prov=validate_source_provenance(manifest,cache,Path(a.provenance),require_trusted_method=True)
 valid_by={(x['group_id'],x['source_url']):x['pass'] for x in prov.get('items',[])}
 for x in items:
  x['provenance_valid']=bool(valid_by.get((x['group_id'],x['url']),False))
 rep={'version':'v1.9','required_count':len(items),'present_count':sum(x['present'] for x in items),'missing_count':sum(not x['present'] for x in items),'provenance_valid_count':sum(x['provenance_valid'] for x in items),'provenance_status':prov.get('status'),'items':items,'complete':all(x['present'] for x in items),'release_source_ready':all(x['present'] and x['provenance_valid'] for x in items)}
 Path(a.report).write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:rep[k] for k in ('required_count','present_count','missing_count','provenance_valid_count','complete','release_source_ready')},ensure_ascii=False))
if __name__=='__main__':main()
