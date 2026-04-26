import requests, re, json, time, urllib.parse
from bs4 import BeautifulSoup

BASE = "https://www.ibarakiken-jinjacho.or.jp/ibaraki"

# 各エリアの市町村ページ（HTMLから確認済み）
AREA_CITIES = [
    ('kenhoku', ['hitachi','hitachiota','hitachiomiya','kita','takahagi','daigo','tokai','naka','oarai','hokota']),
    ('kenou',   ['mito','kasama','omitama','shirosato','tokai']),
    ('kensei',  ['tsuchiura','tukuba','isioka','kasumigaura','ami','miho','tukubamirai','usiku']),
    ('rokko',   ['itako','kamisu','kashima','koga','sashima']),
    ('kennan',  ['tukuba','tuchiura','isioka','kasumigaura','ami','miho','tukubamirai','usiku','inasiki','moriya','toride','ryugasaki','kawati','tone']),
]

# まず各エリアのHTMLから市町村リストを取得
all_shrine_urls = set()
for area, cities in AREA_CITIES:
    for city in cities:
        url = f"{BASE}/{area}/{city}.html"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            text = r.content.decode('shift_jis', errors='replace')
            links = re.findall(r'href="(jinja/\d+\.html?)"', text)
            for l in links:
                all_shrine_urls.add(f"{BASE}/{area}/{l}")
            if links:
                print(f"{area}/{city}: {len(links)}件")
        except:
            pass
        time.sleep(0.3)

print(f"\n総神社URL: {len(all_shrine_urls)}")

# 個別ページ取得
shrines = []
for i, url in enumerate(all_shrine_urls):
    try:
        r = requests.get(url, timeout=15)
        text = r.content.decode('shift_jis', errors='replace')
        soup = BeautifulSoup(text, 'html.parser')

        # 神社名・住所・例祭日
        name_m = re.search(r'神社名[^：:]*[：:]\s*([^\n<]{2,30})', text)
        addr_m = re.search(r'〒[\d-]+\s+([^\n<]+)', text)
        
        name = name_m.group(1).strip() if name_m else ''
        if not name:
            continue

        addr = addr_m.group(1).strip() if addr_m else ''
        
        reisai = ''
        reisai_m = re.search(r'例大祭|例祭', text)
        if reisai_m:
            idx = reisai_m.start()
            nearby = text[max(0,idx-80):idx+150]
            dm = re.search(r'(\d+)月\s*(\d+)日', nearby)
            if dm:
                reisai = f"{dm.group(1)}月{dm.group(2)}日"

        s = {
            'name': name,
            'address': '茨城県' + addr if addr and not addr.startswith('茨城') else addr,
            'pref': '茨城県',
            'source': 'ibaraki_jinjacho',
            'source_url': url,
        }
        if reisai:
            m2 = re.search(r'(\d+)月', reisai)
            if m2:
                s['festivals'] = [{'month': int(m2.group(1)), 'date_str': reisai, 'name': '例祭'}]
                s['festivals_raw'] = reisai
        shrines.append(s)
    except Exception as e:
        pass

    if i % 10 == 0:
        print(f"{i}/{len(all_shrine_urls)}: {len(shrines)}件")
    time.sleep(0.5)

print(f"完了: {len(shrines)}件")
reisai_count = sum(1 for s in shrines if s.get('festivals'))
print(f"例祭あり: {reisai_count}件")

# ジオコーディング
success = 0
for s in shrines:
    if s.get('lat') or not s.get('address'):
        continue
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

with open('ibaraki_raw.json', 'w', encoding='utf-8') as f:
    json.dump(shrines, f, ensure_ascii=False, indent=2)
if shrines:
    print(shrines[0])
