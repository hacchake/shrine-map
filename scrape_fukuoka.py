# -*- coding: utf-8 -*-
"""
福岡県神社庁 スクレイパー（新規作成・置き換え）
https://fukuoka-jinjacho.or.jp/

背景: 既存data.jsonのfukuoka_jinjacho 143件は、カスタム投稿タイプ
`/search/{名前}/`（REST API `/wp-json/wp/v2/search`で280件確認可能）由来
だったが、このページ自体は「神社検索」機能の共通テンプレートを使い回した
導入ページで、個別の実データ（住所等）を一切含んでいないことが2026-07-05の
偵察調査で判明。名前のみ・住所が全件空という不完全なデータだった。

実際のデータは`/area/{エリア}/`ページの静的HTML（`.p-area-list__cont`）に
名前・住所・電話が掲載されていることが判明したため、こちらから取得し直す。

構造（2026-07-05実確認）:
- エリアは4つ固定（area-sitemap.xmlで確認済み）: kitakyusyu, chikuho,
  fukuoka, chikugo
- 各エリアページの`.p-area-list__cont`が1神社分:
  `.p-area-list__text`(神社名、<a>で囲まれ外部公式サイトへのリンクを持つ
  ことがある) / `.p-area-list__add`(住所、市区町村から) /
  `.p-area-list__tel`(電話番号、個人情報配慮でスキップ)
- 4エリア合計280件（`/wp-json/wp/v2/search`のX-WP-Total件数と一致確認済み）
- 例祭・御祭神のフィールド自体が存在しない（香川方式）
- 座標は掲載されていないためGSI APIでジオコーディング
"""
import re
import time
import json
import unicodedata
import urllib.parse
import requests
from bs4 import BeautifulSoup

BASE = 'https://fukuoka-jinjacho.or.jp'
AREAS = ['kitakyusyu', 'chikuho', 'fukuoka', 'chikugo']
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}
SLEEP = 1.0

FULLWIDTH_KATAKANA = re.compile(r'[｡-ﾟ]')
_HALFWIDTH_TABLE = {cp: unicodedata.normalize('NFKC', chr(cp)) for cp in range(0xFF61, 0xFFA0)}
_HALFWIDTH_TABLE[ord('ｹ')] = 'ヶ'


def normalize_name(name):
    if FULLWIDTH_KATAKANA.search(name):
        return name.translate(_HALFWIDTH_TABLE)
    return name


def fetch_area(area):
    url = f'{BASE}/area/{area}/'
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = 'utf-8'
    soup = BeautifulSoup(r.text, 'html.parser')

    shrines = []
    for cont in soup.select('.p-area-list__cont'):
        text_el = cont.select_one('.p-area-list__text')
        add_el = cont.select_one('.p-area-list__add')
        if not text_el:
            continue
        name = normalize_name(text_el.get_text(strip=True))
        if not name:
            continue
        official_url = ''
        a = text_el.find('a')
        if a and a.get('href'):
            official_url = a['href']
        address = add_el.get_text(strip=True) if add_el else ''
        if address and not address.startswith('福岡県'):
            address = '福岡県' + address
        shrines.append({'name': name, 'address': address, 'official_url': official_url, 'area': area})
    return shrines


def main():
    print('=== 福岡県神社庁 スクレイプ開始 ===')
    all_shrines = []
    for area in AREAS:
        shrines = fetch_area(area)
        print(f'  {area}: {len(shrines)}件')
        all_shrines.extend(shrines)
        time.sleep(SLEEP)

    print(f'取得完了: {len(all_shrines)}件')

    # 情報源側の重複登録チェック（高知・新潟で確認済みのパターン）
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
            'pref': '福岡県',
            'address': s['address'],
            'deity': '',
            'lat': None,
            'lng': None,
            'festivals': [],
            'festivals_raw': '',
            'notes': s['area'],
            'official_url': s['official_url'],
            'source_url': f"{BASE}/area/{s['area']}/",
            'source': 'fukuoka_jinjacho',
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

    with open('fukuoka_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)

    print(f'保存: fukuoka_raw.json ({len(shrines)}件)')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
