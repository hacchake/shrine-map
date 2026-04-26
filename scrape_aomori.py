"""
青森県神社庁スクレイパー
http://www.aomori-jinjacho.or.jp/jinja/sub_1{a-h}.html
→ 個別ページ: http://www.aomori-jinjacho.or.jp/jinja/{region}/sub_1{x}_{num}.html

恒例祭セクションから例祭日を取得
"""

import requests, re, json, time
from bs4 import BeautifulSoup

BASE = "http://www.aomori-jinjacho.or.jp"

# 8地区のリストページ
REGION_PAGES = [
    (f"{BASE}/jinja/sub_1{c}.html", c)
    for c in "abcdefgh"
]

def parse_month(text):
    """テキストから月を抽出（旧暦対応）"""
    # 旧暦は月を変換しない（そのまま使う）
    m = re.search(r'(\d+)月', text)
    if m:
        return int(m.group(1))
    return None

def parse_festivals(section_text):
    """恒例祭テキストをパース → festivals[], festivals_raw, 例祭の月"""
    raw = section_text.strip()
    festivals = []
    reisai_month = None

    # 行ごとに処理
    lines = [l.strip() for l in raw.split('\n') if l.strip()]
    
    current_name = None
    current_date = None
    
    for line in lines:
        # 名前と日付が同じ行にある場合（スペースで区切られる）
        # 例: "開運厄除節分祭　　二月第一日曜日"
        #     "新嘗祭　　　　　　十一月二十三日"
        
        # 全角スペースやタブで分割を試みる
        parts = re.split(r'[\u3000\s]{2,}', line)
        
        if len(parts) >= 2:
            name = parts[0].strip()
            date = parts[-1].strip()
            if name and date:
                month = parse_month_jp(date)
                entry = {'name': name, 'date_str': date}
                if month:
                    entry['month'] = month
                festivals.append(entry)
                
                if '例祭' in name and not reisai_month:
                    reisai_month = month
        elif len(parts) == 1:
            # 単独の名前行（次の行が日付かも）
            # または日付のみの行（前のエントリの追加情報）
            # 行内に例祭が含まれる場合
            if '例祭' in line:
                month = parse_month_jp(line)
                if month and not reisai_month:
                    reisai_month = month

    return festivals, raw, reisai_month

def parse_month_jp(text):
    """日本語・数字の月表記から月を抽出"""
    # 数字: "10月", "１０月"
    text = text.replace('０','0').replace('１','1').replace('２','2').replace('３','3')\
               .replace('４','4').replace('５','5').replace('６','6').replace('７','7')\
               .replace('８','8').replace('９','9')
    m = re.search(r'(\d+)月', text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return n
    # 漢数字
    kanji_map = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,
                 '七':7,'八':8,'九':9,'十':10,'十一':11,'十二':12}
    for k, v in kanji_map.items():
        if f'{k}月' in text:
            return v
    return None

def scrape_detail(url):
    """個別神社ページをスクレイプ"""
    try:
        r = requests.get(url, timeout=15)
        soup = BeautifulSoup(r.content.decode('utf-8', errors='replace'), 'html.parser')
        
        # メインコンテンツ領域
        # 神社名: 最初の太字/h系タグ
        name = ''
        # ページタイトルから取得
        title = soup.find('title')
        if title:
            t = title.get_text()
            # "青森県神社庁-神社紹介-猿賀神社" → "猿賀神社"
            parts = t.split('-')
            if parts:
                name = parts[-1].strip()
        
        # テキスト全体をセクション分割
        text = soup.get_text('\n')
        lines = [l.strip() for l in text.split('\n')]
        
        address = ''
        deity = ''
        festivals_raw = ''
        
        # セクションを探す
        i = 0
        in_section = None
        section_buf = []
        
        while i < len(lines):
            line = lines[i]
            if line == '住所':
                in_section = 'address'
                section_buf = []
            elif line in ('御祭神', '祭神'):
                in_section = 'deity'
                section_buf = []
            elif line in ('恒例祭', '例祭', '年中祭事'):
                in_section = 'festivals'
                section_buf = []
            elif line in ('由緒', '地図', ''):
                if in_section == 'address' and section_buf:
                    address = ' '.join(section_buf)
                elif in_section == 'deity' and section_buf:
                    deity = ' '.join(section_buf)
                elif in_section == 'festivals' and section_buf:
                    festivals_raw = '\n'.join(section_buf)
                if line in ('由緒', '地図'):
                    in_section = None
            elif in_section and line:
                section_buf.append(line)
            i += 1
        
        # festivals_rawが空なら section_bufを使う
        if in_section == 'festivals' and section_buf and not festivals_raw:
            festivals_raw = '\n'.join(section_buf)
        
        # 祭りをパース
        festivals = []
        reisai_month = None
        if festivals_raw:
            festivals, _, reisai_month = parse_festivals(festivals_raw)
        
        # 住所に青森県を付与
        if address and not address.startswith('青森'):
            address = '青森県' + address
        
        result = {
            'name': name,
            'pref': '青森県',
            'address': address,
            'deity': deity,
            'festivals_raw': festivals_raw,
            'festivals': festivals,
            'source': 'aomori_jinjacho',
            'source_url': url,
            'lat': None,
            'lng': None,
            'notes': '',
            'official_url': '',
        }
        
        # 例祭のみのfestivalsを作る（月がある祭りのうち「例祭」含む）
        reisai_festivals = [f for f in festivals if '例祭' in f.get('name', '') and f.get('month')]
        if reisai_festivals:
            result['festivals'] = reisai_festivals
        elif festivals:
            # 例祭が特定できなければ全部入れる
            result['festivals'] = [f for f in festivals if f.get('month')]
        
        return result
        
    except Exception as e:
        print(f"  ERROR {url}: {e}")
        return None

def get_shrine_links(list_url):
    """リストページから個別ページのリンクを取得"""
    try:
        r = requests.get(list_url, timeout=15)
        soup = BeautifulSoup(r.content.decode('utf-8', errors='replace'), 'html.parser')
        
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            # 個別ページのパターン: sub_1x_NNN.html
            if re.search(r'sub_1[a-h]_\d+\.html', href):
                if not href.startswith('http'):
                    href = BASE + '/jinja/' + href.lstrip('/')
                links.append(href)
        return list(set(links))
    except Exception as e:
        print(f"  ERROR {list_url}: {e}")
        return []

def main():
    all_shrines = []
    
    for list_url, region_code in REGION_PAGES:
        print(f"\n=== 地区 {region_code}: {list_url} ===")
        links = get_shrine_links(list_url)
        print(f"  → {len(links)}件のリンク")
        
        for j, url in enumerate(sorted(links)):
            shrine = scrape_detail(url)
            if shrine and shrine['name']:
                all_shrines.append(shrine)
            if j % 10 == 0:
                print(f"  {j+1}/{len(links)} 完了")
            time.sleep(0.5)
    
    print(f"\n=== 完了: {len(all_shrines)}件 ===")
    reisai = sum(1 for s in all_shrines if s.get('festivals'))
    print(f"例祭データあり: {reisai}件 ({reisai/max(len(all_shrines),1)*100:.1f}%)")
    
    with open('aomori_raw.json', 'w', encoding='utf-8') as f:
        json.dump(all_shrines, f, ensure_ascii=False, indent=2)
    print("aomori_raw.json を保存しました")

if __name__ == '__main__':
    main()
