import requests, re, json, time, urllib.parse
from bs4 import BeautifulSoup

BASE = "http://www.tochigi-jinjacho.or.jp"
AREA_PAGES = ['63','114','90','80','74','110','95','1012','129','1205','112','1017',
              '78','84','82','88','86','65','103','118','120','97','124','122','1019']

# 各地域ページから神社個別URLを収集
all_shrine_ps = set()
for p in AREA_PAGES:
    url = f"{BASE}/?p={p}"
    try:
        r = requests.get(url, timeout=15)
        text = r.content.decode('utf-8', errors='replace')
        # リンクあり神社のみ
        ps = re.findall(r'href="http://www\.tochigi-jinjacho\.or\.jp/\?p=(\d+)"[^>]*>[^<]*(?:神社|宮|神宮|大社)', text)
        all_shrine_ps.update(ps)
        print(f"p={p}: {len(ps)}件")
    except Exception as e:
        print(f"ERROR p={p}: {e}")
    time.sleep(0.3)

# エリアページのp番号を除外
all_shrine_ps -= set(AREA_PAGES)
all_shrine_ps -= {'59','1','186'} # トップ等
print(f"総神社p数: {len(all_shrine_ps)}")

shrines = []
for i, p in enumerate(all_shrine_ps):
    url = f"{BASE}/?p={p}"
    try:
        r = requests.get(url, timeout=15)
        text = r.content.decode('utf-8', errors='replace')
        soup = BeautifulSoup(text, 'html.parser')

        # 神社名
        h2 = soup.find('h2', class_='S_tit04') or soup.find('div', class_='S_tit04')
        name = h2.get_text(strip=True) if h2 else ''
        if not name:
            title = soup.find('title')
            if title:
                name = title.get_text().split('«')[0].strip()
        if not name:
            continue

        # 住所
        addr = ''
        addr_m = re.search(r'【住所】</th>\s*<td>([^<]+)', text)
        if addr_m:
            addr = addr_m.group(1).strip()

        # 例祭日
        reisai = ''
        rei_m = re.search(r'【例祭日】</th>\s*<td>([^<]+)', text)
        if rei_m:
            reisai = rei_m.group(1).strip()
        else:
            # 年間行事から例大祭を探す
            gyoji_m = re.search(r'年間行事(.{0,1000})', text, re.DOTALL)
            if gyoji_m:
                gyoji = gyoji_m.group(1)
                dm = re.search(r'(\d+)月(\d+)日[^<]*例[大]?祭', gyoji)
                if dm:
                    reisai = f"{dm.group(1)}月{dm.group(2)}日"
                else:
                    dm2 = re.search(r'例[大]?祭[^\d]*(\d+)月(\d+)', gyoji)
                    if dm2:
                        reisai = f"{dm2.group(1)}月{dm2.group(2)}日"

        # 座標
        latlng = re.search(r'q=([\d.]+),([\d.]+)', text)

        s = {
            'name': name,
            'address': '栃木県' + addr if addr and not addr.startswith('栃木') else addr,
            'pref': '栃木県',
            'source': 'tochigi_jinjacho',
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
    except:
        pass

    if i % 20 == 0:
        print(f"{i}/{len(all_shrine_ps)}: {len(shrines)}件")
    time.sleep(0.3)

print(f"完了: {len(shrines)}件")
reisai_count = sum(1 for s in shrines if s.get('festivals'))
print(f"例祭あり: {reisai_count}件 ({reisai_count/len(shrines)*100:.1f}%)")

# ジオコーディング
no_coords = [s for s in shrines if not s.get('lat') and s.get('address')]
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

with open('tochigi_raw.json', 'w', encoding='utf-8') as f:
    json.dump(shrines, f, ensure_ascii=False, indent=2)
if shrines:
    print(shrines[0])
