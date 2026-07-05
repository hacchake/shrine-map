# -*- coding: utf-8 -*-
"""
festivals[].date_str（自然言語表記）を実際の暦日に解決するモジュール。
parse_festivals.pyの日付表現の語彙（祝日名・干支基準日・第N曜日・相対語等）を
土台に、名前/日付の「分離」ではなく「解決」を行う点が異なる。

用途: UIの日付範囲フィルタ（index.htmlのJS版はこのロジックを移植したもの）。
祭りは毎年同じ時期に繰り返される前提で、年をまたいだ絶対日付には対応しない
（resolve_festival_date(festival, year)で「その年に何回・いつ開催されるか」を
求め、範囲判定側で複数年をまたいで呼び出す）。

対応方針:
  - 固定日・第N曜日・最終曜日・期間（範囲）・毎月（複数曜日可）・祝日基準日は
    具体的な暦日（またはその年の全該当日）まで解決する
  - 旧暦・干支基準日（初午・巳の日等）は変換が複雑すぎるため月単位の
    フォールバックに留める（月の1日〜末日を「範囲」として返す）
  - 完全にパースできない場合、date_str中に月の手がかりが無くても
    festival['month']フィールドがあればそれで月単位フォールバックする
  - 上記すべてが失敗したら空リスト（判定不能）を返す
"""
import re
import datetime
import calendar

