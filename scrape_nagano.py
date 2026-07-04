import requests
import re
import json
import time
from bs4 import BeautifulSoup

BASE = "https://www.nagano-jinjacho.jp"

SHIBU_URLS = [
    f"{BASE}/shibu/hansui.htm",
    f"{BASE}/shibu/kamitakai.htm",
    f"{BASE}/shibu/shimotakai.htm",
    f"{BASE}/shibu/nagano.htm",
    f"{BASE}/shibu/kamiminochi.htm",
    f"{BASE}/shibu/kousyoku.htm",
    f"{BASE}/shibu/sarashina.htm",
    f"{BASE}/shibu/syouenchiku.htm",
    f"{BASE}/shibu/kiso.htm",
    f"{BASE}/shibu/jousyou.htm",
    f"{BASE}/shibu/kitasaku.htm",
    f"{BASE}/shibu/minamisaku.htm",
    f"{BASE}/shibu/kamiina.htm",
    f"{BASE}/shibu/suwa.htm",
    f"{BASE}/shibu/hani.htm",
]

def fetch_sjis(url):
    """サイトはページによって文字コードが混在（一覧=Shift_JIS、詳細=UTF-8等）
    なので、UTF-8を優先して試し、失敗したらShift_JISにフォールバックする。
    2026-07-04: 旧実装はshift_jisをerrors='replace'で強制していたため、
    実際はUTF-8のページを誤デコードして文字化けが発生していた（判明済み）。"""
    try:
        r = requests.get(url, timeout=15)
    except Exception as e:
        print(f"  ERROR: {url} -> {e}")
        return ""
    try:
        return r.content.decode('utf-8')
    except UnicodeDecodeError:
        pass
    try:
        return r.content.decode('shift_jis')
    except UnicodeDecodeError:
        return r.content.decode('shift_jis', errors='replace')

def parse_month_jp(text):
    text = (text or '').translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    m = re.search(r'(\d+)月', text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return n
    return None


def extract_field(html, fieldname):
    pattern = rf'{re.escape(fieldname)}</TD>\s*<TD[^>]*>([^<]+)</TD>'
    m = re.search(pattern, html)
    return m.group(1).strip() if m else None

def parse_detail_page(url):
    html = fetch_sjis(url)
    if not html:
        return None
    data = {}
    for field, key in [('神社名', 'name'), ('鎮座地', 'address'), ('例祭日', 'reisai'), ('支部名', 'shibu')]:
        val = extract_field(html, field)
        if val:
            data[key] = val
    return data if data else None

def parse_list_page(url):
    html = fetch_sjis(url)
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    base_dir = url.rsplit('/', 1)[0]
    results = []
    seen_urls = set()

    # 詳細ページリンクを全収集
    detail_links = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.endswith('.htm') and not href.startswith('http') and '/' in href:
            detail_url = base_dir + '/' + href
            detail_links.add(detail_url)

    # 詳細ページを取得
    for detail_url in sorted(detail_links):
        if detail_url in seen_urls:
            continue
        seen_urls.add(detail_url)
        print(f"  詳細: {detail_url}")
        detail = parse_detail_page(detail_url)
        time.sleep(0.3)
        if detail:
            results.append(detail)

    # 詳細ページのない神社（zip行のみ）
    detail_names = {r.get('name', '') for r in results}
    for row in soup.find_all('tr'):
        tds = row.find_all('td')
        if len(tds) < 3:
            continue
        zip_text = tds[1].get_text(strip=True)
        if not re.match(r'^\d{3}-\d{4}$', zip_text):
            continue
        if tds[0].find('a'):
            continue  # 詳細リンクあり行はスキップ
        name = tds[0].get_text(strip=True)
        addr = tds[2].get_text(strip=True)
        if name and name != '神社名' and name not in detail_names:
            results.append({'name': name, 'address': addr})

    return results

all_shrines = []
for shibu_url in SHIBU_URLS:
    print(f"\n支部: {shibu_url}")
    shrines = parse_list_page(shibu_url)
    for s in shrines:
        s['source'] = 'nagano_jinjacho'
        s['pref'] = '長野県'
        reisai = s.pop('reisai', None)
        if reisai:
            entry = {'name': '例祭', 'date_str': reisai}
            month = parse_month_jp(reisai)
            if month:
                entry['month'] = month
            s['festivals'] = [entry]
            s['festivals_raw'] = reisai
    print(f"  -> {len(shrines)}件")
    all_shrines.extend(shrines)

print(f"\n合計: {len(all_shrines)}件")
with open('nagano_raw.json', 'w', encoding='utf-8') as f:
    json.dump(all_shrines, f, ensure_ascii=False, indent=2)

reisai_count = sum(1 for s in all_shrines if s.get('festivals'))
print(f"例祭あり: {reisai_count}件 ({reisai_count/len(all_shrines)*100:.1f}%)")
