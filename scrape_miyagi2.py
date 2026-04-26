import requests, re, json, time
from bs4 import BeautifulSoup

BASE = "https://miyagi-jinjacho.or.jp/jinja-search"

# 既存データ読み込み（再開用）
try:
    shrines = json.load(open('miyagi_raw.json'))
    done_names = {s['name'] for s in shrines}
    print(f"既存: {len(shrines)}件")
except:
    shrines = []
    done_names = set()

# codeリスト読み込み
all_codes = json.load(open('miyagi_codes.json')) if __import__('os').path.exists('miyagi_codes.json') else []

if not all_codes:
    import urllib.parse
    r = requests.get(f"{BASE}/list.php?chinzachi=%E7%9F%B3%E5%B7%BB%E5%B8%82&PC=1", timeout=15)
    soup = BeautifulSoup(r.text, 'html.parser')
    areas = [o['value'] for o in soup.select('select#chinzachi option') if o['value']]
    for area in areas:
        url = f"{BASE}/list.php?chinzachi={urllib.parse.quote(area)}&per_page_def=9999&page_jinja=0&PC=1"
        r = requests.get(url, timeout=15)
        codes = re.findall(r"detail\('(\d+)'\)", r.text)
        all_codes.extend(codes)
        time.sleep(0.3)
    all_codes = list(set(all_codes))
    json.dump(all_codes, open('miyagi_codes.json','w'))
    print(f"総code数: {len(all_codes)}")

done_codes = {s.get('source_url','').split('code=')[1].split('&')[0] for s in shrines if 'code=' in s.get('source_url','')}

for i, code in enumerate(all_codes):
    if code in done_codes:
        continue
    url = f"{BASE}/detail.php?code={code}&PC=1"
    for retry in range(3):
        try:
            r = requests.get(url, timeout=20)
            break
        except:
            time.sleep(3)
    else:
        continue

    text = r.text
    name_m = re.search(r'\[([^\]]+)\]</div>', text)
    addr_m = re.search(r'鎮座地</li>\s*<div[^>]*>([^<]+)', text)
    reisai_m = re.search(r'例祭日</li>\s*<div[^>]*>([^<]+)', text)
    latlng_m = re.search(r'q=([\d.]+),([\d.]+)', text)

    if not name_m:
        continue

    s = {
        'name': name_m.group(1).strip(),
        'address': addr_m.group(1).strip() if addr_m else '',
        'pref': '宮城県',
        'source': 'miyagi_jinjacho',
        'source_url': url,
    }
    if latlng_m:
        s['lat'] = float(latlng_m.group(1))
        s['lng'] = float(latlng_m.group(2))
    if reisai_m:
        reisai = reisai_m.group(1).strip()
        if reisai:
            m2 = re.search(r'(\d+)月', reisai)
            s['festivals'] = [{'month': int(m2.group(1)), 'date_str': reisai, 'name': '例祭'}] if m2 else []
            s['festivals_raw'] = reisai
    shrines.append(s)

    if len(shrines) % 50 == 0:
        json.dump(shrines, open('miyagi_raw.json','w'), ensure_ascii=False, indent=2)
        print(f"{len(shrines)}件保存")
    time.sleep(0.3)

json.dump(shrines, open('miyagi_raw.json','w'), ensure_ascii=False, indent=2)
reisai_count = sum(1 for s in shrines if s.get('festivals'))
print(f"完了: {len(shrines)}件 例祭{reisai_count}件 ({reisai_count/len(shrines)*100:.1f}%)")
