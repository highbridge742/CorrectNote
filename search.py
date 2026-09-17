# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
検索と置換。Windows 11 のメモ帳の機能を目安にする。

  - 検索: 次を検索／前を検索、大文字小文字の区別、
          単語単位、折り返し（末尾まで行ったら先頭に戻る）
  - 置換: 置換して次へ、すべて置換
  - 正規表現に対応（メモ帳には無いが、こちらの要件）

テキストの走査だけを担い、画面の操作は行わない。
そうしておくと、tkinter の無い環境でも一致の計算を検証できる
（この開発環境には tkinter が入らないため、これは実際に重要）。

位置は「テキスト全体の先頭からの文字数」で扱う。
tkinter の "行.桁" との変換は app.py 側で行う。
"""

import re


class SearchError(ValueError):
    """正規表現が正しくないなど、利用者に伝えるべき誤り。"""


def build_pattern(query, regex=False, match_case=False, whole_word=False):
    """
    検索条件から、実際に使う正規表現を組み立てる。

    regex=False のときは、記号を文字そのものとして扱う
    （「.」や「*」を打っても、その文字を探す）。
    """
    if not query:
        raise SearchError('検索する文字列を入力してください。')

    body = query if regex else re.escape(query)

    if whole_word:
        # 日本語には単語の区切りが無いので \b は当てにならないが、
        # 英数字を含む語では期待どおりに働く。
        body = r'(?<!\w)' + body + r'(?!\w)'

    flags = 0 if match_case else re.IGNORECASE
    try:
        return re.compile(body, flags)
    except re.error as e:
        raise SearchError(f'正規表現が正しくありません:\n{e}')


def content_line_span(text):
    """First through last nonblank line, including their indentation.

    The outer blank lines are padding. Inner blank lines belong to the
    document. This definition is shared with the editor's Select All.
    """
    first = len(text) - len(text.lstrip())
    if first == len(text):
        return None
    last = len(text.rstrip())
    start = text.rfind('\n', 0, first) + 1
    end = text.find('\n', last)
    return start, len(text) if end < 0 else end


def _within_newline_scope(text, start, end, bounds):
    if '\n' not in text[start:end]:
        return True
    return bounds is not None and bounds[0] <= start < end <= bounds[1]


def match_allowed(text, start, end):
    """A match containing a newline must stay within the content lines."""
    return _within_newline_scope(text, start, end, content_line_span(text))


def _matches(text, pattern):
    bounds = content_line_span(text)
    for match in pattern.finditer(text):
        start, end = match.span()
        if start != end and _within_newline_scope(text, start, end, bounds):
            yield match


def find_all(text, pattern):
    """Return nonempty matching spans within the shared newline scope."""
    return list(iter_spans(text, pattern))


def iter_spans(text, pattern):
    """一覧表示でも、通常検索と同じ改行の境界を通す。"""
    for match in _matches(text, pattern):
        yield match.span()


def find_next(text, pattern, start, backwards=False, wrap=True):
    """
    次（または前）の一致を探す。

    start: 探し始める位置（文字数）。
        前方検索では、この位置以降で最初の一致。
        後方検索では、この位置より前で最後の一致。

    戻り値: (開始, 終了) または None
    """
    spans = find_all(text, pattern)
    if not spans:
        return None

    if backwards:
        before = [s for s in spans if s[1] <= start]
        if before:
            return before[-1]
        return spans[-1] if wrap else None

    after = [s for s in spans if s[0] >= start]
    if after:
        return after[0]
    return spans[0] if wrap else None


def replace_one(text, pattern, span, replacement, regex=False):
    """
    指定した範囲ひとつを置き換える。

    正規表現のときは \\1 のような後方参照を使えるようにする。
    そうでないときは、置換文字列を文字そのものとして扱う
    （「\\1」と打ったらその文字列がそのまま入る）。

    戻り値: (置換後のテキスト, 置換後の範囲の終わりの位置)
    """
    start, end = span
    if not match_allowed(text, start, end):
        return text, end
    match = pattern.match(text, start)
    if match is not None and match.end() != end:
        match = None
    actual = _replacement_value(match, replacement, regex)
    return text[:start] + actual + text[end:], start + len(actual)


def _replacement_value(match, replacement, regex):
    if not regex or match is None:
        return replacement
    try:
        return match.expand(replacement)
    except re.error as error:
        raise SearchError(f'置換文字列が正しくありません:\n{error}')


def replace_all(text, pattern, replacement, regex=False):
    """Replace matches from the original text and fixed content bounds."""
    pieces = []
    previous = count = 0
    for match in _matches(text, pattern):
        pieces.append(text[previous:match.start()])
        pieces.append(_replacement_value(match, replacement, regex))
        previous = match.end()
        count += 1
    if not count:
        return text, 0
    pieces.append(text[previous:])
    return ''.join(pieces), count


def count_matches(text, pattern):
    return len(find_all(text, pattern))
