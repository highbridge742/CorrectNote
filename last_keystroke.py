# -*- coding: utf-8 -*-
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

"""**紫が残った短いかなを、1打だけ戻して読み直す**（2026-10-16）。

補正を全部通したあとに、短いかなの紫（6字まで）が残った行だけを見る。
紫のまわりで、かなキーの1打の誤り（隣のキー・1字抜け・隣どうしの
入れ替わり）を1つだけ戻した行を作り、**補正の入口をそのまま通し直す**。
通し直した行に紫も「迷い」も残らないものだけを答えの候補にする。

    にもつがとどはました → 荷物が届きました（は → き・隣のキー）
    みちにまよました     → 道にまよいました（い の抜け）
    かぜをひいしてまいました → かぜをひいてしまいました（入れ替わり）

紫が出ているのに直らなかった誤字を測ると、正解の1字抜けは候補に
出ていても、補正の途中の門（述語を守る門など）で落ちていた。門は
正しい文を守るためのものなので緩めない。代わりに、**直した行を丸ごと
読み直して、何の印も残らない**ことを証拠にする（濁点・伸ばし棒の
戻しと同じ形）。最後に置く直しは、ほかの直しと同じ共通の最終検査を
通す（2026-10-16 の通しの試験で、ここを迂回した直し過ぎが出た）。

採る条件（どれか1つでも欠けたら元の結果のまま）:

- かな入力（`input_method == 'kana'`）。表はかなキーの配列
  （`kana_layout`。選んだかな配列に従う）
- 紫が全部、6字までのひらがなだけ（ー を含む紫は見ない。JIS かなでは
  ー は遠いキーで、伸ばし棒の打ち間違いは設計40 の道が受け持つ）。
  直すのは最初の紫。行末の同じかなの2つ続きが紫の中にあれば見ない
  （重なり打ちの直しは切ってある）
- 戻す場所は紫の中（入れ替わりは紫の端の1字まで）。原文で3字以上の
  語として辞書に在る並びの内側は触らない。1字の足しは、足した字が
  動詞・助動詞の中に入るときだけ
- 並びの自然さ（`morphology.path_cost`）の下がり幅と、読みの並び
  （`yomigram`）の上がり幅を合わせた点で順に試す。いちばん良い候補が
  点 4000（1字の足しは 6000）以上、並びの自然さだけで 2000 以上、
  読みの並びが元より 1.0 を超えて悪くならず、次に良い候補と 2000 以上
  離れていること
- 利用者の判断（守る語・取り下げた補正・引用など保護した範囲）に
  触れないこと
- 紫の外に、同じ文（句点・かぎ括弧・タブで区切る）の語が残っていること。
  文が丸ごと紫なら、読み直しが通ってもつなぐ相手が無く証拠にならない
- 戻した場所か、同じ文のその後ろに述語（動詞・形容詞・助動詞）が
  あること。述語の無い言いさしはどの読みでも紫が付かない
- 小書きと並の大きさの同じ字（ぃ と い）は戻さない（書き方の好み）
- 置く直しは、ほかの直しと同じ共通の最終検査（`_check_replacement`）を
  元の行の上で通ること。読み直した行の中の検査は直した行が相手なので、
  これを欠くと守りの門（目的語と述語の門など）を素通りする

読み直しは、紫の消える1つ目が見つかるまで3つ、2つ目を探す分を含めて
5つまで（1回はふつう0.2〜3秒）。点が足りない時点・1つ目と2000以上
離れた時点でやめるので、正しい文に紫が付いている行（いちばん多い）は
読み直しをせずに終わる。
"""

from contextvars import ContextVar
from functools import wraps
import inspect

# 読み直しの中でさらに読み直さない
_ACTIVE = ContextVar('correctnote_last_keystroke', default=False)

MAX_SPAN = 6
MAX_TRIALS = 5        # 読み直しの数の上限（2つ目を探す分も含む）
FIRST_TRIALS = 3      # 1つ目が見つかるまでの上限
NEED_SUB = 4000
NEED_INSERT = 6000
MIN_PATH_GAIN = 2000
MIN_YOMI_GAIN = -1.0
MARGIN = 2000
YOMI_WEIGHT = 1000
KEY_DISTANCE = 1.05

