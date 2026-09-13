from __future__ import annotations
import hashlib, json
from datetime import datetime
from pathlib import Path
from typing import Any
import cv2, numpy as np

PROVENANCE_VERSION = "source-provenance-v1"
TRUSTED_METHOD = "http_fetch_v1"


def cache_name(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20] + ".jpg"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sniff_image_mime(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def inspect_image(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    mime = sniff_image_mime(data)
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"image decode failed: {path}")
    h, w = img.shape[:2]
    return {
        "sha256": sha256_file(path),
        "bytes": len(data),
        "mime_magic": mime,
        "width": int(w),
        "height": int(h),
    }


def manifest_items(manifest: dict[str, Any]):
    for group in manifest.get("groups", []):
        gid = group.get("id")
        for item in group.get("images", []):
            yield gid, item


def load_provenance(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def validate_source_provenance(
    manifest: dict[str, Any],
    cache_dir: Path,
    provenance_path: Path,
    *,
    require_trusted_method: bool = True,
) -> dict[str, Any]:
    prov = load_provenance(provenance_path)
    if prov is None:
        return {
            "pass": False,
            "status": "missing_provenance",
            "provenance_path": str(provenance_path),
            "required_count": sum(1 for _ in manifest_items(manifest)),
            "valid_count": 0,
            "items": [],
        }

    entries = prov.get("items", []) if isinstance(prov, dict) else []
    prov_version_ok = isinstance(prov, dict) and prov.get("provenance_version") == PROVENANCE_VERSION
    urls = [e.get("source_url") for e in entries if e.get("source_url")]
    duplicate_urls = {u for u in urls if urls.count(u) > 1}
    by_url = {e.get("source_url"): e for e in entries if e.get("source_url")}
    out = []
    for gid, item in manifest_items(manifest):
        url = item["url"]
        expected_name = cache_name(url)
        path = cache_dir / expected_name
        e = by_url.get(url)
        reasons = []
        if e is None:
            reasons.append("missing_provenance_entry")
        if not path.exists():
            reasons.append("missing_cache_file")
            actual = None
        else:
            try:
                actual = inspect_image(path)
            except Exception as ex:
                actual = None
                reasons.append(f"decode_or_inspect_failed:{type(ex).__name__}:{ex}")

        if not prov_version_ok:
            reasons.append("provenance_version_mismatch")
        if url in duplicate_urls:
            reasons.append("duplicate_provenance_entry")
        if e is not None:
            if e.get("group_id") != gid:
                reasons.append("group_id_mismatch")
            if e.get("cache_filename") != expected_name:
                reasons.append("cache_filename_mismatch")
            if e.get("referer", "") != item.get("referer", ""):
                reasons.append("referer_mismatch")
            if require_trusted_method and e.get("acquisition_method") != TRUSTED_METHOD:
                reasons.append("untrusted_acquisition_method")
            ts=e.get("fetched_at_utc")
            if not ts:
                reasons.append("missing_fetched_at_utc")
            else:
                try:
                    datetime.fromisoformat(str(ts).replace("Z","+00:00"))
                except Exception:
                    reasons.append("invalid_fetched_at_utc")
            if e.get("http_status") != 200:
                reasons.append("http_status_not_200")
            ctype=str(e.get("content_type_header") or "").lower()
            if ctype and not ctype.startswith("image/"):
                reasons.append("non_image_content_type_header")
            if not e.get("final_url"):
                reasons.append("missing_final_url")
            if actual is not None:
                for key in ("sha256", "bytes", "width", "height", "mime_magic"):
                    if e.get(key) != actual.get(key):
                        reasons.append(f"{key}_mismatch")
                if actual.get("mime_magic") not in {"image/jpeg", "image/png", "image/webp"}:
                    reasons.append("unsupported_or_unknown_image_magic")
                if actual.get("bytes", 0) < 10_000:
                    reasons.append("image_too_small_bytes")
                if actual.get("width", 0) < 300 or actual.get("height", 0) < 300:
                    reasons.append("image_too_small_dimensions")

        out.append({
            "group_id": gid,
            "source_url": url,
            "cache_filename": expected_name,
            "pass": not reasons,
            "reasons": reasons,
            "actual": actual,
        })

    required_count = len(out)
    valid_count = sum(1 for x in out if x["pass"])
    return {
        "pass": required_count > 0 and valid_count == required_count,
        "status": "provenance_valid" if required_count > 0 and valid_count == required_count else "provenance_invalid_or_incomplete",
        "provenance_version": prov.get("provenance_version") if isinstance(prov, dict) else None,
        "provenance_path": str(provenance_path),
        "required_count": required_count,
        "valid_count": valid_count,
        "items": out,
    }
