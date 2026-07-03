# 神社まつりマップ (shrine-map)

日本全国の神社と例祭日を地図表示するプロジェクト。GitHub Pagesで公開: https://hacchake.github.io/shrine-map

## 構成

- `index.html` — Leaflet.jsベースの地図UI（GitHub Pagesで配信）
- `data.json` — 神社データ本体（5万件超）。**巨大なので全読み込み禁止**。検索はpythonかjq/grepで
- `scrape_*.py` — 都道府県別スクレイパー。出力は `{県名}_raw.json`
- `merge_new_prefectures.py` — raw jsonをdata.jsonにマージ（同一sourceは削除して再追加）
- `geocode_file.py` — 座標なしレコードをGSI APIで補完する汎用ツール
- `NOTES_*.md` — セッションごとの調査メモ・引き継ぎ

## データスキーマ（data.json / raw json共通）

```json
{"id": "...", "name": "疫神社", "pref": "岡山県", "address": "...", "deity": "素盞嗚尊",
 "lat": 34.6, "lng": 133.9,
 "festivals": [{"month": 10, "date_str": "10月第2日曜日", "name": "秋祭"}],
 "festivals_raw": "...", "notes": "", "official_url": "", "source_url": "...", "source": "okayama_jinjacho"}
```

- festivalsのmonthはint必須（地図のフィルタで使用）
- addressは「○○県」から始める（県判定は `startswith('○○県')`。「岩手」だけだと岩手郡に誤マッチした前科あり）

## 典型的なワークフロー

```bash
python3 scrape_XXX.py                 # → XXX_raw.json
python3 merge_new_prefectures.py XXX_raw.json --dry-run   # 件数確認
python3 merge_new_prefectures.py XXX_raw.json             # 本マージ
git add -A && git commit && git push  # Pagesに自動反映
```

## スクレイパー作成時の注意

- ラベル完全一致は禁物。実サイトは「住 所」「例 祭」のように空白が混入する（青森で実例）
- 正規表現の `\s*` は改行を越えて次行を拾う。行内空白は `[ \t\u3000]*` を使う（香川で実例）
- 座標を地図リンクから取るときは `soup.get_text()` でなく生HTML（`r.text`）を検索（href属性はget_textに含まれない）
- ジオコーディングはGSI API（`msearch.gsi.go.jp/address-search/AddressSearch?q=`）、sleep 0.1秒
- 各リクエスト間 sleep 1秒、User-Agentに連絡目的を明記
- robots.txtで拒否されているサイト（例: 北海道神社庁）はスクレイプしない
- 由緒などの長文は著作権配慮で取得しない。事実データ（名称/住所/祭神/例祭日/座標）のみ

## 未完了タスク（2026-07-03時点）

1. 岩手・山形・青森・香川スクレイパーの実サイト通し実行（合成HTMLテストのみ済み）
2. okinawa_raw.json のジオコーディング＋マージ
3. 奈良の例祭パース率改善
4. UI改善: 詳細モーダル、カタカナ表示修正
5. ジオコーディング全体強化（geocode_file.py data.json --data-format が使える）

詳細は NOTES_20260703.md を参照。
