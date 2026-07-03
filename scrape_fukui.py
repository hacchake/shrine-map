# -*- coding: utf-8 -*-
"""
福井県神社庁「神社を探す」スクレイパー（香川方式: 名前+住所+御祭神。例祭情報は
サイトの「主な祭典」欄がほぼ空で構造化されていないため取得しない）

構造（2026-07-04確認）:
- https://www.jinja-fukui.jp/search/index.php の市町村検索（SearchType=1,
  Chiku=市町村コード）はJSでフォーム送信されるが、実体は
  POST https://www.jinja-fukui.jp/result/ (SearchType=1, Chiku=コード)
  で、該当市町村の全神社が1ページにまとめて返る（ページネーション無し確認済み）
- 検索結果は `<div class="result_shrine"><a href="javascript:clickDetail('ID');">
  <span>かな</span><br>神社名</a></div>` の直後に `result_recinct`（境内社名、
  多くは空）、`result_enshrined`（住所 ※クラス名と内容が食い違うが実体は住所）
- 御祭神は詳細ページ（GET /detail/index.php?ID=xxx）のtableに `<th>御祭神</th>
  <td>神名<br>神名...</td>` として存在（一覧には出ない）
- 宮司名・電話番号・FAX番号・e-mailは個人/連絡先情報のため取得しない
"""
import requests
import json
import re
import time
from bs4 import BeautifulSoup

BASE = 'https://www.jinja-fukui.jp'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research)'}
SLEEP = 1.0
GEOCODE = True

# search/index.php の SelectChiku 選択肢（市町村コード）
MUNICIPALITY_CODES = [f'{i:02d}' for i in range(1, 18)]


def get_shrine_list():
    """市町村コードごとに検索し、(id, name, address) を収集"""
    shrines = {}
    for code in MUNICIPALITY_CODES:
        try:
            r = requests.post(f'{BASE}/result/', data={'SearchType': '1', 'Chiku': code},
                               headers=HEADERS, timeout=15)
        except Exception as e:
            print(f'  ERROR Chiku={code}: {e}')
            continue
        if r.status_code != 200:
            print(f'  HTTP {r.status_code}: Chiku={code}')
            continue
        soup = BeautifulSoup(r.content, 'html.parser')
        count = 0
        for shrine_div in soup.select('div.result_shrine'):
            a = shrine_div.find('a', href=True)
            if not a:
                continue
            m = re.search(r"clickDetail\('([\d_]+)'\)", a['href'])
            if not m:
                continue
            shrine_id = m.group(1)
            # <span>かな</span><br />名前 の名前部分（spanの後のテキスト）
            name = a.get_text(strip=True)
            span = a.find('span')
            if span:
                name = name[len(span.get_text(strip=True)):].strip()
            addr_div = shrine_div.find_next_sibling('div', class_='result_enshrined')
            address = addr_div.get_text(strip=True) if addr_div else ''
            if shrine_id not in shrines:
                shrines[shrine_id] = {'name': name, 'address': address}
                count += 1
        print(f'  Chiku={code}: {count}件 (累計{len(shrines)})')
        time.sleep(SLEEP)
    return shrines


def parse_detail(shrine_id):
    """詳細ページから御祭神を取得"""
    try:
        r = requests.get(f'{BASE}/detail/index.php', params={'ID': shrine_id},
                          headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return '', ''
        soup = BeautifulSoup(r.content, 'html.parser')
        data = {}
        for row in soup.find_all('tr'):
            th = row.find('th')
            td = row.find('td')
            if th and td:
                data[th.get_text(strip=True)] = td.get_text('\n', strip=True)
        deity = data.get('御祭神', '').replace('\n', '、')
        postal = data.get('郵便番号', '')
        return deity, postal
    except Exception as e:
        print(f'  ERROR detail {shrine_id}: {e}')
        return '', ''


def main():
    print('=== 福井県神社庁 神社を探す スクレイプ開始 ===')
    shrine_list = get_shrine_list()
    print(f'一覧取得: {len(shrine_list)}件')

    shrines = []
    for i, (shrine_id, info) in enumerate(shrine_list.items()):
        deity, postal = parse_detail(shrine_id)
        name = info['name']
        address = info['address']
        if address and not address.startswith('福井県'):
            address = '福井県' + address
        notes = f'〒{postal}' if postal else ''
        shrines.append({
            'name': name,
            'pref': '福井県',
            'address': address,
            'deity': deity,
            'lat': None,
            'lng': None,
            'festivals': [],
            'festivals_raw': '',
            'notes': notes,
            'official_url': '',
            'source_url': f'{BASE}/detail/index.php?ID={shrine_id}',
            'source': 'fukui_jinjacho',
        })
        if (i + 1) % 50 == 0:
            print(f'  {i+1}/{len(shrine_list)} 完了')
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

    with open('fukui_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)
    print(f'保存: fukui_raw.json ({len(shrines)}件)')
    with_deity = sum(1 for s in shrines if s['deity'])
    with_coord = sum(1 for s in shrines if s.get('lat'))
    print(f'御祭神あり: {with_deity}件 / 座標あり: {with_coord}件')


if __name__ == '__main__':
    main()
