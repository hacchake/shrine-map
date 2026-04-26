"""
山形県神社庁スクレイパー
https://yamagata-jinjyacho.or.jp/shrine_detail/{id}
IDは5桁ゼロ埋め（例: 09338）

まずリストページからIDを収集、次に個別ページをスクレイプ
"""

import requests, re, json, time, warnings
from bs4 import BeautifulSoup

warnings.filterwarnings('ignore')  # SSL警告を抑制

BASE = "https://yamagata-jinjyacho.or.jp"
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot/1.0)'}

def parse_month_jp(text):
    """月を抽出（漢数字・全角数字・半角数字）"""
    text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    m = re.search(r'(\d+)月', text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return n
    kanji = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,
              '七':7,'八':8,'九':9,'十':10,'十一':11,'十二':12}
    for k, v in sorted(kanji.items(), key=lambda x: -len(x[0])):
        if f'{k}月' in text:
            return v
    return None

def parse_shrine_page(url, shrine_id):
    """個別神社ページをスクレイプ"""
    try:
        r = requests.get(url, timeout=15, verify=False, headers=HEADERS)
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            print(f"  HTTP {r.status_code}: {url}")
            return None
        
        soup = BeautifulSoup(r.content.decode('utf-8', errors='replace'), 'html.parser')
        
        # ページが存在するか確認（404ページや空ページ除外）
        body_text = soup.get_text()
        if len(body_text.strip()) < 100:
            return None
        
        # 神社名
        name = ''
        # h1 or タイトル
        for tag in ['h1', 'h2', '.shrine-name', '.name']:
            el = soup.select_one(tag) if tag.startswith('.') else soup.find(tag)
            if el:
                name = el.get_text(strip=True)
                if name and len(name) < 50:
                    break
        
        # テーブル形式のデータを取得
        data = {}
        for row in soup.find_all('tr'):
            th = row.find('th')
            td = row.find('td')
            if th and td:
                key = th.get_text(strip=True)
                val = td.get_text('\n', strip=True)
                data[key] = val
        
        # DL形式の場合
        for dl in soup.find_all('dl'):
            dts = dl.find_all('dt')
            dds = dl.find_all('dd')
            for dt, dd in zip(dts, dds):
                data[dt.get_text(strip=True)] = dd.get_text('\n', strip=True)
        
        # フィールドを取得
        address = data.get('住所', data.get('鎮座地', data.get('所在地', '')))
        deity = data.get('御祭神', data.get('祭神', ''))
        reisai_raw = data.get('例祭', data.get('例祭日', data.get('例大祭', '')))
        festivals_raw_all = data.get('年中行事', data.get('恒例祭', data.get('行事', '')))
        
        # 神社名をデータから補完
        if not name:
            name = data.get('神社名', data.get('社名', ''))
        
        if not name:
            return None  # 名前がなければスキップ
        
        # 例祭をパース
        festivals = []
        festivals_raw = reisai_raw or ''
        
        if reisai_raw:
            month = parse_month_jp(reisai_raw)
            if month:
                festivals = [{'month': month, 'date_str': reisai_raw, 'name': '例祭'}]
        
        # 例祭が取得できなければ年中行事から探す
        if not festivals and festivals_raw_all:
            festivals_raw = festivals_raw_all
            for line in festivals_raw_all.split('\n'):
                if '例祭' in line:
                    month = parse_month_jp(line)
                    if month:
                        festivals = [{'month': month, 'date_str': line.strip(), 'name': '例祭'}]
                        break
        
        # 緯度経度（地図リンクから）
        lat, lng = None, None
        latlng = re.search(r'(?:q|ll)=([\d.]+)[,/]([\d.]+)', body_text)
        if latlng:
            lat = float(latlng.group(1))
            lng = float(latlng.group(2))
        
        if address and not address.startswith('山形'):
            address = '山形県' + address
        
        return {
            'id': f'yamagata_{shrine_id}',
            'name': name,
            'pref': '山形県',
            'address': address,
            'deity': deity,
            'lat': lat,
            'lng': lng,
            'festivals': festivals,
            'festivals_raw': festivals_raw,
            'notes': '',
            'official_url': '',
            'source': 'yamagata_jinjacho',
            'source_url': url,
        }
    
    except Exception as e:
        print(f"  ERROR {url}: {e}")
        return None

