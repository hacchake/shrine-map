"""
青森県神社庁スクレイパー v2
リスト: http://www.aomori-jinjacho.or.jp/jinja/sub_1{a-h}.html （8地区）
個別:   http://www.aomori-jinjacho.or.jp/jinja/{region}/sub_1{x}_{num}.html

実ページ構造（2026-07-03 確認済み: /jinja/Nishitu/sub_1b_031.html）はテーブル形式:
  | 住 所 | つがる市木造町兼館字高取17 |
  | 御祭神 | 誉田別尊 |
  | 例 祭 | ７月１５日 |
  | 由 緒 | 寶永二年創立｡... |
※ラベルに全角/半角スペースが混入する（「住 所」「例 祭」）ため、
  比較時は空白を全除去して正規化する。v1はこれで例祭率0%になっていた。
"""

import requests, re, json, time, urllib.parse
from urllib.parse import urljoin
from bs4 import BeautifulSoup

BASE = "http://www.aomori-jinjacho.or.jp"
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot/1.0)'}
GEOCODE = True  # GSI APIで住所→座標変換（+0.1s/件）

REGION_PAGES = [(f"{BASE}/jinja/sub_1{c}.html", c) for c in "abcdefgh"]


def norm_label(s):
    """ラベル比較用: 全空白（半角/全角/改行）を除去"""
    return re.sub(r'[\s\u3000]+', '', s or '')


def parse_month_jp(text):
    """日本語・数字の月表記から月を抽出"""
    text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
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


def parse_festivals(section_text):
    """恒例祭リスト形式（大社の複数行）をパース → festivals[]"""
    festivals = []
    lines = [l.strip() for l in section_text.split('\n') if l.strip()]
    for line in lines:
        parts = re.split(r'[\u3000\s]{2,}', line)
        if len(parts) >= 2:
            fname = parts[0].strip()
            date = parts[-1].strip()
            if fname and date:
                month = parse_month_jp(date)
                entry = {'name': fname, 'date_str': date}
                if month:
                    entry['month'] = month
                festivals.append(entry)
    return festivals


def scrape_detail(url):
    """個別神社ページをスクレイプ"""
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        if r.status_code != 200:
            return None
        # 文字コードはBS4に自動判定させる（UTF-8/Shift_JIS両対応）
        soup = BeautifulSoup(r.content, 'html.parser')

        # 神社名: <title>青森県神社庁-神社紹介-八幡宮</title>
        name = ''
        title = soup.find('title')
        if title:
            parts = title.get_text().split('-')
            if parts:
                name = parts[-1].strip()

        # --- 1) テーブル直接パース（標準形式） ---
        data = {}
        for row in soup.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            if len(cells) >= 2:
                key = norm_label(cells[0].get_text())
                val = cells[1].get_text('\n', strip=True)
                if key and len(key) <= 8 and key not in data and val:
                    data[key] = val

        address = data.get('住所', data.get('鎮座地', data.get('所在地', '')))
        deity = data.get('御祭神', data.get('祭神', ''))
        reisai_raw = data.get('例祭', data.get('例祭日', data.get('例大祭', '')))
        korei_raw = data.get('恒例祭', data.get('年中祭事', ''))

        # --- 2) 行ベースフォールバック（非テーブル形式ページ用） ---
        if not (address or deity or reisai_raw):
            lines = [l.strip() for l in soup.get_text('\n').split('\n')]
            in_section, bufs = None, {}
            for line in lines:
                key = norm_label(line)
                if key in ('住所', '鎮座地', '所在地'):
                    in_section = 'addr'
                elif key in ('御祭神', '祭神'):
                    in_section = 'deity'
                elif key in ('例祭', '例祭日', '恒例祭', '年中祭事'):
                    in_section = 'fest'
                elif key in ('由緒', '地図'):
                    in_section = None
                elif in_section and line:
                    bufs.setdefault(in_section, []).append(line)
            address = address or ' '.join(bufs.get('addr', []))
            deity = deity or ' '.join(bufs.get('deity', []))
            reisai_raw = reisai_raw or '\n'.join(bufs.get('fest', []))

        # --- 例祭パース ---
        festivals = []
        festivals_raw = reisai_raw or korei_raw or ''
        if reisai_raw:
            month = parse_month_jp(reisai_raw)
            first = reisai_raw.split('\n')[0].strip()
            if month:
                festivals = [{'month': month, 'date_str': first, 'name': '例祭'}]
        if not festivals and korei_raw:
            fs = [f for f in parse_festivals(korei_raw) if f.get('month')]
            reisai_only = [f for f in fs if '例祭' in f.get('name', '')]
            festivals = reisai_only if reisai_only else fs

        if address and not address.startswith('青森県'):
            address = '青森県' + address

        if not name or not (address or deity or festivals):
            return None

        return {
            'name': name,
            'pref': '青森県',
            'address': address,
            'deity': deity,
            'lat': None,
            'lng': None,
            'festivals': festivals,
            'festivals_raw': festivals_raw,
            'notes': '',
            'official_url': '',
            'source': 'aomori_jinjacho',
            'source_url': url,
        }
    except Exception as e:
        print(f"  ERROR {url}: {e}")
        return None


