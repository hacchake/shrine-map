# -*- coding: utf-8 -*-
"""
熊本県神社庁 スクレイパー
https://kumamotokenjinjacho.jp/patron-god/

構造（2026-07-04 実確認）:
- WordPressカスタム投稿タイプ「patron-god」（氏神様を探す）。一覧は
  /wp-json/wp/v2/patron-god?per_page=100&page=N で全件（571件）のlink/titleが
  取れるが、住所はREST APIに含まれない（ACF未公開）ため個別ページのHTMLが必要
- 個別ページの概要表（class="c-table-single"）に「対象神社名」「お住まいの地域」
  の2行のみ。御祭神・例祭・座標は一切掲載されていない → 香川方式（名称+住所のみ）
- 住所はセル内にHTMLコメントが混在するので get_text() で除去してから使う
- 住所は「阿蘇市...」のように県名なし → 「熊本県」を前置
"""
import requests
import json
import re
import time
import urllib.parse
from bs4 import BeautifulSoup

BASE = 'https://kumamotokenjinjacho.jp'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}


def fetch_list():
    items = []
    page_num = 1
    while True:
        r = requests.get(f'{BASE}/wp-json/wp/v2/patron-god',
                          params={'per_page': 100, 'page': page_num},
                          headers=HEADERS, timeout=20)
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        items.extend(batch)
        total_pages = int(r.headers.get('X-WP-TotalPages', page_num))
        if page_num >= total_pages:
            break
        page_num += 1
        time.sleep(0.3)
    return items


def parse_detail(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return ''
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table', class_='c-table-single')
        if not table:
            return ''
        for tr in table.find_all('tr'):
            th = tr.find('th')
            td = tr.find('td')
            if th and td and 'お住まいの地域' in th.get_text():
                return re.sub(r'\s+', '', td.get_text())
    except Exception as e:
        print(f'  ERROR {url}: {e}')
    return ''


def main():
    print('=== 熊本県神社庁 スクレイプ開始 ===')
    items = fetch_list()
    print(f'一覧取得: {len(items)}件')

    shrines = []
    for i, item in enumerate(items):
        name = re.sub(r'\s+', '', item['title']['rendered'])
        address = parse_detail(item['link'])
        if address and not address.startswith('熊本県'):
            address = '熊本県' + address
        shrines.append({
            'name': name,
            'pref': '熊本県',
            'address': address,
            'deity': '',
            'lat': None,
            'lng': None,
            'festivals': [],   # 御祭神・例祭とも掲載なし
            'festivals_raw': '',
            'notes': '',
            'official_url': '',
            'source_url': item['link'],
            'source': 'kumamoto_jinjacho',
        })
        if (i + 1) % 50 == 0:
            print(f'  {i+1}/{len(items)}')
        time.sleep(0.3)

    no_coords = [s for s in shrines if not s.get('lat') and s.get('address')]
    print(f'ジオコーディング対象: {len(no_coords)}件')
    ok = 0
    for i, s in enumerate(no_coords):
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
        if (i + 1) % 100 == 0:
            print(f'  {i+1}/{len(no_coords)} (成功{ok})')
        time.sleep(0.1)
    print(f'ジオコーディング成功: {ok}件')

    with open('kumamoto_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)
    print(f'保存: kumamoto_raw.json ({len(shrines)}件)')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
