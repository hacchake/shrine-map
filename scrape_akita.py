import requests, re, json, time, urllib.parse
from bs4 import BeautifulSoup

BASE = "https://akita-jinjacho.sakura.ne.jp"

# WP APIで全slugを取得
all_links = []
page = 1
while True:
    url = f"{BASE}/wp-json/wp/v2/shrine_search?per_page=100&page={page}&_fields=link"
    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        break
    data = r.json()
    if not data:
        break
    all_links.extend([s['link'] for s in data])
    print(f"page={page}: {len(data)}件 累計{len(all_links)}")
    if len(data) < 100:
        break
    page += 1
    time.sleep(0.3)

print(f"総URL: {len(all_links)}")

shrines = []
for i, url in enumerate(all_links):
    try:
        r = requests.get(url, timeout=15)
        text = r.content.decode('utf-8', errors='replace')
        soup = BeautifulSoup(text, 'html.parser')

        # テーブルから情報取得
        data = {}
        for row in soup.find_all('tr'):
            th = row.find('th')
            td = row.find('td')
            if th and td:
                data[th.get_text(strip=True)] = td.get_text(strip=True)

        name = data.get('神社名', '')
        if not name:
            h1 = soup.find('h1')
            name = h1.get_text(strip=True) if h1 else ''
        if not name:
            continue

        addr = data.get('鎮座地', data.get('住所', ''))
        reisai = data.get('例祭', '')

        # 座標
        latlng = re.search(r'q=([\d.]+),([\d.]+)', text)

        s = {
            'name': name,
            'address': '秋田県' + addr if addr and not addr.startswith('秋田') else addr,
            'pref': '秋田県',
            'source': 'akita_jinjacho',
            'source_url': url,
        }
        if latlng:
            s['lat'] = float(latlng.group(1))
            s['lng'] = float(latlng.group(2))
        if reisai:
            m2 = re.search(r'(\d+)月', reisai)
            if m2:
                s['festivals'] = [{'month': int(m2.group(1)), 'date_str': reisai, 'name': '例祭'}]
                s['festivals_raw'] = reisai
        shrines.append(s)
    except Exception as e:
        print(f"ERROR {url}: {e}")

    if i % 100 == 0:
        print(f"{i}/{len(all_links)}: {len(shrines)}件")
    time.sleep(0.2)

print(f"完了: {len(shrines)}件")
reisai_count = sum(1 for s in shrines if s.get('festivals'))
print(f"例祭あり: {reisai_count}件 ({reisai_count/len(shrines)*100:.1f}%)")

# ジオコーディング
no_coords = [s for s in shrines if not s.get('lat') and s.get('address')]
print(f"ジオコーディング対象: {len(no_coords)}件")
success = 0
for s in no_coords:
    try:
        r2 = requests.get(f"https://msearch.gsi.go.jp/address-search/AddressSearch?q={urllib.parse.quote(s['address'])}", timeout=8)
        results = r2.json()
        if results:
            s['lng'] = float(results[0]['geometry']['coordinates'][0])
            s['lat'] = float(results[0]['geometry']['coordinates'][1])
            success += 1
    except:
        pass
    time.sleep(0.1)
print(f"ジオコーディング: {success}件")

with open('akita_raw.json', 'w', encoding='utf-8') as f:
    json.dump(shrines, f, ensure_ascii=False, indent=2)
if shrines:
    print(shrines[0])
