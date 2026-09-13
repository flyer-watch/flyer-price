from __future__ import annotations
import argparse, json, os, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

from source_provenance import (
    PROVENANCE_VERSION, TRUSTED_METHOD, cache_name, inspect_image,
    validate_source_provenance,
)

ROOT = Path(__file__).resolve().parents[1]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142 Safari/537.36"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_content_type(v: str | None) -> str:
    return (v or "").split(";", 1)[0].strip().lower()


def download_one(session: requests.Session, group_id: str, item: dict, cache_dir: Path, retries: int = 3) -> dict:
    url = item["url"]
    referer = item.get("referer", "")
    name = cache_name(url)
    final = cache_dir / name
    tmp = final.with_suffix(final.suffix + ".part")
    last = None
    for attempt in range(1, retries + 1):
        try:
            headers = {"Referer": referer} if referer else {}
            with session.get(url, headers=headers, timeout=(15, 60), stream=True, allow_redirects=True) as r:
                r.raise_for_status()
                ctype = safe_content_type(r.headers.get("Content-Type"))
                if ctype and not ctype.startswith("image/"):
                    raise ValueError(f"non-image content-type: {ctype}")
                total = 0
                with tmp.open("wb") as f:
                    for chunk in r.iter_content(256 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > 60 * 1024 * 1024:
                            raise ValueError("image exceeds 60 MiB safety limit")
                        f.write(chunk)
                meta = inspect_image(tmp)
                if meta["bytes"] < 10_000 or meta["width"] < 300 or meta["height"] < 300:
                    raise ValueError(f"implausibly small flyer image: {meta}")
                if meta["mime_magic"] not in {"image/jpeg", "image/png", "image/webp"}:
                    raise ValueError(f"unsupported image magic: {meta['mime_magic']}")
                os.replace(tmp, final)
                return {
                    "group_id": group_id,
                    "source_url": url,
                    "referer": referer,
                    "cache_filename": name,
                    "acquisition_method": TRUSTED_METHOD,
                    "fetched_at_utc": utc_now(),
                    "final_url": r.url,
                    "http_status": int(r.status_code),
                    "content_type_header": ctype,
                    "etag": r.headers.get("ETag"),
                    "last_modified": r.headers.get("Last-Modified"),
                    **meta,
                }
        except Exception as e:
            last = e
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            if attempt < retries:
                time.sleep(min(2 ** (attempt - 1), 4))
    raise RuntimeError(f"download failed after {retries} attempts: {url}: {type(last).__name__}: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(ROOT / "fixtures" / "remote_regression_manifest.json"))
    ap.add_argument("--cache-dir", default=str(ROOT / "data" / "remote_cache"))
    ap.add_argument("--provenance", default=str(ROOT / "data" / "remote_cache" / "source_provenance.json"))
    ap.add_argument("--offline-verify", action="store_true", help="Do not access network; verify existing cache and provenance only")
    ap.add_argument("--retries", type=int, default=3)
    a = ap.parse_args()

    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    cache_dir = Path(a.cache_dir); cache_dir.mkdir(parents=True, exist_ok=True)
    prov_path = Path(a.provenance); prov_path.parent.mkdir(parents=True, exist_ok=True)

    if not a.offline_verify:
        session = requests.Session()
        session.headers.update({
            "User-Agent": UA,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.5",
        })
        items = []
        errors = []
        for g in manifest.get("groups", []):
            for item in g.get("images", []):
                try:
                    rec = download_one(session, g.get("id"), item, cache_dir, retries=max(1, a.retries))
                    items.append(rec)
                    print(json.dumps({"fetched": rec["cache_filename"], "group": rec["group_id"], "bytes": rec["bytes"], "size": [rec["width"], rec["height"]]}, ensure_ascii=False), flush=True)
                except Exception as e:
                    errors.append({"group_id": g.get("id"), "source_url": item.get("url"), "error": str(e)})
                    print(json.dumps({"fetch_error": str(e), "group": g.get("id")}, ensure_ascii=False), flush=True)
        provenance = {
            "provenance_version": PROVENANCE_VERSION,
            "created_at_utc": utc_now(),
            "manifest": str(Path(a.manifest).resolve()),
            "items": items,
            "fetch_errors": errors,
        }
        prov_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")

    result = validate_source_provenance(manifest, cache_dir, prov_path, require_trusted_method=True)
    print(json.dumps({k: result[k] for k in ("pass", "status", "required_count", "valid_count")}, ensure_ascii=False))
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
