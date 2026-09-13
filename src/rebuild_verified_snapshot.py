from __future__ import annotations
import csv, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
STAGING=DATA/'staging'
STAGING.mkdir(parents=True,exist_ok=True)
BASE=DATA/'local_beta_products_filtered.csv'
OUT=STAGING/'products.csv'
CURRENT='2026-09-13'
FIELDS=['store_id','chain','store_name','sale_start','sale_end','product_name','specification','price_ex_tax_yen','price_in_tax_yen','tax_rate','promotion','category','availability_rule','scope_level','source_type','validation_status','source_url','source_image','source_fingerprint','verification_note']

def fp(s:str)->str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def row(store_id,chain,store_name,start,end,name,spec,ex,inc,category,source_type,source_url,source_image,note='source-visual-verified',tax_rate=None):
    if tax_rate is None: tax_rate=0.10 if category in ('日用品','酒類') else 0.08
    return dict(store_id=store_id,chain=chain,store_name=store_name,sale_start=start,sale_end=end,product_name=name,specification=spec,price_ex_tax_yen=int(ex),price_in_tax_yen=int(inc),tax_rate=tax_rate,promotion='',category=category,availability_rule='',scope_level='verified_snapshot',source_type=source_type,validation_status='verified',source_url=source_url,source_image=source_image,source_fingerprint=fp(source_url+'|'+source_image+'|'+start+'|'+end),verification_note=note)

rows=[]
# vNext publishes only the current Life issue. Older handoff rows stay in source fixtures, not canonical output.
life_url='https://tokubai.co.jp/transit/rail_lines/station_groups/5171/leaflet'
life_img='e30a242f248b50e5f0f3.jpg|abb0949e11a5f2d78ca6.jpg'
life=[
('玉ねぎ（お得用）','1袋',290,313,'青果'),('じゃがいも（お得用）','1袋',290,313,'青果'),('にんじん（お得用）','1袋',290,313,'青果'),
('ブロッコリー','1株',188,203,'青果'),('長ねぎ（2本入）','1束',188,203,'青果'),('甘さたっぷりミニトマト（赤）','1パック',298,321,'青果'),
('そらち南トマト','1パック',498,537,'青果'),('生プルーン','1パック',498,537,'青果'),('栗まさるマロン南瓜','100g当り',59,63,'青果'),
('北海道産帆立入り海鮮丼','1パック',999,1078,'惣菜'),('北海道産帆立入りにぎり盛り合わせ','1パック（1人前）',999,1078,'寿司'),
('北海道産帆立入りにぎり盛り合わせ','1パック（2人前）',1980,2138,'寿司'),('げんこつ鶏ザンギ','100g当り',259,279,'惣菜'),
('自社製タルタルソースで食べる北海道産鱈フライ','1パック',390,421,'惣菜'),('豚丼（ソラチのたれ使用）','1パック',699,754,'惣菜'),
('北海道産あまに豚入り よくばりカレー','1パック',590,637,'惣菜'),('北海道産じゃが芋コロッケ（あまに豚入り）','1袋（5コ入）',280,302,'惣菜'),
('北海道名物 豚丼のたれ','108g',199,214,'調味料'),('北海道コーンもっち〜','1袋（5コ入）',348,375,'惣菜'),('ちくわパン（ツナ）','1コ',228,246,'ベーカリー'),
('北海道産帆立照焼き重','1パック',880,950,'惣菜'),('北海道産帆立＆コーン使用の塩焼きそば','1パック',550,594,'惣菜'),
('北海道産3種チーズ＆コーンのグラタン','1パック',459,495,'惣菜'),('北海道産ポテトとサーモンのチーズ焼き','1パック（3コ）',499,538,'惣菜'),
('じゃがベーコン','1コ',198,213,'ベーカリー'),('長沼じんぎすかん ラム味付','350g',890,961,'精肉'),
]
for x in life: rows.append(row('life_hikawadai','ライフ','氷川台店','2026-09-12','2026-09-14',*x,source_type='local_original_visual_verified',source_url=life_url,source_image=life_img,note='current-issue-general-9/12-9/14-visual-check'))