def get_shrine_links(list_url):
    """リストページから個別ページのリンクを取得"""
    try:
        r = requests.get(list_url, timeout=15, headers=HEADERS)
        soup = BeautifulSoup(r.content, 'html.parser')
        links = set()
        for a in soup.find_all('a', href=True):
            if re.search(r'sub_1[a-h]_\d+\.html', a['href']):
                links.add(urljoin(list_url, a['href']))
        return sorted(links)
    except Exception as e:
        print(f"  ERROR {list_url}: {e}")
        return []


def get_list_only_shrines(list_url):
    """一覧ページのテーブル行から、個別詳細ページへのリンクを持たない神社を
    名前＋住所のみで抽出する（2026-07-03確認: 全行が[番号,名前,住所]の3セル形式。
    名前セルに<a>があれば詳細ページ有り＝scrape_detail側で取得済みなのでスキップ）。
    例祭・御祭神は一覧に無いため空のまま。
    """
    shrines = []
    try:
        r = requests.get(list_url, timeout=15, headers=HEADERS)
        soup = BeautifulSoup(r.content, 'html.parser')
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if len(cells) != 3:
                    continue
                name_cell, addr_cell = cells[1], cells[2]
                if name_cell.find('a'):
                    continue  # 詳細ページありはscrape_detail側で取得済み
                name = name_cell.get_text(strip=True)
                address = addr_cell.get_text(strip=True)
                if not name or not address:
                    continue
                if not address.startswith('青森県'):
                    address = '青森県' + address
                shrines.append({
                    'name': name,
                    'pref': '青森県',
                    'address': address,
                    'deity': '',
                    'lat': None,
                    'lng': None,
                    'festivals': [],
                    'festivals_raw': '',
                    'notes': '',
                    'official_url': '',
                    'source': 'aomori_jinjacho_list',
                    'source_url': list_url,
                })
        return shrines
    except Exception as e:
        print(f"  ERROR (list-only) {list_url}: {e}")
        return []


def geocode(shrines):
    no_coords = [s for s in shrines if not s.get('lat') and s.get('address')]
    print(f"ジオコーディング対象: {len(no_coords)}件")
    success = 0
    for s in no_coords:
        try:
            r = requests.get(
                "https://msearch.gsi.go.jp/address-search/AddressSearch?q="
                + urllib.parse.quote(s['address']), timeout=8)
            results = r.json()
            if results:
                s['lng'] = float(results[0]['geometry']['coordinates'][0])
                s['lat'] = float(results[0]['geometry']['coordinates'][1])
                success += 1
        except Exception:
            pass
        time.sleep(0.1)
    print(f"ジオコーディング成功: {success}件")


def main():
    all_shrines = []
    for list_url, region_code in REGION_PAGES:
        print(f"\n=== 地区 {region_code}: {list_url} ===")
        links = get_shrine_links(list_url)
        print(f"  → {len(links)}件のリンク")
        for j, url in enumerate(links):
            shrine = scrape_detail(url)
            if shrine:
                all_shrines.append(shrine)
            if (j + 1) % 20 == 0:
                print(f"  {j+1}/{len(links)} 完了")
            time.sleep(0.5)

        list_only = get_list_only_shrines(list_url)
        print(f"  → 詳細ページなし(名前+住所のみ): {len(list_only)}件")
        all_shrines.extend(list_only)
        time.sleep(0.5)

    print(f"\n=== 取得完了: {len(all_shrines)}件 ===")
    list_only_count = sum(1 for s in all_shrines if s.get('source') == 'aomori_jinjacho_list')
    print(f"  うち詳細ページなし(名前+住所のみ): {list_only_count}件")
    reisai = sum(1 for s in all_shrines if s.get('festivals'))
    if all_shrines:
        print(f"例祭データあり: {reisai}件 ({reisai/len(all_shrines)*100:.1f}%)")

    if GEOCODE:
        geocode(all_shrines)

    with open('aomori_raw.json', 'w', encoding='utf-8') as f:
        json.dump(all_shrines, f, ensure_ascii=False, indent=2)
    print("aomori_raw.json を保存しました")


if __name__ == '__main__':
    main()
