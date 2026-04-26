"""
新規スクレイプデータをdata.jsonにマージ

使い方:
  python3 merge_new_prefectures.py aomori_raw.json yamagata_raw.json hokkaido_raw.json

既存のsourceが一致するデータは一旦削除して再追加
"""

import json, sys, re, argparse
from pathlib import Path

def make_id(shrine, prefix, idx):
    """一意IDを生成"""
    existing_id = shrine.get('id', '')
    if existing_id:
        return existing_id
    name_slug = re.sub(r'[^\w]', '', shrine.get('name', 'unknown'))[:20]
    return f"{prefix}_{name_slug}_{idx:05d}"

def normalize_shrine(shrine, prefix, idx):
    """フィールドを正規化"""
    return {
        'id': make_id(shrine, prefix, idx),
        'name': shrine.get('name', ''),
        'pref': shrine.get('pref', ''),
        'address': shrine.get('address', ''),
        'deity': shrine.get('deity', ''),
        'lat': shrine.get('lat'),
        'lng': shrine.get('lng'),
        'festivals': shrine.get('festivals', []),
        'festivals_raw': shrine.get('festivals_raw', ''),
        'notes': shrine.get('notes', ''),
        'official_url': shrine.get('official_url', ''),
        'source_url': shrine.get('source_url', ''),
        'source': shrine.get('source', prefix),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_files', nargs='+', help='マージするJSONファイル')
    parser.add_argument('--data', default='data.json', help='data.jsonのパス')
    parser.add_argument('--dry-run', action='store_true', help='保存せず確認のみ')
    args = parser.parse_args()

    # data.jsonを読み込む
    data_path = Path(args.data)
    print(f"data.json 読み込み中: {data_path}")
    with open(data_path, encoding='utf-8') as f:
        data = json.load(f)
    print(f"  既存: {len(data)}件")

    # 各ファイルを処理
    for input_file in args.input_files:
        path = Path(input_file)
        if not path.exists():
            print(f"ファイルが見つかりません: {path}")
            continue
        
        with open(path, encoding='utf-8') as f:
            new_shrines = json.load(f)
        
        if not new_shrines:
            print(f"{path}: データが空")
            continue
        
        # sourceを特定
        source = new_shrines[0].get('source', '')
        if not source:
            source = path.stem.replace('_raw', '') + '_jinjacho'
        
        prefix = source
        
        # 既存データから同じsourceを除去
        before = len(data)
        data = [s for s in data if s.get('source') != source]
        removed = before - len(data)
        
        print(f"\n{path.name}:")
        print(f"  source: {source}")
        print(f"  新規データ: {len(new_shrines)}件")
        print(f"  既存データ削除: {removed}件")
        
        # 新規データを追加
        normalized = []
        for i, shrine in enumerate(new_shrines):
            if not shrine.get('name'):
                continue
            normalized.append(normalize_shrine(shrine, prefix, i))
        
        data.extend(normalized)
        
        # 統計
        reisai = sum(1 for s in normalized if s.get('festivals'))
        print(f"  追加: {len(normalized)}件")
        print(f"  例祭率: {reisai}/{len(normalized)} ({reisai/max(len(normalized),1)*100:.1f}%)")
        
        # 月別分布
        month_counts = {}
        for s in normalized:
            for f in s.get('festivals', []):
                m = f.get('month')
                if m:
                    month_counts[m] = month_counts.get(m, 0) + 1
        if month_counts:
            sorted_months = sorted(month_counts.items())
            print("  月別例祭数:", {f'{m}月': c for m, c in sorted_months})

    print(f"\n合計: {len(data)}件")
    
    if not args.dry_run:
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        print(f"data.json 保存完了: {len(data)}件")
    else:
        print("（ドライランのため保存しません）")

if __name__ == '__main__':
    main()
