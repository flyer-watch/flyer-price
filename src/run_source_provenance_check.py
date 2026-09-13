from __future__ import annotations
import argparse, json
from pathlib import Path
from source_provenance import validate_source_provenance

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', default=str(ROOT/'fixtures'/'remote_regression_manifest.json'))
    ap.add_argument('--cache-dir', default=str(ROOT/'data'/'remote_cache'))
    ap.add_argument('--provenance', default=str(ROOT/'data'/'remote_cache'/'source_provenance.json'))
    ap.add_argument('--report', default=str(ROOT/'reports'/'source_provenance_current_v1_9.json'))
    a = ap.parse_args()
    manifest = json.loads(Path(a.manifest).read_text(encoding='utf-8'))
    result = validate_source_provenance(manifest, Path(a.cache_dir), Path(a.provenance), require_trusted_method=True)
    Path(a.report).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('pass','status','required_count','valid_count')}, ensure_ascii=False))
    raise SystemExit(0 if result['pass'] else 1)

if __name__ == '__main__':
    main()
