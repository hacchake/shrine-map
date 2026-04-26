import requests, re, json, time, urllib.parse
from bs4 import BeautifulSoup

all_urls = set()
for i in range(1, 14):
    page = 'jinja.html' if i == 1 else f'jinja{i:02d}.html'
    url = f"https://www.naraken-jinjacho.jp/{page}"
    try:
        r = requests.get(url, timeout=15)
        text = r.content.decode('utf-8', errors='replace')
        links = re.findall(r'href="(http://www\.narashinsei\.com/search/[^"]+)"', text)
        all_urls.update(links)
        print(f"{page}: {len(links)}件")
    except Exception as e:
        print(f"ERROR {page}: {e}")
    time.sleep(0.3)

print(f"総URL: {len(all_urls)}")

shrines = []
for i, url in enumerate(all_urls):
    try:
        r = requests.get(url, timeout=15)
        soup = BeautifulSoup(r.content.decode('utf-8', errors='replace'), 'html.parser')

        h1 = soup.find('h1')
        name = h1.get_text(strip=True) if h1 else ''
        if not name:
            continue

        addr = ''
        addr_m = re.search(r'〒[\d-]+\s*([^\n<]+)', r.text)
        if addr_m:
            addr = addr_m.group(1).strip()

        reisai = ''
        text = r.text
        gyoji_m = re.search(r'年中行事(.{0,2000})', text, re.DOTALL)
        if gyoji_m:
            gyoji = gyoji_m.group(1)
            rei_m = re.search(r'例祭[^\d]*(\d+)月(\d+)', gyoji)
            if rei_m:
                reisai = f"{rei_m.group(1)}月{rei_m.group(2)}日"
            else:
                rei_m2 = re.search(r'(\d+)月(\d+)[日]?[^\n]*例祭', gyoji)
                if rei_m2:
                    reisai = f"{rei_m2.group(1)}月{rei_m2.group(2)}日"

        s = {
            'name': name,
            'address': '奈良県' + addr if addr and not addr.startswith('奈良') else addr,
            'pref': '奈良県',
            'source': 'nara_jinjacho',
            'source_url': url,
        }

        latlng = re.search(r'q=([\d.]+),([\d.]+)', text)
        if latlng:
            s['lat'] = float(latlng.group(1))
            s['lng'] = float(latlng.group(2))

        if reisai:
            m2 = re.search(r'(\d+)月', reisai)
            if m2:
                s['festivals'] = [{'month': int(m2.group(1)), 'date_str': reisai, 'name': '例祭'}]
                s['festivals_raw'] = reisai

        shrines.append(s)
    except:
        pass

    if i % 50 == 0:
        print(f"{i}/{len(all_urls)}: {len(shrines)}件")
    time.sleep(0.3)

print(f"完了: {len(shrines)}件")
reisai_count = sum(1 for s in shrines if s.get('festivals'))
print(f"例祭あり: {reisai_count}件 ({reisai_count/len(shrines)*100:.1f}%)")

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

with open('nara_raw.json', 'w', encoding='utf-8') as f:
    json.dump(shrines, f, ensure_ascii=False, indent=2)
if shrines:
    print(shrines[0])
