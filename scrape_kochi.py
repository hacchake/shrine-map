# -*- coding: utf-8 -*-
"""
高知県神社庁 スクレイパー（新規作成）
https://www.kochi-jinjyacho.com/高知県神社一覧

背景: 過去のセッションでWixサイトのJSレンダリング（Velo Cloud Data）のため
静的取得は不可能と判断していたが、検索エンジンには神社名・住所がテキストで
見えていたため2026-07-05に再調査。

構造（2026-07-05実確認）:
- 一覧ページはWixのリピーターコンポーネント(comp-ljqfjyd6)がCloud Data
  コレクション(id: 4gq343hu3awdp28flsx)をクライアントサイドでフェッチして
  描画する作りで、生HTMLには神社データが含まれない
- ただし各ページのHTMLには `<script type="application/json"
  id="wix-warmup-data">` としてSEO/ハイドレーション用のJSONが埋め込まれており、
  その中の appsWarmupData.dataBinding.dataStore.recordsByCollectionId に
  「そのページの12件」のレコードがそのまま入っている（SSRはしないがWarmup
  データとして最初の描画分だけ埋め込む方式）
- ページ送りは `?comp-ljqfjyd6_page=N` パラメータで、これを変えて再取得する
  たびにwarmup-dataの中身がそのページの12件に変わることを確認済み
  （通常のGETリクエストで取得可、ブラウザ操作不要）
- 総件数は同JSON内の datasetSize.total で取得可能（2026-07-05時点4,215件）
- フィールド構成（スキーマのdisplayNameで確認）:
    title=支部 / text=神社名 / text1=住所（市郡より下の部分） /
    text2=電話（スキップ,個人情報に準じる扱い） /
    text3=宮司名（スキップ,個人情報） / text4=郵便番号 /
    newField=県市郡（住所の上位部分） / url=URL / image=画像（スキップ）
  例祭・御祭神のフィールド自体が存在しない（香川方式）。住所は
  newField + text1 で結合する
- 座標は掲載されていないためGSI APIでジオコーディング
- **情報源側の重複**: 収集元のWixコレクション自体に、同じ神社が異なる
  `_id`で2件ずつ登録されている（2026-07-05実確認、4,214件中4,210件が
  2,105組のペア、内容は完全一致）。`_id`でのdedupだけでは検出できないため、
  (name, address)が完全一致するものを最終的に1件へ集約する
- name中の半角カタカナ（例:「須ﾉ浦神社」の「ﾉ」）は地名表記の慣例に合わせ
  全角へ正規化する
"""
import re
import unicodedata
import requests
import json
import time
import urllib.parse

BASE = 'https://www.kochi-jinjyacho.com'
PAGE_PATH = '/%E9%AB%98%E7%9F%A5%E7%9C%8C%E7%A5%9E%E7%A4%BE%E4%B8%80%E8%A6%A7'  # 高知県神社一覧
COLLECTION_ID = '4gq343hu3awdp28flsx'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; shrine-map-bot; personal research; contact hacchake@gmail.com)'}
SLEEP = 1.0

FULLWIDTH_KATAKANA = re.compile(r'[｡-ﾟ]')
_HALFWIDTH_TABLE = {cp: unicodedata.normalize('NFKC', chr(cp)) for cp in range(0xFF61, 0xFFA0)}
_HALFWIDTH_TABLE[ord('ｹ')] = 'ヶ'  # 地名の「ヶ」代用として使われる慣例（NOTES_20260704/20260705）


def normalize_name(name):
    if FULLWIDTH_KATAKANA.search(name):
        return name.translate(_HALFWIDTH_TABLE)
    return name


def fetch_page_records(page, retries=3):
    """まれにwarmup-dataにappsWarmupData自体が含まれない応答が返る
    （2026-07-05実確認、page=116でthinderbolt側の一時的な描画ゆれと推定）。
    リトライで解消するため数回再試行する"""
    url = f'{BASE}{PAGE_PATH}?comp-ljqfjyd6_page={page}'
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            r.encoding = 'utf-8'
            html = r.text
            marker = '<script type="application/json" id="wix-warmup-data"'
            start = html.find(marker)
            if start == -1:
                raise ValueError('warmup-data script tag not found')
            start = html.find('>', start) + 1
            end = html.find('</script>', start)
            warmup = json.loads(html[start:end])
            db = warmup['appsWarmupData']['dataBinding']
            records = db['dataStore']['recordsByCollectionId'].get(COLLECTION_ID, {})
            total = None
            rid = db['dataStore'].get('recordInfosByDatasetId', {})
            for info in rid.values():
                ds = info.get('datasetSize')
                if ds:
                    total = ds.get('total')
            return list(records.values()), total
        except Exception as e:
            last_err = e
            time.sleep(2.0)
    raise last_err


