# -*- coding: utf-8 -*-
"""
埼玉県神社庁 スクレイパー（新規作成）
https://www.saitama-jinjacho.or.jp/shrine/

背景: 旧scrape_saitama.pyはリポジトリに存在しない（gitログにも痕跡なし、
早期の一括インポートデータと推定）。旧データは全1,542件でnameフィールドが
「神社名＋ふりがな＋(公式ホームページ)＋市区町村名」を区切りなく連結した
ページ上部のサマリーカード領域から誤って取得されており、かつaddressは
**全件が空文字列**という重大な不具合を抱えていた（2026-07-04、秩父神社の
名前汚染をユーザーが発見したことをきっかけに全件調査して判明）。

構造（2026-07-04実確認）:
- 一覧 `/shrine/page/N/`（N=1〜397、1ページ5件、計約1,985件）から個別詳細
  URL `/shrine/{id}/` を収集
- 個別詳細ページの本体データは `<table class="data_shrine">` 内に整理されている:
    <caption id="shrine_name">神社名</caption>（←ここが正しい名前。ページ上部の
    サマリーカードのnameフィールドは誤りの元だったので使わない）
    tr.address（鎮座地）/ tr.content（スキップ,御朱印有無等のバッジ）/
    tr.tel（スキップ,電話番号）/ tr.gods（祭神）/ tr.virtue（スキップ,神徳の説明文）/
    tr.festival（お祭り）
  由緒（tableの外の自由記述文）は著作権配慮で取得しない。公式サイトURLへの
  直接リンクは無い（「ホームページあり」はバッジ表示のみ）ためofficial_urlは空
- お祭り欄は表記が一定しない（実サイトで複数パターン確認）:
    A) 読点｢、｣区切り: 「例祭　10月19・20日、　おかめ市（大歳祭）12月15日、」
    B) 改行区切り: 「1月 1日　　歳旦祭\n2月節分日　  節分祭\n...」
    C) 区切り文字なし: 「夏越祓い7月1日大祭10月8日」
  区切り文字がある場合は区切りで分割し各断片内で日付位置を手がかりに
  前後どちらが名前か判定、区切りが無い場合は日付出現位置をアンカーに
  「前回の日付終端〜今回の日付終端」を1ブロックとしてブロック先頭側を
  名前とみなす（このサイトは概ね名前→日付の順）
- 座標はページ内のGoogleMapリンク `maps.google.com?q=lat,lng` から直接取得
  （ジオコーディング不要）
"""
import requests
import re
import json
import time
import urllib.parse
from bs4 import BeautifulSoup

BASE = 'https://www.saitama-jinjacho.or.jp'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}
SLEEP = 1.0

FULLWIDTH_DIGITS = str.maketrans('０１２３４５６７８９', '0123456789')
DATE_ANCHOR = re.compile(r'[0-9０-９一二三四五六七八九十]+月[0-9０-９第一二三四五六七八九十日曜月火水木金土・･\s]*')


def parse_month_jp(text):
    text = (text or '').translate(FULLWIDTH_DIGITS)
    m = re.search(r'(\d+)月', text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return n
    return None


def make_entry(name, date_str):
    entry = {'name': name.strip() or '祭礼', 'date_str': date_str.strip()}
    month = parse_month_jp(date_str)
    if month:
        entry['month'] = month
    return entry


def parse_festivals(raw):
    raw = (raw or '').strip()
    if not raw:
        return []

    chunks = [c.strip() for c in re.split(r'[、\r\n]+', raw) if c.strip()]
    if len(chunks) > 1:
        results = []
        for chunk in chunks:
            dm = DATE_ANCHOR.search(chunk)
            if not dm:
                results.append(make_entry(chunk, ''))
                continue
            before = chunk[:dm.start()].strip('　 ')
            after = chunk[dm.end():].strip('　 ')
            name = before or after or '祭礼'
            results.append(make_entry(name, dm.group()))
        return results

    # 区切り文字なし：日付出現位置をアンカーに「名前→日付」のブロックに分割
    matches = list(DATE_ANCHOR.finditer(raw))
    if not matches:
        return [make_entry(raw, '')]
    results = []
    prev_end = 0
    for m in matches:
        name = raw[prev_end:m.start()].strip('　 ')
        results.append(make_entry(name, m.group()))
        prev_end = m.end()
    return results


def get_all_urls():
    urls = []
    seen = set()
    page = 1
    while True:
        url = f'{BASE}/shrine/' if page == 1 else f'{BASE}/shrine/page/{page}/'
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
        except Exception as e:
            print(f'  ERROR page={page}: {e}')
            break
        if r.status_code != 200:
            break
        found = re.findall(rf'{re.escape(BASE)}/shrine/(\d+)/', r.text)
        new_ids = [i for i in found if i not in seen]
        if not new_ids and page > 1:
            break
        for i in new_ids:
            seen.add(i)
            urls.append(f'{BASE}/shrine/{i}/')
        if (page) % 20 == 0:
            print(f'  page={page}: 累計{len(urls)}件')
        page += 1
        time.sleep(SLEEP)
    return urls


def parse_detail(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
    except Exception as e:
        print(f'  ERROR {url}: {e}')
        return None

    soup = BeautifulSoup(r.text, 'html.parser')
    table = soup.find('table', class_='data_shrine')
    if not table:
        return None
    caption = table.find('caption')
    name = caption.get_text(strip=True) if caption else ''
    if not name:
        return None

    def row_text(cls):
        tr = table.find('tr', class_=cls)
        if not tr:
            return ''
        td = tr.find('td')
        return td.get_text(' ', strip=True) if td else ''

    address = row_text('address')
    if address and not address.startswith('埼玉県'):
        address = '埼玉県' + address
    deity = row_text('gods')
    festival_raw = row_text('festival')

    lat = lng = None
    m = re.search(r'maps\.google\.com\?q=([\d.\-]+)%2C([\d.\-]+)', r.text)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))

    return {
        'name': name,
        'pref': '埼玉県',
        'address': address,
        'deity': deity,
        'lat': lat,
        'lng': lng,
        'festivals': parse_festivals(festival_raw),
        'festivals_raw': festival_raw,
        'notes': '',
        'official_url': '',
        'source_url': url,
        'source': 'saitama_jinjacho',
    }


def main():
    print('=== 埼玉県神社庁 スクレイプ開始 ===')
    urls = get_all_urls()
    print(f'URL一覧取得: {len(urls)}件')

    shrines = []
    for i, url in enumerate(urls):
        s = parse_detail(url)
        if s:
            shrines.append(s)
        if (i + 1) % 100 == 0:
            print(f'  詳細 {i+1}/{len(urls)}')
        time.sleep(SLEEP)

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

    with open('saitama_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)

    reisai = sum(1 for s in shrines if s.get('festivals'))
    deity_n = sum(1 for s in shrines if s.get('deity'))
    addr_n = sum(1 for s in shrines if s.get('address'))
    print(f'保存: saitama_raw.json ({len(shrines)}件)')
    print(f'住所あり: {addr_n}/{len(shrines)}')
    print(f'例祭あり: {reisai}/{len(shrines)} ({reisai/max(len(shrines),1)*100:.1f}%)')
    print(f'御祭神あり: {deity_n}/{len(shrines)} ({deity_n/max(len(shrines),1)*100:.1f}%)')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
