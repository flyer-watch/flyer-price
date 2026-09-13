from __future__ import annotations
import json, shutil, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/'src'
sys.path.insert(0,str(SRC))
from recognition_fingerprint import validate_recognition_fingerprint

def main():
    fp=ROOT/'fixtures'/'recognition_source_fingerprint_v1_9.json'
    positive=validate_recognition_fingerprint(SRC,fp)
    with tempfile.TemporaryDirectory(prefix='recognition_fp_') as td:
        t=Path(td); shutil.copytree(SRC,t/'src')
        target=t/'src'/'generic_price_detector.py'
        target.write_text(target.read_text(encoding='utf-8')+'\n# fingerprint-negative-test\n',encoding='utf-8')
        negative=validate_recognition_fingerprint(t/'src',fp)
    checks={
      'current_matches_v1_9_baseline':positive['pass'],
      'single_core_change_detected':(not negative['pass'] and 'generic_price_detector.py' in negative['changed']),
    }
    out={'version':'v1.9','checks':checks,'positive':positive,'negative':negative,'pass':all(checks.values())}
    p=ROOT/'reports'/'recognition_fingerprint_regression_v1_9.json'; p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False,indent=2))
    raise SystemExit(0 if out['pass'] else 1)
if __name__=='__main__':main()
