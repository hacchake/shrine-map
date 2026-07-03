# -*- coding: utf-8 -*-
"""
佐賀県神社庁 スクレイパー
https://saga-jinjacho.jp/

構造（2026-07-04 実確認）:
- WordPress。神社ごとに個別ページ（固定ページ）があり、WP REST API
  （/wp-json/wp/v2/pages?per_page=100&page=N）で全件取得できる（全151ページ、
  クロールやHTML一覧探索は不要）
- 本文はテーブルではなく自由記述。ラベルは全角【】で囲まれる:
  【鎮座地】住所 / 【祭神】または【御祭神】 / 【祭礼】（例祭・春祭・秋祭等の日付、
  まれに【例祭】表記）/ 【由緒】【神事と芸能】【社宝】は由緒・長文につき著作権配慮で取得しない
- 【祭礼】は「名前（日付）　名前（日付）」の羅列だが、括弧なしで
  「名前日付」が全角スペース区切りで並ぶ場合もある（荒穂神社で実例）→
  括弧パターンを先に抽出し、残りは日付パターン(N月N日)を手がかりに分割
- 座標はGoogle Maps埋め込みiframeのsrcにある pb パラメータの !2d{lng}!3d{lat} から取得
  （ジオコーディング不要、既に高精度）
- 【鎮座地】が無いページ（お知らせ等の非神社ページ、151中約17件）は除外
"""
import requests
import json
import re
import time

BASE = 'https://saga-jinjacho.jp'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}

FULLWIDTH_DIGITS = str.maketrans('０１２３４５６７８９', '0123456789')


def parse_month_jp(text):
    text = text.translate(FULLWIDTH_DIGITS)
    m = re.search(r'(\d+)月', text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return n
    return None


def parse_festivals(raw):
    raw = (raw or '').strip()
    if not raw:
        return []
    results = []
    matched_spans = []
    for m in re.finditer(r'([^　\s（）]{0,10}?)（([^）]+)）', raw):
        name = m.group(1).strip() or '祭礼'
        date_str = m.group(2).strip()
        entry = {'name': name, 'date_str': date_str}
        month = parse_month_jp(date_str)
        if month:
            entry['month'] = month
        results.append(entry)
        matched_spans.append((m.start(), m.end()))

    leftover = raw
    for start, end in sorted(matched_spans, reverse=True):
        leftover = leftover[:start] + '　' + leftover[end:]
    leftover = leftover.strip('　 ')

    if leftover:
        date_pat = re.compile(r'[0-9０-９一二三四五六七八九十]+月[0-9０-９一二三四五六七八九十]+日[^　]*')
        pos = 0
        for dm in date_pat.finditer(leftover):
            name_part = leftover[pos:dm.start()].strip('　 ')
            date_str = dm.group(0).strip()
            entry = {'name': name_part or '祭礼', 'date_str': date_str}
            month = parse_month_jp(date_str)
            if month:
                entry['month'] = month
            results.append(entry)
            pos = dm.end()
    return results


def get_field(text, label):
    m = re.search(r'【' + re.escape(label) + r'】\s*\n?([^【]{1,300})', text)
    return m.group(1).strip() if m else ''


def fetch_all_pages():
    pages = []
    page_num = 1
    while True:
        r = requests.get(f'{BASE}/wp-json/wp/v2/pages',
                          params={'per_page': 100, 'page': page_num},
                          headers=HEADERS, timeout=20)
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        pages.extend(batch)
        total_pages = int(r.headers.get('X-WP-TotalPages', page_num))
        if page_num >= total_pages:
            break
        page_num += 1
        time.sleep(0.5)
    return pages


def parse_shrine(page):
    html = page['content']['rendered']
    text = re.sub(r'<[^>]+>', '\n', html)

    address = get_field(text, '鎮座地')
    if not address:
        return None

    deity = get_field(text, '祭神') or get_field(text, '御祭神')
    festival_raw = get_field(text, '祭礼') or get_field(text, '例祭')

    if address and not address.startswith('佐賀県'):
        address = '佐賀県' + address

    lat = lng = None
    m = re.search(r'!2d([\d.\-]+)!3d([\d.\-]+)', html)
    if m:
        lng, lat = float(m.group(1)), float(m.group(2))

    festivals = parse_festivals(festival_raw)

    return {
        'name': re.sub(r'\s+', '', page['title']['rendered']),
        'pref': '佐賀県',
        'address': address,
        'deity': deity,
        'lat': lat,
        'lng': lng,
        'festivals': festivals,
        'festivals_raw': festival_raw,
        'notes': '',
        'official_url': '',
        'source_url': page['link'],
        'source': 'saga_jinjacho',
    }


def main():
    print('=== 佐賀県神社庁 スクレイプ開始 ===')
    pages = fetch_all_pages()
    print(f'WPページ取得: {len(pages)}件')

    shrines = []
    for p in pages:
        s = parse_shrine(p)
        if s:
            shrines.append(s)
    print(f'神社データ: {len(shrines)}件')

    no_coords = [s for s in shrines if not s.get('lat') and s.get('address')]
    print(f'ジオコーディング対象: {len(no_coords)}件')
    import urllib.parse
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

    with open('saga_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)

    reisai = sum(1 for s in shrines if s.get('festivals'))
    print(f'保存: saga_raw.json ({len(shrines)}件)')
    print(f'例祭率: {reisai}/{len(shrines)} ({reisai/max(len(shrines),1)*100:.1f}%)')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
