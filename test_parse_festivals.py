# -*- coding: utf-8 -*-
"""
parse_festivals.py の単体テスト。実装前にdata.jsonの祭典ズレ328件（主に
okayama_jinjacho・ehime_jinjacho）から代表的なパターンを10件選び、
先にテストケースとして固定してから parse_festivals.py を実装する。

使い方: python3 test_parse_festivals.py
"""
from parse_festivals import parse_concat, parse_lines

CASES_CONCAT = [
    # TC1: 中旬/下旬修飾語 + 曜日の読点区切り複数曜日
    (
        '４月中旬：春季大祭７月下旬：茅輪祭１０月第２土曜日、日曜日：秋季大祭',
        [
            {'date_str': '４月中旬', 'name': '春季大祭', 'month': 4},
            {'date_str': '７月下旬', 'name': '茅輪祭', 'month': 7},
            {'date_str': '１０月第２土曜日、日曜日', 'name': '秋季大祭', 'month': 10},
        ],
    ),
    # TC2: 「、」区切りの複数日（春季/秋季/萬燈でそれぞれ独立した2日間表記）
    (
        '５月５、６日：春季慰霊大祭１０月５、６日：秋季慰霊大祭８月１５、１６日：萬燈みたま祭',
        [
            {'date_str': '５月５、６日', 'name': '春季慰霊大祭', 'month': 5},
            {'date_str': '１０月５、６日', 'name': '秋季慰霊大祭', 'month': 10},
            {'date_str': '８月１５、１６日', 'name': '萬燈みたま祭', 'month': 8},
        ],
    ),
    # TC3: 祝日名が括弧書きで月の直後に付く
    (
        '１月２日：歳旦祭４月２３日：春祭１０月(体育の日)：大祭',
        [
            {'date_str': '１月２日', 'name': '歳旦祭', 'month': 1},
            {'date_str': '４月２３日', 'name': '春祭', 'month': 4},
            {'date_str': '１０月(体育の日)', 'name': '大祭', 'month': 10},
        ],
    ),
    # TC4: 「に近い◯曜日」修飾（複数ブロック）
    (
        '３月２０日に近い土曜日：御日待祭１０月第２土・日曜日：秋季例祭１月１日：元旦祭',
        [
            {'date_str': '３月２０日に近い土曜日', 'name': '御日待祭', 'month': 3},
            {'date_str': '１０月第２土・日曜日', 'name': '秋季例祭', 'month': 10},
            {'date_str': '１月１日', 'name': '元旦祭', 'month': 1},
        ],
    ),
    # TC5: 月+祝日名のみ（日付数字なし）
    (
        '５月第３土曜日・日曜日：春祭７月海の日：夏祭１０月第３日曜日：例祭',
        [
            {'date_str': '５月第３土曜日・日曜日', 'name': '春祭', 'month': 5},
            {'date_str': '７月海の日', 'name': '夏祭', 'month': 7},
            {'date_str': '１０月第３日曜日', 'name': '例祭', 'month': 10},
        ],
    ),
    # TC6: 祝日名 + 前後修飾（月表記なし、単発）
    (
        '秋分の日前後の日曜日：祈年祭',
        [
            {'date_str': '秋分の日前後の日曜日', 'name': '祈年祭'},
        ],
    ),
]

CASES_LINES = [
    # TC7: 「旧」+日付（暦なし）
    (
        '旧６月１５日　例大祭',
        [{'date_str': '旧６月１５日', 'name': '例大祭', 'month': 6}],
    ),
    # TC8: 「旧暦」+全角スペース+日付
    (
        '旧暦　６月１４日　例大祭',
        [{'date_str': '旧暦　６月１４日', 'name': '例大祭', 'month': 6}],
    ),
    # TC9: 祝日名+修飾語の連鎖（月表記なし）
    (
        '体育の日と前日の日曜日　例大祭',
        [{'date_str': '体育の日と前日の日曜日', 'name': '例大祭'}],
    ),
    # TC10: 名前が先、日付が後ろ（順序が逆）
    (
        '例祭　４月１０日',
        [{'date_str': '４月１０日', 'name': '例祭', 'month': 4}],
    ),
]


def run():
    failures = 0
    for i, (raw, expected) in enumerate(CASES_CONCAT, 1):
        got = parse_concat(raw)
        if got != expected:
            failures += 1
            print(f'FAIL concat TC{i}')
            print(f'  raw:      {raw!r}')
            print(f'  expected: {expected!r}')
            print(f'  got:      {got!r}')
    for i, (raw, expected) in enumerate(CASES_LINES, 7):
        got = parse_lines(raw)
        if got != expected:
            failures += 1
            print(f'FAIL lines TC{i}')
            print(f'  raw:      {raw!r}')
            print(f'  expected: {expected!r}')
            print(f'  got:      {got!r}')

    total = len(CASES_CONCAT) + len(CASES_LINES)
    print(f'{total - failures}/{total} passed')
    return failures == 0


if __name__ == '__main__':
    import sys
    sys.exit(0 if run() else 1)
