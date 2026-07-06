# -*- coding: utf-8 -*-
"""
新潟県神社庁 スクレイパー（新規作成）
https://niigata-jinjacho.jp/shrine_niigata/

背景: 2026-07-05の偵察調査で、`/shrine_niigata/search.php` が
`area=`（空＝県内全域）・`num=100`（1ページ件数）・`page=N`で全件を
静的HTMLとして返すことを確認。robots.txt自体が存在せず（アクセス時に
トップページが返る＝実質無制限）、高知のようなJSレンダリングは不要。

構造（2026-07-05実確認）:
- `search.php?area=&num=100&page=N` の1ページに`<div class="shrine">`が
  最大100件並ぶ。各div内は
  `<dt class="name">/<dd class="name">神社名</dd>`
  `<dt class="furigana">/<dd class="furigana">ふりがな</dd>`
  `<dt class="place">/<dd class="place">住所<span>(Google Map...)</span></dd>`
  の3項目のみ。例祭・御祭神のフィールド自体が存在しない（香川方式）
- 座標は掲載されていない（Google Map検索リンクのみ）ためGSI APIでジオコーディング
- ページ1件目（page省略時）に総件数が `<p class="number"><strong>N</strong>件</p>`
  として表示される
- 高知と同様、情報源側の重複登録・半角カタカナ混入が無いか取得後に確認すること
"""
import re
import time
import json
import unicodedata
import urllib.parse
import requests
from bs4 import BeautifulSoup

BASE = 'https://niigata-jinjacho.jp/shrine_niigata/search.php'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}
SLEEP = 1.0
PER_PAGE = 100

FULLWIDTH_KATAKANA = re.compile(r'[｡-ﾟ]')
_HALFWIDTH_TABLE = {cp: unicodedata.normalize('NFKC', chr(cp)) for cp in range(0xFF61, 0xFFA0)}
_HALFWIDTH_TABLE[ord('ｹ')] = 'ヶ'


def normalize_name(name):
    if FULLWIDTH_KATAKANA.search(name):
        return name.translate(_HALFWIDTH_TABLE)
    return name


def fetch_page(page):
    params = {'area': '', 'num': PER_PAGE, 'page': page}
    r = requests.get(BASE, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = 'utf-8'
    soup = BeautifulSoup(r.text, 'html.parser')

    total = None
    m = soup.select_one('p.number strong')
    if m:
        total = int(m.get_text(strip=True))

    shrines = []
    for div in soup.select('div.shrine'):
        dl = div.find('dl')
        if not dl:
            continue
        name_dd = dl.find('dd', class_='name')
        place_dd = dl.find('dd', class_='place')
        name = name_dd.get_text(strip=True) if name_dd else ''
        if not name:
            continue
        # placeの<span>(Google Map...)</span>は除去してから住所本体だけ取る
        address = ''
        if place_dd:
            span = place_dd.find('span')
            if span:
                span.extract()
            address = place_dd.get_text(strip=True)
        if address and not address.startswith('新潟県'):
            address = '新潟県' + address
        shrines.append({'name': normalize_name(name), 'address': address})
    return shrines, total


def main():
    print('=== 新潟県神社庁 スクレイプ開始 ===')
    all_shrines = []
    total = None
    page = 1
    while True:
        try:
            shrines, page_total = fetch_page(page)
        except Exception as e:
            print(f'  ERROR page={page}: {e}')
            break
        if page_total:
            total = page_total
        if not shrines:
            print(f'  page={page}: 0件、終了')
            break
        all_shrines.extend(shrines)
        print(f'  page={page}: {len(shrines)}件 (累計{len(all_shrines)}件 / 全{total}件)')
        if total and len(all_shrines) >= total:
            break
        page += 1
        time.sleep(SLEEP)

    print(f'取得完了: {len(all_shrines)}件')

    # 情報源側の重複登録チェック（高知で確認済みのパターン）
    seen = set()
    deduped = []
    for s in all_shrines:
        key = (s['name'], s['address'])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)
    print(f'重複除去: {len(all_shrines)}件 → {len(deduped)}件')

    shrines = []
    for s in deduped:
        shrines.append({
            'name': s['name'],
            'pref': '新潟県',
            'address': s['address'],
            'deity': '',
            'lat': None,
            'lng': None,
            'festivals': [],
            'festivals_raw': '',
            'notes': '',
            'official_url': '',
            'source_url': BASE,
            'source': 'niigata_jinjacho',
        })

    no_coords = [s for s in shrines if not s.get('lat') and s.get('address')]
    print(f'ジオコーディング対象: {len(no_coords)}件')
    ok = 0
    for s in no_coords:
        try:
            r = requests.get(
                'https://msearch.gsi.go.jp/address-search/AddressSearch?q='
                + urllib.parse.quote(s['address']), timeout=8)
            results = r.json()
            if results:
                s['lng'] = float(results[0]['geometry']['coordinates'][0])
                s['lat'] = float(results[0]['geometry']['coordinates'][1])
                ok += 1
        except Exception:
            pass
        time.sleep(0.1)
    print(f'ジオコーディング成功: {ok}件')

    with open('niigata_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)

    print(f'保存: niigata_raw.json ({len(shrines)}件)')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
