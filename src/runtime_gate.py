from __future__ import annotations
from collections import Counter

def validate_runtime_issue(rows:list[dict], manifest:dict)->dict:
    """Validate source/data consistency without arbitrary product-count floors.

    A flyer may legitimately have any number of products. Runtime release is
    therefore driven by source evidence: every discovered page must be fetched
    and processed, rows must belong to the current source fingerprint, and an
    image with detected price evidence must not collapse to zero product rows.
    """
    errors=[]; warnings=[]
    groups={g.get('store_id'):g for g in manifest.get('groups',[]) if g.get('store_id')}
    report=(manifest.get('extraction') or {}).get('stores') or {}
    counts=Counter(r.get('store_id') for r in rows)
    for sid,g in groups.items():
        n=counts[sid]
        rr=report.get(sid,{})
        expected_images=len(g.get('images') or [])
        processed_images=int(rr.get('images') or rr.get('images_processed') or 0)
        anchors=int(rr.get('price_anchors') or 0)
        candidates=int(rr.get('candidate_rows') or n)
        if expected_images and processed_images != expected_images:
            errors.append(f'image_processing_incomplete {sid}={processed_images}/{expected_images}')
        if expected_images and anchors<=0:
            # This is not a product-count floor: the source flyer pages were
            # fetched but the detector found no price evidence at all. Treat it
            # as a parser/layout failure and preserve the previous publication.
            errors.append(f'no_price_evidence {sid} images={expected_images}')
        if anchors>0 and candidates<=0:
            errors.append(f'price_evidence_without_products {sid} anchors={anchors}')
        if anchors>0 and candidates>anchors:
            errors.append(f'extraction_report_inconsistent {sid} candidates={candidates} anchors={anchors}')
        unresolved=max(0,anchors-candidates)
        if unresolved:
            warnings.append(f'unresolved_price_evidence {sid}={unresolved}/{anchors}')
        fp=str(g.get('fingerprint') or '')
        badfp=[r for r in rows if r.get('store_id')==sid and str(r.get('source_fingerprint') or '')!=fp]
        if badfp:
            errors.append(f'stale_fingerprint {sid}={len(badfp)}')
        badsrc=[r for r in rows if r.get('store_id')==sid and not str(r.get('source_url') or '').strip()]
        if badsrc:
            errors.append(f'missing_source {sid}={len(badsrc)}')
    unexpected=sorted(set(r.get('store_id') for r in rows)-set(groups))
    if unexpected: errors.append('unexpected_stores='+','.join(map(str,unexpected)))
    return {'pass':not errors,'counts':dict(counts),'errors':errors,'warnings':warnings}
