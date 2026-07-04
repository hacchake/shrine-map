# -*- coding: utf-8 -*-
"""
data.json 総合品質チェック（レポート専用・修正は一切行わない）

使い方:
  python3 check_data.py            # 全件チェックしてレポートをファイル出力
  python3 check_data.py --data other.json

出力: check_data_report.txt に
  - 検査項目×source別 件数マトリクス（多い順）
  - 各検査項目の実例（最大3件）

検査項目（2026-07-04までに実セッションで発見した不具合パターンを網羅）:
  1. 文字化け        cp932/UTF-8二重デコードの痕跡（U+FFFD、半角カナ混入）
  2. name汚染        ページタイトル等の混入（「公式ホームページ」「〜市」直結等）
  3. ルビ連結        カタカナ読み+漢字名が区切りなく連結（ヤクモジンジャ八雲神社型）
  4. 住所の残骸      郵便番号が先頭以外の位置にある、TEL/FAX等の混入
  5. 県名整合        addressの先頭県名とprefフィールドの不一致・県名なし
  6. 座標整合        lat/lngの位置が示す県とaddressの県が食い違う、日本域外
  7. 祭典増殖        festivals内の重複・開始位置ズレによる分裂（静岡型）
  8. 祭典ズレ        日付＋次の祭典名が1フィールドに合体（岡山型）
  9. 形式不備        festivals=null、month範囲外、idフィールド欠落
  10. 完全重複        name+addressが一致する重複レコード
"""
import json
import re
import math
import argparse
from collections import defaultdict, Counter

FULLWIDTH_KATAKANA = re.compile(r'[｡-ﾟ]')  # 半角カナ全域(記号込み)

# 都道府県の大まかな緯度経度範囲（本土＋主要離島を含む生成、判定は緩め）
PREF_BBOX = {
    '北海道': (41.3, 45.6, 139.3, 148.9), '青森県': (40.2, 41.6, 139.5, 141.7),
    '岩手県': (38.7, 40.4, 140.6, 142.1), '宮城県': (37.8, 39.0, 140.3, 141.7),
    '秋田県': (38.9, 40.5, 139.7, 140.9), '山形県': (37.7, 39.2, 139.5, 140.7),
    '福島県': (36.8, 37.9, 139.2, 141.1), '茨城県': (35.7, 36.9, 139.7, 140.9),
    '栃木県': (36.2, 37.2, 139.3, 140.3), '群馬県': (35.9, 37.1, 138.4, 139.7),
    '埼玉県': (35.7, 36.3, 138.7, 139.9), '千葉県': (34.9, 36.1, 139.7, 140.9),
    '東京都': (24.2, 35.9, 136.0, 153.9), '神奈川県': (35.1, 35.7, 138.9, 139.8),
    '新潟県': (36.7, 38.6, 137.6, 139.9), '富山県': (36.3, 36.9, 136.8, 137.8),
    '石川県': (36.0, 37.6, 136.2, 137.4), '福井県': (35.3, 36.3, 135.4, 136.8),
    '山梨県': (35.1, 35.9, 138.2, 139.2), '長野県': (35.2, 37.0, 137.3, 138.8),
    '岐阜県': (35.1, 36.5, 136.3, 137.7), '静岡県': (34.6, 35.7, 137.5, 139.2),
    '愛知県': (34.5, 35.5, 136.7, 137.9), '三重県': (33.7, 35.3, 135.8, 136.9),
    '滋賀県': (34.8, 35.7, 135.8, 136.5), '京都府': (34.7, 35.8, 134.8, 136.0),
    '大阪府': (34.2, 34.9, 135.1, 135.7), '兵庫県': (34.1, 35.7, 134.2, 135.5),
    '奈良県': (33.9, 34.8, 135.5, 136.2), '和歌山県': (33.4, 34.4, 135.0, 136.0),
    '鳥取県': (35.0, 35.6, 133.1, 134.5), '島根県': (34.3, 36.4, 131.6, 133.4),
    '岡山県': (34.3, 35.4, 133.3, 134.4), '広島県': (34.0, 35.1, 132.0, 133.5),
    '山口県': (33.7, 34.8, 130.8, 132.5), '徳島県': (33.6, 34.4, 133.6, 134.8),
    '香川県': (34.0, 34.6, 133.4, 134.5), '愛媛県': (32.9, 34.3, 132.0, 133.7),
    '高知県': (32.7, 33.9, 132.5, 134.3), '福岡県': (33.1, 34.2, 129.9, 131.2),
    '佐賀県': (32.9, 33.6, 129.7, 130.5), '長崎県': (32.5, 34.7, 128.0, 130.5),
    '熊本県': (32.1, 33.2, 129.9, 131.4), '大分県': (32.7, 33.8, 130.8, 132.1),
    '宮崎県': (31.3, 32.9, 130.7, 131.9), '鹿児島県': (24.0, 32.3, 122.9, 131.2),
    '沖縄県': (24.0, 27.9, 122.9, 131.4),
}
JAPAN_BBOX = (20.0, 46.0, 122.0, 154.0)
PREF_NAMES = list(PREF_BBOX.keys())


