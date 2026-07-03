# -*- coding: utf-8 -*-
"""
鹿児島県神社庁 スクレイパー
https://www.kagojinjacho.or.jp/

構造（2026-07-04 実確認）:
- WordPress通常投稿（post）として神社ごとに1記事。REST API
  （/wp-json/wp/v2/posts?per_page=100&page=N、全1250件）で全件取得でき、
  クロール不要。本文に「神社名：」を含むものが神社記事（1104件）、
  それ以外はお知らせ等（146件）
- 本文構造:
    <div id="detail"><ul>
      <li>神社名：...</li><li>神社名カナ：...</li><li>鎮座地：〒NNN-NNNN 住所</li>
      <li>例祭日：漢数字の月日（例: 九月二十三日）</li><li>通称：</li>
      <li>旧社格：</li><li>神紋：</li><li>摂末社：</li><li>社宝：</li>
    </ul></div>
    <h4>御祭神</h4><div class="templeMain"><ul class="gList"><li>神名（カナ）</li>...
    <h4>由緒</h4>...  ← 由緒は著作権配慮のため取得しない
- 例祭日は例祭率99.8%と非常に高いが、全角空白区切りで複数日程が
  並ぶことがあり、末尾に（春祭）等の全角/半角括弧で名前が付くことがある
- 鎮座地は郵便番号付きで県名なし（「垂水市市木2212」等）→ 郵便番号除去＋
  「鹿児島県」前置。ジオコーディング不要な精度の住所なのでGSIで座標付与
"""
import requests
import json
import re
import time
import urllib.parse
from bs4 import BeautifulSoup

BASE = 'https://www.kagojinjacho.or.jp'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}

KANJI_MONTH = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
               '七': 7, '八': 8, '九': 9, '十': 10, '十一': 11, '十二': 12}


def parse_month_jp(text):
    text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    m = re.search(r'(\d+)月', text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return n
    for k, v in sorted(KANJI_MONTH.items(), key=lambda x: -len(x[0])):
        if f'{k}月' in text:
            return v
    return None


def parse_festivals(raw):
    raw = (raw or '').strip()
    if not raw:
        return []
    results = []
    for tok in re.split(r'[　\s]+', raw):
        if not tok:
            continue
        m = re.search(r'[（(]([^）)]+)[）)]\s*$', tok)
        if m:
            name = m.group(1).strip()
            date_str = tok[:m.start()].strip()
        else:
            name = '例祭'
            date_str = tok
        entry = {'name': name, 'date_str': date_str}
        month = parse_month_jp(date_str)
        if month:
            entry['month'] = month
        results.append(entry)
    return results


def fetch_all_posts():
    posts = []
    page_num = 1
    while True:
        r = requests.get(f'{BASE}/wp-json/wp/v2/posts',
                          params={'per_page': 100, 'page': page_num},
                          headers=HEADERS, timeout=20)
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        posts.extend(batch)
        total_pages = int(r.headers.get('X-WP-TotalPages', page_num))
        if page_num >= total_pages:
            break
        page_num += 1
        time.sleep(0.3)
    return posts


def parse_shrine(post):
    html = post['content']['rendered']
    if '神社名：' not in html:
        return None
    soup = BeautifulSoup(html, 'html.parser')
    detail = soup.find('div', id='detail')
    if not detail:
        return None
    fields = {}
    for li in detail.find_all('li'):
        t = li.get_text(strip=True)
        if '：' in t:
            k, v = t.split('：', 1)
            fields[k.strip()] = v.strip()

    name = fields.get('神社名', '')
    if not name:
        return None
    address = fields.get('鎮座地', '')
    address = re.sub(r'^〒?\d{3}-?\d{4}\s*', '', address)
    if address and not address.startswith('鹿児島県'):
        address = '鹿児島県' + address

    deity_parts = []
    for h4 in soup.find_all('h4'):
        if h4.get_text(strip=True) == '御祭神':
            div = h4.find_next_sibling('div', class_='templeMain')
            if div:
                deity_parts = [li.get_text(strip=True) for li in div.find_all('li')]
            break
    deity = '・'.join(deity_parts)

    festival_raw = fields.get('例祭日', '')

    return {
        'name': name,
        'pref': '鹿児島県',
        'address': address,
        'deity': deity,
        'lat': None,
        'lng': None,
        'festivals': parse_festivals(festival_raw),
        'festivals_raw': festival_raw,
        'notes': '',
        'official_url': '',
        'source_url': post['link'],
        'source': 'kagoshima_jinjacho',
    }


def main():
    print('=== 鹿児島県神社庁 スクレイプ開始 ===')
    posts = fetch_all_posts()
    print(f'投稿取得: {len(posts)}件')

    shrines = []
    for p in posts:
        s = parse_shrine(p)
        if s:
            shrines.append(s)
    print(f'神社データ: {len(shrines)}件')

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

    with open('kagoshima_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)

    reisai = sum(1 for s in shrines if s.get('festivals'))
    print(f'保存: kagoshima_raw.json ({len(shrines)}件)')
    print(f'例祭率: {reisai}/{len(shrines)} ({reisai/max(len(shrines),1)*100:.1f}%)')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
