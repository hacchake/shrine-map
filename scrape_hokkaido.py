"""
北海道神社庁スクレイパー
https://hokkaidojinjacho.jp/

WordPress系サイトの場合、WP REST APIを試みる
個別ページ例: https://hokkaidojinjacho.jp/北海道神宮/
"""

import requests, re, json, time, warnings, urllib.parse
from bs4 import BeautifulSoup

warnings.filterwarnings('ignore')

BASE = "https://hokkaidojinjacho.jp"
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot/1.0)'}

def parse_month_jp(text):
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

def get_all_links_wp_api():
    """WP REST APIで全神社URLを取得"""
    all_links = []
    page = 1
    
    while True:
        # カスタム投稿タイプを試す
        for post_type in ['jinja', 'shrine', 'posts']:
            url = f"{BASE}/wp-json/wp/v2/{post_type}?per_page=100&page={page}&_fields=link,slug"
            try:
                r = requests.get(url, timeout=15, headers=HEADERS)
                if r.status_code == 200:
                    data = r.json()
                    if data:
                        links = [s.get('link', '') for s in data if s.get('link')]
                        all_links.extend(links)
                        print(f"  WP API ({post_type}) page={page}: {len(links)}件")
                        if len(data) < 100:
                            return all_links, post_type
                        page += 1
                        time.sleep(0.5)
                        break
            except Exception:
                pass
        else:
            break
    
    return all_links, None

def get_all_links_sitemap():
    """サイトマップからURLを収集"""
    links = []
    for sitemap_url in [
        f"{BASE}/sitemap.xml",
        f"{BASE}/sitemap_index.xml",
        f"{BASE}/wp-sitemap.xml",
    ]:
        try:
            r = requests.get(sitemap_url, timeout=15, headers=HEADERS)
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, 'xml')
                # サイトマップインデックスの場合
                for loc in soup.find_all('loc'):
                    url = loc.get_text(strip=True)
                    if 'sitemap' in url.lower():
                        # サブサイトマップを取得
                        try:
                            r2 = requests.get(url, timeout=15, headers=HEADERS)
                            soup2 = BeautifulSoup(r2.content, 'xml')
                            for loc2 in soup2.find_all('loc'):
                                shrine_url = loc2.get_text(strip=True)
                                if BASE in shrine_url:
                                    links.append(shrine_url)
                        except Exception:
                            pass
                    elif BASE in url:
                        links.append(url)
                
                if links:
                    print(f"サイトマップ {sitemap_url} から{len(links)}件")
                    return links
        except Exception:
            pass
    return links

def get_all_links_list_page():
    """リストページから全URLを収集"""
    links = []
    
    # メインの神社一覧ページを試みる
    list_candidates = [
        f"{BASE}/jinja-list/",
        f"{BASE}/shrine-list/",
        f"{BASE}/jinja/",
        f"{BASE}/shrines/",
        f"{BASE}/",
    ]
    
    for list_url in list_candidates:
        try:
            r = requests.get(list_url, timeout=15, headers=HEADERS)
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, 'html.parser')
                page_links = []
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if href.startswith(BASE) and href != list_url:
                        # 神社っぽいURL（数字、神社名など）
                        path = href.replace(BASE, '').strip('/')
                        if path and '?' not in path and '#' not in path:
                            page_links.append(href)
                if len(page_links) > 10:
                    print(f"リストページ {list_url} から{len(page_links)}件")
                    links.extend(page_links)
                    break
        except Exception as e:
            pass
    
    return list(set(links))

