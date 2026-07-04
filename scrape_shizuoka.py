# -*- coding: utf-8 -*-
"""
静岡県神社庁 スクレイパー（新規作成）
http://www.shizuoka-jinjacho.or.jp/shokai/

背景: 旧scrape_shizuoka.pyはリポジトリから消失していた。旧データはサイトの
UTF-8応答をcp932として誤デコードして保存する文字化けバグを持っていた
（2026-07-04発見）。本スクリプトは正しいUTF-8処理で全件を再取得する。

構造（2026-07-04実確認）:
- エリア一覧 /shokai/area.php?area=1〜6 → 各エリア内の市町村ID一覧
  （市町村IDは1〜36の通し番号、21は欠番。全35市町村）
- 市町村別一覧 /shokai/search.php?mode=city&city=N → 神社名/よみがな/鎮座地
  （住所は郵便番号なし、市区町村から始まる）＋詳細ページへのリンク(id)
- 個別詳細 /shokai/jinja.php?id=NNNNNNN:
    神社名（よみがな） / 代表者(スキップ,個人情報) / 各種御祈祷(スキップ) /
    鎮座地(〒付き) / 問い合わせ先(スキップ) / URL(→official_url) /
    御祭神 / 御神徳(スキップ,説明文) / 御由緒(スキップ,著作権配慮) /
    御祭典: <h6>祭典名（よみ）　日付</h6>の繰り返し。大きな神社ほど多数。
    小さな神社は空のことも多い（詳細ページ自体に情報が無い）
  座標はページ内埋め込みJS `new google.maps.LatLng(lat,lng,0)` から取得
  （ジオコーディング不要、GSIはフォールバックのみ）
"""
import requests
import json
import re
import time
import urllib.parse
from bs4 import BeautifulSoup

BASE = 'http://www.shizuoka-jinjacho.or.jp/shokai'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}
SLEEP = 1.0

CITY_IDS = [i for i in range(1, 37) if i != 21]

FULLWIDTH_DIGITS = str.maketrans('０１２３４５６７８９', '0123456789')


def parse_month_jp(text):
    text = text.translate(FULLWIDTH_DIGITS)
    m = re.search(r'(\d+)月', text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return n
    kanji_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
                 '七': 7, '八': 8, '九': 9, '十': 10, '十一': 11, '十二': 12}
    for k, v in sorted(kanji_map.items(), key=lambda x: -len(x[0])):
        if f'{k}月' in text:
            return v
    return None


def strip_kana_paren(s):
    """「越方神社（おちかたじんじゃ）」→「越方神社」"""
    return re.split(r'[（(]', s, maxsplit=1)[0].strip()


def collect_city_shrines():
    """全市町村ページから id/name/kana/address を収集"""
    shrines = {}
    for city in CITY_IDS:
        url = f'{BASE}/search.php?mode=city&city={city}'
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.encoding = 'utf-8'
        except Exception as e:
            print(f'  ERROR city={city}: {e}')
            continue
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table', class_='data_tbl')
        if not table:
            continue
        for tr in table.find_all('tr'):
            if tr.find('th'):
                continue
            tds = tr.find_all('td')
            if len(tds) < 3:
                continue
            a = tds[0].find('a', href=True)
            if not a:
                continue
            m = re.search(r'id=(\d+)', a['href'])
            if not m:
                continue
            sid = m.group(1)
            shrines[sid] = {
                'id': sid,
                'name': a.get_text(strip=True),
                'address': tds[2].get_text(strip=True),
            }
        print(f'  city={city}: 累計{len(shrines)}件')
        time.sleep(SLEEP)
    return shrines