def addr_pref(addr):
    """addressの先頭が実在の都道府県名で始まるか判定。汎用正規表現
    （例: r'^...??[都道府県]'）だと「三木市府内783」の「府」を誤って
    プレフィックスとして拾う事故があったため、実在47都道府県名の
    完全一致リストでチェックする"""
    addr = addr or ''
    for p in PREF_NAMES:
        if addr.startswith(p):
            return p
    return None


def check_mojibake(d):
    """U+FFFDは全フィールドで真の破損の証拠。半角カナ文字（｡-ﾟ）はaddressでは
    「猿ｹ京」「木ﾉ庄」等の正当な地名表記（ヶ/ノ/・/ーの半角代用）である
    ケースが大半（2026-07-04調査済み）なので、name/deityのみで半角カナを検査し
    誤検出を抑える。addressは念のためU+FFFDのみ検査する"""
    hits = []
    for field in ('name', 'address', 'deity'):
        v = d.get(field) or ''
        if not v:
            continue
        if '�' in v:
            hits.append(f'{field}={v!r} (U+FFFD)')
        elif field != 'address' and FULLWIDTH_KATAKANA.search(v):
            hits.append(f'{field}={v!r} (半角カナ混入)')
    return hits


def check_name_pollution(d):
    name = d.get('name') or ''
    reasons = []
    if '公式ホームページ' in name or 'ホームページ' in name:
        reasons.append('「ホームページ」混入')
    if re.search(r'(市|区|町|村)$', name) and len(name) > 12:
        reasons.append('末尾が市区町村名で長すぎる')
    if re.search(r'[（(]?公式[)）]?$', name):
        reasons.append('「公式」で終端')
    return reasons


RUBY_SUFFIX_PAIRS = [
    ('ジンジャ', '神社'), ('ジングウ', '神宮'), ('タイシャ', '大社'),
    ('グウ', '宮'), ('シャ', '社'), ('ジンジャチョウ', '神社庁'),
]


def check_ruby_concat(d):
    """「ヤクモジンジャ八雲神社」型: 冒頭の片仮名ブロックが直後の漢字名の
    「読み」になっている（片仮名側が神社系の読みで終わり、漢字側も対応する
    表記で終わる）場合のみ検出。単に片仮名の固有名（例:「ビリケン神社」
    「オートバイ神社」）は片仮名部分が読みの語尾（ジンジャ等）で終わらない
    ため誤検出しない"""
    name = d.get('name') or ''
    m = re.match(r'^([ァ-ヶー]{4,})([一-龠].*)$', name)
    if not m:
        return []
    kana, kanji = m.group(1), m.group(2)
    for kana_suf, kanji_suf in RUBY_SUFFIX_PAIRS:
        if kana.endswith(kana_suf) and kanji.endswith(kanji_suf):
            return [f'name={name!r} (読み={kana} / 実名={kanji})']
    return []


def check_address_debris(d):
    addr = d.get('address') or ''
    reasons = []
    if not addr:
        return reasons
    zip_m = re.search(r'\d{3}-?\d{4}', addr)
    if zip_m and zip_m.start() > 3:
        reasons.append(f'郵便番号が先頭以外(pos={zip_m.start()})')
    if re.search(r'TEL|FAX|電話|連絡先', addr, re.IGNORECASE):
        reasons.append('TEL/FAX/連絡先の混入')
    return reasons


def check_pref_noprefix(d):
    """addressが都道府県名から始まっていない（低優先度・大半は単なる表記省略。
    kagawa/toyama等、元々スクレイパーが「県」を前置しない方針の由来データも
    多く含まれる）"""
    addr = d.get('address') or ''
    pref = d.get('pref') or ''
    if not addr or not pref:
        return []
    if addr_pref(addr) is None:
        return [f'addressが都道府県名で始まらない: {addr!r}']
    return []


def check_pref_wrong(d):
    """addressの先頭県名とprefフィールドが実際に食い違う（高優先度・
    データが指す実際の場所が別県である可能性が高い真のバグ）"""
    addr = d.get('address') or ''
    pref = d.get('pref') or ''
    if not addr or not pref:
        return []
    ap = addr_pref(addr)
    if ap is not None and ap != pref:
        return [f'address県({ap}) != prefフィールド({pref})']
    return []


def check_coord_mismatch(d):
    lat, lng = d.get('lat'), d.get('lng')
    pref = d.get('pref') or ''
    if lat is None or lng is None:
        return []
    reasons = []
    jmin_lat, jmax_lat, jmin_lng, jmax_lng = JAPAN_BBOX
    if not (jmin_lat <= lat <= jmax_lat and jmin_lng <= lng <= jmax_lng):
        reasons.append(f'日本域外の座標 lat={lat},lng={lng}')
        return reasons
    box = PREF_BBOX.get(pref)
    if box:
        min_lat, max_lat, min_lng, max_lng = box
        if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
            reasons.append(f'{pref}の範囲外の座標 lat={lat},lng={lng}')
    return reasons


