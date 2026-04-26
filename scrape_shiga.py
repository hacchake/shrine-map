import requests, re, json, time

BASE = "https://www.shiga-jinjacho.jp/ycBBS/Board.cgi/02_jinja_db/db/"
POST_URL = BASE + "ycDB_02jinja-pc-search.html"

def fetch_page(page):
    data = {
        "view:tree": "0",
        "search:method": "group",
        "mode:search": "1",
        "view:term": "100",
        "view:sort": "address_1:1",
        "view:direct": "0",
        "view:page": str(page),
        "s:REI1,REI2,REI3,REI4,REI5:eq:9:REISAI:or": "1",
        "s:REISAI,KENSAKU:eq:19:ALL:and": "1",
    }
    r = requests.post(POST_URL, data=data, timeout=20)
    return r.content.decode('shift_jis', errors='replace')

# 全oid収集
all_oids = set()
page = 1
while True:
    text = fetch_page(page)
    oids = re.findall(r'view:oid=(\d+)', text)
    if not oids:
        break
    all_oids.update(oids)
    print(f"page={page}: {len(oids)}件 累計{len(all_oids)}")
    if len(oids) < 100:
        break
    page += 1
    time.sleep(0.5)

print(f"総oid: {len(all_oids)}")

# 詳細ページ取得
shrines = []
for i, oid in enumerate(all_oids):
    url = BASE + f"ycDB_02jinja-pc-detail.html?mode:view=1&view:oid={oid}"
    try:
        r = requests.get(url, timeout=15)
        text = r.content.decode('shift_jis', errors='replace')
    except:
        continue

    name_m = re.search(r'〔[^〕]+〕\s*([^\n<]+)', text)
    addr_m = re.search(r'〒(\d{7})\s*([^\n<]+)', text)
    reisai_m = re.search(r'祭礼日[^<]*</[^>]+>\s*(.+?)(?:<br|$)', text, re.DOTALL)
    latlng_m = re.search(r'q=([\d.]+),([\d.]+)', text)

    if not name_m:
        continue

    # 住所組み立て
    addr = ''
    if addr_m:
        addr = '〒' + addr_m.group(1) + ' ' + addr_m.group(2).strip()

    s = {
        'name': name_m.group(1).strip(),
        'address': addr,
        'pref': '滋賀県',
        'source': 'shiga_jinjacho',
        'source_url': url,
    }
    if latlng_m:
        s['lat'] = float(latlng_m.group(1))
        s['lng'] = float(latlng_m.group(2))

    if reisai_m:
        reisai = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', reisai_m.group(1))).strip()
        if reisai:
            m2 = re.search(r'(\d+)月', reisai)
            s['festivals'] = [{'month': int(m2.group(1)), 'date_str': reisai, 'name': '例祭'}] if m2 else []
            s['festivals_raw'] = reisai

    shrines.append(s)
    if i % 100 == 0:
        print(f"{i}/{len(all_oids)}: {len(shrines)}件")
    time.sleep(0.2)

print(f"完了: {len(shrines)}件")
reisai_count = sum(1 for s in shrines if s.get('festivals'))
print(f"例祭あり: {reisai_count}件 ({reisai_count/len(shrines)*100:.1f}%)")

with open('shiga_raw.json', 'w', encoding='utf-8') as f:
    json.dump(shrines, f, ensure_ascii=False, indent=2)
