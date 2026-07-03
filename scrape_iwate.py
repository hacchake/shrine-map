"""
岩手県 神社スクレイパー（岩手県神道青年会「岩手県内 神社検索」）
https://ganshinsei.livedoor.blog/

※岩手県神社庁公式(jinjacho.jp)は2025年末のリニューアルで神社検索ページが廃止
  （旧 serviceindex1.html は404確認済み 2026-07-03）。
  神社庁トップからリンクされている神道青年会作成のDBを利用する。

構造: 1記事=1神社、市町村カテゴリ計 約857社（2026-07-03時点）
記事フィールド: 神社名 / 御祭神 / 例祭日 / 鎮座地(郵便番号付) / 由緒
→ 由緒（長文）は転載になるため取得しない。事実データのみ抽出。
→ meta description に「神社名 X 御祭神 Y 例祭日 Z 鎮座地 W 由緒…」が
  そのまま入っているので、これを第一ソースにする（本文はフォールバック）。

URL収集: sitemap.xml（livedoorブログ標準）→ 失敗時 ?p=N（1記事/ページ）
"""

import requests, re, json, time, urllib.parse
from bs4 import BeautifulSoup

BASE = "https://ganshinsei.livedoor.blog"
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot/1.0)'}
GEOCODE = True

LABELS = ['神社名', '御祭神', '例祭日', '鎮座地', '由緒', 'タグ']


def parse_month_jp(text):
    text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    m = re.search(r'(\d+)月', text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return n
    kanji = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
             '七': 7, '八': 8, '九': 9, '十': 10, '十一': 11, '十二': 12}
    for k, v in sorted(kanji.items(), key=lambda x: -len(x[0])):
        if f'{k}月' in text:
            return v
    return None


def get_article_urls():
    """全記事URLを収集"""
    urls = set()
    pat = re.compile(r'https?://ganshinsei\.livedoor\.blog/archives/\d+\.html')

    # 1) sitemap.xml
    try:
        r = requests.get(f"{BASE}/sitemap.xml", timeout=15, headers=HEADERS)
        if r.status_code == 200:
            urls.update(pat.findall(r.text))
            # sitemap indexの場合は子sitemapを辿る
            for sm in re.findall(r'<loc>\s*(https?://[^<\s]+sitemap[^<\s]*)\s*</loc>', r.text):
                if sm.rstrip('/') == f"{BASE}/sitemap.xml":
                    continue
                try:
                    r2 = requests.get(sm, timeout=15, headers=HEADERS)
                    urls.update(pat.findall(r2.text))
                    time.sleep(0.3)
                except Exception:
                    pass
    except Exception as e:
        print(f"sitemap取得失敗: {e}")

    if len(urls) >= 500:
        print(f"sitemapから{len(urls)}件のURL取得")
        return sorted(urls)

    # 2) ページネーション（1記事/ページ、約858ページ）
    print("sitemap不十分。ページネーションでURL収集します...")
    urls = set()
    empty_streak = 0
    for p in range(1, 1000):
        try:
            r = requests.get(f"{BASE}/?p={p}", timeout=15, headers=HEADERS)
            found = set(pat.findall(r.text))
            found |= {f"{BASE}/archives/{n}.html"
                      for n in re.findall(r'href="/archives/(\d+)\.html"', r.text)}
            new = found - urls
            if not new:
                empty_streak += 1
                if empty_streak >= 3:
                    break
            else:
                empty_streak = 0
                urls |= new
            if p % 50 == 0:
                print(f"  page {p}: 累計{len(urls)}件")
            time.sleep(0.4)
        except Exception:
            break
    print(f"ページネーションから{len(urls)}件のURL取得")
    return sorted(urls)


