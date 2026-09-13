from __future__ import annotations
import hashlib, json, shutil, sys, tempfile, threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
from fetch_original_images import download_one
from source_provenance import PROVENANCE_VERSION, validate_source_provenance


def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def main():
    report_path = ROOT / "reports" / "source_provenance_regression_v1_9.json"
    fixture_names = ["synthetic_ok_dense_v2.jpg", "synthetic_comodi_page1_mixed.jpg"]
    result = {"version": "v1.9", "tests": []}

    with tempfile.TemporaryDirectory(prefix="flyer_prov_") as td:
        t = Path(td)
        serve = t / "serve"; serve.mkdir()
        cache = t / "cache"; cache.mkdir()
        for name in fixture_names:
            shutil.copy2(ROOT / "fixtures" / name, serve / name)

        handler = lambda *a, **kw: QuietHandler(*a, directory=str(serve), **kw)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        th = threading.Thread(target=httpd.serve_forever, daemon=True); th.start()
        port = httpd.server_address[1]
        try:
            manifest = {"groups": [{
                "id": "prov_mock",
                "images": [
                    {"url": f"http://127.0.0.1:{port}/{fixture_names[0]}", "referer": ""},
                    {"url": f"http://127.0.0.1:{port}/{fixture_names[1]}", "referer": ""},
                ],
                "anchor_prices": [1], "minimum_recall": 1.0,
            }]}
            session = requests.Session(); session.headers.update({"User-Agent": "flyer-provenance-regression/1.0"})
            records = [download_one(session, "prov_mock", item, cache, retries=1) for item in manifest["groups"][0]["images"]]
            prov = {
                "provenance_version": PROVENANCE_VERSION,
                "created_at_utc": now_utc(),
                "manifest": "regression-inline",
                "items": records,
                "fetch_errors": [],
            }
            pp = cache / "source_provenance.json"
            pp.write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")

            positive = validate_source_provenance(manifest, cache, pp, require_trusted_method=True)
            result["tests"].append({"name": "positive_local_http_fetch", "pass": positive["pass"], "valid_count": positive["valid_count"], "required_count": positive["required_count"]})

            # Tamper bytes while keeping a valid image: overwrite first cached file with second image.
            first = cache / records[0]["cache_filename"]
            backup = first.read_bytes()
            first.write_bytes((serve / fixture_names[1]).read_bytes())
            tampered = validate_source_provenance(manifest, cache, pp, require_trusted_method=True)
            tamper_detected = (not tampered["pass"] and any("sha256_mismatch" in x["reasons"] for x in tampered["items"]))
            result["tests"].append({"name": "detect_valid_image_substitution", "pass": tamper_detected, "validator_pass": tampered["pass"], "first_reasons": tampered["items"][0]["reasons"]})
            first.write_bytes(backup)

            # Tamper provenance only.
            bad = json.loads(pp.read_text(encoding="utf-8"))
            bad["items"][0]["sha256"] = "0" * 64
            pp.write_text(json.dumps(bad, ensure_ascii=False, indent=2), encoding="utf-8")
            bad_meta = validate_source_provenance(manifest, cache, pp, require_trusted_method=True)
            meta_detected = not bad_meta["pass"] and "sha256_mismatch" in bad_meta["items"][0]["reasons"]
            result["tests"].append({"name": "detect_provenance_hash_tamper", "pass": meta_detected, "validator_pass": bad_meta["pass"]})

            # Missing provenance must never silently adopt existing files.
            pp.unlink()
            missing = validate_source_provenance(manifest, cache, pp, require_trusted_method=True)
            result["tests"].append({"name": "reject_unprovenanced_existing_cache", "pass": not missing["pass"] and missing["status"] == "missing_provenance", "status": missing["status"]})
        finally:
            httpd.shutdown(); httpd.server_close(); th.join(timeout=2)

    result["pass"] = all(t["pass"] for t in result["tests"])
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