FULLWIDTH_DIGITS = str.maketrans('０１２３４５６７８９', '0123456789')
KANJI_DIGIT = {'〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
WEEKDAY_MAP = {'月': 0, '火': 1, '水': 2, '木': 3, '金': 4, '土': 5, '日': 6}

HOLIDAY_FIXED = {
    '元日': (1, 1),
    '建国記念の日': (2, 11),
    '昭和の日': (4, 29),
    '山の日': (8, 11),
    '文化の日': (11, 3),
    '勤労感謝の日': (11, 23),
}
# ハッピーマンデー制度の祝日（第何週の月曜か）
HOLIDAY_NTH_MONDAY = {
    '成人の日': (1, 2),
    '海の日': (7, 3),
    '敬老の日': (9, 3),
    '体育の日': (10, 2),
    'スポーツの日': (10, 2),
}


def _equinox_day(year, kind):
    """春分の日・秋分の日は天文計算が必要な移動祝日。1980〜2099年で有効な
    近似式（国立天文台の計算に準拠した一般的な近似）を用いる。旅行用途の
    目安であり法的な正確性は求めない"""
    base = 20.8431 if kind == 'spring' else 23.2488
    return int(base + 0.242194 * (year - 1980) - (year - 1980) // 4)


def _kanji_to_int(s):
    if not s:
        return None
    if s == '十':
        return 10
    idx = s.find('十')
    if idx < 0:
        return KANJI_DIGIT.get(s) if len(s) == 1 else None
    tens = KANJI_DIGIT.get(s[0], 1) if idx > 0 else 1
    ones_str = s[idx + 1:]
    ones = KANJI_DIGIT.get(ones_str, 0) if ones_str else 0
    if ones_str and ones_str not in KANJI_DIGIT:
        return None
    return tens * 10 + ones


_KANJI_NUM_RE = re.compile(r'[一二三四五六七八九十〇]+')


def _normalize_digits(text):
    """全角数字→半角、月/日/曜日の直前にある漢数字→算用数字"""
    text = text.translate(FULLWIDTH_DIGITS)

    def repl(m):
        n = _kanji_to_int(m.group())
        return str(n) if n is not None else m.group()

    # 「月」「日」の直前の漢数字だけを変換対象にする（名前中の漢数字巻き込み防止）
    text = re.sub(r'[一二三四五六七八九十〇]+(?=月)', repl, text)
    text = re.sub(r'[一二三四五六七八九十〇]+(?=日)', repl, text)
    return text


def _month_range(year, month):
    last = calendar.monthrange(year, month)[1]
    return (datetime.date(year, month, 1), datetime.date(year, month, last))


def _nth_weekday(year, month, nth, weekday):
    """nth: 1-5の整数 or 'last'。weekday: Pythonの曜日番号(月=0..日=6)"""
    if nth == 'last':
        d = datetime.date(year, month, calendar.monthrange(year, month)[1])
        while d.weekday() != weekday:
            d -= datetime.timedelta(days=1)
        return d
    d = datetime.date(year, month, 1)
    count = 0
    while d.month == month:
        if d.weekday() == weekday:
            count += 1
            if count == nth:
                return d
        d += datetime.timedelta(days=1)
    return None


NTH_TOKEN_RE = re.compile(r'第?(\d+|最終)')
WEEKDAY_TOKEN_RE = re.compile(r'(土|日|月|火|水|木|金)(?:曜日?)?')
RANGE_RE = re.compile(r'(\d+)日?[〜～\-](\d+)日')
FIXED_DAY_RE = re.compile(r'^(\d+)日')
AMBIGUOUS_RE = re.compile(r'(上旬|中旬|下旬)')


def _resolve_nth_weekday_group(rest, year, month):
    """「第2日曜日」「第1、第3日曜日」（複数nth・単一曜日）「第1土曜・日曜」
    （単一nth・複数曜日）等を解決する。曖昧な組み合わせは総当たりで解決し、
    取りこぼしより出しすぎを優先する"""
    if not re.match(r'^(第|最終|土|日|月|火|水|木|金)', rest):
        return None
    prefix = rest[:20]  # 末尾の祭典名等を巻き込まないよう先頭の短い範囲だけ見る
    nths = [('last' if x == '最終' else int(x)) for x in NTH_TOKEN_RE.findall(prefix)]
    weekdays = [WEEKDAY_MAP[w] for w in WEEKDAY_TOKEN_RE.findall(prefix)]
    if not nths or not weekdays:
        return None
    if len(nths) == 1:
        pairs = [(nths[0], wd) for wd in weekdays]
    elif len(weekdays) == 1:
        pairs = [(n, weekdays[0]) for n in nths]
    elif len(nths) == len(weekdays):
        pairs = list(zip(nths, weekdays))
    else:
        pairs = [(n, wd) for n in nths for wd in weekdays]
    results = []
    seen = set()
    for nth, wd in pairs:
        d = _nth_weekday(year, month, nth, wd)
        if d and d not in seen:
            seen.add(d)
            results.append((d, d))
    return results or None


def _resolve_in_month(rest, year, month):
    """月名を取り除いた残りテキストから、その月内の該当日を解決する。
    解決できなければNoneを返す（呼び出し側が月単位フォールバックする）"""
    r = _resolve_nth_weekday_group(rest, year, month)
    if r:
        return r

    # 期間（日〜日）
    m = RANGE_RE.match(rest)
    if m:
        d1, d2 = int(m.group(1)), int(m.group(2))
        try:
            return [(datetime.date(year, month, d1), datetime.date(year, month, d2))]
        except ValueError:
            return None

    # 固定日
    m = FIXED_DAY_RE.match(rest)
    if m:
        d1 = int(m.group(1))
        try:
            d = datetime.date(year, month, d1)
            return [(d, d)]
        except ValueError:
            return None

    # 上旬・中旬・下旬
    m = AMBIGUOUS_RE.match(rest)
    if m:
        last = calendar.monthrange(year, month)[1]
        ranges = {'上旬': (1, 10), '中旬': (11, 20), '下旬': (21, last)}
        s, e = ranges[m.group(1)]
        return [(datetime.date(year, month, s), datetime.date(year, month, min(e, last)))]

    return None


def _resolve_holiday(text, year):
    for name, (month, day) in HOLIDAY_FIXED.items():
        if name in text:
            d = datetime.date(year, month, day)
            return [(d, d)]
    for name, (month, nth) in HOLIDAY_NTH_MONDAY.items():
        if name in text:
            d = _nth_weekday(year, month, nth, 0)
            if d:
                return [(d, d)]
    if '春分の日' in text:
        d = datetime.date(year, 3, _equinox_day(year, 'spring'))
        return [(d, d)]
    if '秋分の日' in text:
        d = datetime.date(year, 9, _equinox_day(year, 'autumn'))
        return [(d, d)]
    return None


LUNAR_RE = re.compile(r'旧暦|旧')
MONTH_RE = re.compile(r'(\d+)月')
SLASH_DATE_RE = re.compile(r'(\d{1,2})/(\d{1,2})')


def resolve_festival_date(festival, year):
    """festival(dict: date_str/month等を含む)がyear年に何回・いつ開催されるかを
    [(開始日, 終了日), ...] のリストで返す。判定不能なら空リスト"""
    date_str = (festival.get('date_str') or '').strip()
    month_hint = festival.get('month')

    if not date_str:
        if month_hint:
            return [_month_range(year, month_hint)]
        return []

    text = _normalize_digits(date_str)

    # 旧暦/旧: 変換せず月単位フォールバック（月が取れなければ判定不能）。
    # 「旧6月15日」のような漢字表記だけでなく「旧 06/15」のようなスラッシュ
    # 表記の月も手がかりにする
    if LUNAR_RE.search(text):
        m = MONTH_RE.search(text) or SLASH_DATE_RE.search(text)
        if m:
            return [_month_range(year, int(m.group(1)))]
        if month_hint:
            return [_month_range(year, month_hint)]
        return []

    # 毎月: 日付ルールを1〜12月それぞれに適用
    if text.startswith('毎月'):
        rest = text[len('毎月'):]
        occurrences = []
        for m in range(1, 13):
            r = _resolve_in_month(rest, year, m)
            if r:
                occurrences.extend(r)
        if occurrences:
            return occurrences
        if month_hint:
            return [_month_range(year, month_hint)]
        return []

    # 祝日名（例:「10月体育の日」「体育の日」）は自身の月・日を規定するため、
    # 冒頭に月の数字が併記されていてもそちらより優先する
    holiday_result = _resolve_holiday(text, year)
    if holiday_result:
        return holiday_result

    # 通常: 先頭付近の「N月」を手がかりに、その月内の日付ルールを解決
    m = MONTH_RE.search(text)
    if m:
        month = int(m.group(1))
        if not (1 <= month <= 12):
            month = None
        if month:
            rest = text[m.end():]
            result = _resolve_in_month(rest, year, month)
            if result:
                return result
            # 月は分かったが日付ルールが解決できない → 月単位フォールバック
            return [_month_range(year, month)]

    # 「10/18」のようなスラッシュ区切り（月の漢字が無い）表記。複数あれば
    # それぞれ固定日として扱う
    slash_matches = list(SLASH_DATE_RE.finditer(text))
    if slash_matches:
        results = []
        for sm in slash_matches:
            month, day = int(sm.group(1)), int(sm.group(2))
            if 1 <= month <= 12:
                try:
                    d = datetime.date(year, month, day)
                    results.append((d, d))
                except ValueError:
                    pass
        if results:
            return results

    # 完全にパース不能。festival['month']があれば月単位フォールバック
    if month_hint:
        return [_month_range(year, month_hint)]
    return []
