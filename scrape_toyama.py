# -*- coding: utf-8 -*-
"""
富山県神社庁「氏神神社検索」スクレイパー（香川方式: 住所+名前のみ。御祭神フィールドは
サイトに存在しないため常に空 — 2026-07-04 実ページ確認済み）

構造:
- https://toyama-jinjacho.sakura.ne.jp/ujigami/ はWordPressサブサイト
- 個別記事はWP標準検索（?s=キーワード）で市町村名検索すると該当地域の記事がヒットする
  （wp-json REST APIはsearch結果を返さない/投稿一覧も空を返すため使えず、
  HTML検索結果ページのページネーションで収集する）
- 検索結果 <h2 class="entry-title"><a href="...">地域名</a></h2> → 個別ページへのリンク
- 個別ページはtable形式: 神社名/社名カナ/郵便番号/住所/宮司名/電話番号/FAX番号/鎮座地/
  御神札/ホームページ。御祭神フィールドは無い
- 宮司名（個人名）・電話番号・FAX番号は事実データ（名称/住所/祭神/例祭日/座標）の
  範囲外のため取得しない
"""
import requests
import json
import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup

BASE = 'https://toyama-jinjacho.sakura.ne.jp/ujigami'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research)'}
SLEEP = 1.0
GEOCODE = True

MUNICIPALITIES = [
    '富山市', '高岡市', '魚津市', '氷見市', '滑川市', '黒部市', '砺波市', '小矢部市',
    '南砺市', '射水市', '舟橋村', '上市町', '立山町', '入善町', '朝日町',
]


def get_shrine_urls():
    """全市町村名でWP検索し、ページネーションを辿って個別記事URLを収集"""
    urls = []
    seen = set()
    for muni in MUNICIPALITIES:
        page = 1
        while True:
            url = f'{BASE}/' if page == 1 else f'{BASE}/page/{page}/'
            try:
                r = requests.get(url, params={'s': muni}, headers=HEADERS, timeout=15)
            except Exception as e:
                print(f'  ERROR {muni} page{page}: {e}')
                break
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.content, 'html.parser')
            found_new = 0
            for h2 in soup.select('h2.entry-title'):
                a = h2.find('a', href=True)
                if not a:
                    continue
                href = urljoin(BASE + '/', a['href'])
                if href not in seen:
                    seen.add(href)
                    urls.append(href)
                    found_new += 1
            print(f'  {muni} page{page}: 新規{found_new}件 (累計{len(urls)})')
            has_next = bool(soup.select_one('.nav-next a'))
            if found_new == 0 or not has_next:
                break
            page += 1
            time.sleep(SLEEP)
        time.sleep(SLEEP)
    return urls


def parse_shrine_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content, 'html.parser')
        data = {}
        for row in soup.find_all('tr'):
            th = row.find('th')
            td = row.find('td')
            if th and td:
                data[th.get_text(strip=True)] = td.get_text(strip=True)

        name = data.get('神社名', '')
        if not name:
            return None
        address = data.get('住所', '')
        postal = data.get('郵便番号', '')
        if address and not address.startswith('富山県'):
            address = '富山県' + address

        notes = ''
        if postal:
            notes = f'〒{postal}'

        return {
            'name': name,
            'pref': '富山県',
            'address': address,
            'deity': '',   # サイトに御祭神フィールド自体が無い
            'lat': None,
            'lng': None,
            'festivals': [],
            'festivals_raw': '',
            'notes': notes,
            'official_url': '',
            'source_url': url,
            'source': 'toyama_jinjacho',
        }
    except Exception as e:
        print(f'  ERROR {url}: {e}')
        return None


def main():
    print('=== 富山県神社庁 氏神神社検索 スクレイプ開始 ===')
    urls = get_shrine_urls()
    print(f'詳細ページURL: {len(urls)}件')

    shrines = []
    for i, url in enumerate(urls):
        s = parse_shrine_page(url)
        if s:
            shrines.append(s)
        if (i + 1) % 50 == 0:
            print(f'  {i+1}/{len(urls)} 完了 (取得{len(shrines)}件)')
        time.sleep(SLEEP)

    if GEOCODE:
        import urllib.parse
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

    with open('toyama_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)
    print(f'保存: toyama_raw.json ({len(shrines)}件)')
    with_coord = sum(1 for s in shrines if s.get('lat'))
    print(f'座標あり: {with_coord}件')


if __name__ == '__main__':
    main()