_SMALL = 'ぁぃぅぇぉゃゅょっゎ'
_LARGE = 'あいうえおやゆよつわ'
# 文の区切り（この中に、直した語と述語がそろっていること）
_CLAUSE_END = '。．.！？!?」』）)］]\t\n'
_CLAUSE_START = '。．.！？!?「『（(［[\t\n'
_I_ROW = 'きぎしじちぢにひびぴみりい'


def _hira(ch):
    return 'ぁ' <= ch <= 'ゖ' or ch == 'ー'


def _kana(ch):
    """戻してよい字（ひらがな）。ー は遠いキーで、伸ばし棒の打ち間違いは別の道。"""
    return 'ぁ' <= ch <= 'ゖ'


def _plausible(text, lo, hi):
    """小書き・ん・ー が、置けない場所に立っていないか。"""
    for i in range(max(0, lo - 1), min(len(text), hi + 2)):
        ch = text[i]
        prev = text[i - 1] if i else ''
        if ch in _SMALL:
            if not prev or not _hira(prev) or prev in _SMALL + 'んー':
                return False
            if ch in 'ゃゅょ' and prev not in _I_ROW:
                return False
        if ch in 'んー' and (not prev or not _hira(prev)):
            return False
    return True


def _same_kana_size(a, b):
    """小書きと並の大きさの同じ字（ぃ と い）。

    かなキーでは同じキーで、どちらで書くかは書き方の好み（くださぃ・
    しゅごぃ）。紫でも、ここでは打ち違いとして戻さない。
    """
    return any({a, b} == {x, y} for x, y in zip(_SMALL, _LARGE))


def _keys():
    import kana_layout as kl
    return [ch for ch in kl.KANA_POSITIONS
            if len(ch) == 1 and 'ぁ' <= ch <= 'ゖ']


def candidates(line, start, end):
    """紫 [start, end) のまわりで1打を戻した行 → (種類, 位置)。"""
    import kana_layout as kl
    keys = _keys()
    lo = max(0, start - 1)
    hi = min(len(line), end + 1)
    out = {}
    for i in range(lo, hi):
        if not _kana(line[i]):
            continue
        for ch in keys:
            if (ch != line[i] and not _same_kana_size(ch, line[i])
                    and kl.kana_key_distance(line[i], ch) <= KEY_DISTANCE):
                text = line[:i] + ch + line[i + 1:]
                if _plausible(text, i, i + 1):
                    out.setdefault(text, ('sub', i))
        if i + 1 < hi and _kana(line[i + 1]) and line[i] != line[i + 1]:
            text = line[:i] + line[i + 1] + line[i] + line[i + 2:]
            if _plausible(text, i, i + 2):
                out.setdefault(text, ('swap', i))
    for i in range(lo, hi + 1):
        if not ((i < len(line) and _kana(line[i])) or (i > 0 and _kana(line[i - 1]))):
            continue
        for ch in keys:
            text = line[:i] + ch + line[i:]
            if _plausible(text, i, i + 1):
                out.setdefault(text, ('ins', i))
    out.pop(line, None)
    return out


def _inside_position(op, i, start, end):
    if op == 'ins':
        return start <= i <= end
    if op == 'sub':
        return start <= i < end
    return start <= i and i + 2 <= end + 1


def _edit_range(op, i):
    return (i, i) if op == 'ins' else (i, i + 1) if op == 'sub' else (i, i + 2)


def _inside_word(line, lo, hi, dict_index):
    """戻す場所が、原文で3字以上の辞書の語（かなだけ）の内側か。"""
    n = len(line)
    for s in range(max(0, lo - 8), lo + 1):
        for e in range(max(hi, s + 3), min(n, s + 10) + 1):
            if lo == hi:
                if not s < lo < e:
                    continue
            elif not (s <= lo and hi <= e):
                continue
            word = line[s:e]
            if all(_hira(ch) for ch in word) and dict_index.is_world_reading(word):
                return True
    return False


def _verb_insert(text, i):
    from morphology import tokenize
    for t in tokenize(text):
        if t.start <= i < t.end:
            return bool(t.has_reading) and t.pos in ('動詞', '助動詞')
    return False


