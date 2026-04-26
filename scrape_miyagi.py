import requests, re, json, time
from bs4 import BeautifulSoup
import urllib.parse

BASE = "https://miyagi-jinjacho.or.jp/jinja-search"

# 地域リスト取得
r = requests.get(f"{BASE}/list.php?chinzachi=%E7%9F%B3%E5%B7%BB%E5%B8%82&PC=1", timeout=15)
text = r.text
soup = BeautifulSoup(text, 'html.parser')
areas = [o['value'] for o in soup.select('select#chinzachi option') if o['value']]
print(f"地域数: {len(areas)}")

# 全codeを収集
all_codes = set()
for area in areas:
    url = f"{BASE}/list.php?chinzachi={urllib.parse.quote(area)}&per_page_def=9999&page_jinja=0&PC=1"
    r = requests.get(url, timeout=15)
    codes = re.findall(r"detail\('(\d+)'\)", r.text)
    all_codes.update(codes)
    print(f"  {area}: {len(codes)}件")
    time.sleep(0.3)

print(f"\n総code数: {len(all_codes)}")

# 詳細ページ取得
shrines = []
for i, code in enumerate(all_codes):
    url = f"{BASE}/detail.php?code={code}&PC=1"
    r = requests.get(url, timeout=15)
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
            m = re.search(r'(\d+)月', reisai)
            s['festivals'] = [{'month': int(m.group(1)), 'date_str': reisai, 'name': '例祭'}] if m else []
            s['festivals_raw'] = reisai
    shrines.append(s)

    if i % 100 == 0:
        print(f"{i}/{len(all_codes)}: {len(shrines)}件")
    time.sleep(0.2)

print(f"\n合計: {len(shrines)}件")
reisai_count = sum(1 for s in shrines if s.get('festivals'))
print(f"例祭あり: {reisai_count}件 ({reisai_count/len(shrines)*100:.1f}%)")

with open('miyagi_raw.json', 'w', encoding='utf-8') as f:
    json.dump(shrines, f, ensure_ascii=False, indent=2)
