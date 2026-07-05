# -*- coding: utf-8 -*-
"""
神社庁サイトの「主な祭典」欄の生テキストから festivals=[{name,date_str,month}] を
抽出する共通パーサー。okayama_jinjacho型（区切り文字なしで複数「日付：名前」が連結）と
ehime_jinjacho型（改行区切りで各行が「日付　名前」、まれに「名前　日付」の逆順）の
どちらの生成元でも使う。

背景: 2026-07-05、check_data.pyの8_祭典ズレで新スクレイパー(scrape_okayama.py/
scrape_ehime.py)の日付パーサーがなお312件で祭典名/日付を取り違えることが判明。
原因は「前後」「に近い日曜日」「体育の日」等の修飾語・祝日名・干支基準日、
「５、６日」のような複数日表記、「旧暦」等の日付が、当時の素朴な文字クラス方式の
アンカー正規表現でカバーしきれていなかったこと。本モジュールはこれらの日付表現を
明示的な部品(COMPONENT)の組み合わせとして認識するよう拡張したもの。
"""
import re

FULLWIDTH_DIGITS = str.maketrans('０１２３４５６７８９', '0123456789')

SEP_STRIP_CHARS = '　、：, 　'

HOLIDAY_WORDS = (
    '体育の日|海の日|成人の日|文化の日|国民の休日|敬老の日|建国記念の日|'
    '春分の日|秋分の日|山の日|みどりの日|昭和の日|勤労感謝の日|元日'
)
ZODIAC_WORDS = (
    '初午の日|初午|巳の日|初卯の日|戌の日|社日|立春|節分|土用の丑の日|土用'
)
# 「末日」は「末日曜日(=末の日曜日)」の一部を誤って食わないよう、直後が「曜」の
# 場合は末日として確定させない（否定先読み）
RELATIVE_WORDS = (
    r'最終|最後の|最初の|初旬|中旬|下旬|上旬|末ごろ|中頃|末日(?!曜)|末|頃|中(?!旬|頃)'
)

# 各COMPONENTは text[pos:] に対して ^ アンカーでマッチさせる（re.match(text, pos)）
COMPONENT_PATTERNS = [
    # 月＋日（複数日は「、」「．」「.」「／」「/」「・」「〜」「～」区切り、または区切りなしで連結。
    # 末尾に時刻「10：00」が付くこともある）
    re.compile(
        r'[0-9０-９一二三四五六七八九十]+月[\s　]*'
        r'(?:[0-9０-９一二三四五六七八九十]+日?)?'
        r'(?:[、．.／/・]?[0-9０-９一二三四五六七八九十]+日)*'
        r'(?:[〜～][0-9０-９一二三四五六七八九十]+日?)?'
        r'(?:[\s　]*[0-9０-９]{1,2}[:：][0-9０-９]{2})?'
    ),
    # 括弧書きの祝日名（例: (体育の日)）
    re.compile(r'[（(](?:' + HOLIDAY_WORDS + r')[）)]'),
    # 祝日名
    re.compile(HOLIDAY_WORDS),
    # 干支・雑節基準日
    re.compile(ZODIAC_WORDS),
    # 第N◯曜日、◯曜日・◯曜日、◯・◯曜日 等（第の後ろは全角/半角数字か漢数字、無い場合もある。
    # 「土曜日・日曜日」（各曜に曜日が付く）と「土・日曜日」（末尾だけ曜日が付く）の
    # 両方に対応するため、末尾以外の「曜日」は省略可、最後の要素だけ必須にする）
    re.compile(
        r'第?[0-9０-９一二三四五六七八九]*[\s]*'
        r'(?:(?:土|日|月|火|水|木|金)(?:曜日)?[・、.．][\s]*)*'
        r'(?:土|日|月|火|水|木|金)曜日?'
    ),
    # 上旬・中旬・下旬・末・頃 等の相対語
    re.compile(RELATIVE_WORDS),
]

# 直前の部品にだけ続けて許す「連結語」。単独では日付とみなさない。
# 「旧暦」「旧」も、直後に本当の日付が続く場合のみ日付の一部として認める
# （「旧例祭日の10月15日」のように「旧」が名詞にかかる用法と区別するため）
CONNECTOR_PATTERNS = [
    re.compile(r'旧暦[\s　]*|旧[\s　]*'),
    re.compile(r'又は|または|の|と|、|・'),
]

MODIFIER_PATTERNS = [
    re.compile(r'に近い(?:土|日|金|月|火|水|木)曜日'),
    re.compile(r'前後の(?:土|日)曜日'),
    re.compile(r'前後'),
    re.compile(r'と前日'),
    re.compile(r'と翌日'),
    re.compile(r'の前々日から[0-9０-９]+日間'),
    re.compile(r'の前日'),
    re.compile(r'前日'),
    re.compile(r'翌日'),
    re.compile(r'翌(?:土|日|月|火|水|木|金)曜日'),
    re.compile(r'から[0-9０-９]+日間'),
    re.compile(r'[（(](?:不定|随時)[）)]'),
    # 「（第２日曜日の土日）」等、実施日が近い週末にずれる場合の補足括弧
    re.compile(r'[（(]第?[0-9０-９一二三四五六七八九]*(?:土|日|月|火|水|木|金)曜日?の土日[）)]'),
]