def parse_detail(sid):
    url = f'{BASE}/jinja.php?id={sid}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = 'utf-8'
        if r.status_code != 200:
            return None
    except Exception as e:
        print(f'  ERROR id={sid}: {e}')
        return None

    soup = BeautifulSoup(r.text, 'html.parser')
    fields = {}
    for table in soup.find_all('table', class_='data_tbl2'):
        for tr in table.find_all('tr'):
            th, td = tr.find('th'), tr.find('td')
            if not th or not td:
                continue
            label = th.get_text(strip=True)
            fields[label] = td

    name = ''
    if '神社名' in fields:
        name = strip_kana_paren(fields['神社名'].get_text(strip=True))

    address = ''
    if '鎮座地' in fields:
        raw_addr = fields['鎮座地'].get_text(strip=True)
        address = re.sub(r'^〒?\d{3}-?\d{4}[\s　]*', '', raw_addr)
        if address and not address.startswith('静岡県'):
            address = '静岡県' + address

    deity = fields['御祭神'].get_text(' ', strip=True) if '御祭神' in fields else ''

    official_url = ''
    if 'URL' in fields:
        a = fields['URL'].find('a', href=True)
        if a:
            official_url = a['href']

    festivals = []
    seen = set()
    if '御祭典' in fields:
        for h6 in fields['御祭典'].find_all('h6'):
            text = h6.get_text(strip=True)
            if not text:
                continue
            text_nokana = strip_kana_paren(text) if '（' in text.split('月')[0] else text
            dm = re.search(r'[0-9０-９一二三四五六七八九十]+月.*', text_nokana)
            if dm:
                fname = text_nokana[:dm.start()].strip('　 ')
                date_str = dm.group(0).strip()
            else:
                fname = text_nokana.strip()
                date_str = ''
            key = (fname, date_str)
            if key in seen:
                continue
            seen.add(key)
            entry = {'name': fname or '祭典', 'date_str': date_str}
            month = parse_month_jp(date_str) if date_str else None
            if month:
                entry['month'] = month
            festivals.append(entry)

    lat = lng = None
    m = re.search(r'LatLng\(([\d.\-]+),\s*([\d.\-]+)', r.text)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))

    return {
        'name': name,
        'pref': '静岡県',
        'address': address,
        'deity': deity,
        'lat': lat,
        'lng': lng,
        'festivals': festivals,
        'festivals_raw': '',
        'notes': '',
        'official_url': official_url,
        'source_url': url,
        'source': 'shizuoka_jinjacho',
    }


def main():
    print('=== 静岡県神社庁 スクレイプ開始 ===')
    print('市町村一覧取得中...')
    city_shrines = collect_city_shrines()
    print(f'一覧件数: {len(city_shrines)}件')

    shrines = []
    ids = sorted(city_shrines.keys(), key=int)
    for i, sid in enumerate(ids):
        detail = parse_detail(sid)
        if detail and detail['name']:
            shrines.append(detail)
        else:
            # 詳細ページ取得失敗時は一覧の情報でフォールバック
            fallback = city_shrines[sid]
            addr = fallback['address']
            if addr and not addr.startswith('静岡県'):
                addr = '静岡県' + addr
            shrines.append({
                'name': fallback['name'], 'pref': '静岡県', 'address': addr,
                'deity': '', 'lat': None, 'lng': None, 'festivals': [],
                'festivals_raw': '', 'notes': '', 'official_url': '',
                'source_url': f'{BASE}/jinja.php?id={sid}', 'source': 'shizuoka_jinjacho',
            })
        if (i + 1) % 100 == 0:
            print(f'  詳細 {i+1}/{len(ids)}')
        time.sleep(SLEEP)

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
        time.sleep(0.1)
    print(f'ジオコーディング成功: {ok}件')

    with open('shizuoka_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)

    reisai = sum(1 for s in shrines if s.get('festivals'))
    deity_n = sum(1 for s in shrines if s.get('deity'))
    print(f'保存: shizuoka_raw.json ({len(shrines)}件)')
    print(f'例祭あり: {reisai}/{len(shrines)} ({reisai/max(len(shrines),1)*100:.1f}%)')
    print(f'御祭神あり: {deity_n}/{len(shrines)} ({deity_n/max(len(shrines),1)*100:.1f}%)')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
