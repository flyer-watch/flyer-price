チラシ価格比較 vNext-20260913g SOURCE-ACCURACY / CONTINUOUS
最終PDCA: 2026-09-13 JST

目的
- 9/13時点のチラシを保存するのではなく、Life氷川台店 / OK上板橋店 / Comodi食彩館桜川店 / スーパーベルクス板橋中台店の最新チラシへ継続追従する。
- 新号を発見したら原画像を取得し、商品・価格・販売期間を抽出し、Gate合格時だけ現行公開データを新号へ置換する。
- 失敗時は壊れたデータを公開せず直前の正常公開を保持する。

スーパーベルクス板橋中台店追加
- store_id: belx_itabashi_nakadai
- discovery primary: https://tokubai.co.jp/スーパーベルクス/3761
- discovery fallback: https://chirashi-guide.com/東京都/板橋区/32429/
- 現行号: 2026-09-12〜2026-09-18、2ページ。
- チラシガイドのページ見出しが旧週を示す場合があるため、ベルクスはページの更新日を号開始日として7日間を構成する。
- 同一URLの画像差替えはdownloaded image SHA256で検出する。
- Tokubaiで原画像取得を優先し、取得不能時だけChirashi-Guideをfallbackとして使う。
- fallback時も複数ページをすべて取得する。
- 初回baselineはユーザー提供Tokubai PDF2枚から原紙確認した164商品。毎時runtime OCRが品質Gateを通れば次号へ置換する。

継続運用の重要仕様
- GitHub Actions更新確認は毎時。
- 新号判定は販売期間 + URL + 原画像content SHA256。
- data/current_issue_manifest.jsonが現行号メタデータの正本。
- 日付ボタンはcurrent issue manifest / temporal OCRから生成し、固定日付には依存しない。
- runtime canonicalは現行号だけに置換し、期限切れ旧号を蓄積しない。
- discovery / OCR / provenance / source-integrity / DOM Gate失敗時はfail-closedで直前正常版を保持する。
- 日用品は掲載可。食品8%、日用品10%で税込計算する。

将来号擬似回帰
- FLYER_JST_DATE=2026-09-14で4店舗の新号を擬似投入。
- 旧号行: 0件残存。
- runtime promotion / DOM / rollback: PASS。
- 4店舗×10行=40行へ完全置換し、issue manifestもtransactional rollback対象。

現在の初期スナップショット
- 全305件
- Life 64 / OK 46 / Comodi 31 / Belx 164
- 9/13に有効: Life 40 / OK 46 / Comodi 12 / Belx 39
- 日付ボタン: 9/12 / 9/13 / 9/14 / 9/15 / 9/16 / 9/17 / 9/18
- Belxはユーザー提供Tokubai PDF2枚から原紙確認した164行を初期baselineに採用。次号はruntime Gate PASS時のみ置換される。

件数に関する方針
- Life/OK/Comodi/Belxの総件数・当日有効件数に最低値を設けない。
- 件数は監視・比較のために記録するだけ。
- Release判断はsource evidence、provenance、商品名/価格/期間の妥当性、公開経路一致で行う。
- python src/run_no_count_floor_regression.py で「1件・当日0件でもsource evidenceが正しければPASS」を固定回帰する。

公開経路
source discovery
 -> current original flyer fetch + content hash
 -> OCR / temporal scope
 -> runtime staging
 -> runtime quality gate
 -> transactional promotion
 -> data/products.csv
 -> data/products_publish.csv
 -> preview/data.js
 -> docs/data.js
 -> Chromium DOM

日付フィルタ
- 日付ボタンは sale_start == sale_end == 選択日の「その日限定商品」だけ表示。
- 複数日商品は日付ボタンに混入させない。

検証
- python src/run_distribution_gates.py
- python src/run_continuous_update_regression.py
- python src/final_display_gate.py
- python src/source_discovery.py --fixture-test

重要な限界
- 商品件数はGateではない。将来号が1件でも100件でも、件数だけでPASS/FAILしない。
- 当日限定品が0件でも、それだけではFAILしない。
- 未知レイアウトでは赤価格だけに依存せず、非赤色数値OCRも使う。
- 取得した全チラシページを処理し、各公開行をsource_url/source_image/source_fingerprintへ追跡できることを重視する。
- 原画像に価格情報があるのに商品化が完全に0件へ崩壊した場合はparser/layout failureとして直前正常版を保持する。
- Belx現行号はユーザー提供PDF2枚から164件を確認済みbaselineとして保持するが、164は将来号の最低件数ではない。