def main():
    print('=== 高知県神社庁 スクレイプ開始 ===')
    seen_ids = set()
    shrines = []
    total = None
    failed_pages = []
    page = 1
    max_page = None
    while True:
        if max_page and page > max_page:
            break
        try:
            records, page_total = fetch_page_records(page)
        except Exception as e:
            print(f'  ERROR page={page}: {e} (スキップして続行)')
            failed_pages.append(page)
            page += 1
            time.sleep(SLEEP)
            continue
        if page_total:
            total = page_total
            if max_page is None:
                max_page = -(-total // 12)
        if not records:
            print(f'  page={page}: 0件、終了')
            break

        new_count = 0
        for rec in records:
            rid = rec.get('_id')
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            new_count += 1

            name = normalize_name((rec.get('text') or '').strip())
            if not name:
                continue
            addr_prefix = (rec.get('newField') or '').strip()
            addr_rest = (rec.get('text1') or '').strip()
            address = addr_prefix + addr_rest
            if address and not address.startswith('高知県'):
                address = '高知県' + address

            shrines.append({
                'name': name,
                'pref': '高知県',
                'address': address,
                'deity': '',
                'lat': None,
                'lng': None,
                'festivals': [],
                'festivals_raw': '',
                'notes': (rec.get('title') or ''),
                'official_url': (rec.get('url') or ''),
                'source_url': f'{BASE}{PAGE_PATH}?comp-ljqfjyd6_page={page}',
                'source': 'kochi_jinjacho',
            })

        print(f'  page={page}: 新規{new_count}件 (累計{len(shrines)}件 / 全{total}件)')
        if total and len(seen_ids) >= total:
            break
        page += 1
        time.sleep(SLEEP)

    if failed_pages:
        print(f'失敗ページ再試行: {failed_pages}')
        still_failed = []
        for page in failed_pages:
            try:
                records, _ = fetch_page_records(page)
            except Exception as e:
                print(f'  再試行も失敗 page={page}: {e}')
                still_failed.append(page)
                continue
            new_count = 0
            for rec in records or []:
                rid = rec.get('_id')
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
                new_count += 1
                name = normalize_name((rec.get('text') or '').strip())
                if not name:
                    continue
                addr_prefix = (rec.get('newField') or '').strip()
                addr_rest = (rec.get('text1') or '').strip()
                address = addr_prefix + addr_rest
                if address and not address.startswith('高知県'):
                    address = '高知県' + address
                shrines.append({
                    'name': name, 'pref': '高知県', 'address': address, 'deity': '',
                    'lat': None, 'lng': None, 'festivals': [], 'festivals_raw': '',
                    'notes': (rec.get('title') or ''), 'official_url': (rec.get('url') or ''),
                    'source_url': f'{BASE}{PAGE_PATH}?comp-ljqfjyd6_page={page}',
                    'source': 'kochi_jinjacho',
                })
            print(f'  再試行page={page}: 新規{new_count}件')
            time.sleep(SLEEP)
        if still_failed:
            print(f'最終的に取得できなかったページ: {still_failed}')

    print(f'取得完了: {len(shrines)}件')

    seen_key = set()
    deduped = []
    for s in shrines:
        key = (s['name'], s['address'])
        if key in seen_key:
            continue
        seen_key.add(key)
        deduped.append(s)
    print(f'情報源側の重複除去: {len(shrines)}件 → {len(deduped)}件')
    shrines = deduped

    no_coords = [s for s in shrines if not s.get('lat') and s.get('address')]
    print(f'ジオコーディング対象: {len(no_coords)}件')
    ok = 0
    for s in no_coords:
        try:
            r = requests.get(
                'https://msearch.gsi.go.jp/address-search/AddressSearch?q='
                + urllib.parse.quote(s['address']), timeout=8)
            results = r.json()
            if results:
                s['lng'] = float(results[0]['geometry']['coordinates'][0])
                s['lat'] = float(results[0]['geometry']['coordinates'][1])
                ok += 1
        except Exception:
            pass
        time.sleep(0.1)
    print(f'ジオコーディング成功: {ok}件')

    with open('kochi_raw.json', 'w', encoding='utf-8') as f:
        json.dump(shrines, f, ensure_ascii=False, indent=1)

    deity_n = sum(1 for s in shrines if s.get('deity'))
    print(f'保存: kochi_raw.json ({len(shrines)}件)')
    print(f'御祭神あり: {deity_n}/{len(shrines)}')
    print(f'座標あり: {sum(1 for s in shrines if s["lat"])}件')


if __name__ == '__main__':
    main()
