from __future__ import annotations
import json
from datetime import date,timedelta
from pathlib import Path
from vnext_common import DATA,CURRENT_JST

PATH=DATA/'current_issue_manifest.json'

def iso_range(start:str,end:str):
    try:
        a=date.fromisoformat(start); b=date.fromisoformat(end)
    except Exception:
        return []
    out=[]
    while a<=b:
        out.append(a.isoformat()); a+=timedelta(days=1)
    return out

def build_manifest(discovery:dict, extraction_report:dict|None=None, gate_mode:str='runtime')->dict:
    extraction_report=extraction_report or {}
    daily=set(extraction_report.get('daily_dates') or [])
    groups=[]
    for g in discovery.get('groups',[]):
        groups.append({k:g.get(k) for k in ('id','store_id','chain','store_name','page_url','sale_start','sale_end','images','fingerprint')})
    # Prefer independently detected daily-special dates.  If OCR cannot identify them,
    # keep the current flyer window visible rather than silently hiding date buttons.
    if not daily:
        for g in groups:
            daily.update(iso_range(g.get('sale_start',''),g.get('sale_end','')))
    return {
        'version':'current-issue-manifest-v2',
        'as_of_jst':CURRENT_JST,
        'gate_mode':gate_mode,
        'groups':groups,
        'date_buttons':sorted(daily),
        'extraction':extraction_report,
    }

def load_manifest():
    if not PATH.exists(): return {}
    return json.loads(PATH.read_text(encoding='utf-8'))

def write_manifest(m:dict,path:Path=PATH):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
