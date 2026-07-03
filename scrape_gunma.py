# -*- coding: utf-8 -*-
"""
群馬県神社庁 スクレイパー
https://www.gunma-jinjacho.jp/jinja/

構造（2026-07-04 実確認）:
- 単一ページ（/jinja/）に14支部ぶんのtableが埋め込まれている（ページネーションなし）
- 各table行: 神社名(th) / カナ(td) / 所在地(td) / 連絡先(td, rowspanで複数神社共有) / ホームページ(td, rowspanで共有)
- 例祭・御祭神の項目はページ自体に存在しない → festivals/deityは常に空。名称+住所+ホームページのみ取得
- 所在地は「伊勢崎市...」のように県名なし → 「群馬県」を前置
- 旧scrape_gunma.py（リポジトリから消失）で生成されたgunma_raw.jsonは文字コード破損
  （U+FFFD混入で不可逆）だったため、本スクリプトで取り直す
"""
import requests
import json
import re
import time
import urllib.parse
from bs4 import BeautifulSoup

BASE = 'https://www.gunma-jinjacho.jp'
URL = f'{BASE}/jinja/'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}


def scrape():
    r = requests.get(URL, headers=HEADERS, timeout=15)
    r.encoding = 'utf-8'
    soup = BeautifulSoup(r.text, 'html.parser')

    shrines = []
    for section in soup.select('#list section'):
        shibu_h2 = section.find('h2')
        shibu = shibu_h2.get_text(strip=True) if shibu_h2 else ''

        for table in section.find_all('table'):
            current_url = ''
            for tr in table.find('tbody').find_all('tr'):
                th = tr.find('th')
                if not th:
                    continue
                name = th.get_text(strip=True)
                tds = tr.find_all('td')
                if not name or not tds:
                    continue
                address = tds[1].get_text(strip=True) if len(tds) > 1 else ''
                # ホームページ列（rowspanで最初の行にのみ出現）
                url_td = tr.find('td', class_='url')
                if url_td is not None:
                    a = url_td.find('a', href=True)
                    current_url = a['href'] if a else ''

                if address and not address.startswith('群馬県'):
                    address = '群馬県' + address

                shrines.append({
                    'name': name,
                    'pref': '群馬県',
                    'address': address,
                    'deity': '',
                    'lat': None,
                    'lng': None,
                    'festivals': [],       # 例祭フィールド自体がサイトに存在しない
                    'festivals_raw': '',
                    'notes': shibu,
                    'official_url': current_url,
                    'source_url': URL,
                    'source': 'gunma_jinjacho',
                })
    return shrines


def main():
    print('=== 群馬県神社庁 スクレイプ開始 ===')
    shrines = scrape()
    print(f'取得: {len(shrines)}件')

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

    with open('gunma_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)
    print(f'保存: gunma_raw.json ({len(shrines)}件)')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
