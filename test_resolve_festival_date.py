# -*- coding: utf-8 -*-
"""
resolve_festival_date() の単体テスト。実装前にdata.json内の実際のdate_strから
代表的なパターンを20件選び、先にテストケースとして固定してから実装する。

使い方: python3 test_resolve_festival_date.py
"""
import datetime
from resolve_festival_date import resolve_festival_date

D = datetime.date
YEAR = 2026  # 2026年は10/1が木曜始まりのテスト用固定年


def f(date_str, month=None):
    return {'date_str': date_str, 'month': month, 'name': 'x'}


CASES = [
    # 1. 固定日
    (f('9月15日'), [(D(2026, 9, 15), D(2026, 9, 15))]),
    # 2. 固定日（全角数字）
    (f('３月１８日'), [(D(2026, 3, 18), D(2026, 3, 18))]),
    # 3. 第N曜日
    (f('10月第2日曜日'), [(D(2026, 10, 11), D(2026, 10, 11))]),
    # 4. 最終曜日
    (f('11月最終日曜'), [(D(2026, 11, 29), D(2026, 11, 29))]),
    # 5. 第N曜日＋末尾に祭典名が続く（本来はnameだが date_str に紛れ込むケースを想定）
    (f('10月第4日曜日'), [(D(2026, 10, 25), D(2026, 10, 25))]),
    # 6. 同じ週内の複数曜日（土・日それぞれ1件ずつ）
    (f('8月第1土曜・日曜'), [(D(2026, 8, 1), D(2026, 8, 1)), (D(2026, 8, 2), D(2026, 8, 2))]),
    # 7. 期間（同月内の範囲）
    (f('７月１１～１４日'), [(D(2026, 7, 11), D(2026, 7, 14))]),
    # 8. 期間（半角ハイフン区切り）
    (f('1月1-3日'), [(D(2026, 1, 1), D(2026, 1, 3))]),
    # 9. 期間（月除去後に日範囲だけが残るケース）
    (f('10月14〜15日'), [(D(2026, 10, 14), D(2026, 10, 15))]),
    # 10. 毎月＋複数曜日（月×2件で年24件になるはず）
    (f('毎月第1、第3日曜日'), 'MONTHLY_24'),
    # 11. 旧暦（変換せず月単位フォールバック）
    (f('旧6月1日'), [(D(2026, 6, 1), D(2026, 6, 30))]),
    # 12. 旧暦（「旧暦」表記）
    (f('旧暦9月10日'), [(D(2026, 9, 1), D(2026, 9, 30))]),
    # 13. 下旬
    (f('7月下旬'), [(D(2026, 7, 21), D(2026, 7, 31))]),
    # 14. 上旬
    (f('4月上旬'), [(D(2026, 4, 1), D(2026, 4, 10))]),
    # 15. 中旬（全角）
    (f('２月中旬'), [(D(2026, 2, 11), D(2026, 2, 20))]),
    # 16. 祝日（体育の日 = 10月第2月曜）
    (f('10月体育の日'), [(D(2026, 10, 12), D(2026, 10, 12))]),
    # 17. 祝日（成人の日 = 1月第2月曜）
    (f('1月成人の日'), [(D(2026, 1, 12), D(2026, 1, 12))]),
    # 18. 祝日（海の日 = 7月第3月曜）
    (f('7月海の日'), [(D(2026, 7, 20), D(2026, 7, 20))]),
    # 19. 干支基準日（変換せず月単位フォールバック、月はdate_str中の数字から抽出）
    (f('2月初午'), [(D(2026, 2, 1), D(2026, 2, 28))]),
    # 20. 完全にパース不能・monthフィールドも無い → 対応不能（空リスト）
    (f('の土曜日'), []),
]

# 追加検証: date_strが不明でもmonthフィールドがあれば月単位フォールバック
EXTRA_CASE = (f('よくわからない表記', month=5), [(D(2026, 5, 1), D(2026, 5, 31))])

# 追加検証（2026-07回帰）: 「．」区切りの期間表記が解決できず月全体に
# フォールバックしてしまっていたバグ（実データ okayama_jinjacho「八幡宮」で発覚）
EXTRA_CASE2 = (f('３月１７.１８日'), [(D(2026, 3, 17), D(2026, 3, 18))])


def run():
    failures = 0
    for i, (fest, expected) in enumerate(CASES, 1):
        got = resolve_festival_date(fest, YEAR)
        if expected == 'MONTHLY_24':
            ok = len(got) == 24 and (D(2026, 1, 4), D(2026, 1, 4)) in got and (D(2026, 1, 18), D(2026, 1, 18)) in got
            if not ok:
                failures += 1
                print(f'FAIL TC{i} (毎月): got {len(got)} entries: {got[:4]}...')
            continue
        if got != expected:
            failures += 1
            print(f'FAIL TC{i}')
            print(f'  date_str: {fest["date_str"]!r}')
            print(f'  expected: {expected!r}')
            print(f'  got:      {got!r}')

    got_extra = resolve_festival_date(EXTRA_CASE[0], YEAR)
    if got_extra != EXTRA_CASE[1]:
        failures += 1
        print('FAIL EXTRA (month fallback)')
        print(f'  expected: {EXTRA_CASE[1]!r}')
        print(f'  got:      {got_extra!r}')

    got_extra2 = resolve_festival_date(EXTRA_CASE2[0], YEAR)
    if got_extra2 != EXTRA_CASE2[1]:
        failures += 1
        print('FAIL EXTRA2 (．区切り期間)')
        print(f'  expected: {EXTRA_CASE2[1]!r}')
        print(f'  got:      {got_extra2!r}')

    total = len(CASES) + 2
    print(f'{total - failures}/{total} passed')
    return failures == 0


if __name__ == '__main__':
    import sys
    sys.exit(0 if run() else 1)
