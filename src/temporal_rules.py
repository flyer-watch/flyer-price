from __future__ import annotations
import re
from datetime import date

WD="月火水木金土日"

def _iso(year,month,day):
    return date(int(year),int(month),int(day)).isoformat()

def parse_temporal_text(text:str,year:int=2026):
    raw=text or ""
    t=re.sub(r"\s+","",raw)
    out=[]

    # Time constraints may coexist with a date rule.
    m=re.search(r"夕方(\d{1,2})時(?:から|〜|～)",t)
    if m:
        h=int(m.group(1))
        if 1<=h<=11:h+=12
        out.append({"rule_type":"time_start","start_date":"","end_date":"",
                    "time_start":f"{h:02d}:00","time_end":"","weekday":"",
                    "raw_text":raw,"confidence":0.96})
    else:
        m=re.search(r"(?<!\d)(\d{1,2})時(?:から|〜|～)",t)
        if m:
            h=int(m.group(1))
            out.append({"rule_type":"time_start","start_date":"","end_date":"",
                        "time_start":f"{h:02d}:00","time_end":"","weekday":"",
                        "raw_text":raw,"confidence":0.95})

    # Explicit range: 9/12(土)〜14(月), 9/9(水)～9/11(金)
    m=re.search(
        r"(\d{1,2})/(\d{1,2})(?:\([月火水木金土日]\))?"
        r"[〜～~-]"
        r"(?:(\d{1,2})/)?(\d{1,2})(?:\([月火水木金土日]\))?",
        t
    )
    if m:
        m1,d1,m2,d2=m.groups()
        m2=m2 or m1
        out.append({"rule_type":"date_range","start_date":_iso(year,m1,d1),
                    "end_date":_iso(year,m2,d2),"time_start":"","time_end":"",
                    "weekday":"","raw_text":raw,"confidence":0.99})
        return _dedupe(out)

    # Pair: 9/12(土)・13(日), optionally "限り"/"2日間限り".
    m=re.search(
        r"(\d{1,2})/(\d{1,2})(?:\([月火水木金土日]\))?[・･]"
        r"(?:(\d{1,2})/)?(\d{1,2})(?:\([月火水木金土日]\))?",
        t
    )
    if m:
        m1,d1,m2,d2=m.groups();m2=m2 or m1
        out.append({"rule_type":"date_pair","start_date":_iso(year,m1,d1),
                    "end_date":_iso(year,m2,d2),"time_start":"","time_end":"",
                    "weekday":"","raw_text":raw,"confidence":0.98})
        return _dedupe(out)

    # Single explicit M/D. This deliberately allows weekday prefix: 土9/12.
    m=re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})(?:\([月火水木金土日]\))?",t)
    if m:
        mo,da=m.groups();dt=_iso(year,mo,da)
        if re.search(r"(?:限り|のみ|限定)",t):
            typ="single_date_limited"
            end=dt
            conf=0.99
        elif re.search(r"(?:より販売|から販売|発売)",t):
            typ="start_date_only"
            end=""
            conf=0.98
        else:
            typ="single_date"
            end=dt
            conf=0.94
        out.append({"rule_type":typ,"start_date":dt,"end_date":end,
                    "time_start":"","time_end":"","weekday":"",
                    "raw_text":raw,"confidence":conf})
        return _dedupe(out)

    # Labels like 月9/14 are already caught above; recurring weekday is separate.
    m=re.search(r"毎週([月火水木金土日])曜(?:日)?",t)
    if m:
        out.append({"rule_type":"recurring_weekday","start_date":"","end_date":"",
                    "time_start":"","time_end":"","weekday":m.group(1),
                    "raw_text":raw,"confidence":0.93})
        return _dedupe(out)

    if "本日限り" in t or "今日限り" in t:
        out.append({"rule_type":"relative_today","start_date":"","end_date":"",
                    "time_start":"","time_end":"","weekday":"",
                    "raw_text":raw,"confidence":0.90})
    return _dedupe(out)

def _dedupe(items):
    seen=set();out=[]
    for r in items:
        k=(r["rule_type"],r["start_date"],r["end_date"],r["time_start"],r["weekday"])
        if k not in seen:
            seen.add(k);out.append(r)
    return out

def resolve_scope(parent_start,parent_end,rules,current_date=""):
    """
    Local rule overrides parent only where explicit.
    - start_date_only inherits parent's end.
    - explicit single/range/pair may extend outside parent (e.g. preview 9/15).
    - time rule augments whichever date rule won.
    """
    result={
        "sale_start":parent_start or "",
        "sale_end":parent_end or "",
        "time_start":"","time_end":"",
        "weekday":"","availability_rule":"",
        "date_source":"parent"
    }
    date_rule=None
    for r in rules:
        if r["rule_type"]=="time_start":
            result["time_start"]=r["time_start"]
        elif r["rule_type"]=="recurring_weekday":
            result["weekday"]=r["weekday"]
            result["availability_rule"]="recurring_weekday"
        elif r["rule_type"]=="relative_today" and current_date:
            result["sale_start"]=current_date;result["sale_end"]=current_date
            result["date_source"]="relative_today"
        elif r["start_date"]:
            # highest-confidence explicit date wins
            if date_rule is None or r["confidence"]>date_rule["confidence"]:
                date_rule=r

    if date_rule:
        result["sale_start"]=date_rule["start_date"]
        if date_rule["rule_type"]=="start_date_only":
            result["sale_end"]=parent_end or date_rule["start_date"]
        else:
            result["sale_end"]=date_rule["end_date"] or date_rule["start_date"]
        result["date_source"]=date_rule["rule_type"]
    return result
