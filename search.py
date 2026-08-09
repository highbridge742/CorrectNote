# CorrectNote — かな入力誤字補正メモ帳
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


def find_all(text, pattern):
    """一致する範囲を全て返す。[(開始, 終了), ...]"""
    out = []
    for m in pattern.finditer(text):
        # 長さ0の一致（^ や \b など）は無限に進まないよう飛ばす
        if m.end() == m.start():
            continue
        out.append((m.start(), m.end()))
    return out


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
    if regex:
        m = pattern.match(text, start, end)
        if m is None:
            # 範囲が一致しなくなっている場合は、そのまま入れる
            actual = replacement
        else:
            try:
                actual = m.expand(replacement)
            except re.error as e:
                raise SearchError(f'置換文字列が正しくありません:\n{e}')
    else:
        actual = replacement

    new_text = text[:start] + actual + text[end:]
    return new_text, start + len(actual)


def replace_all(text, pattern, replacement, regex=False):
    """
    全ての一致を置き換える。

    戻り値: (置換後のテキスト, 置換した件数)
    """
    spans = find_all(text, pattern)
    if not spans:
        return text, 0

    # 後ろから置き換える。前から進めると、置換で長さが変わったときに
    # 以降の位置が全部ずれてしまうため。
    out = text
    for start, end in reversed(spans):
        out, _ = replace_one(out, pattern, (start, end), replacement,
                             regex=regex)
    return out, len(spans)


def count_matches(text, pattern):
    return len(find_all(text, pattern))
