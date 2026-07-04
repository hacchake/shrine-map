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
import sys
import time
import argparse
import urllib.parse
import requests

ENRICH_FIELDS = ['festivals', 'festivals_raw', 'notes', 'official_url']


def addr_core(addr):
    """都道府県名を除いた住所本体（曖昧な部分一致比較用）"""
    return re.sub(r'^..?[都道府県]', '', addr or '').strip()


def disambiguate(entry, data, matches):
    """同名・同県のレコードが複数ヒットした場合、住所で絞り込む。
    「日枝神社」「八幡宮」等ありふれた社名は県内に多数存在するため、
    name+prefだけでは無関係な神社に祭事情報を誤注入する危険がある
    （実例: 富山県「日枝神社」で43件ヒットしたが該当は1件のみ）。"""
    entry_addr = addr_core(entry.get('address', ''))
    if not entry_addr:
        return None, matches  # 住所情報がなく絞り込めない
    narrowed = []
    for i in matches:
        cand_addr = addr_core(data[i].get('address', ''))
        if not cand_addr:
            continue  # 空文字列は全ての文字列の部分文字列扱いになり誤検出するため除外
        if entry_addr in cand_addr or cand_addr in entry_addr:
            narrowed.append(i)
    if len(narrowed) == 1:
        return narrowed, None
    if len(narrowed) == 0:
        return None, matches  # 住所でも特定できず→スキップ
    return narrowed, None  # 複数一致（同一神社の重複登録等）はまとめて注入


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
        if matches and len(matches) > 1:
            narrowed, ambiguous = disambiguate(entry, data, matches)
            if narrowed is None:
                skipped += 1
                print(f"  警告: {entry.get('name')}（{entry.get('pref')}）は同名{len(matches)}件がヒットしたが"
                      f"住所で特定できず注入をスキップ（要目視確認: {entry.get('address')}）")
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
            addr = entry.get('address', '')
            lat, lng = entry.get('lat'), entry.get('lng')
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
