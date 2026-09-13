from __future__ import annotations
import hashlib, json
from pathlib import Path

# Files that orchestrate tests, previews, network/cache acquisition, and release
# reporting. Any new .py file NOT listed here is conservatively treated as
# recognition/core logic and must be present in the immutable fingerprint.
NON_RECOGNITION_FILES = {
    'build_preview.py','remote_regression.py','run_release_gate.py',
    'run_life_0909_uniform_e2e.py','run_life_0909_decoy_safety.py',
    'run_output_policy_regression.py','list_remote_cache_requirements.py',
    'run_local_regressions.py','run_preview_regression.py',
    'run_original_product_e2e.py','run_original_e2e_runner_regression.py',
    'source_provenance.py','fetch_original_images.py',
    'run_source_provenance_regression.py','run_source_provenance_check.py',
    'run_original_release_validation.py','recognition_fingerprint.py',
    'run_recognition_fingerprint_regression.py','price_detect_worker.py',
    # vNext orchestration/release layers. These do not replace the immutable v1.9 recognition core.
    'vnext_common.py','rebuild_verified_snapshot.py','build_from_canonical.py','dom_gate.py',
    'final_display_gate.py','promotion.py','source_discovery.py','auto_update.py',
    'extract_runtime_candidates.py','run_all_gates.py','run_distribution_gates.py','vnext_output_policy.py',
    'issue_manifest.py','runtime_gate.py','run_continuous_update_regression.py','run_no_count_floor_regression.py',
}

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def core_files(src_dir: Path):
    return sorted(p for p in src_dir.glob('*.py') if p.name not in NON_RECOGNITION_FILES)

def build_fingerprint(src_dir: Path, baseline_version: str) -> dict:
    return {
        'fingerprint_version':'recognition-source-sha256-v1',
        'baseline_version':baseline_version,
        'files':{p.name:sha256_file(p) for p in core_files(src_dir)},
    }

def validate_recognition_fingerprint(src_dir: Path, fingerprint_path: Path) -> dict:
    if not fingerprint_path.exists():
        return {'pass':False,'status':'missing_fingerprint','fingerprint_path':str(fingerprint_path),'changed':[],'missing':[],'unexpected':[]}
    fp=json.loads(fingerprint_path.read_text(encoding='utf-8'))
    expected=fp.get('files',{})
    current={p.name:sha256_file(p) for p in core_files(src_dir)}
    missing=sorted(set(expected)-set(current))
    unexpected=sorted(set(current)-set(expected))
    changed=sorted(n for n in set(expected)&set(current) if expected[n]!=current[n])
    passed=not missing and not unexpected and not changed and bool(expected)
    return {
        'pass':passed,
        'status':'recognition_source_matches_baseline' if passed else 'recognition_source_differs_from_baseline',
        'baseline_version':fp.get('baseline_version'),
        'fingerprint_path':str(fingerprint_path),
        'file_count':len(expected),
        'changed':changed,'missing':missing,'unexpected':unexpected,
    }