def _protected(line, decisions):
    from literal_examples import protected_ranges
    ranges = list(protected_ranges(line))
    listed = getattr(decisions, 'protected_list', None)
    if callable(listed):
        for entry in listed():
            word = entry.get('word', '')
            if not isinstance(word, str) or len(word) < 2:
                continue
            pos = line.find(word)
            while pos >= 0:
                ranges.append((pos, pos + len(word)))
                pos = line.find(word, pos + 1)
    return ranges


def _doubled_tail(line, odd):
    """行末の同じかなの2つ続き（`くださいい`・`ますす`）が紫の中にあるか。

    行末で同じキーを2度押すのはよくある誤りで、それは1字を消せば直る。
    重なり打ちの直しは切ってある（決まり）ので、ここでも別の字に
    置き換えて読ませない（`ますす → ますか` のように意味が変わる）。
    """
    end = len(line.rstrip(' 　。、．，！？!?…'))
    if end < 2 or line[end - 1] != line[end - 2] or not _kana(line[end - 1]):
        return False
    return any(a < end and end - 1 < b for a, b in odd)


def _clause(line, pos):
    """`pos` を含む文（句点・かぎ括弧・タブで区切る）の [始まり, 終わり)。"""
    lo = pos
    while lo > 0 and line[lo - 1] not in _CLAUSE_START:
        lo -= 1
    hi = pos
    while hi < len(line) and line[hi] not in _CLAUSE_END:
        hi += 1
    return lo, hi


def _anchored(line, odd):
    """紫の外に、同じ文の語が残っているか。

    読み直した行に紫が残らないことは、紫の部分がまわりの読めた語と
    つながることの証拠になる。文が丸ごと紫（`こさせう。`・語の並びごと
    崩れた文）なら、つなげる相手が無く、1打を戻しても証拠にならない。
    """
    start = odd[0][0]
    lo, hi = _clause(line, start)
    for i in range(lo, hi):
        if any(a <= i < b for a, b in odd):
            continue
        ch = line[i]
        if ch.isalnum() and not ch.isspace():
            return True
    return False


def _predicate_follows(text, lo, hi):
    """戻した場所 [lo, hi)（戻した行の上）か、同じ文のその後ろに述語があるか。

    述語の無い言いさし（`そのようにも、`・かぎ括弧の中の `このようにも`）は
    どの読みでも紫が付かないので、読み直しが通っても証拠にならない
    （補正本体も、続く述語が無ければ直さない）。
    """
    from morphology import tokenize
    _lo, end = _clause(text, max(lo, hi - 1) if hi > lo else lo)
    for t in tokenize(text):
        if t.end <= lo or t.start >= end:
            continue
        if t.has_reading and t.pos in ('動詞', '形容詞', '助動詞'):
            return True
    return False


def _clean(result):
    return not (result.get('odd_spans') or result.get('unsure_spans'))


def repair(line, result, retry, input_method='kana', decisions=None,
           dict_index=None):
    """
    `result`（`line` の補正結果）に短いかなの紫が残っていれば、1打を
    戻した行を `retry(行)` で読み直し、採れるものがあれば
    `(戻した行, 読み直した結果, (始まり, 終わり, 戻した字))` を返す
    （位置は元の行の上）。無ければ None。
    """
    if input_method != 'kana' or dict_index is None or not line:
        return None
    odd = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
    if not odd:
        return None
    for a, b in odd:
        if not (0 <= a < b <= len(line) and b - a <= MAX_SPAN
                and all(_kana(ch) for ch in line[a:b])):
            return None
    start, end = odd[0]
    if _doubled_tail(line, odd):
        return None
    if not _anchored(line, odd):
        return None
    import morphology
    import yomigram
    base = morphology.path_cost(line)
    if base is None:
        return None
    guard = _protected(line, decisions)
    if any(lo < end + 1 and start - 1 < hi for lo, hi in guard):
        return None
    yomi0 = yomigram.logp_parts(line)[0]
    pool = []
    for text, (op, i) in candidates(line, start, end).items():
        if not _inside_position(op, i, start, end):
            continue
        cost = morphology.path_cost(text)
        if cost is None:
            continue
        gain = base - cost
        yomi = yomigram.logp_parts(text)[0] - yomi0
        pool.append((gain + YOMI_WEIGHT * yomi, gain, yomi, text, op, i))
    pool.sort(key=lambda row: (-row[0], row[3]))
    found = []
    trials = 0
    for score, gain, yomi, text, op, i in pool:
        if not found and score < NEED_SUB:
            break
        if found and score < found[0][0] - MARGIN:
            break
        if op == 'ins' and not _verb_insert(text, i):
            continue
        if _inside_word(line, *_edit_range(op, i), dict_index):
            continue
        lo, hi = _edit_range(op, i)
        if not _predicate_follows(text, lo, hi + (op == 'ins')):
            continue
        trials += 1
        if trials > (MAX_TRIALS if found else FIRST_TRIALS):
            break
        got = retry(text)
        if got and _clean(got):
            found.append((score, gain, yomi, text, op, got, i))
            if len(found) >= 2:
                break
    if not found:
        return None
    score, gain, yomi, text, op, got, i = found[0]
    if score < (NEED_INSERT if op == 'ins' else NEED_SUB):
        return None
    if gain < MIN_PATH_GAIN or yomi < MIN_YOMI_GAIN:
        return None
    if len(found) > 1 and score - found[1][0] < MARGIN:
        return None
    lo, hi = _edit_range(op, i)
    return text, got, (lo, hi, text[lo:hi + (op == 'ins')])


