# -*- coding: utf-8 -*-
"""
raw JSONファイルの座標なしレコードをGSI APIでジオコーディングする汎用ツール

使い方:
  python3 geocode_file.py okinawa_raw.json           # 上書き保存
  python3 geocode_file.py kagawa_raw.json --dry-run  # 件数確認のみ

data.json本体にも使える（--data-format）:
  python3 geocode_file.py data.json --data-format --dry-run
"""
import json
import sys
import time
import argparse
import urllib.parse
import requests


def geocode(address):
    try:
        r = requests.get(
            'https://msearch.gsi.go.jp/address-search/AddressSearch?q='
            + urllib.parse.quote(address), timeout=8)
        results = r.json()
        if results:
            coords = results[0]['geometry']['coordinates']
            return float(coords[1]), float(coords[0])  # lat, lng
    except Exception:
        pass
    return None, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('file')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--data-format', action='store_true',
                   help='data.json形式（トップレベルがdictの場合に対応）')
    args = p.parse_args()

    with open(args.file, encoding='utf-8') as f:
        data = json.load(f)
    shrines = data['shrines'] if (args.data_format and isinstance(data, dict)) else data

    targets = [s for s in shrines
               if not s.get('lat') and s.get('address')]
    print(f'対象: {len(targets)}件 / 全{len(shrines)}件')
    if args.dry_run:
        for s in targets[:20]:
            print(' ', s.get('name'), s.get('address'))
        return

    ok = 0
    for i, s in enumerate(targets):
        # 郵便番号はGSIの精度を下げるので除去
        addr = s['address'].replace('〒', '')
        import re
        addr = re.sub(r'^\s*\d{3}-\d{4}\s*', '', addr)
        lat, lng = geocode(addr)
        if lat:
            s['lat'], s['lng'] = lat, lng
            ok += 1
        if (i + 1) % 50 == 0:
            print(f'  {i+1}/{len(targets)} (成功{ok})')
        time.sleep(0.1)

    print(f'成功: {ok}/{len(targets)}')
    with open(args.file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f'保存: {args.file}')


if __name__ == '__main__':
    main()