# Daily-special panels on the current Life flyer. These are intentionally exact-day rows.
life_daily={
'2026-09-12':[
('スマイルライフ 生切り餅','1kg',748,807,'食品'),
('伊藤園 ビタミン野菜／1日分の野菜','各1ケース（200ml×12本）',798,861,'飲料'),
('大王製紙 エリエール トイレットティシュー（シングル／ダブル）','各12ロール',598,657,'日用品'),
('レタス','1コ',158,170,'青果'),
('ハウス バーモントカレー／完熟トマトのハヤシライスソース','各1個',199,214,'加工食品'),
('デルモンテ トマトケチャップ／リコピンリッチ トマトケチャップ','各1本',199,214,'調味料'),
('紀文 だしおでん','390g×2',438,473,'日配食品'),
('日清製粉ウェルナ もちっと生パスタ クリーミーボロネーゼ','1人前',158,170,'冷凍食品'),
('中国産 うなぎ長焼','1尾',880,950,'鮮魚'),
('P&G ファブリーズ W除菌 詰替','320ml',278,305,'日用品'),
],
'2026-09-13':[
('マルちゃん 焼そば／期間限定ほたてバター醤油味','各3人前',179,193,'麺類'),
('UCC ザ・ブレンド 114／117','各70g',478,516,'飲料'),
('P&G ボールド ジェル 詰替超特大','690g',328,360,'日用品'),
('マルちゃん 赤いきつねうどん／緑のたぬき天そば／焼そば','各1個',109,117,'加工食品'),
('キユーピー マヨネーズ／ハーフ','450g／400g',278,300,'調味料'),
('マルちゃん あったかごはん','200g×5個',698,753,'米飯'),
('キッコーマン 調製豆乳／無調整豆乳／特濃調製豆乳','各1000ml',198,213,'飲料'),
('地中海産 本まぐろ赤身（養殖・解凍）サク','100g当り',798,861,'鮮魚'),
('なす','1袋',198,213,'青果'),
('ぶなしめじ','1パック',99,106,'青果'),
('ピーマン（大容量）','1袋',358,386,'青果'),
('国内産 若どりむね肉','100g当り',69,74,'精肉'),
('ナガノパープル','1房',1280,1382,'青果'),
('バナナ／アボカド','各1コ',100,108,'青果'),
],
'2026-09-14':[
('国内産若どりカタ肉（解凍品）／あまに豚挽肉','各100g当り',99,106,'精肉'),
('ほうれん草','1袋',178,192,'青果'),
('蒸しベビーほたて（解凍・生食用）','100g当り',390,421,'鮮魚'),
('染みタレメンチカツ丼／牛カルビささがきごぼう丼','各1パック',399,430,'惣菜'),
('はごろもフーズ シーチキン Lフレーク','70g×4缶',438,473,'加工食品'),
('はごろもフーズ オイル不使用シーチキンマイルド','70g×4缶',398,429,'加工食品'),
('ヤクルト Newヤクルト／ヤクルト糖質・カロリー50%オフ','各65ml×10本',378,408,'飲料'),
('ライオン ソフラン プレミアム消臭 詰替特大','750ml',388,426,'日用品'),
('Haleon シュミテクト 歯周病ケア','95g',578,635,'日用品'),
],
'2026-09-15':[
('有機小松菜','1袋',128,138,'青果'),
('有機キウイフルーツ（サンゴールド）','1パック',690,745,'青果'),
('マルちゃん 麺づくり／ホットワンタン','各1個',99,106,'加工食品'),
('ミツカン 金のつぶ たれたっぷりたまご醤油たれ','40g×3',89,96,'日配食品'),
('プリマハム 香薫 あらびきウインナー','90g×2',259,279,'日配食品'),
],
}
for day,items in life_daily.items():
    for x in items:
        rows.append(row('life_hikawadai','ライフ','氷川台店',day,day,*x,source_type='current_flyer_daily_visual_verified',source_url=life_url,source_image=life_img,note=f'current-Life-daily-panel-{day}-visual-check'))

