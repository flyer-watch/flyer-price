from __future__ import annotations
import json,re
from vnext_common import DATA,DOCS,read_csv,STORE_LABELS,parse_data_js

def main():
    rows=read_csv(DATA/'products.csv')
    expected_total=len(rows)
    expected_store={sid:sum(1 for r in rows if r['store_id']==sid) for sid in STORE_LABELS}
    payload=parse_data_js(DOCS/'data.js')
    configured_dates=list(payload.get('meta',{}).get('date_buttons') or [])
    if not configured_dates:
        configured_dates=sorted({r.get('sale_start','') for r in rows if r.get('sale_start') and r.get('sale_start')==r.get('sale_end')})
    expected_dates={d:sum(1 for r in rows if r.get('sale_start')==d and r.get('sale_end')==d) for d in configured_dates}
    try:
        from playwright.sync_api import sync_playwright
        html=(DOCS/'index.html').read_text(encoding='utf-8')
        html=re.sub(r'<script\s+src="[^"]+"\s*></script>','',html)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            page=browser.new_page()
            page.set_content(html,wait_until='domcontentloaded')
            for name in ('data.js','date_utils.js','app.js'):
                page.add_script_tag(content=(DOCS/name).read_text(encoding='utf-8'))
            page.wait_for_function("document.querySelectorAll('.card').length > 0")
            got_total=page.locator('.card').count()
            store_counts={}
            for sid,label in STORE_LABELS.items():
                page.get_by_role('button',name=label,exact=True).click(); page.wait_for_timeout(20)
                store_counts[sid]=page.locator('.card').count()
            page.get_by_role('button',name='全店',exact=True).click(); page.wait_for_timeout(20)
            date_counts={}; missing_buttons=[]
            for day in configured_dates:
                btn=page.get_by_role('button',name=day,exact=True)
                if btn.count()!=1:
                    missing_buttons.append(day); date_counts[day]=None; continue
                btn.click(); page.wait_for_timeout(20)
                date_counts[day]=page.locator('.card').count()
                # every rendered card must carry the exact selected day, never a multi-day range
                badges=page.locator('.card .badge.date').all_text_contents()
                if any(x!=day for x in badges):
                    raise AssertionError(f'non-exact row leaked into {day}: {badges[:10]}')
            browser.close()
        ok=(got_total==expected_total and store_counts==expected_store and date_counts==expected_dates and not missing_buttons)
        result={'pass':ok,'engine':'chromium','total':got_total,'expected_total':expected_total,'store_counts':store_counts,'expected_store_counts':expected_store,'date_buttons':configured_dates,'date_counts':date_counts,'expected_date_counts':expected_dates,'missing_date_buttons':missing_buttons}
    except Exception as e:
        result={'pass':False,'engine':'chromium','error':repr(e),'date_buttons':configured_dates,'expected_date_counts':expected_dates}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
