# -*- coding: utf-8 -*-
"""
愛媛県神社庁 スクレイパー（新規作成）
http://ehime-jinjacho.jp/jinja/

背景: 旧scrape_ehime.pyはリポジトリに存在しない（gitログにも痕跡なし、
早期の一括インポートデータと推定）。旧データは全849件中825件で
festivalsのname/date_strに同一文字列（日付＋祭事名の生テキストそのもの）
が重複格納されており、名前と日付の分離が行われていなかった
（2026-07-04、UIモーダルでの確認中にユーザー指摘で発覚）。

構造（2026-07-04実確認）:
- WordPress（REST APIは無効/404）。/jinja/ 一枚のインデックスページに
  全神社への ?p=NNNN リンクが列挙されている（ページネーション不要、約1236件）
- 個別詳細ページ（?p=NNNN）はテーブル形式:
    神社名 / ふりがな / 宮司名(スキップ,個人情報) / 電話番号(スキップ) /
    神社主な祭礼 / 神社主祭神 / 神社由緒(スキップ,著作権配慮) /
    神社鎮座地 / 神社駐車場(スキップ)
  ※ページ内に複数<table>があり、データ本体は行数が最大のtable
- 神社主な祭礼は複数件が<br>区切り（get_text('\n')で改行として取得）、
  各行は基本「日付　祭事名」の順（例:「７月１７日　十七夜祭」）だが、
  まれに「祭事名　日付」の逆順の行もある（parse_festivals.parse_linesが両対応）。
  旧バグはこの複数行テキストを分割せずname/date_str両方にそのまま
  コピーしていたと推定される。「旧暦」「体育の日」等の日付表現の対応は
  2026-07-05にparse_festivals.pyへ切り出し・拡張（NOTES_20260705参照）
- 座標はGoogleMaps埋め込みiframeの `ll=lat,lng` パラメータから直接取得
  （ジオコーディング不要）
"""
import requests
import re
import json
import time
import urllib.parse
from bs4 import BeautifulSoup
from parse_festivals import parse_lines as parse_festivals

BASE = 'http://ehime-jinjacho.jp/jinja'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}
SLEEP = 1.0


def get_all_ids():
    r = requests.get(f'{BASE}/', headers=HEADERS, timeout=20)
    r.encoding = 'utf-8'
    ids = sorted(set(re.findall(r'\?p=(\d+)', r.text)), key=int)
    return ids


def parse_detail(pid):
    url = f'{BASE}/?p={pid}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = 'utf-8'
        if r.status_code != 200:
            return None
    except Exception as e:
        print(f'  ERROR id={pid}: {e}')
        return None

    soup = BeautifulSoup(r.text, 'html.parser')
    tables = soup.find_all('table')
    if not tables:
        return None
    data_table = max(tables, key=lambda t: len(t.find_all('tr')))
    fields = {}
    for tr in data_table.find_all('tr'):
        th, td = tr.find('th'), tr.find('td')
        if th and td:
            fields[th.get_text(strip=True)] = td.get_text('\n', strip=True)

    name = fields.get('神社名', '').strip()
    if not name:
        return None

    address = fields.get('神社鎮座地', '').strip()
    if address and not address.startswith('愛媛県'):
        address = '愛媛県' + address

    deity = fields.get('神社主祭神', '').strip()
    festival_raw = fields.get('神社主な祭礼', '').strip()

    lat = lng = None
    m = re.search(r'll=([\d.\-]+),([\d.\-]+)', r.text)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))

    return {
        'name': name,
        'pref': '愛媛県',
        'address': address,
        'deity': deity,
        'lat': lat,
        'lng': lng,
        'festivals': parse_festivals(festival_raw),
        'festivals_raw': festival_raw,
        'notes': '',
        'official_url': '',
        'source_url': url,
        'source': 'ehime_jinjacho',
    }


def main():
    print('=== 愛媛県神社庁 スクレイプ開始 ===')
    ids = get_all_ids()
    print(f'ID一覧取得: {len(ids)}件')

    shrines = []
    for i, pid in enumerate(ids):
        s = parse_detail(pid)
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

    with open('ehime_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)

    reisai = sum(1 for s in shrines if s.get('festivals'))
    deity_n = sum(1 for s in shrines if s.get('deity'))
    print(f'保存: ehime_raw.json ({len(shrines)}件)')
    print(f'例祭あり: {reisai}/{len(shrines)} ({reisai/max(len(shrines),1)*100:.1f}%)')
    print(f'御祭神あり: {deity_n}/{len(shrines)} ({deity_n/max(len(shrines),1)*100:.1f}%)')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
