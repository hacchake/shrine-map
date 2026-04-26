import requests, re, json, time, urllib.parse
from bs4 import BeautifulSoup

BASE = "http://kyoka.mie-jinjacho.or.jp"
CATS = ['cat/01_nanki','cat/02_watarai','cat/03_matsusaka','cat/04_taki','cat/05_toba',
        'cat/06_owase','cat/07_kitamuro','cat/08_ise','cat/09_iinan','cat/10_shima',
        'cat/11_kuwana','cat/12_inabe','cat/13_mie','cat/14_yokkaichi','cat/15_suzuka',
        'cat/16_kameyama_seki','cat/17_age','cat/18_ichishi','cat/19_tsu','cat/20_hisai',
        'cat/21_ayama','cat/22_naga','cat/23_ueno','cat/24_nabari']

all_urls = set()
for cat in CATS:
    page = 1
    while True:
        url = f"{BASE}/shrine/{cat}/page/{page}/" if page > 1 else f"{BASE}/shrine/{cat}/"
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            break
        links = re.findall(r'href="(http://kyoka\.mie-jinjacho\.or\.jp/shrine/[^c/][^"]+)"', r.text)
        links = [l for l in links if l.count('/') == 5]
        if not links:
            break
        all_urls.update(links)
        page += 1
        time.sleep(0.3)

print(f"総URL: {len(all_urls)}")

shrines = []
for i, url in enumerate(all_urls):
    try:
        r = requests.get(url, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')

        # タイトルから神社名
        title = soup.find('title')
        name = ''
        if title:
            name = title.get_text().replace('三重県神社庁教化委員会 »', '').strip()

        if not name:
            continue

        # テーブルから情報取得
        rows = soup.find_all('tr')
        addr = ''
        reisai = ''
        for row in rows:
            tds = row.find_all('td')
            if len(tds) == 1:
                text = tds[0].get_text(strip=True)
                if re.match(r'[^\d]', text) and not addr and len(text) > 5 and '市' in text or '町' in text or '村' in text:
                    addr = text
                if '例祭' in text and not '育' in text and not reisai:
                    reisai_m = re.search(r'例祭\s*(\S+)', text)
                    if reisai_m:
                        reisai = reisai_m.group(1)

        # 2列テーブルも確認
        for row in rows:
            tds = row.find_all('td')
            if len(tds) == 2:
                k = tds[0].get_text(strip=True)
                v = tds[1].get_text(strip=True)
                if '鎮座地' in k:
                    addr = v
                if '例祭' in k and '育' not in k and not reisai:
                    reisai = v

        latlng = re.search(r'q=([\d.]+),([\d.]+)', r.text)

        s = {
            'name': name,
            'address': '三重県' + addr if addr and not addr.startswith('三重') else addr,
            'pref': '三重県',
            'source': 'mie_jinjacho',
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
        print(f"{i}/{len(all_urls)}: {len(shrines)}件")
    time.sleep(0.3)

print(f"完了: {len(shrines)}件")
reisai_count = sum(1 for s in shrines if s.get('festivals'))
print(f"例祭あり: {reisai_count}件 ({reisai_count/len(shrines)*100:.1f}%)")

# ジオコーディング
no_coords = [s for s in shrines if not s.get('lat') and s.get('address')]
print(f"ジオコーディング対象: {len(no_coords)}件")
success = 0
for s in no_coords:
    try:
        url2 = f"https://msearch.gsi.go.jp/address-search/AddressSearch?q={urllib.parse.quote(s['address'])}"
        r2 = requests.get(url2, timeout=8)
        results = r2.json()
        if results:
            s['lng'] = float(results[0]['geometry']['coordinates'][0])
            s['lat'] = float(results[0]['geometry']['coordinates'][1])
            success += 1
    except:
        pass
    time.sleep(0.1)
print(f"ジオコーディング完了: {success}件")

with open('mie_raw.json', 'w', encoding='utf-8') as f:
    json.dump(shrines, f, ensure_ascii=False, indent=2)
print(shrines[0])