def check_festival_dup(d):
    fests = d.get('festivals') or []
    if len(fests) < 2:
        return []
    reasons = []
    seen = []
    for f in fests:
        key = ((f.get('name') or '').strip(), (f.get('date_str') or '').strip())
        if key in seen:
            reasons.append(f'完全重複エントリ: {key}')
        seen.append(key)
    combined = [(f.get('name') or '') + (f.get('date_str') or '') for f in fests]
    for i in range(len(combined)):
        for j in range(i + 1, len(combined)):
            a, b = combined[i], combined[j]
            if len(a) >= 6 and len(b) >= 6 and a != b and (a in b or b in a):
                reasons.append(f'部分文字列重複(分裂疑い): {a!r} <-> {b!r}')
    return reasons


MISALIGN_PATTERN = re.compile(r'[0-9０-９]+月|：|曜日')


def check_festival_misalign(d):
    fests = d.get('festivals') or []
    reasons = []
    for f in fests:
        name = f.get('name') or ''
        if MISALIGN_PATTERN.search(name):
            reasons.append(f'nameに日付らしき文字列混入: {name!r}')
    return reasons


def check_schema(d):
    reasons = []
    if d.get('festivals') is None:
        reasons.append('festivals=null')
    for f in (d.get('festivals') or []):
        m = f.get('month')
        if m is not None and not (isinstance(m, int) and 1 <= m <= 12):
            reasons.append(f'month範囲外: {m!r}')
    if not d.get('id'):
        reasons.append('idフィールド欠落')
    return reasons


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', default='data.json')
    p.add_argument('--out', default='check_data_report.txt')
    args = p.parse_args()

    with open(args.data, encoding='utf-8') as f:
        data = json.load(f)
    total = len(data)

    checks = [
        ('1_文字化け', check_mojibake),
        ('2_name汚染', check_name_pollution),
        ('3_ルビ連結', check_ruby_concat),
        ('4_住所残骸', check_address_debris),
        ('5a_県名プレフィックスなし_低優先', check_pref_noprefix),
        ('5b_県名不一致_要確認', check_pref_wrong),
        ('6_座標不整合', check_coord_mismatch),
        ('7_祭典増殖', check_festival_dup),
        ('8_祭典ズレ', check_festival_misalign),
        ('9_形式不備', check_schema),
    ]

    matrix = defaultdict(Counter)  # matrix[category][source] = count
    examples = defaultdict(list)   # examples[category] = [(record, reasons), ...]

    for d in data:
        src = d.get('source', '?')
        for cat, fn in checks:
            reasons = fn(d)
            if reasons:
                matrix[cat][src] += 1
                if len(examples[cat]) < 3:
                    examples[cat].append((d, reasons))

    # 10. 完全重複（name+address一致）
    dup_groups = defaultdict(list)
    for i, d in enumerate(data):
        addr = d.get('address') or ''
        if not addr:
            continue
        key = (d.get('name', ''), addr)
        dup_groups[key].append(i)
    dup_cat = '10_完全重複'
    for key, idxs in dup_groups.items():
        if len(idxs) > 1:
            src = data[idxs[0]].get('source', '?')
            matrix[dup_cat][src] += len(idxs)
            if len(examples[dup_cat]) < 3:
                examples[dup_cat].append((data[idxs[0]], [f'{len(idxs)}件重複: {key}']))

    lines = []
    lines.append(f'# data.json 総合品質チェックレポート\n')
    lines.append(f'総レコード数: {total}\n')

    lines.append('## 検査項目×source別 件数マトリクス\n')
    all_cats = [c for c, _ in checks] + [dup_cat]
    for cat in all_cats:
        counter = matrix[cat]
        total_hits = sum(counter.values())
        lines.append(f'\n### {cat}（該当 {total_hits}件）')
        if not counter:
            lines.append('  該当なし')
            continue
        for src, cnt in counter.most_common(15):
            lines.append(f'  {src}: {cnt}件')
        if len(counter) > 15:
            lines.append(f'  ...他{len(counter)-15}ソース')

    lines.append('\n\n## 実例（各項目最大3件）\n')
    for cat in all_cats:
        lines.append(f'\n### {cat}')
        if not examples[cat]:
            lines.append('  該当なし')
            continue
        for d, reasons in examples[cat]:
            lines.append(f'  id={d.get("id")} name={d.get("name")!r} pref={d.get("pref")} source={d.get("source")}')
            for r in reasons:
                lines.append(f'    - {r}')

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'レポート出力: {args.out}')
    print(f'総レコード数: {total}')
    for cat in all_cats:
        print(f'{cat}: {sum(matrix[cat].values())}件')


if __name__ == '__main__':
    main()