def get_all_ids():
    """神社IDリストを取得（リストページから）"""
    ids = []
    
    # まずリストページを探す
    list_urls = [
        f"{BASE}/shrine_list",
        f"{BASE}/shrines",
        f"{BASE}/jinja",
        f"{BASE}/",
    ]
    
    for list_url in list_urls:
        try:
            r = requests.get(list_url, timeout=15, verify=False, headers=HEADERS)
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, 'html.parser')
                for a in soup.find_all('a', href=True):
                    m = re.search(r'/shrine_detail/(\d+)', a['href'])
                    if m:
                        ids.append(m.group(1))
                if ids:
                    print(f"リストページ {list_url} から{len(ids)}件のIDを取得")
                    return list(set(ids))
        except Exception as e:
            pass
    
    # リストページが見つからない場合、ページネーションを試みる
    print("ページネーション検索を試みます...")
    for page in range(1, 50):
        try:
            r = requests.get(f"{BASE}/shrine_list?page={page}", timeout=15, verify=False, headers=HEADERS)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.content, 'html.parser')
            page_ids = []
            for a in soup.find_all('a', href=True):
                m = re.search(r'/shrine_detail/(\d+)', a['href'])
                if m:
                    page_ids.append(m.group(1))
            if not page_ids:
                break
            ids.extend(page_ids)
            print(f"  page={page}: {len(page_ids)}件 累計{len(ids)}件")
            time.sleep(0.5)
        except Exception as e:
            break
    
    return list(set(ids))

def main():
    print("=== 山形県神社庁スクレイパー ===")
    
    # IDリストを取得
    ids = get_all_ids()
    
    # IDが取得できなかった場合、既知のIDから連番を推定
    if not ids:
        print("IDリストが取得できませんでした。連番スキャンを実行します...")
        # 既知ID: 09338 → 約9000〜10000台のIDがある可能性
        # まず範囲を確認
        test_ids = ['00001', '01000', '05000', '09338', '10000', '15000']
        max_id = 0
        for test_id in test_ids:
            url = f"{BASE}/shrine_detail/{test_id}"
            r = requests.get(url, timeout=15, verify=False, headers=HEADERS)
            if r.status_code == 200 and len(r.content) > 500:
                print(f"  存在: {test_id}")
                max_id = max(max_id, int(test_id))
            else:
                print(f"  なし: {test_id} (HTTP {r.status_code})")
            time.sleep(0.3)
        
        # 連番スキャン（1〜max_id+5000）
        scan_max = max(max_id + 2000, 12000)
        print(f"1〜{scan_max}を連番スキャンします（時間がかかります）")
        ids = [f'{i:05d}' for i in range(1, scan_max + 1)]
    
    print(f"\n対象ID数: {len(ids)}")
    
    shrines = []
    errors = 0
    
    for i, shrine_id in enumerate(ids):
        url = f"{BASE}/shrine_detail/{shrine_id}"
        shrine = parse_shrine_page(url, shrine_id)
        if shrine:
            shrines.append(shrine)
        else:
            errors += 1
        
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(ids)}: {len(shrines)}件取得 (エラー/スキップ:{errors})")
        
        time.sleep(0.3)
    
    print(f"\n=== 完了: {len(shrines)}件 ===")
    reisai = sum(1 for s in shrines if s.get('festivals'))
    if shrines:
        print(f"例祭データあり: {reisai}件 ({reisai/len(shrines)*100:.1f}%)")
    
    with open('yamagata_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=2)
    print("yamagata_raw.json を保存しました")

if __name__ == '__main__':
    main()
