from __future__ import annotations
import argparse,hashlib,json,re
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from source_adapter import extract_image_urls,filter_original_flyer_urls,parse_japanese_date_range
from vnext_common import ROOT

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142 Safari/537.36'
SOURCES=[
 {'id':'life','store_id':'life_hikawadai','chain':'ライフ','store_name':'氷川台店','page_url':'https://tokubai.co.jp/%E3%83%A9%E3%82%A4%E3%83%95/124065'},
 {'id':'ok','store_id':'ok_kamiitabashi','chain':'オーケー','store_name':'上板橋店','page_url':'https://tokubai.co.jp/%E3%82%AA%E3%83%BC%E3%82%B1%E3%83%BC/230806'},
 {'id':'comodi','store_id':'comodi_sakuragawa','chain':'コモディイイダ','store_name':'食彩館桜川店','page_url':'https://chirashi-guide.com/%E6%9D%B1%E4%BA%AC%E9%83%BD/%E6%9D%BF%E6%A9%8B%E5%8C%BA/2443/'},
 {'id':'belx','store_id':'belx_itabashi_nakadai','chain':'スーパーベルクス','store_name':'板橋中台店','page_url':'https://tokubai.co.jp/%E3%82%B9%E3%83%BC%E3%83%91%E3%83%BC%E3%83%99%E3%83%AB%E3%82%AF%E3%82%B9/3761','fallback_page_urls':['https://chirashi-guide.com/%E6%9D%B1%E4%BA%AC%E9%83%BD/%E6%9D%BF%E6%A9%8B%E5%8C%BA/32429/']},
]

def discover_from_html(src:dict,html:str)->dict:
    soup=BeautifulSoup(html,'html.parser'); text=' '.join(soup.stripped_strings)
    year=datetime.now(ZoneInfo('Asia/Tokyo')).year
    start,end=parse_japanese_date_range(text,year)
    # Chirashi-Guide's Belx page heading can lag the newly replaced flyer image.
    # The page itself carries an update stamp; Belx publishes a Sat-Fri 7-day issue.
    # Prefer that update date for Belx so a stale heading cannot pin the site to the prior week.
    if src.get('id')=='belx':
        m=re.search(r'ベルクス板橋中台店\s*(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})日?更新',text)
        if not m:
            m=re.search(r'(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})日?更新',text)
        if m:
            y,mo,da=map(int,m.groups()); d=datetime(y,mo,da).date()
            if not start or not end:
                start=d.isoformat(); end=(d+timedelta(days=6)).isoformat()
        elif not start or not end:
            # Tokubai often exposes only an MM月DD日 update stamp in the page
            # shell. Use it as a provisional weekly window; temporal OCR on the
            # actual flyer image remains authoritative for day-specific rows.
            m2=re.search(r'(\d{1,2})月(\d{1,2})日更新',text)
            if m2:
                mo,da=map(int,m2.groups()); d=datetime(year,mo,da).date()
                start=d.isoformat(); end=(d+timedelta(days=6)).isoformat()
    raw_urls=extract_image_urls(src['page_url'],html)
    urls=filter_original_flyer_urls(raw_urls)
    if src.get('id')=='belx':
        # Chirashi-Guide stores this Belx issue as page suffixes _0.jpg and _1.jpg.
        # The legacy generic filter accepted only _0.jpg, so explicitly admit numbered
        # original pages here without changing the frozen legacy source adapter.
        extra=[u for u in raw_urls if 'chirashi-guide.com/chirashi-file/' in u.lower() and re.search(r'_\d+\.(?:jpg|jpeg|png)(?:\?|$)',u,re.I) and 'thum' not in u.lower() and 'thumb' not in u.lower()]
        for u in extra:
            if u not in urls: urls.append(u)
    # A page may contain recent history. Favor first two source-hosted originals; current issue is presented first on both supported sites.
    urls=urls[:2]
    fingerprint=hashlib.sha256((src['page_url']+'|'+start+'|'+end+'|'+'|'.join(urls)).encode()).hexdigest()
    return {**src,'sale_start':start,'sale_end':end,'images':urls,'fingerprint':fingerprint,'ok':bool(start and end and urls)}

def discover_live(timeout=30)->dict:
    ses=requests.Session(); ses.headers.update({'User-Agent':UA,'Accept-Language':'ja-JP,ja;q=0.9'})
    groups=[]; errors=[]
    for s in SOURCES:
        last_error=None; g=None
        candidates=[s['page_url'],*(s.get('fallback_page_urls') or [])]
        for page_url in candidates:
            try:
                ss={**s,'page_url':page_url}
                r=ses.get(page_url,timeout=timeout); r.raise_for_status(); gg=discover_from_html(ss,r.text)
                if gg.get('ok'):
                    g=gg; break
                last_error='period or original flyer image not discovered'
            except Exception as e:
                last_error=repr(e)
        if g is None:
            groups.append({**s,'ok':False,'sale_start':'','sale_end':'','images':[],'fingerprint':''})
            errors.append({'id':s['id'],'error':last_error or 'discovery failed'})
        else:
            groups.append(g)
    return {'version':'runtime-discovery-v1','pass':not errors and all(g['ok'] for g in groups),'groups':groups,'errors':errors}

def fixture_test()->dict:
    tests=[]
    life={**SOURCES[0]}
    h='<html><body>2026年9月11日〜9月14日<img alt="チラシ" src="https://image.tokubai.co.jp/images/bargain_office_leaflets/a.jpg"></body></html>'
    g=discover_from_html(life,h); tests.append(g['sale_start']=='2026-09-11' and g['sale_end']=='2026-09-14' and len(g['images'])==1)
    com={**SOURCES[2]}
    h='<html><body>2026年9月12日〜9月15日<img alt="チラシ" src="/chirashi-file/2026/09/x_0thum.jpg"><img alt="チラシ" src="/chirashi-file/2026/09/y_0thum.jpg"></body></html>'
    g2=discover_from_html(com,h); tests.append(g2['sale_start']=='2026-09-12' and g2['sale_end']=='2026-09-15' and all('_0.jpg' in u for u in g2['images']))
    bel={**SOURCES[3]}
    h='<html><body><div>09月12日更新</div><img alt="チラシ" src="https://image.tokubai.co.jp/images/bargain_office_leaflets/a.jpg"><img alt="チラシ" src="https://image.tokubai.co.jp/images/bargain_office_leaflets/b.jpg"></body></html>'
    g3=discover_from_html(bel,h); tests.append(g3['sale_start']=='2026-09-12' and g3['sale_end']=='2026-09-18' and len(g3['images'])==2)
    return {'pass':all(tests),'tests':tests}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',default=str(ROOT/'data'/'runtime_source_manifest.json')); ap.add_argument('--fixture-test',action='store_true'); a=ap.parse_args()
    if a.fixture_test: result=fixture_test()
    else:
        result=discover_live(); Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False)); return 0 if result['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
