# -*- coding: utf-8 -*-
"""
手動キュレーションJSON（例: famous_shrines_manual.json）でdata.jsonを充実させる汎用スクリプト

使い方:
  python3 enrich_manual.py famous_shrines_manual.json --dry-run   # 件数確認
  python3 enrich_manual.py famous_shrines_manual.json             # 本適用

入力JSONは配列で、各エントリはdata.jsonと同じスキーマを想定:
  name, pref, address, deity, lat, lng, festivals, festivals_raw, notes,
  official_url, source_url, source

処理内容:
  - name＋prefで既存data.jsonレコードと照合（完全一致）
  - 既存があれば festivals / festivals_raw / notes / official_url を注入
    （値が空でないフィールドのみ上書き）。住所・座標・御祭神など他の
    フィールドは既存を優先し変更しない
  - 既存が見つからなければGSI APIでジオコーディングし新規レコードとして追加
    （入力側にlat/lngが既にあればジオコーディングはスキップ）
"""
import json
import re
import math
import sys
import time
import argparse
import urllib.parse
import requests

ENRICH_FIELDS = ['festivals', 'festivals_raw', 'notes', 'official_url']
NEAR_KM = 1.0  # 座標一致とみなす許容距離（厳しめ。都市部の高密度な神社群では
# 同名神社が数百m間隔で多数実在するため、緩い閾値だと無関係な近隣の神社を
# 誤って一致とみなす危険がある。実例: 富山市中心部の「日枝神社」は同名43件が
# 3km圏内に密集しており3km閾値では26件が誤ヒットしたが、1km閾値でも候補が
# 絞り切れないため below のexactly-one判定で正しくスキップされる）


def addr_core(addr):
    """都道府県名を除き、番地表記のゆらぎ（甲849番地 と 849 等）を吸収した
    住所本体（曖昧な部分一致比較用）。「榛名山町849」対「榛名山町甲849番地」
    のように地番の甲乙丙丁や「番地」の有無だけで不一致になるケースに対応"""
    a = re.sub(r'^..?[都道府県]', '', addr or '').strip()
    a = re.sub(r'番地?', '', a)
    a = re.sub(r'[甲乙丙丁](?=[0-9０-９])', '', a)
    return a


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def disambiguate(entry, data, matches, entry_lat=None, entry_lng=None):
    """同名・同県のレコードが複数ヒットした場合、住所→座標の順で絞り込む。
    「日枝神社」「八坂神社」「熱田神宮」等ありふれた社名・広域信仰の社名は
    県内に多数（無関係な）候補が存在するため、name+prefだけでは誤注入の
    危険がある（実例: 富山県「日枝神社」で43件ヒット中、該当は1件のみ。
    京都府「八坂神社」は5件とも住所が空で全て別の神社だった）。
    住所での特定に失敗し、かつ入力側に座標があれば、近接（NEAR_KM以内）の
    候補を探すフォールバックを行う（同名だが遠方にある無関係な神社を除外）。"""
    entry_addr = addr_core(entry.get('address', ''))
    if entry_addr:
        narrowed = []
        for i in matches:
            cand_addr = addr_core(data[i].get('address', ''))
            if not cand_addr:
                continue  # 空文字列は全ての文字列の部分文字列扱いになり誤検出するため除外
            if entry_addr in cand_addr or cand_addr in entry_addr:
                narrowed.append(i)
        if len(narrowed) >= 1:
            return narrowed, None  # 1件なら確定、複数なら同一神社の重複登録等とみなしまとめて注入

    if entry_lat is not None and entry_lng is not None:
        near = []
        for i in matches:
            clat, clng = data[i].get('lat'), data[i].get('lng')
            if clat is None or clng is None:
                continue
            if haversine_km(entry_lat, entry_lng, clat, clng) <= NEAR_KM:
                near.append(i)
        if len(near) == 1:
            return near, None  # 候補が1件に絞り切れた場合のみ確定（複数残るなら密集地帯とみなしスキップ）

    return None, matches  # 住所でも座標でも特定できず→スキップ


