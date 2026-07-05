# -*- coding: utf-8 -*-
"""
festival_matches_range() の単体テスト。日付範囲フィルタ(旅程指定)の核心となる
「祭りの開催日が指定範囲と1日でも重なるか」を、実装前に15パターンで固定する。

使い方: python3 test_festival_matches_range.py
"""
import datetime
from resolve_festival_date import festival_matches_range

D = datetime.date


def f(date_str, month=None):
    return {'date_str': date_str, 'month': month, 'name': 'x'}


CASES = [
    # 1. 固定日が範囲内
    (f('9月15日'), D(2026, 9, 14), D(2026, 9, 16), True),
    # 2. 固定日が範囲外（鶴岡八幡宮の例祭9/14-16に対し9/20-22を指定した想定と対の
    #    シンプル版：単発の9/15に対し範囲外の9/20-22）
    (f('9月15日'), D(2026, 9, 20), D(2026, 9, 22), False),
    # 3. 固定日が範囲の開始境界に一致
    (f('9月14日'), D(2026, 9, 14), D(2026, 9, 16), True),
    # 4. 固定日が範囲の終了境界に一致
    (f('9月16日'), D(2026, 9, 14), D(2026, 9, 16), True),
    # 5. 期間祭が範囲と部分的に重なる（祭りの終端=範囲の始端）
    (f('9月14日〜16日'), D(2026, 9, 16), D(2026, 9, 18), True),
    # 6. 期間祭が範囲と全く重ならない（実例: 鶴岡八幡宮の例大祭9/14-16に対し
    #    旅程9/20-22を指定 → ヒットしないのが正しい）
    (f('9月14日〜16日'), D(2026, 9, 20), D(2026, 9, 22), False),
    # 7. 期間祭が範囲を包含する
    (f('9月1日〜30日'), D(2026, 9, 14), D(2026, 9, 16), True),
    # 8. 第N曜日が範囲内（2026年10月第2日曜日=10/11）
    (f('10月第2日曜日'), D(2026, 10, 10), D(2026, 10, 12), True),
    # 9. 第N曜日が範囲外
    (f('10月第2日曜日'), D(2026, 10, 1), D(2026, 10, 5), False),
    # 10. 毎月（複数回開催）のうち1回が範囲と重なる（10月第1日曜日=10/4）
    (f('毎月第1日曜日'), D(2026, 10, 1), D(2026, 10, 6), True),
    # 11. 毎月だが範囲がどの回にも重ならない「谷間」の週
    (f('毎月第1日曜日'), D(2026, 10, 7), D(2026, 10, 10), False),
    # 12. 下旬（7/21-31）と範囲が重なる
    (f('7月下旬'), D(2026, 7, 25), D(2026, 7, 28), True),
    # 13. 上旬（4/1-10）と範囲が重ならない
    (f('4月上旬'), D(2026, 4, 15), D(2026, 4, 20), False),
    # 14. 旧暦（変換せず月単位フォールバック=6月全体）と範囲が重なる
    #     （取りこぼしより出しすぎを優先する方針の確認）
    (f('旧6月1日'), D(2026, 6, 10), D(2026, 6, 12), True),
    # 15. 年をまたぐ範囲指定（12/30〜1/2）に対し、1/1固定の祭りがヒットする
    (f('1月1日'), D(2026, 12, 30), D(2027, 1, 2), True),
]


def run():
    failures = 0
    for i, (fest, start, end, expected) in enumerate(CASES, 1):
        got = festival_matches_range(fest, start, end)
        if got != expected:
            failures += 1
            print(f'FAIL TC{i}')
            print(f'  date_str: {fest["date_str"]!r} range: {start}〜{end}')
            print(f'  expected: {expected!r}  got: {got!r}')

    print(f'{len(CASES) - failures}/{len(CASES)} passed')
    return failures == 0


if __name__ == '__main__':
    import sys
    sys.exit(0 if run() else 1)