def grab(src, label, stop_labels):
    """label直後〜次のラベルまでを抽出"""
    stops = '|'.join(re.escape(s) for s in stop_labels)
    m = re.search(re.escape(label) + r'\s*(.+?)(?=' + stops + r'|$)', src, re.S)
    if not m:
        return ''
    val = re.sub(r'\s+', ' ', m.group(1)).strip()
    # 別ラベルを誤って拾った場合は捨てる
    if val in LABELS:
        return ''
    return val


def parse_article(url):
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content, 'html.parser')

        # タイトル: 「三社座神社（雫石町上町西） : 岩手県内　神社検索…」
        name, district = '', ''
        t = soup.find('title')
        if t:
            head = t.get_text().split(':')[0].strip()
            m = re.match(r'(.+?)（(.+?)）', head)
            if m:
                name, district = m.group(1).strip(), m.group(2).strip()
            else:
                name = head

        # meta description 優先、本文フォールバック
        desc = ''
        md = soup.find('meta', attrs={'name': 'description'})
        if md:
            desc = md.get('content', '') or ''
        src = desc + '\n' + soup.get_text('\n')

        # 神社記事でなければスキップ（例: 「このサイトの検索方法について」）
        if '神社名' not in src or '鎮座地' not in src:
            return None

        name2 = grab(src, '神社名', ['御祭神', '例祭日', '鎮座地', '由緒'])
        if name2:
            name = name2
        deity = grab(src, '御祭神', ['例祭日', '鎮座地', '由緒'])
        reisai_raw = grab(src, '例祭日', ['鎮座地', '由緒', '御祭神'])
        loc = grab(src, '鎮座地', ['由緒', 'タグ'])

        # 郵便番号を除去して県名を付与
        address = re.sub(r'〒\s*\d{3}[-−ーｰ]?\d{4}', '', loc)
        address = re.sub(r'\s+', '', address).strip()
        if not address and district:
            address = district
        if address and not address.startswith('岩手県'):
            address = '岩手県' + address

        festivals = []
        if reisai_raw:
            month = parse_month_jp(reisai_raw)
            if month:
                festivals = [{'month': month, 'date_str': reisai_raw, 'name': '例祭'}]

        if not name:
            return None

        return {
            'name': name,
            'pref': '岩手県',
            'address': address,
            'deity': deity[:300],
            'lat': None,
            'lng': None,
            'festivals': festivals,
            'festivals_raw': reisai_raw,
            'notes': '',
            'official_url': '',
            'source': 'iwate_ganshinsei',
            'source_url': url,
        }
    except Exception as e:
        print(f"  ERROR {url}: {e}")
        return None


def geocode(shrines):
    no_coords = [s for s in shrines if not s.get('lat') and s.get('address')]
    print(f"ジオコーディング対象: {len(no_coords)}件")
    success = 0
    for s in no_coords:
        try:
            r = requests.get(
                "https://msearch.gsi.go.jp/address-search/AddressSearch?q="
                + urllib.parse.quote(s['address']), timeout=8)
            results = r.json()
            if results:
                s['lng'] = float(results[0]['geometry']['coordinates'][0])
                s['lat'] = float(results[0]['geometry']['coordinates'][1])
                success += 1
        except Exception:
            pass
        time.sleep(0.1)
    print(f"ジオコーディング成功: {success}件")


def main():
    print("=== 岩手県（神道青年会DB）スクレイパー ===\n")
    urls = get_article_urls()
    print(f"対象URL: {len(urls)}件\n")

    shrines = []
    for i, url in enumerate(urls):
        s = parse_article(url)
        if s:
            shrines.append(s)
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(urls)}: {len(shrines)}件取得")
        time.sleep(0.4)

    print(f"\n=== 取得完了: {len(shrines)}件 ===")
    reisai = sum(1 for s in shrines if s.get('festivals'))
    if shrines:
        print(f"例祭データあり: {reisai}件 ({reisai/len(shrines)*100:.1f}%)")

    if GEOCODE:
        geocode(shrines)

    with open('iwate_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=2)
    print("iwate_raw.json を保存しました")


if __name__ == '__main__':
    main()
