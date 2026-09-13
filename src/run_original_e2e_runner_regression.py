from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
import cv2
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src';sys.path.insert(0,str(SRC))
from run_original_product_e2e import evaluate_group,anchor_cells
from generic_price_detector import detect_red_price_anchors, PRICE_OCR_VERSION
from product_dictionary_matcher import dictionary_score

EXPECTED_NAMES=[
 'キャベツ','長ねぎ','バナナ','ブロッコリー','豚ロース切身','牛もも肉',
 '紅鮭甘口','さば塩焼','ロースハム','ベーコン','おいしい牛乳','ヨーグルト',
 'キムチ','むぎ茶','スパゲッティ','キッチンペーパー','アリエールジェル','椎茸海老詰めフライ',
 'ミニパンオショコラ','ローストビーフ','海鮮バラちらし','サラダチキン','ピーナッツ','マヨネーズ'
]

def hname(url):return hashlib.sha256(url.encode()).hexdigest()[:20]+'.jpg'

TRUTH=json.loads((ROOT/'fixtures'/'synthetic_price_anchor_truth_v1_9.json').read_text(encoding='utf-8'))['groups']

def _sha256(path:Path):
    h=hashlib.sha256();h.update(path.read_bytes());return h.hexdigest()

def seed_anchor_cache(group_id:str,image_path:Path,cache_dir:Path,profile=None):
    profile=profile or {'mode':'red_only','include_red':True}
    anchors=[{'value':int(a['value']),'bbox':list(a['bbox']),'source':'synthetic_truth','confidence':1.0} for a in TRUTH[group_id]]
    result={'version':PRICE_OCR_VERSION,'broad_anchors':anchors,'association_anchors':anchors,'name_tokens':[],'observations':[{'mode':'synthetic_fixed_anchor_truth','count':len(anchors)}]}
    cache_dir.mkdir(parents=True,exist_ok=True)
    payload={'detector_version':PRICE_OCR_VERSION,'image_filename':image_path.name,'image_sha256':_sha256(image_path),'profile':profile,'result':result}
    (cache_dir/(image_path.stem+'.json')).write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')


def main():
    manifest=json.loads((ROOT/'fixtures'/'remote_regression_localhost.json').read_text(encoding='utf-8'))
    pos=next(g for g in manifest['groups'] if g['id']=='ok_mock')
    pos_path=ROOT/'data'/'remote_mock_cache'/hname(pos['images'][0]['url'])
    seed_anchor_cache('ok_mock',pos_path,ROOT/'data'/'remote_mock_anchor_cache_v1_9')
    pos_result=evaluate_group(pos,ROOT/'data'/'remote_mock_cache',ROOT/'data'/'remote_mock_anchor_cache_v1_9',.55)
    assocs=pos_result.get('association_sample',[])
    scores=[dictionary_score(a.get('name_text',''),n) for a,n in zip(assocs,EXPECTED_NAMES)]
    strong=sum(s>=40 for s in scores)

    # Build a negative copy that preserves price anchors but erases the local
    # evidence zone above each price. This verifies that page headers/spec-only
    # noise cannot satisfy the product-association gate.
    src=ROOT/'fixtures'/'synthetic_ok_dense_v2.jpg'
    img=cv2.imread(str(src)); anchors=detect_red_price_anchors(img)
    cells=anchor_cells(anchors,*img.shape[:2]); H,W=img.shape[:2]
    neg=img.copy()
    for c in cells:
        a=c['anchor']; ay1=int(a['bbox'][1]); ah=max(1,a['bbox'][3]-a['bbox'][1])
        ty=max(int(c['y1']),int(ay1-max(H*.15,ah*4.5)))
        cv2.rectangle(neg,(max(0,c['x1']+1),max(0,ty)),(min(W-1,c['x2']-1),max(0,ay1-2)),(255,255,255),-1)
    neg_fixture=ROOT/'fixtures'/'synthetic_ok_price_only_negative_v1_9.jpg'
    cv2.imwrite(str(neg_fixture),neg,[int(cv2.IMWRITE_JPEG_QUALITY),95])
    neg_url='http://127.0.0.1:47783/synthetic_ok_price_only_negative_v1_9.jpg'
    neg_cache=ROOT/'data'/'original_e2e_negative_cache';neg_cache.mkdir(parents=True,exist_ok=True)
    (neg_cache/hname(neg_url)).write_bytes(neg_fixture.read_bytes())
    neg_group={**pos,'id':'ok_price_only_negative','images':[{'url':neg_url,'referer':''}]}
    neg_path=neg_cache/hname(neg_url)
    seed_anchor_cache('ok_mock',neg_path,ROOT/'data'/'remote_mock_anchor_cache_v1_9')
    neg_result=evaluate_group(neg_group,neg_cache,ROOT/'data'/'remote_mock_anchor_cache_v1_9',.55)

    generic=[]
    for gid in ('comodi_mixed_mock','comodi_nested_mock'):
        gg=next(x for x in manifest['groups'] if x['id']==gid)
        gp=ROOT/'data'/'remote_mock_cache'/hname(gg['images'][0]['url'])
        seed_anchor_cache(gid,gp,ROOT/'data'/'remote_mock_anchor_cache_v1_9')
        gr=evaluate_group(gg,ROOT/'data'/'remote_mock_cache',ROOT/'data'/'remote_mock_anchor_cache_v1_9',.55)
        generic.append({'id':gid,'pass_should_be_false':not gr['pass'],'price_recall':gr['price_recall'],'name_coverage':gr['name_coverage']})

    checks={
      'positive_price_recall_1':pos_result.get('price_recall')==1.0,
      'positive_name_coverage_ge_90':pos_result.get('name_coverage',0)>=.90,
      'positive_expected_name_similarity_23_of_24':strong>=23 and len(scores)==24,
      'negative_keeps_price_recall_1':neg_result.get('price_recall')==1.0,
      'negative_product_gate_fails':not neg_result.get('pass',False),
      'negative_name_coverage_below_threshold':neg_result.get('name_coverage',1)<.55,
      'generic_labels_do_not_pass':all(x['pass_should_be_false'] and x['price_recall']==1.0 for x in generic),
    }
    rep={'version':'v1.9','checks':checks,'positive':{'price_recall':pos_result.get('price_recall'),'name_coverage':pos_result.get('name_coverage'),'similarity_scores':scores,'strong_count':strong},'negative':{'price_recall':neg_result.get('price_recall'),'name_coverage':neg_result.get('name_coverage'),'pass':neg_result.get('pass')},'generic_label_controls':generic,'pass':all(checks.values())}
    out=ROOT/'reports'/'original_product_e2e_runner_regression_v1_9.json'
    out.write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pass':rep['pass'],'checks':checks,'positive_name_coverage':pos_result.get('name_coverage'),'negative_name_coverage':neg_result.get('name_coverage'),'strong':strong},ensure_ascii=False))
    raise SystemExit(0 if rep['pass'] else 1)
if __name__=='__main__':main()