ok_url='https://tokubai.co.jp/%E3%82%AA%E3%83%BC%E3%82%B1%E3%83%BC/230806'
ok_img='5b5a513970be83e84534.jpg|67ce40d4d4c1e74bc9da.jpg'
# Five structured rows carried over from the handoff package.
with (DATA/'verified_products_floor.csv').open('r',encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        if r.get('store_id')!='ok_kamiitabashi': continue
        rows.append(row('ok_kamiitabashi','オーケー','上板橋店','2026-09-07','2026-09-13',r['product_name'],r['specification'],int(float(r['price_ex_tax_yen'])),int(float(r['price_in_tax_yen'])),'食品','tokubai_structured_verified',ok_url,ok_img,'handoff-structured-source-verified'))

ok=[
('和牛（黒毛和種）A4・A5等級 もも肉 厚切り／うすぎり','100g当り',579,625,'精肉'),('大粒牡蠣のフライ（広島県江田島産）','4個',399,430,'惣菜'),
('本まぐろ 中とろ 刺身用','100g当り',899,970,'鮮魚'),('バナメイえび','100g当り',159,171,'鮮魚'),('かつおたたき 刺身用','100g当り',199,214,'鮮魚'),
('めかじき 切身','100g当り',248,267,'鮮魚'),('豚ロース肉（ロイン）ステーキカット','100g当り',195,210,'精肉'),('若鶏手羽元','100g当り',89,96,'精肉'),
('大粒 味付あさり（スタミナ味・塩たれ味）','100g当り',168,181,'鮮魚'),('めかじき カツレツ用 香草＆焦がし醤油風','1枚',90,97,'鮮魚'),
('鰻蒲焼 網カット','160g',898,969,'鮮魚'),('ビビンバ丼 温泉玉子入り','1パック',359,387,'惣菜'),('大盛り 豚ロース生姜焼き弁当','1パック',359,387,'惣菜'),
('岩手県大船渡産 さんま竜田揚げ','100g当り',279,301,'惣菜'),('5種のナムル（だいこん・ぜんまい・ほうれん草・もやし・にんじん）','1パック',319,344,'惣菜'),
('ねぎとろ中巻','16カン＋2カン増量',580,626,'寿司'),('トーラク 北海道産かぼちゃのプリン','95g',108,116,'デザート'),('SUNTORY 伊右衛門 京都サイダー','500ml',98,105,'飲料'),
('AJINOMOTO ザ★チャーハン','580g',389,420,'冷凍食品'),('AJINOMOTO ギョーザ','12個',183,197,'冷凍食品'),('ニコニコのり 味のり ○等級原料使用 卓上','10切70枚（全型7枚）',513,554,'乾物'),
('日清 国内麦小麦粉','700g',183,197,'粉類'),('オーケー 白菜キムチ','360g＋40g',459,495,'漬物'),('ハナマルキ 塩こうじ','300g',240,259,'調味料'),
('オーケー 国産 煎り大豆','75g',98,105,'豆類'),('ロッテ 生チョコパイ','1個',168,181,'菓子'),
('伊藤ハム アルトバイエルン（ウインナー）','292g＋30g増量',381,411,'日配食品'),
('リケン 素材力だし 本かつおだし お徳用','5gスティック×28本',615,664,'調味料'),
('ヤマサ 特選 有機丸大豆の吟選しょうゆ','1L',299,322,'調味料'),
('秋本 白菜の浅漬','270g＋30g増量',198,213,'漬物'),
('中国産 ピーナッツ','230g',199,214,'豆類'),
('ひかり味噌 朝のむ あまざけ','1000ml',298,321,'飲料'),
('Pasco たっぷりコーンマヨネーズ','1個',116,125,'パン'),
('ヤマザキ シュガーロール','5個',139,150,'パン'),
('グリコ 炊き込み御膳 とり五目／鶏ごぼう','各3合用',319,344,'加工食品'),
]
for x in ok: rows.append(row('ok_kamiitabashi','オーケー','上板橋店','2026-09-07','2026-09-13',*x,source_type='local_original_visual_verified',source_url=ok_url,source_image=ok_img))
# 10% taxable priced items on the same current OK flyer. Household goods are now permitted.
ok_tax10=[
('デリブティック ティシューペーパー','200組×5個',299,328,'日用品'),
('アサヒビール GINON レモン（缶チューハイ）','350ml',99,108,'酒類'),
('JNTLコンシューマーヘルス 薬用リステリン トータルケアプラス','洗口液 1000ml×2本パック',1380,1518,'日用品'),
('P&G JOY W除菌 逆さボトル さわやか微香','食器用洗剤 本体290ml',158,173,'日用品'),
('レキットベンキーザー フィニッシュ 凝縮パワーキューブ','食洗機用洗剤 特大サイズ100個',1320,1452,'日用品'),
('NSファーファ・ジャパン ファーファ ストーリー そらのお散歩 フローラルソープの香り','柔軟剤 詰替用 特大1200ml',540,594,'日用品'),
]
for x in ok_tax10: rows.append(row('ok_kamiitabashi','オーケー','上板橋店','2026-09-07','2026-09-13',*x,source_type='local_original_visual_verified',source_url=ok_url,source_image=ok_img,tax_rate=0.10))

# Old 9/9 Comodi rows are not published in vNext; canonical data follows the current 9/12-9/15 issue.
com_url='https://chirashi-guide.com/chirashi-file/2026/09/56/56-260912o___3102002_0.jpg'
# 9/13 panel: use only entries visibly tied to the 9/13 section. Names are kept conservative where branding is not material.
com_current=[
('大阪王将 羽根つき餃子','1パック',158,170,'冷凍食品'),('フジッコ ごま昆布','1パック',138,149,'佃煮'),('ヤマザキ ダブルソフト','6枚',178,192,'パン'),
('トマト','1パック',350,378,'青果'),('シャインマスカット','1房',1000,1080,'青果'),
('豚肉 切り落とし','100g当り',89,96,'精肉'),('牛肉 切り落とし','100g当り',599,646,'精肉'),('まぐろたたき','1パック',350,378,'鮮魚'),('刺身用サーモン','1パック',599,646,'鮮魚'),
]
for x in com_current: rows.append(row('comodi_sakuragawa','コモディイイダ','食彩館桜川店','2026-09-13','2026-09-13',*x,source_type='current_web_visual_verified',source_url=com_url,source_image='56-260912o___3102002_0.jpg',note='current-issue-9/13-panel-visual-check'))

com_daily={
'2026-09-12':[
('あづま食品 国産中粒納豆','3個組',88,95,'日配食品'),
('ヤクルト プレーン／カロリーハーフ','1パック',348,375,'飲料'),
('うさぎ 生切り餅','1kg',898,969,'食品'),
('ブロッコリー','1コ',178,192,'青果'),
('北海道産 生さんま','1尾',198,213,'鮮魚'),
('北海道産 じゃがいも','1袋',198,213,'青果'),
('刺身盛合せ','1パック',850,918,'鮮魚'),
('銀鮭切身','1パック',599,646,'鮮魚'),
],
'2026-09-14':[
('明治 ブルガリアヨーグルト','1パック',118,127,'日配食品'),
('味の素 丸鶏がらスープ','1袋',278,300,'調味料'),
('レタス','1個',98,105,'青果'),
('国内産 若どりむね肉','100g当り',69,74,'精肉'),
('ネスカフェ エクセラ ボトルコーヒー','1本',98,105,'飲料'),
],
'2026-09-15':[
('きゅうり','1袋',98,105,'青果'),
('ミニトマト','1パック',128,138,'青果'),
('ハーゲンダッツ アソートボックス','1箱',777,839,'アイス'),
('ロールパン','1袋',98,105,'パン'),
('ハンバーグ','1パック',99,106,'惣菜'),
('挽肉','100g当り',369,398,'精肉'),
],
}
for day,items in com_daily.items():
    img='56-260912o___3102002_0.jpg' if day in ('2026-09-12','2026-09-13') else '56-260912u___3141311_0.jpg'
    url='https://chirashi-guide.com/chirashi-file/2026/09/56/'+img
    for x in items:
        rows.append(row('comodi_sakuragawa','コモディイイダ','食彩館桜川店',day,day,*x,source_type='current_web_visual_verified',source_url=url,source_image=img,note=f'current-issue-{day}-panel-visual-check'))


# Current Comodi 9/12-9/13 period panel (not daily-only; these remain under 全日 and are active on both days).
com_two_day=[
('刺身盛合せ','6点盛',1580,1706,'鮮魚'),
('寿司盛合せ','1パック',980,1058,'寿司'),
('広島県産 大粒カキフライ','1パック',599,646,'惣菜'),
]
for x in com_two_day:
    rows.append(row('comodi_sakuragawa','コモディイイダ','食彩館桜川店','2026-09-12','2026-09-13',*x,source_type='current_web_visual_verified',source_url='https://chirashi-guide.com/chirashi-file/2026/09/56/56-260912u___3141311_0.jpg',source_image='56-260912u___3141311_0.jpg',note='current-issue-9/12-9/13-panel-visual-check'))

# Super Belx Itabashi Nakadai: current 9/12-9/18 issue.
# Source basis: user-provided Tokubai PDF screenshots of both current flyer pages.
# The previous 5-row seed was intentionally replaced with a broad, visually verified baseline.
belx_page='https://sunbelx.com/store/14'
belx_img0='https://chirashi-guide.com/chirashi-file/2026/09/351/351-1_15968215_0.jpg'
belx_img1='https://chirashi-guide.com/chirashi-file/2026/09/351/351-1_15968215_1.jpg'
belx_verified=DATA/'belx_verified_products.csv'
with belx_verified.open('r',encoding='utf-8-sig',newline='') as f:
    for b in csv.DictReader(f):
        source_image=b['source_image']
        source_url=belx_img0 if source_image.endswith('_0.jpg') else belx_img1
        rows.append(row(
            'belx_itabashi_nakadai','スーパーベルクス','板橋中台店',
            b['sale_start'],b['sale_end'],b['product_name'],b['specification'],
            int(b['price_ex_tax_yen']),int(b['price_in_tax_yen']),b['category'],
            source_type='user_uploaded_pdf_visual_verified',
            source_url=source_url,source_image=source_image,
            note='Belx current flyer: visually verified from user-provided Tokubai PDF',
            tax_rate=float(b['tax_rate'])
        ))

# Validation before writing: exact expected composition and no duplicate key.
keys=set(); dup=[]
for r in rows:
    k=(r['store_id'],r['sale_start'],r['sale_end'],r['product_name'],r['specification'],str(r['price_in_tax_yen']))
    if k in keys: dup.append(k)
    keys.add(k)
if dup: raise SystemExit(f'duplicate snapshot keys: {dup[:5]}')
counts={}
active={}
for r in rows:
    counts[r['store_id']]=counts.get(r['store_id'],0)+1
    if r['sale_start']<=CURRENT<=r['sale_end']: active[r['store_id']]=active.get(r['store_id'],0)+1
# Counts are recorded for observability only. They are not release thresholds;
# future flyers may legitimately contain fewer or more products.
# Date buttons are issue metadata, not inferred from surviving rows.
# A 0-row day must remain visible so extraction gaps are observable instead of hiding the button.
with OUT.open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
manifest={
 'version':'vNext-verified-snapshot-20260913f', 'as_of_jst':CURRENT, 'rows':len(rows), 'counts':counts, 'active_counts':active, 'date_buttons':['2026-09-12','2026-09-13','2026-09-14','2026-09-15','2026-09-16','2026-09-17','2026-09-18'],
 'sources':{
  'life_current':{'url':life_url,'period':'2026-09-12..2026-09-14','images':life_img.split('|')},
  'ok_current':{'url':ok_url,'period':'2026-09-07..2026-09-13','images':ok_img.split('|')},
  'comodi_current':{'url':com_url,'period':'2026-09-12..2026-09-15','images':['56-260912o___3102002_0.jpg','56-260912u___3141311_0.jpg']},
  'belx_current':{'url':belx_page,'period':'2026-09-12..2026-09-18','images':[belx_img0.rsplit('/',1)[-1],belx_img1.rsplit('/',1)[-1]]},
 },
 'policy':'Snapshot rows are source-verified baseline data. Product counts are descriptive only, never release thresholds. Automated discovery/extraction is source-driven and fail-closed on integrity/provenance errors.'
}
(DATA/'verified_snapshot_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'out':str(OUT),'rows':len(rows),'counts':counts,'active':active},ensure_ascii=False))
