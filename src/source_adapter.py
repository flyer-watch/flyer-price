from __future__ import annotations
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

IMAGE_EXT_RE=re.compile(r"\.(?:jpe?g|png|webp)(?:\?|$)",re.I)

def normalize_image_url(url: str) -> str:
    # Chirashi Guide thumbnail -> full image.
    url=re.sub(r"_0thum(?=\.jpg(?:\?|$))","_0",url,flags=re.I)
    url=re.sub(r"_0thumb(?=\.jpg(?:\?|$))","_0",url,flags=re.I)
    return url

def image_quality_score(url: str, alt: str="") -> int:
    u=url.lower()
    score=0
    if "image.tokubai.co.jp" in u: score+=50
    if "/chirashi-file/" in u: score+=50
    if "_0.jpg" in u: score+=20
    if "_0thum" in u or "thumb" in u: score-=25
    if "leaflet" in u or "chirashi" in u: score+=10
    if any(x in u for x in ("logo","icon","favicon","banner")): score-=60
    if "チラシ" in (alt or ""): score+=10
    return score

def extract_image_urls(page_url: str, html: str) -> list[str]:
    soup=BeautifulSoup(html,"html.parser")
    found=[]
    for tag in soup.find_all(["img","a","source"]):
        vals=[]
        for k in ("src","href","data-src","data-original"):
            v=tag.get(k)
            if v: vals.append(v)
        if tag.get("srcset"):
            vals.extend(x.strip().split(" ")[0] for x in tag["srcset"].split(","))
        alt=(tag.get("alt") or "")+" "+(" ".join(tag.stripped_strings) if tag.name=="a" else "")
        for raw in vals:
            u=normalize_image_url(urljoin(page_url,raw))
            if IMAGE_EXT_RE.search(u) and image_quality_score(u,alt)>0:
                found.append((image_quality_score(u,alt),u))
    # embedded image URLs
    for m in re.findall(r'https?:[^"\'<>\\\s]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"\'<>\\\s]*)?',html,re.I):
        u=normalize_image_url(m.replace("\\/","/").replace("\\u0026","&"))
        if image_quality_score(u)>0:
            found.append((image_quality_score(u),u))
    out=[]
    for _,u in sorted(found,key=lambda z:z[0],reverse=True):
        if u not in out: out.append(u)
    return out

def choose_original_images(urls: list[str]) -> list[str]:
    # Dedup thumbnail/full variants by canonical path.
    out=[]
    seen=set()
    for raw in urls:
        u=normalize_image_url(raw)
        key=re.sub(r"_0thum(?=\.jpg)","_0",u,flags=re.I)
        if key in seen: continue
        seen.add(key); out.append(u)
    return out

def parse_japanese_date_range(text: str, default_year: int=2026):
    t=re.sub(r"\s+","",text or "")
    patterns=[
        re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日[〜～~-](?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日"),
        re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日[〜～~-](\d{1,2})日"),
        re.compile(r"(\d{1,2})月(\d{1,2})日[〜～~-](\d{1,2})月(\d{1,2})日"),
        re.compile(r"(\d{1,2})/(\d{1,2})[^0-9]{0,5}[〜～~-][^0-9]{0,5}(\d{1,2})/(\d{1,2})")
    ]
    m=patterns[0].search(t)
    if m:
        y1,m1,d1,y2,m2,d2=m.groups(); y2=y2 or y1
        return f"{int(y1):04d}-{int(m1):02d}-{int(d1):02d}",f"{int(y2):04d}-{int(m2):02d}-{int(d2):02d}"
    m=patterns[1].search(t)
    if m:
        y,m1,d1,d2=m.groups()
        return f"{int(y):04d}-{int(m1):02d}-{int(d1):02d}",f"{int(y):04d}-{int(m1):02d}-{int(d2):02d}"
    m=patterns[2].search(t)
    if m:
        m1,d1,m2,d2=map(int,m.groups())
        return f"{default_year:04d}-{m1:02d}-{d1:02d}",f"{default_year:04d}-{m2:02d}-{d2:02d}"
    m=patterns[3].search(t)
    if m:
        m1,d1,m2,d2=map(int,m.groups())
        return f"{default_year:04d}-{m1:02d}-{d1:02d}",f"{default_year:04d}-{m2:02d}-{d2:02d}"
    return "",""


def is_original_flyer_url(url: str) -> bool:
    """
    Accept only source-hosted flyer binaries that can be fetched directly.
    This deliberately rejects viewer screenshots/UI captures.
    """
    u=normalize_image_url(url or "")
    low=u.lower()
    if "image.tokubai.co.jp/images/bargain_office_leaflets/" in low:
        return True
    if "chirashi-guide.com/chirashi-file/" in low and re.search(r"_0\.(?:jpg|jpeg|png)(?:\?|$)",low):
        return True
    # Kurashiru direct image CDN paths may vary; require image extension and
    # a flyer/chirashi semantic path rather than generic screenshots.
    hostish=("kurashiru" in low or "chirashi" in low)
    semantic=("leaflet" in low or "chirashi" in low or "flyer" in low)
    return bool(hostish and semantic and IMAGE_EXT_RE.search(u) and "thumb" not in low)

def filter_original_flyer_urls(urls: list[str]) -> list[str]:
    out=[]
    for u in choose_original_images(urls):
        if is_original_flyer_url(u) and u not in out:
            out.append(u)
    return out
