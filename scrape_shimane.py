import requests, re, json, time
from bs4 import BeautifulSoup

BASE = "https://www.shimane-jinjacho.or.jp"

# 神社地域ディレクトリ
AREA_DIRS = ['matsue','yasugi','unnan','okuizumo','oda','gotsu','hamada',
             'masuda','tsuwano','yoshika','onan','misato','kawamoto','iinan',
             'izumo','okinoshima','nishinoshima','ama','chibumura']

all_urls = []
for area in AREA_DIRS:
    url = f"{BASE}/{area}/index.html"
    r = requests.get(url, timeout=15)
    text = r.content.decode('utf-8', errors='replace')
    links = re.findall(rf'href="({BASE}/{area}/[a-f0-9]+\.html)"', text)
    all_urls.extend(links)
    print(f"{area}: {len(links)}件")
    time.sleep(0.3)

all_urls = list(set(all_urls))
print(f"総URL: {len(all_urls)}")

shrines = []
for i, url in enumerate(all_urls):
    try:
        r = requests.get(url, timeout=15)
        text = r.content.decode('utf-8', errors='replace')
        soup = BeautifulSoup(text, 'html.parser')

        data = {}
        for row in soup.find_all('tr'):
            tds = row.find_all('td')
            if len(tds) == 2:
                key = tds[0].get_text(strip=True)
                val = tds[1].get_text(strip=True)
                data[key] = val

        name = data.get('神社名（正称)')
        addr = data.get('鎮座地', '')
        reisai = data.get('例祭日', '')

        if not name:
            continue

        s = {
            'name': name,
            'address': '島根県' + addr if addr and not addr.startswith('島根') else addr,
            'pref': '島根県',
            'source': 'shimane_jinjacho',
            'source_url': url,
        }

        # 緯度経度
        latlng = re.search(r'q=([\d.]+),([\d.]+)', text)
        if latlng:
            s['lat'] = float(latlng.group(1))
            s['lng'] = float(latlng.group(2))

        if reisai:
            # 10/13 形式を変換
            m = re.search(r'(\d+)[/月](\d+)', reisai)
            if m:
                month = int(m.group(1))
                s['festivals'] = [{'month': month, 'date_str': reisai, 'name': '例祭'}]
                s['festivals_raw'] = reisai

        shrines.append(s)
    except Exception as e:
        print(f"ERROR {url}: {e}")

    if i % 100 == 0:
        print(f"{i}/{len(all_urls)}: {len(shrines)}件")
    time.sleep(0.2)

print(f"完了: {len(shrines)}件")
reisai_count = sum(1 for s in shrines if s.get('festivals'))
print(f"例祭あり: {reisai_count}件 ({reisai_count/len(shrines)*100:.1f}%)")
with open('shimane_raw.json', 'w', encoding='utf-8') as f:
    json.dump(shrines, f, ensure_ascii=False, indent=2)
