# -*- coding: utf-8 -*-
"""
福島県神社庁 スクレイパー（新規作成）
https://fukushima-jinjacho.or.jp/search/

背景: 通常のWP REST APIは無効化されている(`rest_disabled`)が、検索地図
（Googleマップ）が裏で叩く独自PHPエンドポイントが1リクエストで全件を
XMLで返すことを2026-07-05の偵察調査で発見。

構造（2026-07-05実確認）:
- `https://fukushima-jinjacho.or.jp/cms/wp-content/themes/style-jinjatyou/
  search/search_locate.php?q=`（qを空にすると絞り込みなし全件、ページネーション
  不要の1リクエストで316件取得可）
- XML要素<Locate>の子要素: lat/lng(座標、ジオコーディング不要) / name(神社名) /
  furigana(ふりがな) / post(郵便番号) / address(住所、既に「福島県」から始まる) /
  tinzati1-4(住所の内訳) / shozoku(支部) / guujimei(宮司名、個人情報配慮で
  スキップ) / tel・fax(スキップ) / url(公式サイト) / img(画像、スキップ) /
  gosyuin・gosyuinmemo(御朱印関連、スキップ) / gosaishin(御祭神) /
  goshintoku(ご利益、キーワード列挙のため由緒とは異なり著作権上の懸念は
  薄いが、他県のdeityフィールドが祭神名のみのため今回は取得しない)
- 例祭日のフィールド自体が存在しない
"""
import json
import xml.etree.ElementTree as ET
import requests

BASE = 'https://fukushima-jinjacho.or.jp'
API_URL = f'{BASE}/cms/wp-content/themes/style-jinjatyou/search/search_locate.php?q='
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}


def main():
    print('=== 福島県神社庁 スクレイプ開始 ===')
    r = requests.get(API_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = 'utf-8'
    root = ET.fromstring(r.text)
    locs = root.findall('Locate')
    print(f'取得: {len(locs)}件')

    all_shrines = []
    for loc in locs:
        row = {child.tag: (child.text or '').strip() for child in loc}
        name = row.get('name', '')
        if not name:
            continue
        address = row.get('address', '')
        if address and not address.startswith('福島県'):
            address = '福島県' + address
        lat = lng = None
        try:
            if row.get('lat') and row.get('lng'):
                lat, lng = float(row['lat']), float(row['lng'])
        except ValueError:
            pass

        all_shrines.append({
            'name': name,
            'address': address,
            'deity': row.get('gosaishin', ''),
            'lat': lat,
            'lng': lng,
            'notes': row.get('shozoku', ''),
            'official_url': row.get('url', ''),
        })

    print(f'取得完了: {len(all_shrines)}件')

    # 情報源側の重複登録チェック（高知・新潟・福岡で確認済みのパターン）
    seen = set()
    deduped = []
    for s in all_shrines:
        key = (s['name'], s['address'])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)
    print(f'重複除去: {len(all_shrines)}件 → {len(deduped)}件')

    shrines = []
    for s in deduped:
        shrines.append({
            'name': s['name'],
            'pref': '福島県',
            'address': s['address'],
            'deity': s['deity'],
            'lat': s['lat'],
            'lng': s['lng'],
            'festivals': [],
            'festivals_raw': '',
            'notes': s['notes'],
            'official_url': s['official_url'],
            'source_url': API_URL,
            'source': 'fukushima_jinjacho',
        })

    with open('fukushima_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)

    deity_n = sum(1 for s in shrines if s.get('deity'))
    print(f'保存: fukushima_raw.json ({len(shrines)}件)')
    print(f'御祭神あり: {deity_n}/{len(shrines)}')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
