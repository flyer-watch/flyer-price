from __future__ import annotations
import csv, hashlib, json, re, os
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
from pathlib import Path
from typing import Iterable

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
PREVIEW=ROOT/'preview'
DOCS=ROOT/'docs'
CURRENT_JST=os.environ.get('FLYER_JST_DATE') or datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
STORE_LABELS={'life_hikawadai':'ライフ 氷川台店','ok_kamiitabashi':'オーケー 上板橋店','comodi_sakuragawa':'コモディイイダ 食彩館桜川店','belx_itabashi_nakadai':'スーパーベルクス 板橋中台店'}
HOUSEHOLD_MARKERS=('キッチンペーパー','トイレットペーパー','ティッシュ','ティシュー','洗濯洗剤','食器用洗剤','台所用洗剤','衣料用洗剤','柔軟剤','漂白剤','ハミガキ','歯磨き','歯ブラシ','シャンプー','コンディショナー','ボディソープ','ハンドソープ','アリエール','ボールド','リステリン','フィニッシュ','ジョイ')

def read_csv(path:Path)->list[dict]:
    with path.open('r',encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def write_csv(path:Path, rows:list[dict], fields:list[str]|None=None)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if fields is None:
        fields=list(rows[0].keys()) if rows else []
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def parse_data_js(path:Path)->dict:
    s=path.read_text(encoding='utf-8').strip()
    prefix='window.FLYER_DATA='
    if not s.startswith(prefix): raise ValueError(f'bad data.js prefix: {path}')
    s=s[len(prefix):]
    if s.endswith(';'): s=s[:-1]
    return json.loads(s)

def active_on(r:dict, day:str=CURRENT_JST)->bool:
    return str(r.get('sale_start',''))<=day<=str(r.get('sale_end',''))

def norm(s)->str:
    return re.sub(r'\s+','',str(s or '')).lower()

def is_household_name(name:str)->bool:
    n=norm(name)
    return any(norm(m) in n for m in HOUSEHOLD_MARKERS)

def validate_rows(rows:list[dict], day:str=CURRENT_JST, require_gates:bool=True)->dict:
    errors=[]
    total=Counter(r.get('store_id','') for r in rows)
    active=Counter(r.get('store_id','') for r in rows if active_on(r,day))
    # Row counts are observations, never release thresholds. A valid flyer may
    # legitimately contain few products or few products active on a given day.
    # Quality is gated by row integrity/provenance and runtime source evidence.
    dup=[]; seen=set(); household=[]; bad_price=[]; blank=[]; bad_dates=[]; missing_prov=[]; percent_only=[]
    for i,r in enumerate(rows,2):
        name=str(r.get('product_name') or '').strip(); spec=str(r.get('specification') or '').strip()
        if not name: blank.append(i)
        if any(m in norm(name) for m in map(norm,HOUSEHOLD_MARKERS)): household.append((i,name))
        raw=' '.join(str(r.get(k) or '') for k in ('product_name','specification','promotion'))
        if '%off' in norm(raw) and not str(r.get('price_in_tax_yen') or '').strip(): percent_only.append(i)
        try: inc=int(float(r.get('price_in_tax_yen') or 0))
        except Exception: inc=0
        if inc<=0: bad_price.append((i,r.get('price_in_tax_yen')))
        st=str(r.get('sale_start') or ''); en=str(r.get('sale_end') or '')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',st) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',en) or st>en: bad_dates.append((i,st,en))
        key=(norm(r.get('store_id')),st,en,norm(name),norm(spec),str(inc))
        if key in seen: dup.append((i,key))
        seen.add(key)
        # Every published row, not only today's rows, must be traceable back
        # to the source flyer. Accuracy/provenance is the release criterion.
        if (not str(r.get('source_url') or '').strip() or not str(r.get('source_image') or '').strip() or not str(r.get('source_fingerprint') or '').strip()):
            missing_prov.append(i)
    if bad_price: errors.append(f'bad_price={len(bad_price)}')
    if blank: errors.append(f'blank_name={len(blank)}')
    if dup: errors.append(f'duplicates={len(dup)}')
    if bad_dates: errors.append(f'bad_dates={len(bad_dates)}')
    if percent_only: errors.append(f'percent_only={len(percent_only)}')
    if missing_prov: errors.append(f'missing_provenance={len(missing_prov)}')
    return {'pass':not errors,'rows':len(rows),'counts':dict(total),'active_counts':dict(active),'errors':errors,'details':{'household_allowed_count':len(household),'household_samples':household[:10],'bad_price':bad_price[:10],'blank':blank[:10],'duplicates':dup[:10],'bad_dates':bad_dates[:10],'missing_provenance':missing_prov[:10]}}
