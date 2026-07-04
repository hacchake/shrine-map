# -*- coding: utf-8 -*-
"""
岡山県神社庁 スクレイパー（新規作成）
https://www.okayama-jinjacho.or.jp/search/

背景: 旧scrape_okayama.pyはリポジトリに存在しない（gitログにも痕跡なし、
早期の一括インポートデータと推定）。旧データは主な祭典が「日付：名前」の
繰り返しを区切り文字なしで連結した生テキスト（例:
「７月第２日曜日：夏大祓祭１０月第３土・日曜日：秋祭」）をそのまま
一つのfestivalsエントリに格納しており、前の祭典名と次の祭典の日付が
1フィールドに合体していた（2026-07-04、ユーザー指摘で発覚）。

構造（2026-07-04実確認）:
- WordPress。全件一覧 `/search/list/`, `/search/list/page/N/`（1〜約81ページ、
  1609件）の各行に個別詳細ページへのリンク `/search/{id}` が張られている
- 個別詳細ページ（要リダイレクト追従、httpsのtrailing-slash等）:
    神社コード / 神社名（カナ） / 通称名 / 旧社格 / 鎮座地(〒付き) /
    電話番号 / FAX番号(スキップ) / 駐車場(スキップ) / 御祭神 /
    御神徳(スキップ,説明文) / 主な祭典 / 宮司宅電話(スキップ,個人情報) /
    URL(→official_url) / e-mail(スキップ) / 特記事項 / 交通アクセス(スキップ) /
    氏子地域(スキップ)
- 主な祭典は「日付：名前」を**区切り文字なしで連結**した1文字列（複数祭典の
  場合、前の名前の直後に次の日付が続く）。日付パターン+「：」の出現位置を
  アンカーにブロック分割して名前/日付を正しく分離する
- 座標はページ内埋め込みJS `new google.maps.LatLng(lat,lng)` から取得
  （ジオコーディング不要）
"""
import requests
import re
import json
import time
import urllib.parse
from bs4 import BeautifulSoup

BASE = 'https://www.okayama-jinjacho.or.jp'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}
SLEEP = 1.0

FULLWIDTH_DIGITS = str.maketrans('０１２３４５６７８９', '0123456789')
# 日付の「本体」だけを狭くマッチさせる（月・日・第・曜日・干支的な区切り記号のみを
# 続けて許容し、祭事名の漢字に達したら即座に止まる）。区切り文字は：、　など
# 統一されていない（実サイトで複数パターン確認）ため、区切り文字の種類に依存せず
# 「次の日付パターンの開始位置」をブロック境界として使う
DATE_ANCHOR = re.compile(r'[0-9０-９一二三四五六七八九十]+月[0-9０-９第一二三四五六七八九十日曜月火水木金土・]*')


def parse_month_jp(text):
    text = (text or '').translate(FULLWIDTH_DIGITS)
    m = re.search(r'(\d+)月', text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return n
    return None


def parse_festivals(raw):
    """「日付：名前」等を区切りなしで連結した生テキストをブロック分割する。
    日付パターンの出現位置そのものをアンカーにし、マッチ終端〜次のアンカー
    開始までを名前として抽出する（区切り文字が：/、/　/無しのいずれでも
    対応できる）。"""
    raw = (raw or '').strip()
    if not raw:
        return []
    matches = list(DATE_ANCHOR.finditer(raw))
    if not matches:
        return [{'name': raw, 'date_str': ''}]
    results = []
    for i, m in enumerate(matches):
        date_str = m.group().strip()
        name_end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        name = raw[m.end():name_end].strip('　、：　 ') or '祭礼'
        entry = {'name': name, 'date_str': date_str}
        month = parse_month_jp(date_str)
        if month:
            entry['month'] = month
        results.append(entry)
    return results


def get_all_ids():
    ids = []
    seen = set()
    page = 1
    while True:
        url = f'{BASE}/search/list/' if page == 1 else f'{BASE}/search/list/page/{page}/'
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
        except Exception as e:
            print(f'  ERROR page={page}: {e}')
            break
        if r.status_code != 200:
            break
        r.encoding = 'utf-8'
        found = re.findall(r'/search/(\d+)"', r.text)
        new_ids = [i for i in found if i not in seen]
        if not new_ids:
            break
        for i in new_ids:
            seen.add(i)
            ids.append(i)
        print(f'  page={page}: 新規{len(new_ids)}件 (累計{len(ids)})')
        page += 1
        time.sleep(SLEEP)
    return ids


def parse_detail(sid):
    url = f'{BASE}/search/{sid}/'
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
    for tr in soup.find_all('tr'):
        th, td = tr.find('th'), tr.find('td')
        if th and td:
            fields[th.get_text(strip=True)] = td.get_text(strip=True)

    name = fields.get('神社名', '')
    name = re.split(r'[（(]', name, maxsplit=1)[0].strip()
    if not name:
        return None

    address = fields.get('鎮座地', '')
    address = re.sub(r'^〒?\d{3}-?\d{4}[\s　]*', '', address)
    if address and not address.startswith('岡山県'):
        address = '岡山県' + address

    deity = fields.get('御祭神', '')
    festival_raw = fields.get('主な祭典', '')
    official_url = fields.get('URL', '')

    lat = lng = None
    m = re.search(r'LatLng\(([\d.\-]+),\s*([\d.\-]+)\)', r.text)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))

    return {
        'name': name,
        'pref': '岡山県',
        'address': address,
        'deity': deity,
        'lat': lat,
        'lng': lng,
        'festivals': parse_festivals(festival_raw),
        'festivals_raw': festival_raw,
        'notes': '',
        'official_url': official_url,
        'source_url': url,
        'source': 'okayama_jinjacho',
    }


def main():
    print('=== 岡山県神社庁 スクレイプ開始 ===')
    ids = get_all_ids()
    print(f'ID一覧取得: {len(ids)}件')

    shrines = []
    for i, sid in enumerate(ids):
        s = parse_detail(sid)
        if s:
            shrines.append(s)
        if (i + 1) % 100 == 0:
            print(f'  {i+1}/{len(ids)} (取得{len(shrines)}件)')
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

    with open('okayama_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)

    reisai = sum(1 for s in shrines if s.get('festivals'))
    deity_n = sum(1 for s in shrines if s.get('deity'))
    print(f'保存: okayama_raw.json ({len(shrines)}件)')
    print(f'例祭あり: {reisai}/{len(shrines)} ({reisai/max(len(shrines),1)*100:.1f}%)')
    print(f'御祭神あり: {deity_n}/{len(shrines)} ({deity_n/max(len(shrines),1)*100:.1f}%)')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