ALL_LEADING_PATTERNS = COMPONENT_PATTERNS + MODIFIER_PATTERNS


def _match_longest(patterns, text, pos):
    best_end = pos
    for pat in patterns:
        m = pat.match(text, pos)
        if m and m.end() > best_end:
            best_end = m.end()
    return best_end


PAREN_OPEN = {'（': '）', '(': ')'}


def _consume_paren_date(text, pos):
    """位置posが「（」「(」なら、閉じ括弧までの中身が丸ごと日付表現として
    解釈できる場合に限り括弧ごと消費する（例:「１０月中頃（旧10月15日）」の
    「（旧10月15日）」を補足日付として扱う）"""
    if pos >= len(text) or text[pos] not in PAREN_OPEN:
        return pos
    close = PAREN_OPEN[text[pos]]
    end = text.find(close, pos + 1)
    if end == -1:
        return pos
    inner = text[pos + 1:end]
    if inner and consume_date(inner, 0) == len(inner):
        return end + 1
    return pos


def consume_date(text, pos=0):
    """text[pos:]の先頭から日付表現を可能な限り貪欲に消費し、消費後の位置を返す。
    日付として何も消費できなければpos自身を返す"""
    cur = pos
    while True:
        nxt = _match_longest(ALL_LEADING_PATTERNS, text, cur)
        if nxt > cur:
            cur = nxt
            continue
        nxt = _consume_paren_date(text, cur)
        if nxt > cur:
            cur = nxt
            continue
        # 連結語を挟んだ先に日付部品が続く場合のみ連結語ごと消費する
        advanced = False
        for conn in CONNECTOR_PATTERNS:
            cm = conn.match(text, cur)
            if not cm:
                continue
            nxt2 = _match_longest(ALL_LEADING_PATTERNS, text, cm.end())
            if nxt2 > cm.end():
                cur = nxt2
                advanced = True
                break
        if not advanced:
            break
    return cur


def parse_month_jp(text):
    text = (text or '').translate(FULLWIDTH_DIGITS)
    m = re.search(r'(\d+)月', text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return n
    return None


TRAILING_PAREN = re.compile(r'[（(]([^（）()]*)[）)]$')


def _split_trailing_date_paren(name, date_str):
    """nameの末尾に「（第３日曜日）」のような、日付表現そのものだけで構成された
    括弧注記が残っている場合、それをdate_str側へ移す（例: ehime_jinjachoで
    「日付　名前　（補足日付）」の3トークン構成の行に対応するため）"""
    m = TRAILING_PAREN.search(name)
    if not m:
        return name, date_str
    inner = m.group(1)
    end = consume_date(inner, 0)
    if end == len(inner) and end > 0:
        new_name = name[:m.start()]
        new_date = (date_str + '　' + m.group(0)) if date_str else m.group(0)
        return new_name, new_date
    return name, date_str


def _make_entry(date_str, name):
    name, date_str = _split_trailing_date_paren(name.strip(SEP_STRIP_CHARS), date_str)
    name = name.strip(SEP_STRIP_CHARS) or '祭礼'
    date_str = date_str.strip(SEP_STRIP_CHARS)
    entry = {'date_str': date_str, 'name': name}
    month = parse_month_jp(date_str)
    if month:
        entry['month'] = month
    return entry


def parse_concat(raw):
    """okayama_jinjacho型: 区切り文字なしで「日付：名前」が連結された1文字列。
    日付表現の出現位置をアンカーにブロック分割する"""
    raw = (raw or '').strip()
    if not raw:
        return []
    # 日付表現の開始位置をすべて洗い出す
    starts = []
    pos = 0
    while pos < len(raw):
        end = consume_date(raw, pos)
        if end > pos:
            starts.append((pos, end))
            pos = end
        else:
            pos += 1
    if not starts:
        return [{'date_str': '', 'name': raw}]

    results = []
    for i, (s, e) in enumerate(starts):
        date_str = raw[s:e]
        name_end = starts[i + 1][0] if i + 1 < len(starts) else len(raw)
        name = raw[e:name_end]
        results.append(_make_entry(date_str, name))
    return results


def parse_lines(raw):
    """ehime_jinjacho型: 改行区切りで各行が基本「日付　名前」だが、まれに
    「名前　日付」の逆順もある"""
    raw = (raw or '').strip()
    if not raw:
        return []
    results = []
    for line in raw.split('\n'):
        line = line.strip()
        if not line:
            continue
        end = consume_date(line, 0)
        if end > 0:
            results.append(_make_entry(line[:end], line[end:]))
            continue
        # 先頭からは日付が見つからない場合、行内のどこかに日付表現が
        # 現れないか探し、見つかれば前後を入れ替える（名前が先・日付が後の逆順）
        found = None
        for i in range(len(line)):
            e = consume_date(line, i)
            if e > i:
                found = (i, e)
                break
        if found:
            s, e = found
            name = (line[:s] + line[e:]).strip()
            results.append(_make_entry(line[s:e], name))
        else:
            results.append({'date_str': '', 'name': line})
    return results