def scrape_detail(url):
    """個別神社ページをスクレイプ"""
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        if r.status_code != 200:
            return None
        
        soup = BeautifulSoup(r.content.decode('utf-8', errors='replace'), 'html.parser')
        text = soup.get_text('\n')
        
        if len(text.strip()) < 200:
            return None
        
        # 神社名
        name = ''
        for tag in ['h1', 'h2']:
            el = soup.find(tag)
            if el:
                t = el.get_text(strip=True)
                if t and len(t) < 50 and ('神社' in t or '神宮' in t or '宮' in t or '社' in t):
                    name = t
                    break
        
        # タイトルタグから
        if not name:
            title = soup.find('title')
            if title:
                t = title.get_text()
                parts = re.split(r'[|\-–—｜]', t)
                for p in parts:
                    p = p.strip()
                    if '神社' in p or '神宮' in p or '宮' in p:
                        name = p
                        break
        
        if not name:
            return None
        
        # テーブルデータ
        data = {}
        for row in soup.find_all('tr'):
            th = row.find('th')
            td = row.find('td')
            if th and td:
                data[th.get_text(strip=True)] = td.get_text('\n', strip=True)
        
        # DL形式
        for dl in soup.find_all('dl'):
            dts = dl.find_all('dt')
            dds = dl.find_all('dd')
            for dt, dd in zip(dts, dds):
                data[dt.get_text(strip=True)] = dd.get_text('\n', strip=True)
        
        address = data.get('鎮座地', data.get('住所', data.get('所在地', '')))
        deity = data.get('御祭神', data.get('祭神', ''))
        reisai_raw = data.get('例祭', data.get('例祭日', data.get('例大祭', '')))
        
        # 例祭日
        festivals = []
        festivals_raw = reisai_raw or ''
        if reisai_raw:
            month = parse_month_jp(reisai_raw)
            if month:
                festivals = [{'month': month, 'date_str': reisai_raw, 'name': '例祭'}]
        
        # 座標（地図リンクから）
        lat, lng = None, None
        latlng = re.search(r'(?:q|ll)=([\d.]+)[,/]([\d.]+)', text)
        if latlng:
            lat = float(latlng.group(1))
            lng = float(latlng.group(2))
        
        # Googleマップのiframeから
        if not lat:
            iframe = soup.find('iframe', src=True)
            if iframe:
                src = iframe['src']
                m = re.search(r'(?:q|ll)=([\d.]+)[,/]([\d.]+)', src)
                if m:
                    lat = float(m.group(1))
                    lng = float(m.group(2))
        
        if address and not address.startswith('北海道'):
            address = '北海道' + address
        
        return {
            'name': name,
            'pref': '北海道',
            'address': address,
            'deity': deity,
            'lat': lat,
            'lng': lng,
            'festivals': festivals,
            'festivals_raw': festivals_raw,
            'notes': '',
            'official_url': '',
            'source': 'hokkaido_jinjacho',
            'source_url': url,
        }
    
    except Exception as e:
        print(f"  ERROR {url}: {e}")
        return None

def main():
    print("=== 北海道神社庁スクレイパー ===\n")
    
    # URLを収集（複数の方法を試みる）
    all_urls = []
    
    print("1. WP APIを試みます...")
    wp_urls, post_type = get_all_links_wp_api()
    if wp_urls:
        print(f"  WP API ({post_type}): {len(wp_urls)}件")
        all_urls = wp_urls
    
    if not all_urls:
        print("2. サイトマップを試みます...")
        all_urls = get_all_links_sitemap()
    
    if not all_urls:
        print("3. リストページを試みます...")
        all_urls = get_all_links_list_page()
    
    # 神社っぽいURLだけ残す
    shrine_urls = []
    for url in all_urls:
        decoded = urllib.parse.unquote(url)
        if any(word in decoded for word in ['神社', '神宮', '宮', '社', 'jinja', 'shrine']):
            shrine_urls.append(url)
        elif url.count('/') >= 3:  # ある程度深いパス
            shrine_urls.append(url)
    
    shrine_urls = list(set(shrine_urls))
    print(f"\n対象URL: {len(shrine_urls)}件")
    
    if not shrine_urls:
        print("URLが取得できませんでした。手動で確認してください。")
        print(f"サイト: {BASE}")
        return
    
    shrines = []
    for i, url in enumerate(shrine_urls):
        shrine = scrape_detail(url)
        if shrine:
            shrines.append(shrine)
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(shrine_urls)}: {len(shrines)}件")
        time.sleep(0.5)
    
    print(f"\n=== 完了: {len(shrines)}件 ===")
    if shrines:
        reisai = sum(1 for s in shrines if s.get('festivals'))
        print(f"例祭データあり: {reisai}件 ({reisai/len(shrines)*100:.1f}%)")
    
    with open('hokkaido_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=2)
    print("hokkaido_raw.json を保存しました")

if __name__ == '__main__':
    main()