def geocode(address):
    try:
        r = requests.get(
            'https://msearch.gsi.go.jp/address-search/AddressSearch?q='
            + urllib.parse.quote(address), timeout=8)
        results = r.json()
        if results:
            coords = results[0]['geometry']['coordinates']
            return float(coords[1]), float(coords[0])
    except Exception:
        pass
    return None, None


def make_id(entry, idx):
    name_slug = re.sub(r'[^\w]', '', entry.get('name', 'unknown'))[:20]
    source = entry.get('source', 'manual')
    return f"{source}_{name_slug}_{idx:05d}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input_file', help='手動キュレーションJSON')
    p.add_argument('--data', default='data.json', help='data.jsonのパス')
    p.add_argument('--dry-run', action='store_true', help='保存せず確認のみ')
    args = p.parse_args()

    with open(args.data, encoding='utf-8') as f:
        data = json.load(f)
    print(f"data.json 読み込み: {len(data)}件")

    with open(args.input_file, encoding='utf-8') as f:
        manual = json.load(f)
    print(f"{args.input_file} 読み込み: {len(manual)}件")

    # name+prefで索引（同名同県が複数ある場合は全件に注入）
    index = {}
    for i, d in enumerate(data):
        key = (d.get('name', ''), d.get('pref', ''))
        index.setdefault(key, []).append(i)

    enriched = 0
    added = 0
    skipped = 0

    for entry in manual:
        key = (entry.get('name', ''), entry.get('pref', ''))
        matches = index.get(key)

        # 複数ヒット時の座標フォールバック用に、入力側の座標を先に確保しておく
        # （新規追加時のジオコーディングと共用し、二重にAPIを叩かない）
        addr = entry.get('address', '')
        lat, lng = entry.get('lat'), entry.get('lng')
        if not lat and addr and matches and len(matches) > 1:
            lat, lng = geocode(addr)
            time.sleep(0.1)

        if matches and len(matches) > 1:
            narrowed, ambiguous = disambiguate(entry, data, matches, lat, lng)
            if narrowed is None:
                skipped += 1
                print(f"  警告: {entry.get('name')}（{entry.get('pref')}）は同名{len(matches)}件がヒットしたが"
                      f"住所・座標で特定できず注入をスキップ（要目視確認: {entry.get('address')}）")
                continue
            matches = narrowed
        if matches:
            for i in matches:
                for field in ENRICH_FIELDS:
                    val = entry.get(field)
                    if val:
                        data[i][field] = val
            enriched += 1
            print(f"  充実: {entry.get('name')}（{entry.get('pref')}） ×{len(matches)}件")
        else:
            if not lat and addr:
                lat, lng = geocode(addr)
                time.sleep(0.1)
            new_rec = {
                'id': make_id(entry, added),
                'name': entry.get('name', ''),
                'pref': entry.get('pref', ''),
                'address': addr,
                'deity': entry.get('deity', ''),
                'lat': lat,
                'lng': lng,
                'festivals': entry.get('festivals', []),
                'festivals_raw': entry.get('festivals_raw', ''),
                'notes': entry.get('notes', ''),
                'official_url': entry.get('official_url', ''),
                'source_url': entry.get('source_url', ''),
                'source': entry.get('source', 'manual'),
            }
            data.append(new_rec)
            added += 1
            coord_status = 'あり' if lat else ('ジオコーディング失敗' if addr else '住所なし')
            print(f"  新規追加: {entry.get('name')}（{entry.get('pref')}） 座標={coord_status}")

    print(f"\n充実: {enriched}件 / 新規追加: {added}件 / スキップ(要確認): {skipped}件 / 合計: {len(data)}件")

    if not args.dry_run:
        with open(args.data, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        print(f"{args.data} 保存完了: {len(data)}件")
    else:
        print("（ドライランのため保存しません）")


if __name__ == '__main__':
    main()