def with_last_keystroke_repair(fn):
    """`corrector.correct_line` の外側に付ける（読み直しは入口を通す）。"""
    signature = inspect.signature(fn)

    @wraps(fn)
    def wrapped(line, *args, **kwargs):
        import corrector
        root = corrector._CORRECTION_SOURCE.get() is None and not _ACTIVE.get()
        result = fn(line, *args, **kwargs)
        if not root or not isinstance(result, dict) or result.get('original', line) != line:
            return result
        try:
            bound = signature.bind(line, *args, **kwargs)
            bound.apply_defaults()
            options = bound.arguments
        except TypeError:
            return result
        decisions = options.get('decisions')

        def retry(text):
            token = _ACTIVE.set(True)
            try:
                return corrector.correct_line(text, *args, **kwargs)
            finally:
                _ACTIVE.reset(token)

        found = repair(line, result, retry,
                       input_method=options.get('input_method', 'kana'),
                       decisions=decisions,
                       dict_index=options.get('dict_index'))
        if not found:
            return result
        text, inner, (lo, hi, face) = found
        corrected = inner.get('corrected', text)
        # 入れ替わりを「足し」と「消し」の2つに見せない
        pieces = corrector._display_spans_for_reanalysis(
            line, corrected, [(lo, hi, face, 'かな入力')])
        # 置く直しは、ほかの直しと同じ共通の最終検査を通す（読み直した行の
        # 中の検査は直した行が相手で、元の行からの直しは見ていない。
        # 適用点を1つでも迂回させると、守りの門を素通りする）
        for i1, i2, j1, j2 in pieces:
            item = (i1, i2, corrected[j1:j2], 'かな入力')
            accepted, _reason = corrector._check_replacement(
                line, item, options.get('store'), options.get('tokenize_fn'),
                options.get('dict_index'), decisions, conv_taken=((i1, i2),))
            if accepted is None or tuple(accepted[:3]) != item[:3]:
                return result
        blocks = getattr(decisions, 'blocks', None)
        if callable(blocks) and (blocks(line, corrected) or any(
                blocks(line[i1:i2], corrected[j1:j2]) for i1, i2, j1, j2 in pieces)):
            return result
        out = dict(result)
        out.update(
            corrected=corrected,
            changed=corrected != line,
            details=[(line[i1:i2], corrected[j1:j2], 'かな入力')
                     for i1, i2, j1, j2 in pieces],
            spans=[(j1, j2) for _i1, _i2, j1, j2 in pieces],
            original_spans=[(i1, i2) for i1, i2, _j1, _j2 in pieces],
            unsure_spans=[],
            odd_spans=[],
        )
        out.pop('_validated_corrected', None)
        out.pop('_validated_repair_ranges', None)
        # 「なぜ異様と見たか」は元の行の理由のまま（直した語の根拠に出る）
        return out
    return wrapped
