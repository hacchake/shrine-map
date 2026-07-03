# -*- coding: utf-8 -*-
"""
香川県神社庁 スクレイパー
https://kagawakenjinjacho.or.jp/

構造（2026-07-03 実確認）:
- 市町村アーカイブ: /municipalities/{slug}/ （WordPress、/page/N/ でページネーションの可能性）
- 詳細: /shrine/{URLエンコード神社名-N}/
- 詳細フィールド: 神社コード／神社名／鎮座地／電話番号／FAX番号／御祭神／URL／特記事項
  ※「例祭」フィールドは存在しない → festivalsは常に空。住所+御祭神+座標のカバレッジ目的。
- 一覧の住所は「香川郡直島町…」のように県名なし → 「香川県」を前置
"""
import requests
import json
import re
import time
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup

BASE = 'https://kagawakenjinjacho.or.jp'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research)'}
SLEEP = 1.0
GEOCODE = True

MUNICIPALITIES = [
    'sanukishi', 'higashikagawashi', 'takamatsushi', 'kagawagun',
    'kitagun', 'shozugun', 'marugameshi', 'sakaideshi', 'zentujishi',
    'ayautagun', 'nakatadogun', 'kanonjishi', 'mitoyoshi',
]

# ラベル ： 値 形式（区切りは全角コロン、前後に空白/全角空白が入る）
# 実ページはラベルと「：値」が別行にレンダリングされる（get_text('\n')で
# 「鎮座地\n ： さぬき市...」）。ラベル〜コロン間は\s*で改行を跨ぐが、
# コロン〜値は同一行に限定（行内空白のみ）。値が空欄だと「：」の直後が
# 空行続きで次フィールドのラベル文字列に達してしまい、\s*だと次ラベル名
# を値として誤取得するため（例: 御祭神が空欄なのに「URL」を拾う実例あり）
_SP_LABEL = r'\s*'
_SP_VAL = r'[ \t　]*'
FIELD_RE = {
    'code':    re.compile(r'神社コード' + _SP_LABEL + r'[：:]' + _SP_VAL + r'(\S+)'),
    'name':    re.compile(r'神社名' + _SP_LABEL + r'[：:]' + _SP_VAL + r'(.+)'),
    'address': re.compile(r'鎮座地' + _SP_LABEL + r'[：:]' + _SP_VAL + r'(.+)'),
    'deity':   re.compile(r'御祭神' + _SP_LABEL + r'[：:]' + _SP_VAL + r'(.+)'),
    'notes':   re.compile(r'特記事項' + _SP_LABEL + r'[：:]' + _SP_VAL + r'(.+)'),
}


def get_shrine_urls():
    """全市町村アーカイブから詳細ページURLを収集"""
    urls = []
    seen = set()
    for slug in MUNICIPALITIES:
        page = 1
        while True:
            if page == 1:
                url = f'{BASE}/municipalities/{slug}/'
            else:
                url = f'{BASE}/municipalities/{slug}/page/{page}/'
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
            except Exception as e:
                print(f'  ERROR {url}: {e}')
                break
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.content, 'html.parser')
            found_new = 0
            for a in soup.find_all('a', href=True):
                href = urljoin(BASE, a['href'])
                # 詳細ページのみ（/shrine/ 直下はアーカイブトップなので除外）
                if '/shrine/' in href and href.rstrip('/') != f'{BASE}/shrine':
                    if href not in seen:
                        seen.add(href)
                        urls.append(href)
                        found_new += 1
            print(f'  {slug} page{page}: 新規{found_new}件 (累計{len(urls)})')
            if found_new == 0:
                break
            page += 1
            time.sleep(SLEEP)
        time.sleep(SLEEP)
    return urls


def clean_value(v):
    """値のクリーニング（全角空白・markdown残骸の除去）"""
    v = re.sub(r'[\u3000\s]+', ' ', v).strip()
    if v in ('', '：', ':'):
        return ''
    return v


def parse_shrine_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content, 'html.parser')
        text = soup.get_text('\n')
        fields = {}
        for key, pat in FIELD_RE.items():
            m = pat.search(text)
            fields[key] = clean_value(m.group(1)) if m else ''
        name = fields.get('name')
        if not name:
            # フォールバック: h1
            h1 = soup.find('h1')
            name = h1.get_text(strip=True) if h1 else ''
        if not name:
            return None
        address = fields.get('address', '')
        if address and not address.startswith('香川県'):
            address = '香川県' + address
        return {
            'name': name,
            'pref': '香川県',
            'address': address,
            'deity': fields.get('deity', ''),
            'lat': None,
            'lng': None,
            'festivals': [],       # 例祭フィールド自体がサイトに存在しない
            'festivals_raw': '',
            'notes': fields.get('notes', ''),
            'official_url': '',
            'source_url': url,
            'source': 'kagawa_jinjacho',
        }
    except Exception as e:
        print(f'  ERROR {url}: {e}')
        return None


def main():
    print('=== 香川県神社庁 スクレイプ開始 ===')
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

    with open('kagawa_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)
    print(f'保存: kagawa_raw.json ({len(shrines)}件)')
    with_deity = sum(1 for s in shrines if s['deity'])
    print(f'御祭神あり: {with_deity}件 / 座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
