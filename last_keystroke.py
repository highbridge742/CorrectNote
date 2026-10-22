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
  （`kana_layout`。選んだかな配列に従う）。ローマ字入力（`'romaji'`）でも走る（2026-10-19）:
  戻しの候補はローマ字キーの隣（`corrector.adjacent_slip`）と、1打で消える字（ん・母音・っ）の抜け足し
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

MAX_SPAN = 8          # 紫の幅の上限（うちあせわ＋は の7字で入れ替わりが試されず 6→8・2026-10-19）
VOUCH_GAIN = 6000     # 行の費用がこれ以上下がる戻しは、文の組み立てが語の並びとして成り立つようになった形（ごさいます
                      # →ございます: 接頭詞＋名詞＋ます → 動詞＋ます）。読みの並びの表（yomigram）が ございます を低く
                      # 見ても、語の内側（ごさい＝五歳）でも採る。迷いだけの行にも使う（2026-10-19）
MAX_TRIALS = 5        # 読み直しの数の上限（2つ目を探す分も含む）
FIRST_TRIALS = 5      # 1つ目が見つかるまでの上限（3→5・2026-10-19: おつかれさまてす→です が4番目だった）
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
    base = [ch for ch in kl.KANA_POSITIONS
            if len(ch) == 1 and 'ぁ' <= ch <= 'ゖ']
    # 濁点・半濁点の付いた字も戻す字に入れる（゛ ゜ は独立のキー。付け忘れ・付けすぎは1打の戻し: こ↔ご・は↔ば↔ぱ。
    # kana_layout の距離は 0.4）
    try:
        from morphology import _DAKUTEN_COMPOSE, _HANDAKUTEN_COMPOSE
        extra = [v for k, v in list(_DAKUTEN_COMPOSE.items()) + list(_HANDAKUTEN_COMPOSE.items())
                 if k in base and v not in base]
    except Exception:
        extra = []
    return base + extra


def _intruded(line, i):
    """line[i] は、隣の字のキーを巻き込んで余分に打った1打か（`かっさて` の さ）。

    消す字は、前か後ろの字のキーのすぐ隣（距離 1.0 まで）にあること。
    同じ字が隣に並ぶときは重なり打ちで、その直しは切ってあるので消さない。
    """
    import kana_layout as kl
    ch = line[i]
    for j in (i - 1, i + 1):
        if 0 <= j < len(line) and _kana(line[j]):
            if line[j] == ch:
                return False
    return any(0 <= j < len(line) and _kana(line[j])
               and 0 < kl.intrusion_key_distance(ch, line[j]) <= 1.0
               for j in (i - 1, i + 1))


_ROMAJI_ONE_KEY = 'あいうえおんっ'  # ローマ字で1打の字（抜け・余りが1打で起きる）


def _method_label(options):
    return 'ローマ字入力' if (options or {}).get('input_method') == 'romaji' else 'かな入力'


_ROMAJI_ROWS = {
    'k': 'かきくけこ', 's': 'さしすせそ', 't': 'たちつてと', 'n': 'なにぬねの', 'h': 'はひふへほ', 'm': 'まみむめも',
    'y': 'やいゆいえよ', 'r': 'らりるれろ', 'w': 'わいうえを', 'g': 'がぎぐげご', 'z': 'ざじずぜぞ', 'd': 'だぢづでど',
    'b': 'ばびぶべぼ', 'p': 'ぱぴぷぺぽ', 'f': 'ふぁふぃふふぇふぉ', 'j': 'じゃじじゅじぇじょ', 'sh': 'しゃししゅしぇしょ',
    'ch': 'ちゃちちゅちぇちょ', 'ts': 'つぁつぃつつぇつぉ', 'ky': 'きゃきぃきゅきぇきょ', 'sy': 'しゃししゅしぇしょ',
    'ty': 'ちゃちちゅちぇちょ', 'ny': 'にゃにぃにゅにぇにょ', 'hy': 'ひゃひぃひゅひぇひょ', 'my': 'みゃみぃみゅみぇみょ',
    'ry': 'りゃりぃりゅりぇりょ', 'gy': 'ぎゃぎぃぎゅぎぇぎょ', 'by': 'びゃびぃびゅびぇびょ', 'py': 'ぴゃぴぃぴゅぴぇぴょ',
}
# 子音の組の片方が抜けた字（shi の s が抜けて hi、chi の c が抜けて hi、tsu の t が抜けて su）
_ROMAJI_CLUSTER_DROP = {'ひ': 'しち', 'す': 'つ'}


def _romaji_letters_to_kana(letters):
    """残った英字の子音（s・sh・ky）に母音を1つ足したかなの並び（さしすせそ…）。知らない並びは空。"""
    row = _ROMAJI_ROWS.get(letters.lower())
    if not row:
        return []
    if len(row) == 5:
        return list(row)
    # 2字ずつ（しゃ・し・しゅ…: 1字のものは行の中で1字）
    out, i = [], 0
    while i < len(row):
        if i + 1 < len(row) and row[i + 1] in 'ゃゅょぁぃぇぉ':
            out.append(row[i:i + 2]); i += 2
        else:
            out.append(row[i]); i += 1
    return out


def candidates(line, start, end, input_method='kana', free_del=()):
    """紫 [start, end) のまわりで1打を戻した行 → (種類, 位置)。

    種類: sub（隣のキー）・swap（隣どうしの入れ替わり）・ins（1字の抜け）・
    del（隣のキーの巻き込み。2026-10-17 に足した。うにさんの報告
    「隣接キー巻き込み」で、IME が変換した語の中で最も多い形）。
    """
    import kana_layout as kl
    romaji = input_method == 'romaji'
    if romaji:
        from corrector import adjacent_slip
    keys = _keys()
    lo = max(0, start - 1)
    hi = min(len(line), end + 1)
    out = {}
    for i in range(lo, hi):
        if romaji and line[i].isascii() and line[i].isalpha() and (i == 0 or not line[i - 1].isascii()):
            # 母音の抜けで英字が残った形（確認**s**ます・確認**sh**ます）: 英字の並びに母音を足してかなに
            j = i
            while j < len(line) and j - i < 3 and line[j].isascii() and line[j].isalpha():
                j += 1
            for kana in _romaji_letters_to_kana(line[i:j]):
                text = line[:i] + kana + line[j:]
                if _plausible(text, i, i + len(kana)):
                    out.setdefault(text, ('sub', i))
            continue
        if not _kana(line[i]):
            continue
        for ch in keys:
            if ch == line[i] or _same_kana_size(ch, line[i]):
                continue
            # ローマ字: 同じ2字の枠の1字が隣のキー（si→sa）・濁点の付け外し（s↔z）・1打の抜け（ni→i）・
            # 子音の組の片方の抜け（shi→hi: ひ→し）
            if (adjacent_slip(line[i], ch, 'romaji') or ch in _ROMAJI_CLUSTER_DROP.get(line[i], '') if romaji
                    else kl.kana_key_distance(line[i], ch) <= KEY_DISTANCE):
                text = line[:i] + ch + line[i + 1:]
                if _plausible(text, i, i + 1):
                    out.setdefault(text, ('sub', i))
        if not romaji and i + 1 < hi and _kana(line[i + 1]) and line[i] != line[i + 1]:
            # 字の入れ替わりはかな入力の形（ローマ字では字の中の2打の入れ替えは別の字にならない）
            text = line[:i] + line[i + 1] + line[i] + line[i + 2:]
            if _plausible(text, i, i + 2):
                out.setdefault(text, ('swap', i))
        if (_intruded(line, i) if not romaji
                else line[i] in _ROMAJI_ONE_KEY and (i in free_del or not _doubled_at(line, i))):
            text = line[:i] + line[i + 1:]
            if text and _plausible(text, i, i):
                out.setdefault(text, ('del', i))
    for i in range(lo, hi + 1):
        if not ((i < len(line) and _kana(line[i])) or (i > 0 and _kana(line[i - 1]))):
            continue
        # ローマ字の抜けは1打で消える字だけ（kakuni→kakuni**n**: n の押し忘れ）。ん の前には な行も
        # （ni の i が抜けて nn→ん: かく**ん**します→かくにんします）
        for ch in (('んっ' + ('なにぬねの' if i < len(line) and line[i] == 'ん' else '')) if romaji else keys):
            text = line[:i] + ch + line[i:]
            if _plausible(text, i, i + 1):
                out.setdefault(text, ('ins', i))
    if romaji:
        # 文字単位の戻し（順番違い・隣のキーの文字の巻き込み）。かな1字の戻しと同じ行になれば先に入れた種類のまま
        for text, (s, _e_old, _e_new) in _romaji_letter_edits(line, start, end).items():
            out.setdefault(text, ('edit', s))
    out.pop(line, None)
    return out


_ROMAJI_VOWELS = 'aiueo'


def _kana_run_to_romaji(text):
    """かな（と残った英字）の並び → ローマ字の文字列。小書きの ゃゅょ は前の い段とまとめる（きょ→kyo・しょ→syo）、
    っ は次の子音の重ね（がっこう→gakkou）。知らない字が在れば None。"""
    from corrector import _KANA_TO_ROMAJI
    out = []
    i = 0
    while i < len(text):
        c = text[i]
        if c.isascii() and c.isalpha():
            out.append(c.lower()); i += 1; continue
        if c == 'っ':
            j = i + 1
            nxt = _KANA_TO_ROMAJI.get(text[j]) if j < len(text) and not (text[j].isascii()) else (text[j] if j < len(text) else None)
            if not nxt or nxt[0] in _ROMAJI_VOWELS or nxt[0] == 'n':
                return None
            out.append(nxt[0]); i += 1; continue
        r = _KANA_TO_ROMAJI.get(c)
        if r is None or c in 'ぁぃぅぇぉゃゅょー':
            return None
        if i + 1 < len(text) and text[i + 1] in 'ゃゅょ' and r.endswith('i') and len(r) == 2:
            r = r[0] + 'y' + _KANA_TO_ROMAJI[text[i + 1]][1]   # き＋ょ → kyo（し・ち・じ も sy・ty・zy）
            i += 1
        if c == 'ん':
            r = 'nn'
        out.append(r); i += 1
    return ''.join(out)


_ROMAJI_INVERSE = None


def _romaji_inverse():
    global _ROMAJI_INVERSE
    if _ROMAJI_INVERSE is None:
        from corrector import _KANA_TO_ROMAJI
        inv = {}
        for k, r in _KANA_TO_ROMAJI.items():
            if k in 'ぁぃぅぇぉゃゅょー':
                continue
            inv.setdefault(r, k)
        for cons, row in _ROMAJI_ROWS.items():
            for kana, v in zip(_romaji_letters_to_kana(cons), _ROMAJI_VOWELS):
                inv.setdefault(cons + v, kana)
        inv['nn'] = 'ん'
        _ROMAJI_INVERSE = inv
    return _ROMAJI_INVERSE


def _romaji_to_kana(r):
    """ローマ字の文字列 → かな。n は次が母音・y 以外なら ん（nn も ん）、子音の重ねは っ。読めなければ None。"""
    inv = _romaji_inverse()
    out = []
    i = 0
    n = len(r)
    while i < n:
        c = r[i]
        if c == 'n' and (i + 1 == n or r[i + 1] not in _ROMAJI_VOWELS + 'y'):
            out.append('ん'); i += 2 if i + 1 < n and r[i + 1] == 'n' else 1; continue
        if c not in _ROMAJI_VOWELS and c != 'n' and i + 1 < n and r[i + 1] == c:
            out.append('っ'); i += 1; continue
        for k in (3, 2, 1):
            if i + k <= n and r[i:i + k] in inv:
                out.append(inv[r[i:i + k]]); i += k; break
        else:
            return None
    return ''.join(out)


def _romaji_letter_edits(line, lo, hi):
    """[lo, hi) を含むかな（と英字）の並びをローマ字に戻し、文字1つ分の戻し（隣どうしの入れ替え・隣のキーの文字の抜き・
    残った英字の抜き）をしてかなに戻した行 → {行: (始まり, 元の終わり, 新しい終わり)}。"""
    from corrector import _QWERTY_NEAR, _QWERTY_INTRUSION_NEAR
    a, b = lo, hi
    while a > 0 and (_kana(line[a - 1]) or (line[a - 1].isascii() and line[a - 1].isalpha())):
        a -= 1
    while b < len(line) and (_kana(line[b]) or (line[b].isascii() and line[b].isalpha())):
        b += 1
    if b - a > 12 and any(ch.isascii() and ch.isalpha() for ch in line[a:b]):
        first = next(k for k in range(a, b) if line[k].isascii() and line[k].isalpha())
        last = max(k for k in range(a, b) if line[k].isascii() and line[k].isalpha())
        a, b = max(a, first - 6), min(b, last + 7)
        while a < b and line[a] in 'ゃゅょぁぃぅぇぉっー':
            a += 1
    run = line[a:b]
    if len(run) < 2 or len(run) > 12:
        return {}
    rom = _kana_run_to_romaji(run)
    if not rom or len(rom) > 24:
        return {}
    near = set(_QWERTY_NEAR) | set(_QWERTY_INTRUSION_NEAR)
    variants = set()
    has_letter = any(ch.isascii() and ch.isalpha() for ch in run)
    spots = None
    if has_letter:
        # 英字をそのまま読み直すだけで読める形（まsひた → masita → ました）。戻しは残った英字の隣だけ
        # （okurimai**s**ta の o と k の入れ替え こうりました は見ない）
        variants.add(rom)
        spots = set()
        for k, ch in enumerate(run):
            if ch.isascii() and ch.isalpha():
                head = _kana_run_to_romaji(run[:k])
                if head is None:
                    return {}
                spots.update(range(len(head) - 1, len(head) + 2))
        variants = {v for v in variants}
    for i in range(len(rom) - 1):
        if rom[i] != rom[i + 1] and (spots is None or i in spots or i + 1 in spots):
            variants.add(rom[:i] + rom[i + 1] + rom[i] + rom[i + 2:])
    for i, c in enumerate(rom):
        left = rom[i - 1] if i > 0 else ''
        right = rom[i + 1] if i + 1 < len(rom) else ''
        if spots is not None:
            if i in spots:
                variants.add(rom[:i] + rom[i + 1:])
        elif (c, left) in near or (c, right) in near or (c in _ROMAJI_VOWELS and c == right):
            variants.add(rom[:i] + rom[i + 1:])
    out = {}
    for v in variants:
        kana = _romaji_to_kana(v)
        if not kana or kana == run or not _kana_str(kana):
            continue
        text = line[:a] + kana + line[b:]
        if text == line or not _plausible(text, a, a + len(kana)):
            continue
        s, e_old, e_new = _diff_range(line, text)
        out.setdefault(text, (s, e_old, e_new))
    return out


def _diff_range(line, text):
    """2つの行の違う範囲 → (始まり, 元の行の終わり, 新しい行の終わり)。"""
    s = 0
    while s < len(line) and s < len(text) and line[s] == text[s]:
        s += 1
    e_old, e_new = len(line), len(text)
    while e_old > s and e_new > s and line[e_old - 1] == text[e_new - 1]:
        e_old -= 1
        e_new -= 1
    return s, e_old, e_new


def _letter_span(line):
    # かなの中に残った小文字の英字（1〜2字・隣に英字以外の英数字が無い）を含む、かなと英字の並び（MAX_SPAN 字まで）。
    # 英語の語（3字以上・大文字・数字の隣）は見ない。無ければ None
    letters = [i for i, ch in enumerate(line) if ch.isascii() and ch.isalpha()]
    if not letters or len(letters) > 2 or letters[-1] - letters[0] > 1:
        return None
    a, b = letters[0], letters[-1] + 1
    if any(not ch.islower() for ch in line[a:b]):
        return None
    if (a > 0 and line[a - 1].isascii() and line[a - 1].isalnum()) or (b < len(line) and line[b].isascii() and line[b].isalnum()):
        return None
    left_kana = a > 0 and _kana(line[a - 1])
    right_kana = b < len(line) and _kana(line[b])
    if not (left_kana or right_kana):
        return None
    if not (left_kana and right_kana) and any(ch in _ROMAJI_VOWELS for ch in line[a:b]):
        return None
    while a > 0 and _kana(line[a - 1]) and b - a < MAX_SPAN:
        a -= 1
    while b < len(line) and _kana(line[b]) and b - a < MAX_SPAN:
        b += 1
    return (a, b)


def _inside_position(op, i, start, end):
    if op == 'edit':
        return start <= i < end
    if op == 'ins':
        return start <= i <= end
    if op in ('sub', 'del'):
        return start <= i < end
    return start <= i and i + 2 <= end + 1


def _edit_range(op, i):
    return (i, i) if op == 'ins' else (i, i + 1) if op in ('sub', 'del') else (i, i + 2)


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


def _clip_kana(line, a, b):
    """紫 [a, b) の中の、最も長いかなの並び → (始まり, 終わり)。かなが無ければ None。
    入口の紫は後ろの漢字まで掛かることがある（しりょういを**提出**）。1打の戻しはかなの部分だけ見る。"""
    a, b = max(0, a), min(len(line), b)
    best = None
    i = a
    while i < b:
        if not _kana(line[i]):
            i += 1
            continue
        j = i
        while j < b and _kana(line[j]):
            j += 1
        if best is None or j - i > best[1] - best[0]:
            best = (i, j)
        i = j
    return best


_WORD_RIGHT = 'がをにではともへかのや、。！？'


def _breaks_familiar_word(line, lo, hi, dict_index, start=None, end=None, loose=False):
    """[lo, hi) を置き換える戻しが、元の行で語の切れ目どおりに切れる3〜6字のかなの並びで、身近な語の読み
    （しりょう＝資料: 身近さの表で層1）になっているものを崩すか。組み立ての戻し（費用の下がりだけで採る）は
    正しい語を別の語（しちょう＝市長）に替えやすいので、身近な語の読みはそのまま残す。"""
    import morphology
    try:
        from kango_tier import known_usage_tier
        toks = list(morphology.tokenize(line))
    except Exception:
        return False
    edges = {t.start for t in toks} | {t.end for t in toks}
    ends = {t.end: t.end - t.start for t in toks}      # 字句の終わり → その長さ
    starts = {t.start: t.end - t.start for t in toks}  # 字句の始まり → その長さ
    for s in range(max(0, lo - 5), lo + 1):
        if s not in edges:
            continue
        if loose and not (s == 0 or not _kana(line[s - 1]) or line[s - 1] in _WORD_RIGHT or ends.get(s, 0) >= 2):
            continue
        for e in range(max(hi, s + 3), min(len(line), s + 6) + 1):
            if not _kana_str(line[s:e]):
                continue
            if e not in edges and not (loose and (e == len(line) or line[e] in _WORD_RIGHT or not _kana(line[e]))):
                continue
            if loose and e in edges and not (e == len(line) or not _kana(line[e]) or line[e] in _WORD_RIGHT
                                             or starts.get(e, 0) >= 2):
                continue
            if start is not None and not loose and not (s <= start and end <= e):
                continue
            try:
                faces = _kanji_choices(line[s:e], None, dict_index)
            except Exception:
                faces = []
            if any(known_usage_tier(f) == 1 for f in faces[:3]):
                return True
    return False


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


_DIGITS = '0123456789０１２３４５６７８９〇一二三四五六七八九十百千万'


def _katakana_run(text, lo, hi, line, dict_index):
    """戻した行 text の [lo, hi) を含むひらがなの並びが、世の中の表で片仮名の語だけの読み（めにゅー→メニュー）に
    なり、元の行 line の同じ並び（めなゅー）は語の読みでないとき → (始まり, 終わり, 片仮名)。それ以外は None。"""
    if dict_index is None or len(text) != len(line):
        return None
    i, j = lo, hi
    while i > 0 and _hira(text[i - 1]):
        i -= 1
    while j < len(text) and _hira(text[j]):
        j += 1
    run = text[i:j]
    if j - i < 3 or not _kana_str(run.replace('ー', '')) or _world_reading(dict_index, line[i:j]):
        return None
    try:
        faces = list(dict_index.surfaces_for_reading(run))
    except Exception:
        return None
    faces = sorted(set(faces))
    if len(faces) != 1 or not _katakana_str(faces[0]):
        return None
    return i, j, faces[0]


def _doubt_within_run(got, text, lo, hi):
    # 読み直した行 text に紫が無く、迷いがすべて [lo, hi) を含むひらがなの並びの中に収まるか
    if got.get('odd_spans'):
        return False
    i, j = lo, hi
    while i > 0 and _hira(text[i - 1]):
        i -= 1
    while j < len(text) and _hira(text[j]):
        j += 1
    return all(i <= a and b <= j for a, b, *_r in (got.get('unsure_spans') or ()))


def _same_doubt(got, result, delta, keep_odd=False):
    """戻した行に紫が無く、迷いが元の行と同じ所に同じ幅（行末の迷いは delta だけ伸縮）で残るだけか。
    かなだけの行（どうもありがとうございました。）は正しくても入口が迷いを残すので、戻しの結果とは見ない。"""
    if got.get('odd_spans'):
        if not keep_odd:
            return False
        had = {(a, b) for a, b, *_r in (result.get('odd_spans') or ())}
        had |= {(a + delta, b + delta) for a, b in had}
        if any((a, b) not in had for a, b, *_r in got['odd_spans']):
            return False
    before = [(a, b) for a, b, *_r in (result.get('unsure_spans') or ())]
    for a, b, *_r in (got.get('unsure_spans') or ()):
        # 元の迷いに重なり、幅が元＋1字（戻した字の分）までのもの（おはようご (0,5) → おはようござ (0,6)）
        if not any(oa < b and a < ob and b - a <= ob - oa + 1 + abs(delta) for oa, ob in before):
            return False
    return True


def _token_bounds(text, a, b):
    """text の [a, b) に掛かる字句の端まで広げた範囲。"""
    import morphology
    lo, hi = a, b
    for t in morphology.tokenize(text):
        if t.start < b and a < t.end:
            lo, hi = min(lo, t.start), max(hi, t.end)
    return lo, hi


def _region_reading(text, a, b):
    """text の [a, b) に掛かる字句の読み（ひらがな。読みの無い字句は表面）。"""
    import morphology
    from ime_readings import reading_to_hiragana
    out = []
    for t in morphology.tokenize(text):
        if t.start < b and a < t.end:
            out.append(reading_to_hiragana(t.reading) if t.has_reading else reading_to_hiragana(t.surface))
    return ''.join(out)


def _reading_kept(text, a, b, corrected, _b2=None, base=None):
    """読み直した結果 corrected が、戻した行 text の [a, b) の読みを保っているか。1打を戻した上に入口が読みの変わる直し（した→だ）
    を重ねた結果は、2つの直しが積み重なった形なので採らない。かな→漢字の変換
    （とった→撮った）は読みが同じなので通る。範囲の外の直しは、元の行の結果
    `base` にも在る直し（同じ字の組）か、読みの同じ変換だけ許す。"""
    import difflib
    try:
        sm = difflib.SequenceMatcher(None, text, corrected, autojunk=False)
        ops = sm.get_opcodes()

        def mapped(p, end):
            # text の位置 p を corrected の位置に写す（範囲の前の直しで長さが変わっても追える）
            for tag, i1, i2, j1, j2 in ops:
                if (i1 < p <= i2) if end else (i1 <= p < i2):
                    if tag == 'equal':
                        return j1 + (p - i1)
                    return j2 if end else j1
            return len(corrected) if end else 0
        # 範囲を戻した行の字句の境まで広げてから写す。かなの並びの切り方（ちょう|せいし|た）が
        # 文節の端（ちょうせい|した）と合わないとき、片側だけ隣の字句の読み（し）を含めて
        # 比べない（ちょうせいし 対 ちょうせい → 調整 が落ちる）。広げた分は両側に同じに入る
        a2, b2 = _token_bounds(text, a, b)
        if _region_reading(text, a2, b2) != _region_reading(corrected, mapped(a2, False), mapped(b2, True)):
            return False
        pairs = {(d[0], d[1]) for d in (base or {}).get('details') or () if len(d) >= 2}
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal' or (i1 < b and a < i2):
                continue
            if (text[i1:i2], corrected[j1:j2]) in pairs:
                continue
            if _region_reading(text, i1, i2) != _region_reading(corrected, j1, j2):
                return False
        return True
    except Exception:
        return True


def _costly_kana_runs(line):
    """かなだけの並び（4〜MAX_SPAN 字・前後がかなでない）で、1字あたりの並びの費用が CLAUSE_COST 以上の所。"""
    import morphology
    out = []
    i = 0
    while i < len(line):
        if not _hira(line[i]):
            i += 1
            continue
        j = i
        while j < len(line) and _hira(line[j]):
            j += 1
        if 4 <= j - i <= MAX_SPAN:
            cost = morphology.path_cost(line[i:j])
            if cost is not None and cost / (j - i) >= CLAUSE_COST:
                out.append((i, j))
        elif j - i > MAX_SPAN:
            # 長いかなの並び（よろしくおねかいします）は、語の切れ目で切った窓（4〜MAX_SPAN 字）のうち
            # 1字あたりの費用が最も高いもの
            cuts = sorted({i, j} | {t.start for t in morphology.tokenize(line[i:j]) if 0 < t.start < j - i})
            cuts = [i + c if c < j - i else c for c in cuts]
            best = None
            for a in cuts:
                for b in cuts:
                    if 4 <= b - a <= MAX_SPAN:
                        cost = morphology.path_cost(line[a:b])
                        if cost is not None and cost / (b - a) >= CLAUSE_COST and (best is None or cost / (b - a) > best[0]):
                            best = (cost / (b - a), a, b)
            if best:
                out.append((best[1], best[2]))
        i = j
    return out


VOUCH_SUB_YOMI = 8.0   # 迷いの並びの置き換えを読みの並びで採る線（きりがないようなも→ようにも +8.9）
WHOLE_DEL_YOMI = 10.0  # 丸ごと紫の行で、かな1字の抜きを採るのに要る読みの並びの改善（しとゅうがくりょこう→しゅうがくりょこう +24.5）


def _kana_windows(line, spans):
    # spans が覆う MAX_SPAN より長いかなの並びを、語の切れ目で切った窓（4〜MAX_SPAN 字）に分け、1字あたりの費用の高い順に返す
    import morphology
    out = []
    for i, j in spans:
        if j - i <= MAX_SPAN or not all(_hira(ch) for ch in line[i:j]):
            continue
        cuts = sorted({i, j} | {i + t.start for t in morphology.tokenize(line[i:j]) if 0 < t.start < j - i})
        # 切れ目どうしの窓と、並びの両端から MAX_SPAN 字の窓（切れ目が少ない並び し|とゅうがくりょこう でも と を含む窓を見る）
        pairs = {(a, b) for a in cuts for b in cuts if 4 <= b - a <= MAX_SPAN}
        pairs |= {(i, i + MAX_SPAN), (j - MAX_SPAN, j)}
        for a, b in pairs:
            cost = morphology.path_cost(line[a:b])
            if cost is not None:
                out.append((cost / (b - a), a, b))
    out.sort(reverse=True)
    return [(a, b) for _c, a, b in out]


def repair(line, result, retry, input_method='kana', decisions=None,
           dict_index=None, vouch=False, whole=None, widened=False):
    """
    `result`（`line` の補正結果）に短いかなの紫が残っていれば、1打を
    戻した行を `retry(行)` で読み直し、採れるものがあれば
    `(戻した行, 読み直した結果, (始まり, 終わり, 戻した字))` を返す
    （位置は元の行の上）。無ければ None。
    """
    if input_method not in ('kana', 'romaji') or dict_index is None or not line:
        return None
    def usable(spans):
        return bool(spans) and all(0 <= a < b <= len(line) and b - a <= MAX_SPAN
                                   and all(_kana(ch) or (letters and ch.isascii() and ch.isalpha())
                                           for ch in line[a:b]) for a, b in spans)
    letters = _letter_span(line) if input_method == 'romaji' else None
    odd = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
    clipped = False
    if input_method == 'romaji':
        cut = [sp for sp in (_clip_kana(line, *x) for x in odd) if sp]
        clipped = cut != odd
        odd = cut
    vouch_only = False
    doubt_run = False   # 迷い（unsure）か丸ごと紫の並びの中か（読みの並びだけで採る戻しはここだけ）
    letter_entry = False
    if whole and not letters:
        odd = [whole]
        vouch_only = True
        doubt_run = True
    elif letters and result.get('corrected', line) == line:
        # ローマ字で、かなの中に小文字の英字が残っている（おくりまい**s**た・しまし**w**た）: 打ち違いの確かな印なので、
        # 紫と同じ入口（組み立ての戻しでなく、1打の戻しの道）で、英字を含む並びを読み直す。戻しは英字の単位だけ
        odd = [letters]
        letter_entry = True
    elif not (usable(odd) and not _doubled_tail(line, odd) and _anchored(line, odd)):
        if not vouch:
            return None
        # 紫が無い（または紫が長い・文が丸ごと紫）行: 迷い（入口がかなの並びを確かめきれない印）の範囲、それも無ければ
        # かなだけの並び（4〜MAX_SPAN 字、長い並びは語の切れ目の窓）で1字あたりの費用が疑いの線（CLAUSE_COST）を超える所
        # （ありかとう 3034・おねかいします 2580。正しい ありがとう 730・おねがいします 959）を見る。採るのは、文の
        # 組み立てが大きく良くなる1打の戻し（VOUCH_GAIN）だけ（ありかとう→ありがとう・しましゅう→しましょう）
        done = result.get('corrected', line)
        if done != line and _region_reading(done, 0, len(done)) != _region_reading(line, 0, len(line)):
            # 入口がすでに直した行（すこセ氏たい→過ごしたい）には重ねない。読みを変えない置き（ばあい→場合）は別
            return None
        unsure = [tuple(x[:2]) for x in (result.get('unsure_spans') or ())]
        if not whole and not usable(unsure):
            # 行（かなの並び）が丸ごと紫: 窓を費用の順に全部見る（最初に採れた窓の戻し）
            purple = [tuple(x[:2]) for x in (result.get('odd_spans') or ())] or unsure
            for a, b in _kana_windows(line, purple):
                got = repair(line, result, retry, input_method=input_method,
                             decisions=decisions, dict_index=dict_index, vouch=True, whole=(a, b))
                if got:
                    return got
        if not whole and not usable(unsure):
            got = _absorbed_repair(line, retry, dict_index)
            if got:
                return got
        odd = [whole] if whole else (unsure if usable(unsure) else _costly_kana_runs(line))
        vouch_only = True
        doubt_run = bool(whole) or usable(unsure)
        if not usable(odd) or _doubled_tail(line, odd):
            return None
    start, end = odd[0]
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
    for text, (op, i) in candidates(line, start, end, input_method).items():
        if not _inside_position(op, i, start, end):
            continue
        cost = morphology.path_cost(text)
        if cost is None:
            continue
        gain = base - cost
        yomi = yomigram.logp_parts(text)[0] - yomi0
        pool.append((gain + YOMI_WEIGHT * yomi, gain, yomi, text, op, i))
    pool.sort(key=lambda row: (-row[0], row[3]))
    letter_free = input_method == 'romaji' and not any(ch.isascii() and ch.isalpha() for ch in line)
    if letter_free:
        # かな1字の抜き（費用の線を超えるもの）を英字単位の抜きより先に
        pool.sort(key=lambda row: (0 if row[4] == 'del' and row[0] >= NEED_SUB else 1, -row[0], row[3]))
    kana_del_clean = False
    found = []
    trials = 0
    for score, gain, yomi, text, op, i in pool:
        if not found and score < NEED_SUB:
            break
        if letter_free and op == 'edit' and len(text) < len(line) and kana_del_clean:
            continue
        if found and score < found[0][0] - MARGIN:
            break
        if op == 'ins' and not _verb_insert(text, i):
            continue
        if clipped and op not in ('del', 'edit'):
            continue
        if letter_entry and op != 'edit':
            continue
        # 組み立ての戻し（vouched）は、隣のキー・濁点の付け外しの置き換えだけ（抜き・足しは 待ち合わせし→待ち合わし の
        # ように正しい形を崩しても費用が大きく下がることがある）。かなの並びが4字以上（すこ→かこ のような短い並びは見ない）
        if op == 'edit':
            lo, hi, hi_new = _diff_range(line, text)
        else:
            lo, hi = _edit_range(op, i)
            hi_new = hi + (op == 'ins')
        vouched = (vouch and op == 'sub' and gain >= VOUCH_GAIN and end - start >= 4
                   and not (lo > 0 and line[lo - 1] in _DIGITS)
                   and not (input_method == 'romaji' and _breaks_familiar_word(line, lo, hi, dict_index, start, end))
                   and not (input_method == 'kana' and _breaks_familiar_word(line, lo, hi, dict_index, loose=True)))
        if doubt_run and op == 'del' and gain > 0 and yomi >= WHOLE_DEL_YOMI:
            vouched = True
        if doubt_run and op == 'sub' and gain > 0 and yomi >= VOUCH_SUB_YOMI and end - start >= 4:
            vouched = True
        if widened and op == 'sub' and yomi < VOUCH_SUB_YOMI:
            vouched = False
        kata = _katakana_run(text, lo, hi_new, line, dict_index) if op == 'sub' and not vouch_only else None
        if kata:
            vouched = True
        if vouch_only and not vouched:
            continue
        if not vouched and _inside_word(line, lo, hi, dict_index):
            continue
        if not vouched and not _predicate_follows(text, max(0, lo - 1) if op == 'del' and input_method == 'romaji' else lo,
                                                  lo if op == 'del' else hi_new):
            continue
        trials += 1
        if trials > (MAX_TRIALS if found else FIRST_TRIALS):
            break
        got = retry(text)
        if got and (_clean(got) or ((vouched or letter_entry)
                                    and (_same_doubt(got, result, len(text) - len(line), keep_odd=letter_entry)
                                         or (vouched and doubt_run and _doubt_within_run(got, text, lo, hi_new))))):
            corrected = got.get('corrected', text)
            a0, b0 = min(start, lo), max(end, hi_new)
            if not _reading_kept(text, a0, b0, corrected, len(corrected) - (len(text) - b0), result):
                continue
            if kata and _clean(got) and got.get('corrected', text) == text:
                got = dict(got, kata=kata)
            found.append((score, gain, yomi, text, op, got, i))
            if op == 'del' and _clean(got):
                kana_del_clean = True
            if len(found) >= 2:
                break
    if not found:
        if vouch and not whole and not vouch_only and not letter_entry:
            unsure = [tuple(x[:2]) for x in (result.get('unsure_spans') or ())]
            # 迷いが紫と重なるだけ（紫 をか・迷い かいまひ）のときは、両方を覆う並びを読み直す
            wider = [(min(a, start), max(b, end)) for a, b in unsure if a < end and start < b
                     and (min(a, start), max(b, end)) != (start, end)
                     and max(b, end) - min(a, start) <= MAX_SPAN and _kana_str(line[min(a, start):max(b, end)])]
            if wider and result.get('corrected', line) == line:
                return repair(line, result, retry, input_method=input_method, decisions=decisions,
                              dict_index=dict_index, vouch=True, whole=wider[0])
        if (doubt_run and not whole and odd and result.get('corrected', line) == line
                and _kana_str(line.strip(' 　。、．，！？!?…'))):
            i, j = odd[0]
            while i > 0 and _hira(line[i - 1]):
                i -= 1
            while j < len(line) and _hira(line[j]):
                j += 1
            for a, b in (_kana_windows(line, [(i, j)]) if j - i > MAX_SPAN else ([(i, j)] if j - i >= 4 else [])):
                if (a, b) == (start, end) or not (a <= start and end <= b):
                    continue
                got = repair(line, result, retry, input_method=input_method, decisions=decisions,
                             dict_index=dict_index, vouch=True, whole=(a, b), widened=True)
                if got:
                    return got
        return None
    score, gain, yomi, text, op, got, i = found[0]
    if score < (NEED_INSERT if op == 'ins' else NEED_SUB):
        return None
    yomi_del = (doubt_run and op == 'del' and yomi >= WHOLE_DEL_YOMI and _clean(got)
                or (doubt_run and op == 'sub' and yomi >= VOUCH_SUB_YOMI and _clean(got)))
    if (gain < MIN_PATH_GAIN and not yomi_del) or (yomi < MIN_YOMI_GAIN
                                and not (vouch and op == 'sub' and gain >= VOUCH_GAIN and end - start >= 4)
                                and not (doubt_run and op == 'del' and yomi >= WHOLE_DEL_YOMI)):
        return None
    if len(found) > 1 and score - found[1][0] < MARGIN:
        # 差が小さくても、並びの費用と読みの並びの両方で上回り（身近さで勝つ）、読みの並びが置き換えを採る線
        # （VOUCH_SUB_YOMI）を越えて良くなる候補は決める。どちらかが欠けるなら紫のまま（行使くなる→行使くばる +1.3 は採らない）
        if not (gain > found[1][1] and yomi > found[1][2] and yomi >= VOUCH_SUB_YOMI):
            return None
    if yomi_del:
        got = dict(got, yomi_del=True)
    if op == 'edit':
        lo, hi, hi_new = _diff_range(line, text)
        return text, got, (lo, hi, text[lo:hi_new])
    if got.get('kata'):
        ki, kj, kface = got['kata']
        return text, dict(got, corrected=text[:ki] + kface + text[kj:]), (ki, kj, kface)
    lo, hi = _edit_range(op, i)
    face = '' if op == 'del' else text[lo:hi + (op == 'ins')]
    return text, got, (lo, hi, face)


# ---- IME の文節の読み直し（2026-10-17）------------------------------------
#
# うにさんの報告「隣接キーの間違いをしたうえで IME が変換すると補正されない
# ケースが多い」。正しい文235行の語に1打の誤りを入れ、IME の変換をまねた
# 216件を測ると、直るのは18件だった。直らないものの大半は、IME が打ち違いの
# 読みを**忠実に**漢字に変えた形（さむたい → 寒たい・わかれて → 若れて）で、
# 語の並びとしては読めてしまい紫も付かない。ただし janome の並びの費用
# （連接）は正しい文の約2倍になる（1字あたり 正しい文 600〜1,100・
# 打ち違い 1,200〜1,800）。
#
# 直し方: IME の対（文節ごとに保存される）から、文節を**打った読みに戻し**、
# 上と同じ1打の戻しを入れた候補を作り、読みの並び（yomigram）で絞り、
# 辞書で粗く変換した並びの費用の下がり幅で絞ってから、補正の入口に通し直す。
# 採るのは、紫も迷いも残らず、並びの費用が 2000 以上下がり、1字あたりの費用が
# 疑いの線を割るものだけ。置く直しは上と同じ共通の最終検査を通る。
CLAUSE_COST = 1200        # 1字あたりの並びの費用。これ以上なら打ち違い＋IME 変換を疑う
CLAUSE_TOP = 6            # 読みの並びで残す候補の数
CLAUSE_RETRIES = 3        # 1行あたりの読み直しの上限
CLAUSE_TOKENS = 6         # 文節とみなす語の数の上限（見る文節の数の上限でもある）
CLAUSE_GAIN = 2000
CLAUSE_LOCAL_COST = 1500  # 文節だけの1字あたりの費用の線（長い行で余分な1字が行全体の費用を上げないとき用）
CLAUSE_YOMI_TIE = 3.0     # 費用の下がりが並んだとき、読みの並びの差がこれ以上なら上を採る
CLAUSE_KANA_YOMI = 5.0    # かなのまま残る直しは、読みの並びがこれ以上良くなるものだけ
CLAUSE_KEPT_YOMI = 8.0    # IME の顔の漢字に戻した直し（食べ**タフ**→食べた）を行の重さで止めないのは、読みの並びがこれ以上良くなるときだけ
CLAUSE_YOMI_WEIGHT = 200  # 候補を並べるとき、読みの並びの良さ（自然対数）1 を行の費用のいくらと見るか。辞書の費用の尺度
                          # （約700/対数1）で足すと、費用の安い語（調整 15790・読み +1.7）が最も安い戻し（注意 16466・-0.4）
                          # より先に枠を埋めた。費用の差が小さいときだけ読みの並びが順を決める重み
CLAUSE_CONVERTED_YOMI = 0.0  # 入口が自ら漢字にした形を行の重さの門で止めないのは、戻した読みが打った読みより通りのよいときだけ
MAX_CLAUSE_LINE = 80
_COPULA = ('だ', 'です', 'でし', 'だっ', 'なら', 'でしょ', 'らしい', 'な', 'で', 'に', 'だろ', 'でしょう')


def _kanji(ch):
    return '一' <= ch <= '鿿' or ch == '々'


def _old_doubt(a, b, s, e, new_e, result, key='unsure_spans'):
    """直した行の文節の外の迷い (a, b) が、元の行の同じ所の迷い（result の unsure_spans。key で紫 odd_spans も）
    に重なるか。文節の後ろは、文節の長さの変わった分だけ元の位置に戻して見る。"""
    base = [(x[0], x[1]) for x in ((result or {}).get(key) or ()) if len(x) >= 2]
    if a >= new_e:
        a, b = a - new_e + e, b - new_e + e
    return any(x < b and a < y for x, y in base)


def _kanji_seq(text):
    """文字列の中の漢字だけを順に並べたもの。"""
    return ''.join(c for c in text if _kanji(c))


def _kept_word_queries(face, reading, tail=4):
    """_ime_word_kept が引く (語の表記, 付属, 語の読み) の並び（引く前にまとめて種表を引けるように）。"""
    out = []
    if not reading or _kana_str(face) or not any(_kana(c) for c in face):
        return out
    for j in range(len(face) - 1, 0, -1):
        if not _kana(face[j]):
            break
        rest = face[j + 1:]
        if len(rest) > tail or (rest and (not _kana_str(rest) or not reading.endswith(rest))):
            continue
        head = face[:j]
        if _kana_str(head):
            continue
        word = reading[:len(reading) - len(rest)] if rest else reading
        if word:
            out.append((head, rest, word))
    return out


def _ime_word_kept(face, reading, store, dict_index, tail=4, info=None):
    """IME の顔 face の、語の漢字の表記と付属の間にある1字を抜いた形で、読みが reading
    （1打戻した読み）になるもの。無ければ None。info（dict）を渡せば、語の読みに辞書の漢字の
    表記が複数あって IME にも聞けなかった（雲・CI）ことを info['ambiguous'] に入れる。

    確定の前に1字余分に打ち、IME が語の部分だけ変換した跡（保存**な**して・移動**あ**した・
    半分**な**くらい・新しい**す**）。語の漢字は IME が選んだままにし、余った字だけ抜く
    （かなに戻して入口に通すと、前後のかなと長い連なりになって入口が崩れる:
    にかくにんしてもらった）。語の部分は戻した読みの語の辞書の表記であること（い**す**県→
    い県 のように、IME の漢字そのものが打ち違いの跡なら形にしない）。語の前や中の字
    （**し**半分・ち管区）は見ない: そこでは IME の漢字は打ち違いの読みの変換で、残す根拠が無い。
    """
    for head, rest, word in _kept_word_queries(face, reading, tail):
        try:
            faces = _kanji_choices(word, store, dict_index)
        except Exception:
            return None
        if head in faces and _face_attaches(head, rest):
            # 本人の IME が戻した読みで出す顔（辞書の表記の中）が別の語なら、そちら
            # （機器**く**ながら: IME は きき を 機器 にしたが、ききながら なら 聞き）。
            # IME が無ければ（雲・CI）IME の漢字のまま
            other = _ime_face(word, rest, faces)
            if info is not None:
                info['ambiguous'] = other is None and len([f for f in faces if not _kana_str(f)]) >= 2
            if other and other != head:
                return other + rest
            return head + rest
    return None


def _doubled_at(text, i):
    """text[i] が同じかなの重なり（くく・んん）の片方か。"""
    c = text[i]
    return _kana(c) and ((i > 0 and text[i - 1] == c) or (i + 1 < len(text) and text[i + 1] == c))


def _leading_kana_kept(face, original):
    """顔の先頭のかなの並びが、元の文節の先頭と同じか。

    元の語の漢字（甘）がかな（あまく）に戻り、後ろの切れ端だけが漢字になった顔（あまく待て）は、入口が語を
    変換した跡ではない。先頭がかなの語（お礼）は元の文節も同じかなで始まる
    """
    k = 0
    while k < len(face) and _kana(face[k]):
        k += 1
    return original.startswith(face[:k])


def _new_kanji(face, original):
    """顔 `face` に、元の文節 `original` に無い漢字が在るか（入口が自ら漢字にした跡）。

    元の漢字が残っただけの顔（設定を＋元に → 設定を＋ともに: 元 がかなに戻った）は入口の変換ではない。
    """
    old = {c for c in original if _kanji(c)}
    return any(_kanji(c) and c not in old for c in face)


def _kana_str(text):
    return bool(text) and all(_kana(c) or c == 'ー' for c in text)


def _cost_per_char(line, cost):
    return cost / max(1, len(line.strip(' 　。、．，！？!?…')))


def _conjugation_mismatch(toks):
    """活用の形が合わない続き（打ち違いの読みを IME が別の活用形や別の語に変換した跡）→ 前の語の番号。
    文法で確かな印（正しい文には出ない形）:
    形容詞の基本形・体言接続に直に付いた て（新しい**て**靴・良き**て**。正しくは 新しくて）、
    形容詞の語幹（ガル接続）に直に付いた助詞・助動詞（楽し**は**そう。語幹に付くのは そう・さ・がる）、
    動詞の基本形に直に付いた、連用形・未然形に付くはずの助動詞（初める**た**。正しくは 始めた）、
    動詞の基本形に直に付いた、連用形に付くはずの助詞（聞く**ながら**・読む**たり**・行く**て**。正しくは 聞きながら）、
    形容動詞の語幹に直に付いた て（温か**て**飲み物。正しくは 温かい）。"""
    out = set()
    for i in range(len(toks) - 1):
        t, u = toks[i], toks[i + 1]
        sub = t.pos_sub.split(':')[0]
        if ((t.pos == '形容詞' and t.infl_form in ('基本形', '体言接続')
                and u.pos == '助詞' and u.surface == 'て')
                # 形容詞の基本形に直に付いた動詞（多**い**なる・寒**い**なった。正しくは連用形: 多くなる）
                or (t.pos == '形容詞' and t.infl_form == '基本形' and u.pos == '動詞' and u.start == t.end)
                # 形容詞の語幹に直に付いた名詞（温か**飲み物**。語幹に付く名詞は接尾の さ・み・げ・そう だけ）
                or (t.pos == '形容詞' and t.infl_form == 'ガル接続' and len(t.surface) >= 2 and u.pos == '名詞'
                    and not (u.pos_sub or '').startswith(('接尾', '非自立')) and u.start == t.end)
                # 形容詞の語幹に直に付いた自立の動詞（懐かし**なっ**た。語幹に付く動詞は がる・すぎる など非自立だけ）
                or (t.pos == '形容詞' and t.infl_form == 'ガル接続' and len(t.surface) >= 2 and u.pos == '動詞'
                    and not (u.pos_sub or '').startswith('非自立') and u.base_form != 'がる' and u.start == t.end)
                or (t.pos == '形容詞' and t.infl_form == 'ガル接続'
                    and u.pos in ('助詞', '助動詞'))
                or (t.pos == '動詞' and t.infl_form == '基本形' and u.pos == '助動詞'
                    and u.base_form in ('た', 'たい', 'たがる', 'ます', 'ない', 'ぬ', 'ん',
                                        'れる', 'られる', 'せる', 'させる'))
                or (t.pos == '動詞' and t.infl_form == '基本形' and u.pos == '助詞'
                    and u.surface in ('ながら', 'つつ', 'たり', 'て'))
                or (t.pos == '名詞' and sub == '形容動詞語幹'
                    and u.pos == '助詞' and u.surface == 'て')
                # 形容詞の語幹でない形（連用形・基本形）に直に付いた接尾の さ（甘**く**さ・楽し**い**さ。
                # さ が付くのは語幹: 甘さ・楽しさ）
                or (t.pos == '形容詞' and t.infl_form != 'ガル接続'
                    and u.pos == '名詞' and u.pos_sub.split(':')[0] == '接尾' and u.surface == 'さ')
                # 形容詞の連用形（良く）に直に付いた、ない 以外の助動詞（良く**まじ**つ。連用形に付く助動詞は ない だけ）
                or (t.pos == '形容詞' and t.infl_form == '連用テ接続'
                    and u.pos == '助動詞' and u.base_form != 'ない')
                # 形容詞の体言接続（良き・若き）に直に付いた助詞（良き**が**降った。体言接続の後ろは名詞）
                or (t.pos == '形容詞' and t.infl_form == '体言接続' and u.pos == '助詞')
                # 動詞の連用形に直に付いた ください（ご角**煮ください**・内容を角**煮ください**: かくに→角煮）。
                # 連用形に ください が付くのは接頭詞の付いた形（お待ちください）だけ。て形（見てください）は て が
                # 挟まり、角煮をください（注文）は を が挟まる。なさい は連用形に直に付く（書きなさい）ので見ない
                or (t.pos == '動詞' and t.infl_form == '連用形' and u.pos == '動詞' and u.base_form == 'くださる'
                    and not (i > 0 and toks[i - 1].pos == '接頭詞' and toks[i - 1].surface in ('お', 'ご')))
                # 動詞の連用形に直に付いた する（角**煮します**: かくにします→かくにんします）。する は連用形に
                # 付いて複合動詞を作らない（書き直す・読み終える のような複合は する では無い）
                or (t.pos == '動詞' and t.infl_form == '連用形' and t.base_form != 'する'
                    and u.pos == '動詞' and u.base_form == 'する' and u.pos_sub.split(':')[0] == '自立')
                # 助動詞 だ の体言接続「な」に直に付いた助詞（ような**も**・静か**は**。な の後ろは名詞。の（ようなのに）は
                # 準体の名詞に当たり、だけ・ほど・くらい も な に付く（好きなだけ）ので、格助詞・係助詞だけ見る）。顔（霧が内容名も）には出ず、打った読み（きりがないよう**な**も）に出る印
                # 動詞の連用形に直に付いた すら・さえ・こそ・も の後に直に ない（見**すらない**: みすらない→ミスらない）。
                # 連用形＋係助詞・副助詞の後の打ち消しは する を挟む（見もしない・知りさえしない）。形容詞の連用形
                # （高くもない）は印にしない
                or (t.pos == '動詞' and t.infl_form == '連用形' and u.pos == '助詞'
                    and u.surface in ('すら', 'さえ', 'こそ', 'も') and u.start == t.end
                    and i + 2 < len(toks) and toks[i + 2].base_form == 'ない' and toks[i + 2].start == u.end)
                or (t.pos == '助動詞' and t.surface == 'な' and t.infl_form == '体言接続'
                    and u.pos == '助詞' and u.surface in ('も', 'は', 'が', 'を', 'に', 'へ', 'と', 'で', 'や', 'から')
                    and u.start == t.end)):
            out.add(i)
    return out


def _grammar_mark_removed(before, bs, be, after, as_, ae):
    """before の [bs, be) に文法で確かな印が在り、after の [as_, ae) には無く、その範囲の字句が全部 辞書の読みを持つか。"""
    import morphology
    try:
        btoks = list(morphology.tokenize(before))
        atoks = list(morphology.tokenize(after))
    except Exception:
        return False
    had = any(i + 1 < len(btoks) and btoks[i].start < be and bs < btoks[i + 1].end for i in _conjugation_mismatch(btoks))
    if not had:
        return False
    if any(i + 1 < len(atoks) and atoks[i].start < ae and as_ < atoks[i + 1].end for i in _conjugation_mismatch(atoks)):
        return False
    inside = [t for t in atoks if t.start < ae and as_ < t.end]
    return bool(inside) and all(t.has_reading for t in inside)


def _reading_sure_clauses(line, clauses):
    """IME の顔には印が無くても、打った読みに戻した行で文法で確かな印（_conjugation_mismatch）が文節の中に出る
    文節 → {(始まり, 終わり)}。読みはかなだけ・3字以上、顔は漢字を含むこと（きりがないよう**な**も→霧が内容名も）。"""
    import morphology
    out = set()
    for s, e, typed in sorted({(c[0], c[1]): c[2] for c in clauses}.items() and
                              [(k[0], k[1], v) for k, v in {(c[0], c[1]): c[2] for c in clauses}.items()]):
        if not _kana_str(typed) or len(typed) < 3 or not any(_kanji(c) for c in line[s:e]):
            continue
        # IME の顔の語の読みをつなぐと打った読みになる文節（宛名を＝あてな＋を: 読みを あて＋な＋を と切ると印が出るが、
        # IME は正しく変換した）は見ない。顔の読みが打った読みと違う（内容名も＝ないようめいも）ときだけ
        try:
            ftoks = list(morphology.tokenize(line[s:e]))
        except Exception:
            continue
        if ftoks and all(t.has_reading for t in ftoks) and ''.join(_tok_reading(t) for t in ftoks) == typed:
            continue
        try:
            ktoks = list(morphology.tokenize(line[:s] + typed + line[e:]))
        except Exception:
            continue
        if any(i + 1 < len(ktoks) and s <= ktoks[i].start and ktoks[i + 1].end <= s + len(typed)
               for i in _conjugation_mismatch(ktoks)):
            out.add((s, e))
    return out


def line_is_quote_boundary(toks, i):
    """終助詞の直前が引用の閉じ（「〜ね」と言った）や記号なら、後ろに名詞が続いても文の切れ目。"""
    return i + 1 < len(toks) and toks[i + 1].pos == '記号' or (i > 0 and toks[i - 1].pos == '記号')


def _romaji_stray_tokens(toks):
    """ローマ字入力で母音のキー（a i u e o）や t・n の2度押しが1字のかなとして残った形（異様の印）。

    文法で付けない所に付いた1字の う・い・っ・お・え・あ:
    助動詞 う が未然形の後でない（悪い**う**ので・番号**う**を・聞く**う**のは）、非自立の動詞 い・っ が て／で の後でない
    （思う**い**。・考える**い**のが・**っ**天気予報）、1字の感動詞・フィラーが文の途中（記号の後でない）で付属語や用言に
    続く（友達**お**に・今日**う**届いた・前**え**の）、接頭詞 お の直後が助詞（食事**お**を）。
    かな入力では別の打ち違い（別の判定）なので使わない。
    """
    out = set()
    head = set()
    for i, t in enumerate(toks):
        prev = toks[i - 1] if i > 0 else None
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if (len(t.surface) >= 2 and t.surface.endswith('っ') and nxt is not None and nxt.start == t.end
                and _kanji(nxt.surface[0])):
            # 前の語にくっついた っ の直後に漢字（はっ家族・のっ子供）。っ の後に漢字が続く語は無い（まっ白 は1語）
            out.add(i)
            continue
        if (t.pos == '形容詞' and t.infl_form == '連用ゴザイ接続' and len(t.surface) >= 2
                and not (nxt is not None and nxt.surface[:2] in ('ござ', '存じ'))):
            # ウ音便（多**う**・悪**う**・早**う**）は ございます・存じます の前にしか出ない。ローマ字で く の k が抜けた形
            # （ooku→oou）: 多**う**なる→多くなる
            out.add(i)
            continue
        if (t.pos == '動詞' and t.surface[0] in 'あいうえお' and prev is not None and prev.pos == '形容詞'
                and prev.infl_form in ('連用テ接続', 'ガル接続') and prev.end == t.start):
            # 形容詞の連用形・語幹に直に続く、母音の字で始まる動詞（遅く**う**なりました・懐かし**う**なった・
            # 難しく**い**て）: 連用形の後に母音で始まる語が続く形は、く の k の抜け（kuku→kuu）か母音の2度押しの跡
            head.add(i)
            out.add(i)
            continue
        if (t.surface == 'ん' and t.pos == '名詞' and nxt is not None and nxt.pos == '動詞'
                and prev is not None and prev.pos == '動詞'):
            # 動詞の後の ん に動詞が続く（かく**ん**します: ni の i が抜けて nn→ん）。書く**ん**です は です・だ が続く
            out.add(i)
            continue
        if len(t.surface) != 1 or t.surface not in 'あいうえおっ':
            continue
        sub = t.pos_sub or ''
        if t.pos == '助動詞' and t.surface == 'う':
            if prev is not None and not (prev.infl_form or '').startswith('未然'):
                out.add(i)
        elif t.pos == '動詞' and sub.startswith('非自立') and t.surface in 'いっ':
            if not (prev is not None and prev.pos == '助詞' and prev.surface in ('て', 'で')):
                out.add(i)
        elif t.pos in ('感動詞', 'フィラー'):
            if (prev is not None and prev.pos != '記号' and nxt is not None
                    and nxt.pos in ('助詞', '助動詞', '動詞', '形容詞')):
                out.add(i)
        elif t.pos == '接頭詞' and nxt is not None and nxt.pos == '助詞':
            out.add(i)
    return {i: (toks[i].start if (i in head or len(toks[i].surface) == 1) else toks[i].end - 1) for i in out}


def _suspect_tokens(toks):
    """打ち違いの読みを IME が忠実に変換した跡（語の並びの上）→ 疑わしい語の番号。

    1字のかなの自立語（雨**ろ**が・天気**く**です）・語幹だけで終わる形容詞
    （**寒**たい・**若**れて）・読みの取れない語・名詞のすぐ後ろの、動詞に付く
    かな（接尾の動詞・非自立の動詞・コピュラでない助動詞・接続助詞）。
    """
    spots = set()
    sure = _conjugation_mismatch(toks)
    for i, t in enumerate(toks):
        sub = t.pos_sub.split(':')[0]
        if (len(t.surface) == 1 and _kana(t.surface) and (t.pos, sub) in (
                ('名詞', '一般'), ('動詞', '自立'), ('形容詞', '自立'))
                # する の活用形（追加**し**ました・補正**さ**れない・確認**せ**ず）は語。サ変の名詞・助詞・副詞に
                # 続く形は印にしない（印にすると、本人の語彙で軽くなる別の語 活かし に替わる）
                and not _suru_form(toks, i)):
            spots.add(i)
        # 文語の助動詞 つ・き・けり（風が**つ**枠なった・夕**し**どんの: 完了の つ・過去の き）は今の文には出ない
        if t.pos == '助動詞' and t.base_form in _LITERARY_AUXILIARIES:
            spots.add(i)
        if t.pos == '形容詞' and t.surface and _kanji(t.surface[-1]):
            # 語幹だけで終わる形容詞（寒**たい**・若**れて**）。語幹に付く接尾（甘**さ**・高**み**・寒**げ**）が
            # 続く形は正しい形なので印にしない
            u = toks[i + 1] if i + 1 < len(toks) else None
            if not (t.infl_form == 'ガル接続' and u is not None and u.pos == '名詞'
                    and u.pos_sub.split(':')[0] == '接尾' and u.surface in ('さ', 'み', 'げ')):
                spots.add(i)
        if not t.has_reading:
            spots.add(i)
        # 文語の活用形（濃**し**と・深**し**は: 文語基本形）は今の文には出ない
        if t.pos == '形容詞' and '文語' in (t.infl_form or ''):
            spots.add(i)
        if i + 1 < len(toks):
            u = toks[i + 1]
            v = toks[i + 2] if i + 2 < len(toks) else None
            # 格助詞・係助詞の は・が・を に直に続く が・を・は・も（深しは**を**・雨がを）。をも（命をも）だけは正しい形
            if (t.pos == '助詞' and t.surface in ('は', 'が', 'を')
                    and u.pos == '助詞' and u.surface in ('が', 'を', 'は', 'も')
                    and (t.surface, u.surface) != ('を', 'も')):
                spots.add(i)
                spots.add(i + 1)
            # 形容詞の基本形に直に付いた格助詞の を・へ（て良い**を**: 形容詞に を は付かない）
            if (t.pos == '形容詞' and t.infl_form == '基本形' and u.pos == '助詞'
                    and u.pos_sub.startswith('格助詞') and u.surface in ('を', 'へ')):
                spots.add(i)
                spots.add(i + 1)
            # 文節の中の1字のかなのフィラー（運ど**え**かいで）。名詞の直後でなくても印
            if u.pos == 'フィラー' and len(u.surface) == 1 and _kana(u.surface):
                spots.add(i)
                spots.add(i + 1)
            # 名詞に付くはずの接頭詞の直後が助詞・助動詞・記号（前**お**が: お が名詞に付けない）
            if (t.pos == '接頭詞' and _kana_str(t.surface)
                    and u.pos in ('助詞', '助動詞', '記号')):
                spots.add(i)
                spots.add(i + 1)
            if i in sure:
                spots.add(i)
                spots.add(i + 1)
            # 動詞の基本形に直に付いた格助詞 に の後ろが、かなだけの自立語（書く**に**なして・書く**に**なんした: かくにん→
            # 書くに＋切れ端）。戻るには（に＋は）・見るに耐えない（に＋漢字の動詞）は正しい形
            if (t.pos == '動詞' and t.infl_form == '基本形' and t.pos_sub.split(':')[0] == '自立'
                    and u.pos == '助詞' and u.pos_sub.startswith('格助詞') and u.surface == 'に'
                    and v is not None and v.pos in ('動詞', '名詞', '形容詞') and _kana_str(v.surface)):
                spots.add(i)
                spots.add(i + 1)
                spots.add(i + 2)
            # サ変の名詞・形容動詞の語幹に直に付いた連体詞（研修**あの**申し込み・健康**あの**ために）。昨日あの店（副詞可能）・
            # 先生あの件（一般の名詞: 呼び掛け）は正しい形
            if (t.pos == '名詞' and sub in ('サ変接続', '形容動詞語幹') and u.pos == '連体詞'):
                spots.add(i)
                spots.add(i + 1)
            # 1字の し（する）に直に付いた非自立の い（縦の**しい**: たのしい→たてのしい）
            if (t.pos == '動詞' and t.surface == 'し' and u.pos == '動詞'
                    and u.pos_sub.split(':')[0] == '非自立' and u.surface == 'い'):
                spots.add(i)
                spots.add(i + 1)
            # 助動詞 だ に直に付いた非自立の名詞 ん（医科**だん**を: かいだん→いかだん）。だの・だよ は正しい形
            if (t.pos == '助動詞' and t.surface == 'だ' and u.pos == '名詞'
                    and u.pos_sub.split(':')[0] == '非自立' and u.surface == 'ん'):
                spots.add(i)
                spots.add(i + 1)
            # 終助詞に直に続く名詞・接頭詞（何**べ**料理・**よ**悪更かし: 終助詞は文を閉じる。文頭の終助詞も同じ）
            if (t.pos == '助詞' and t.pos_sub.startswith('終助詞') and len(t.surface) == 1
                    and u.pos in ('名詞', '接頭詞') and not (t.start > 0 and line_is_quote_boundary(toks, i))):
                spots.add(i)
                spots.add(i + 1)
            # 体言接続の な に直に付いた接続助詞 が（**なが**語彙て: ながびいて）
            if (t.pos == '助動詞' and t.infl_form == '体言接続' and t.surface == 'な'
                    and u.pos == '助詞' and u.pos_sub.startswith('接続助詞') and u.surface == 'が'):
                spots.add(i)
                spots.add(i + 1)
            # 代名詞でない名詞に直に付いた か の直後の格助詞（時間**か**が・画面**か**が）。
            # 何かが・誰かに・どこかで（代名詞＋か）は正しい形。本かノートを（並立: か の後ろは名詞）も印にしない
            if (t.pos == '名詞' and sub != '代名詞' and u.pos == '助詞' and u.surface == 'か'
                    and v is not None and v.pos == '助詞' and v.pos_sub.startswith('格助詞')):
                spots.add(i)
                spots.add(i + 1)
            if t.pos == '名詞' and _kana_str(u.surface) and (
                    (u.pos == '助動詞' and u.surface not in _COPULA)
                    or (u.pos == '動詞' and u.pos_sub.split(':')[0] in ('接尾', '非自立'))
                    or (u.pos == '助詞' and u.pos_sub.startswith('接続助詞'))
                    # 名詞に直に付いた1字のかなのフィラー（健康**え**診断・約束**ま**の）
                    or (u.pos == 'フィラー' and len(u.surface) == 1)
                    # 連体形の な の直後の格助詞（写真**な**を）。な の後ろに来るのは名詞か
                    # の・だけ・ので・のに（名詞・副助詞・接続助詞）で、格助詞は付かない
                    # 形容動詞の語幹でない名詞の な の後ろの、の・ん 以外の助詞（半分**な**くらい・
                    # 写真**な**が）。学生なので・学生なんだ・静かなくらい は印にしない
                    or (u.pos == '助動詞' and u.surface == 'な' and v is not None
                        and v.pos == '助詞' and (v.pos_sub.startswith('格助詞')
                                                or (sub != '形容動詞語幹'
                                                    and v.surface[:1] not in ('の', 'ん'))))
                    # 名詞に直に付いた1字の終助詞の後ろの の・格助詞（子供**ね**の頃・電話**よ**の）
                    or (u.pos == '助詞' and u.pos_sub.startswith('終助詞') and len(u.surface) == 1
                        and v is not None and v.pos == '助詞'
                        and v.pos_sub.startswith(('連体化', '格助詞')))):
                spots.add(i)
                spots.add(i + 1)
    return spots


_GRAMMAR_POS = ('助詞', '助動詞', '動詞', '形容詞', '接続詞', '記号')


def _reading_str(r):
    """IME の読みとして扱える並びか: かなだけ、またはかなに英字（母音の抜けで残った子音: かくにん**s**ます）が混じる。"""
    if _kana_str(r):
        return True
    rest = ''.join(c for c in r if not (c.isascii() and c.isalpha()))
    return len(rest) < len(r) and bool(rest) and _kana_str(rest)


def _ime_clauses(line, toks, dict_index=None, marks=()):
    """行の中の IME の確定の文節 → [(始まり, 終わり, 打った読み)]。

    今回の確定（`analysis_work` の出現）と、保存した対（文節ごと）から。
    漢字を含む文節だけ（かなだけの文節は上の紫の道が受け持つ）。
    """
    out = {}
    faces = {}
    try:
        from analysis_work import _INPUT
        active = _INPUT.get()
        if active and active[0] == line:
            for x in active[1]:
                if (line[x.start:x.end] == x.surface and _reading_str(x.reading)
                        and x.reading != x.surface and any(_kanji(c) for c in x.surface)):
                    out.setdefault((x.start, x.end), x.reading)
                    faces.setdefault((x.start, x.end), x.end)
    except Exception:
        pass
    from kanji_guess import _IME_READINGS_PROVIDER as prov
    if prov is not None:
        def probe(s, i):
            for j in range(i, min(len(toks), i + CLAUSE_TOKENS)):
                e = toks[j].end
                surf = line[s:e]
                if (s, e) in out or not any(_kanji(c) for c in surf):
                    continue
                # 文節の終わりが字句の途中で切れることがある（例そざうこ|の を
                # 辞書が ざうこの と1つに切る）。終わりの字句がかなだけなら、
                # その内側で切った顔も引き、残りのかなは打った読みに足す
                ends = [e]
                if _kana_str(toks[j].surface) and toks[j].end - toks[j].start >= 2:
                    ends += list(range(e - 1, toks[j].start, -1))
                for e2 in ends:
                    surf = line[s:e2]
                    if not any(_kanji(c) for c in surf):
                        break
                    try:
                        rds = [r for r in (prov(surf) or ()) if r and isinstance(r, str)]
                    except Exception:
                        rds = []
                    rds = [r for r in rds if _reading_str(r) and r != surf]
                    if rds:
                        out[(s, e)] = rds[0] + line[e2:e]
                        faces[(s, e)] = e2
                        break
        for i, t in enumerate(toks):
            probe(t.start, i)
            # 文節の始まりが字句の途中のこともある（にて｜医師とゅつ: IME は て医師とゅつ を1つの文節にした）。
            # 始まりの字句がかなだけなら、その内側から始まる顔も引く
            if _kana_str(t.surface) and t.end - t.start >= 2:
                for s0 in range(t.start + 1, t.end):
                    probe(s0, i)
    # 隣り合う文節をつないだ読み（詩と＋ゅうがく旅行の → しとゅうがくりょこうの）。巻き込んだ1打が文節の切れ目を作る
    # （IME は しとゅうがく を 詩と｜ゅうがく に切る）ので、2つをつないだ読みでも読み直す。
    # ただし、どちらかの文節に疑いの印が在るときだけ。印の無い隣り合う文節（設定を＋元に・今日＋中に）をつなぐと
    # 2語以上の文節に見え、1語ずつは正しい文節が行の重さだけで読み直されていた（正しい608行のうち4行が変わった:
    # 元に→ともに・今日中に→強調に）。印の無い文節は1語ずつのまま（1語に収まる文節は見ない: `split`）
    def marked_in(a, b):
        return any(a <= toks[i].start and toks[i].end <= b for i in marks)
    items = sorted(out.items())
    for (s1, e1), r1 in items:
        for (s2, e2), r2 in items:
            if s2 == e1 and (s1, e2) not in out and (marked_in(s1, e1) or marked_in(s2, e2)):
                out[(s1, e2)] = r1 + r2
                faces[(s1, e2)] = faces.get((s2, e2), e2)
    # 文節の直前のかなの切れ端（でんな＋稀代の → でんなきだいの）。語でないかなの並び（2〜4字）が疑いの印の文節の前に
    # 残る形は、切れ端の中の1打が IME の切れ目を作った跡なので、切れ端をつないだ読みでも読み直す。
    # 切れ端は文法の語（たら・いい・か／を・する・と）だけでは成らず、内容語に見えるかな（でん: 副詞）を含むこと
    # （らいいか閑雅て・をすると良くまじつの をつないで読み直し、本来の文節の試行の枠を使い切っていた）
    # つなぐのは、文節に IME が明示的に稀と判定した語（稀代）が在るか、切れ端そのものに疑いの印が在るときだけ。
    # ふつうの印の文節（帳い）の前のかな（いように）までつないで読み直すと、本来の文節（ちょうい→注意）の
    # 試行の枠（3つ・文節で共有）を使い切っていた
    for (s1, e1), r1 in items:
        inside = [i for i in marks if s1 <= toks[i].start and toks[i].end <= e1]
        if not inside:
            continue
        k = s1
        while k > 0 and _kana(line[k - 1]) and s1 - k < 4:
            k -= 1
        frag = line[k:s1]
        frag_idx = [i for i, t in enumerate(toks) if k <= t.start and t.end <= s1]
        rare_in = any(toks[i].pos == '名詞' and len(toks[i].surface) == 2
                      and _kanji_seq(toks[i].surface) == toks[i].surface and _restricted_face(toks[i].surface)
                      for i in inside)
        if (len(frag) >= 2 and (k, e1) not in out and dict_index is not None
                and (rare_in or any(i in marks for i in frag_idx))
                and not dict_index.is_world_reading(frag)
                and any(_kana_str(toks[i].surface) and toks[i].pos not in _GRAMMAR_POS for i in frag_idx)):
            out[(k, e1)] = frag + r1
            faces[(k, e1)] = faces.get((s1, e1), e1)
    return [(s, e, r, faces.get((s, e), e)) for (s, e), r in sorted(out.items())]


def _ime_head_kept(face, typed, new_reading, store, dict_index):
    # IME の顔の先頭にかなのまま残った小書きの1字（が**っ**好きだ・**っ**天気予報: IME は っ をかなのまま残し、
    # 続きだけ変換した）を抜く戻し。小書きの字は語の頭に立てないので余りの印として確か。普通のかな（**れ**研修・
    # **い**上）は語の一部でもありうる（れけんしゅう→れんしゅう・いうえ→いえ）ので見ない（し半分 と同じ）。
    # 戻した読みが打った読みの先頭1字を抜いたもので、顔がその字＋漢字で始まり、語の漢字が戻した読みの語の辞書の
    # 表記にあるなら、語の漢字は IME のまま先頭の字だけ抜いた形（好きだ）。語の中や語と付属の間は _ime_word_kept
    if len(face) < 3 or len(typed) < 3 or new_reading != typed[1:]:
        return None
    if face[0] not in 'ぁぃぅぇぉっゃゅょゎ' or face[0] != typed[0] or not _kanji(face[1]):
        return None
    body = face[1:]
    tail = _kana_tail(body, limit=len(body) - 1)
    # 語の表記＋付属の切り方は、付属を短い方から（好き＋だ・好＋きだ は 好 が表記でないので外れる）
    for t in range(0, len(tail) + 1):
        head, rest = body[:len(body) - t], body[len(body) - t:]
        if t and not new_reading.endswith(rest):
            continue
        word = new_reading[:len(new_reading) - t] if t else new_reading
        if not word:
            continue
        try:
            faces = _kanji_choices(word, store, dict_index)
        except Exception:
            return None
        if head in faces and _face_attaches(head, rest):
            other = _ime_face(word, rest, faces)
            return (other if other else head) + rest
    return None


def _ime_tail_kept(face, typed, new_reading):
    """IME の顔の漢字（語）はそのまま残し、かなの末尾（送りがな・付属）だけを戻した読みに合わせた形。
    顔のかなの末尾が打った読みの末尾と同じで、戻しがその末尾の中にあるとき（遅く**う**なり→遅くなり・
    懐かし**う**なった→懐かしくなった・多**う**なる→多くなる）。語の読み（頭）は変えない。無ければ None。"""
    tail = _kana_tail(face, limit=len(face))
    if not tail or len(tail) >= len(face) or not typed.endswith(tail):
        return None
    head = face[:len(face) - len(tail)]
    if not any(_kanji(c) for c in head):
        return None
    head_reading = typed[:len(typed) - len(tail)]
    if not head_reading or not new_reading.startswith(head_reading):
        return None
    new_tail = new_reading[len(head_reading):]
    if not new_tail or new_tail == tail or not _kana_str(new_tail):
        return None
    # 漢字の頭と新しい末尾の先頭が1語の用言（遅＋く・懐か＋しく・多＋く・難し＋くて）になること。名詞の頭に別の語が
    # 続く形（外科＋じかんの）は IME の語を残す根拠が無い（試行の枠を使って正しい戻し 玄関 が外れた）
    import morphology
    try:
        toks = list(morphology.tokenize(head + new_tail))
    except Exception:
        return None
    if not toks or toks[0].start != 0:
        return None
    if toks[0].end > len(head) and toks[0].pos in ('動詞', '形容詞'):
        return head + new_tail
    if (toks[0].end == len(head) and toks[0].pos == '名詞' and (toks[0].pos_sub or '').startswith('サ変接続')
            and len(toks) > 1 and toks[1].pos == '動詞' and toks[1].base_form == 'する'):
        # サ変の名詞＋する（確認＋します: 確認し**あ**す→確認します・確認**ひ**ます→確認します）
        return head + new_tail
    return None


def _kana_tail(face, limit=4):
    """顔の末尾のひらがな（limit 字まで: ました・て・までの）。無ければ ''。"""
    n = 0
    while n < len(face) and n < limit and _kana(face[-1 - n]):
        n += 1
    return face[len(face) - n:] if n else ''


def _rough_convert(reading, store, dict_index, nth=0):
    """読みを辞書で粗く漢字に（左から最長一致・ふつうの語だけ・1字はかなのまま）。

    並びの費用を比べて候補を絞るためだけ。置く形は補正の入口が決める。
    `nth` は同じ読みの語が複数あるとき何番目の形を使うか（足りなければ最後）。
    """
    out = ''
    i = 0
    while i < len(reading):
        best = None
        for j in range(len(reading), i + 1, -1):
            seg = reading[i:j]
            faces = []
            try:
                faces = [e['surface'] for e in store.lookup(seg) if not _kana_str(e['surface'])]
            except Exception:
                pass
            if not faces and dict_index is not None:
                try:
                    faces = [f for f in dict_index.surfaces_for_reading(seg, band=False)
                             if not _kana_str(f)]
                except Exception:
                    pass
            if not faces and dict_index is not None and len(seg) >= 3:
                # 索引の帯（費用の線）の外にしか無い語（提出・電気）も、3字以上の読みなら粗い変換に使う。
                # 帯の外の読みはかなのまま残って費用が高く、正しい戻し（ていしゅつして）が試行の枠に入らなかった。
                # 珍しい語（kango_tier の制限）は使わない。置く形は入口が決める
                try:
                    faces = [f for f in dict_index.surfaces_for_reading(seg, band=True)
                             if not _kana_str(f) and not _restricted_face(f)]
                except Exception:
                    pass
            if len(seg) < 3:
                # 2字の読みは漢字の表記だけ（付属の読み ます・した をカタカナの語 マス にしない）
                faces = [f for f in faces if any(_kanji(c) for c in f)]
            if faces:
                best = (j, faces[min(nth, len(faces) - 1)])
                break
        if best is None:
            out += reading[i]
            i += 1
        else:
            out += best[1]
            i = best[0]
    return out


def _known_kana_word(face, clause, typed, dict_index, tail=3, inflected=False):
    """かなの顔が「世の中に在る語の読み（3字以上）＋手を付けていない付属」か。

    入口が漢字にしない語（冷蔵庫・大好き など、かなで書くのも普通の語）は
    かなのまま残るので行の費用は高いまま。辞書に在る読みなら、費用の線を
    越えていても採る。語を名指しせず、辞書の有無だけで決める。
    付属（≤tail 字）は元の文節・打った読みの末尾と同じであること
    （あめふり＋がの のように、戻した字を付属に数えて語を作らない）。
    """
    if dict_index is None or not _kana_str(face):
        return False
    for k in range(len(face), 1, -1):
        rest = face[k:]
        if rest and not _untouched_tail(rest, clause, typed):
            if len(rest) > tail:
                break
            continue
        try:
            if k >= 3 and dict_index.is_world_reading(face[:k]):
                return True
            # 用言の活用形（うえ＋た・とっ＋た）は世の中の読みの表に無い。
            # 活用形の表に顔があれば語と見る（2字の語幹から）
            if inflected and dict_index.inflected_surfaces_for_reading(face[:k]):
                return True
        except Exception:
            return False
    return False


def _untouched_tail(rest, clause, typed):
    """かなの顔の末尾 `rest` が、元の文節と打った読みの末尾そのまま（読み直しが手を付けていない付属）か。

    付属の長さの上限（tail）は、戻した字を付属に数えて語を作らないための目安だった。元の文節と打った読みの
    両方の末尾と同じ並びなら、長くても手を付けていない付属（ていしゅつ＋してください）
    """
    return clause.endswith(rest) and typed.endswith(rest)


def _kana_word_split(face, clause, typed, dict_index, tail=4):
    """_known_kana_word と同じ条件で、顔を（語の部分, 付属）に割る。割れなければ None。
    付属は元の文節・打った読みの末尾そのまま（長さは tail まで。それより長くても末尾そのままなら許す）。"""
    if dict_index is None or not _kana_str(face):
        return None
    for k in range(len(face), 1, -1):
        rest = face[k:]
        if rest and not _untouched_tail(rest, clause, typed):
            if len(rest) > tail:
                break
            continue
        try:
            # 読み2字の語（なつ・よる）は、手を付けていない付属（は・に）が
            # 付いているときだけ語と見る（2字だけの並びはどれかの語の読みになりやすい）。
            # 付属が語に付く形かは置く表記ごとに見る（_face_attaches）
            if (k >= 3 or rest) and dict_index.is_world_reading(face[:k]):
                return face[:k], rest
            if dict_index.inflected_surfaces_for_reading(face[:k]):
                return face[:k], rest
        except Exception:
            return None
    # 辞書の読みの表のどの切り方にも無ければ、同梱の語の表に漢字の表記のある読み4字以上の語（でんきだい→電気代）。
    # 辞書の切り方（ちょうせん＋し）の後に見る（先に見ると ちょうせんし→朝鮮史 のような表の組み立ての語を取る）。
    # 表は展開せず、引いて覚えた分（候補を並べる前にまとめて引く）だけを見る
    for k in range(len(face), 3, -1):
        rest = face[k:]
        if rest and not _untouched_tail(rest, clause, typed):
            if len(rest) > tail:
                break
            continue
        if _seed_cached_kanji(face[:k]):
            return face[:k], rest
    return None


def _seed_cached_kanji(reading):
    """同梱の語の表から引いて覚えた分（_SEED_CACHE）に、この読みの漢字の表記が在るか。表は展開しない。"""
    rows = _SEED_CACHE.get(reading)
    if not rows:
        return False
    return any(c > 0 and _kanji_seq(f) and all(_kanji(ch) or _kana(ch) for ch in f) for f, c in rows)


def _seed_split_queries(face, clause, typed, tail=4):
    """_kana_word_split の同梱の表の読み（4字以上）の候補: まとめて引くために先に並べる。"""
    out = []
    if not _kana_str(face):
        return out
    for k in range(len(face), 3, -1):
        rest = face[k:]
        if rest and not _untouched_tail(rest, clause, typed):
            if len(rest) > tail:
                break
            continue
        out.append(face[:k])
    return out


def _face_attaches(kanji, rest):
    """置いた表記に付属が付く形か（置いた形を字に切って見る）。
    表記と付属で1語（懐かし＋く・掛かれ＋た）か、表記の直後が助詞・助動詞・する
    （図書館＋で・兆＋された）なら付く。名詞に れる が続く形（調査＋れた）は付かない。
    用言の語幹（書か）には れる・られる・せる も付く。"""
    if not rest:
        return True
    import morphology
    try:
        tokens = list(morphology.tokenize(kanji + rest))
    except Exception:
        return True
    edge = len(kanji)
    for i, t in enumerate(tokens):
        if t.start < edge < t.end:
            return t.start == 0
        if t.start == edge:
            if t.pos in ('助詞', '助動詞'):
                return True
            if t.pos == '動詞':
                base = t.base_form or ''
                if base == 'する':
                    return True
                if i > 0 and tokens[i - 1].pos in ('動詞', '形容詞') \
                        and base in ('れる', 'られる', 'せる', 'させる'):
                    return True
            return False
    return True


_SEED_COST_FILE = 'seed_japanese_cost.txt.gz'
PLACE_FAR = 4000  # 行の費用がこれ以上重い表記は形が合わない（_place_kanji）
PLACE_MARGIN = 1000   # 並んだ漢字の表記を行の費用で決めるときの、2番目との差
SEED_GAP = 50         # 同梱の表にしか無い表記を、表の最安より重いとき外す差
PLACE_CHOICES = 12    # 行の費用で比べる表記の数


_SEED_CACHE = {}          # 読み → ((表記, 費用), ...)。引いた分だけ覚える
_SEED_CACHE_MAX = 4096
_SEED_TABLE = None        # (展開した表, 各行の先頭位置)。メモリ使用量「低」でなければ1度展開して持つ（約 15MB）


def _seed_data():
    import gzip
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), _SEED_COST_FILE)
    try:
        with gzip.open(path, 'rb') as f:
            return f.read()
    except Exception:
        return b''


def _seed_hold():
    """展開した表を持ち続けるか。メモリ使用量「低」（compact_tables が効いている）のときは持たず、呼ぶたびに展開する。"""
    try:
        import compact_tables
        return not compact_tables.enabled()
    except Exception:
        return True


def _seed_table():
    """(展開した表, 各行の先頭位置の並び)。表の行は読みの順に並び読みは重複しない（seed_japanese_build）ので二分探索で引ける。

    展開 0.07 秒・先頭位置の並び 0.05 秒。1行ずつ探す（1読み 5ms・1行の読み直しで 100 読み以上）
    のをやめるための持ち方。持たない設定（メモリ「低」）でも、呼ぶたびに作って二分探索する。
    """
    global _SEED_TABLE
    if _SEED_TABLE is not None:
        return _SEED_TABLE
    import re
    from array import array
    data = _seed_data()
    starts = array('I')
    if data:
        starts.append(0)
        for m in re.finditer(b'\n', data):
            if m.end() < len(data):
                starts.append(m.end())
    table = (data, starts)
    if _seed_hold():
        _SEED_TABLE = table
    return table


def _seed_find(table, reading):
    """表の中で その読みの行の (始まり, 終わり) を二分探索で返す。無ければ None。UTF-8 の並びは文字の並びと同じ。"""
    data, starts = table
    head = reading.encode('utf-8')
    lo, hi = 0, len(starts)
    while lo < hi:
        mid = (lo + hi) // 2
        s = starts[mid]
        t = data.find(b'\t', s)
        if t < 0:
            t = len(data)
        key = data[s:t]
        if key < head:
            lo = mid + 1
        elif key > head:
            hi = mid
        else:
            e = data.find(b'\n', t)
            return s, (e if e >= 0 else len(data))
    return None


def _seed_parse(table, reading):
    """表からその読みの行を引いて ((表記, 費用), ...)（費用の小さい順）。無ければ ()。"""
    found = _seed_find(table, reading)
    if found is None:
        return ()
    start, end = found
    line = table[0][start:end].decode('utf-8', 'replace')
    out = []
    for part in line.split('\t')[1:]:
        surface, _, cost = part.rpartition(':')
        try:
            out.append((surface, int(cost)))
        except ValueError:
            pass
    return tuple(sorted(out, key=lambda x: x[1]))


def _seed_remember(reading, rows):
    if len(_SEED_CACHE) >= _SEED_CACHE_MAX:
        _SEED_CACHE.clear()
    _SEED_CACHE[reading] = rows


def _seed_prefetch(readings):
    """複数の読みをまとめて引いておく（候補を並べるときに使う）。"""
    need = [r for r in dict.fromkeys(readings) if r and r not in _SEED_CACHE]
    if not need:
        return
    table = _seed_table()
    for r in need:
        _seed_remember(r, _seed_parse(table, r))


def _seed_surfaces(reading):
    """同梱の語の表（seed_japanese_cost・SudachiDict 由来）から 読み → ((表記, 費用), ...)。

    費用の小さい順。表は1度展開して持ち（メモリ「低」では持たない・_seed_table）、
    読みの行を二分探索で引く。引いた読みは覚える（_SEED_CACHE）。無ければ ()。
    """
    if reading in _SEED_CACHE:
        return _SEED_CACHE[reading]
    rows = _seed_parse(_seed_table(), reading)
    _seed_remember(reading, rows)
    return rows


def _pick_by_context(faces, context_vec, surrounding):
    if len(faces) == 1:
        return faces[0]
    if context_vec is None or not surrounding:
        return None
    try:
        return context_vec.pick_best_by_context(list(faces), list(surrounding)) or None
    except Exception:
        return None


def _kanji_faces(seq):
    # 漢字＋ひらがなだけの表記（カタカナ・記号・絵文字混じりの表記は見ない）
    out = []
    for f in seq:
        if (f and any(_kanji(c) for c in f) and f not in out
                and all(_kanji(c) or _kana(c) for c in f)):
            out.append(f)
    return out


def _own_faces(word, store):
    """本人の語彙にあるこの読みの漢字の表記（使った回数の多い順）。"""
    try:
        entries = sorted((e for e in store.lookup(word) if e.get('surface')),
                         key=lambda e: -e.get('count', 0))
        return _kanji_faces(e['surface'] for e in entries)
    except Exception:
        return []


def _kanji_choices(word, store, dict_index):
    """読み直してかなのまま残った語の、漢字の表記の候補（一般的な順・送りがな違いはまとめる）。

    順: 本人の語彙 → 辞書の索引（名詞）→ 帯の2字漢語 → 活用形の表 → 同梱の語の表。
    語は名指ししない。
    """
    kanji_faces = _kanji_faces

    def settle(faces, seed_cost, seed_only):
        # 並んだ表記が同じ漢字の並びの送りがな違い（大好き・大すき、引っ越し・引越し、打ち合わせ・打合せ・打ちあわせ）
        # なら1つに。残す形: 辞書・索引・本人の語彙に在る形を、同梱の表にしか無い形（新らしい・楽い・逃がし）より先
        # → 表記1つの行の費用（入口の尺度）が最も軽い形と PLACE_MARGIN 未満の差の形（変わら 6016 対 変ら 7223・
        # 楽し 3260 対 楽 5144 は差で決まる）→ 同梱の表の費用が最も安い形（打ち合わせ 98 対 打合せ 106・受け取り
        # 115 対 受けとり 144。表の 0 は費用ではない: 聞く 0・変わら 0）→ 先頭（一般的な順: 夕立 = 夕立ち）。
        # 漢字の並びが違う表記はそれぞれ残す（漢字の多い表記にまとめない: 懐かしく を 可懐しく にまとめて
        # 珍しい表記だけが残った）
        if len(faces) <= 1:
            return faces
        import morphology
        groups, order = {}, []
        for f in faces:
            k = ''.join(c for c in f if _kanji(c))
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(f)
        out = []
        for k in order:
            g = groups[k]
            if len(g) == 1:
                out.append(g[0])
                continue
            cands = [f for f in g if f not in seed_only]
            if not cands:
                # 同梱の表にしか無い形だけの並び（焼き肴・焼肴、夕立・夕立ち）は表の順の先頭。表記1つの行の費用は
                # 短い形を安く見る（焼肴 5339 対 焼き肴 12049）ので、ここでは比べない
                out.append(g[0])
                continue
            pc = {}
            for f in cands:
                try:
                    pc[f] = morphology.path_cost(f)
                except Exception:
                    pc[f] = None
            known = [f for f in cands if pc[f] is not None]
            if known:
                floor = min(pc[f] for f in known)
                cands = [f for f in known if pc[f] - floor < PLACE_MARGIN]
            out.append(min(cands, key=lambda f: (seed_cost.get(f) or 10 ** 9, g.index(f))))
        return out
    # 本人の語彙の表記を先頭に、辞書の表記も並べる（本人の語彙だけに絞ると、同じ読みの
    # 別の語（うえ: 上 と 植え）が置けない。並んだときは呼ぶ側が本人の表記を優先する）
    pool = list(_own_faces(word, store))
    for band in (False, True):
        try:
            pool += kanji_faces(dict_index.surfaces_for_reading(word, band=band))
        except Exception:
            pass
    try:
        pool += kanji_faces(dict_index.inflected_surfaces_for_reading(word))
    except Exception:
        pass
    # 同梱の語の表は表記の出どころとして使う（索引に無い語: 冷蔵庫・夏・夜）。
    # 表の費用で1つに絞らない（返る 134・変える 135・帰る 135、聞く 0・選 0 のように
    # 使われ方を映さず、絞ると正しい読みに誤った漢字を置く）。ただし表にしか無い表記で、
    # 表の中で最も安い表記より SEED_GAP 以上重いもの（夏 65 に対する 捺 136・做つ 163）は
    # 珍しい表記として外す。残った表記は呼ぶ側が文脈と行の費用で決め、決め手が無ければかなのまま
    seed = _seed_surfaces(word)
    known = set(pool)
    costs = [c for f, c in seed if c > 0]
    floor = min(costs) if costs else None
    seed_only = {f for f, _c in seed} - known
    pool += [f for f, c in seed if c > 0 and (f in known or floor is None or c - floor < SEED_GAP)]
    pool += [f for f, c in seed if c <= 0]
    if not pool:
        # 索引に表記の無い長い語（修学旅行: 費用で索引から落ちた）は、辞書の語の組み立てから
        pool = _compound_faces(word, store, dict_index)
    return settle(kanji_faces(pool), {f: c for f, c in seed if c > 0}, seed_only)[:PLACE_CHOICES]


def _kept_stem_query(face, reading, new_reading, dict_index=None, tail=4):
    """_ime_stem_kept が引く (語幹の表記, 新しい活用の読み, 新しい語の読み, 手を付けていない続き)。無ければ None。

    IME の顔が 漢字を含む語幹＋かなの付属（温か＋て・寒＋す）で、1打戻した読みが語幹の読みを
    変えず付属の中だけ変わるとき（あたたか＋い・さむ＋い）。付属の長さは同じ（置き換え・入れ替え）。
    戻した読みが辞書の語（活用形を含む）の読みであること（種表を引く前に辞書で絞る。種表は読み1つに
    0.1 秒ほど掛かるので、語でない読み（ちょうせか）では引かない）。"""
    if (not reading or not new_reading or len(new_reading) != len(reading)
            or new_reading == reading or _kana_str(face)):
        return None
    k = len(face)
    while k > 0 and _kana(face[k - 1]):
        k -= 1
    head, old_tail = face[:k], face[k:]
    if (not head or not old_tail or len(old_tail) > tail or _kana_str(head)
            or not any(_kanji(c) for c in head) or not reading.endswith(old_tail)):
        return None
    stem = reading[:len(reading) - len(old_tail)]
    if not stem or not new_reading.startswith(stem):
        return None
    new_tail = new_reading[len(stem):]
    if new_tail == old_tail or not _kana_str(new_tail):
        return None
    # 付属を、語の活用の部分と手を付けていない続き（聞**く**ながら→聞**き**＋ながら）に分ける:
    # 語幹＋活用の読みが辞書の語（活用形を含む）で、続きは元の読みと同じであること
    for j in range(len(new_tail), 0, -1):
        rest = new_tail[j:]
        if rest and old_tail[j:] != rest:
            continue
        word = stem + new_tail[:j]
        if dict_index is not None:
            try:
                if not (dict_index.is_world_reading(word)
                        or dict_index.inflected_surfaces_for_reading(word)):
                    continue
            except Exception:
                return None
        return head, new_tail[:j], word, rest
    return None


def _ime_stem_kept(face, reading, new_reading, store, dict_index, info=None):
    """IME の顔の語幹の漢字を残し、付属の1打だけ戻した形（寒**す**→寒い・温か**て**→温かい）。
    その形が戻した読みの辞書の表記であること（良い**て**→よてい は 良てい にならないので無し）。
    `_ime_word_kept`（余った1字を抜く形）の、付属の中の置き換え・入れ替えの版。
    本人の IME が戻した読みで別の表記を出すならそちら（温かい/暖かい）。無ければ None。
    info（dict）を渡せば、語の読みに辞書の表記が複数あって IME にも聞けなかった（雨あがり/雨上がり）ことを
    info['ambiguous'] に入れる（呼ぶ側はそのとき、かなに戻して入口が自ら変換した形も見る）。"""
    q = _kept_stem_query(face, reading, new_reading, dict_index)
    if not q:
        return None
    head, new_infl, word, rest = q
    try:
        faces = _kanji_choices(word, store, dict_index)
    except Exception:
        return None
    own = head + new_infl
    if own not in faces:
        return None
    other = _ime_face(word, rest, faces)
    if info is not None:
        info['ambiguous'] = other is None and len([f for f in faces if not _kana_str(f)]) >= 2
    if other and other != own:
        return other + rest
    return own + rest


def _ime_face(word, rest, faces):
    """IME に戻した読みを変換させ、辞書で許した表記（faces）の中にその顔があればそれ。

    同じ読みの表記が並んだとき、行の費用・同梱の表・判定の段はどれも「どちらが
    ふつうに書かれるか」を映さない（楽しい/愉しい・歌う/唄う・親戚/浸せき）。
    打った本人の IME は使われ方と本人の学習を持つので、打ち直して変換したときに
    出る顔を聞く。IME の変換を直しそのものにはしない: 選ぶのは辞書の表記の中だけで、
    置いた形はこれまでどおり共通の最終検査を受ける。IME が無ければ None（従来どおり）。
    付属（rest）が付く語は付属ごと聞く（うえ＋た → 植えた。語だけで聞くと 上 が返り、
    上た を置いてしまう）。
    """
    if len(faces) < 2 or not word:
        return None
    try:
        from ime_language import JapaneseIME
    except Exception:
        return None
    try:
        with JapaneseIME() as ime:
            if not getattr(ime, 'available', False):
                return None
            out = ime.convert(word + rest)
            if not out or not out.endswith(rest):
                return None
            out = out[:len(out) - len(rest)] if rest else out
            if out in faces:
                return out
    except Exception:
        return None
    return None


def _kanji_for_kana(word, store, dict_index, context_vec, surrounding):
    """表記が1通りならそれ、複数なら文脈に決め手があるもの、無ければ本人の語彙の表記
    （本人の語彙にも無ければ None）。"""
    faces = _kanji_choices(word, store, dict_index)
    if not faces:
        return None
    picked = _pick_by_context(faces, context_vec, surrounding)
    if picked:
        return picked
    picked = _ime_face(word, '', faces)
    if picked:
        return picked
    own = _own_faces(word, store)
    return own[0] if own else None


def _morae(reading):
    """読みの拍の数（ちょう＝2、きって＝3）。小書きの ゃゅょ・ぁぃぅぇぉ は前の字に付く。"""
    return sum(1 for c in reading if c not in 'ゃゅょぁぃぅぇぉゎヶ')


def _familiar_kango(face):
    """置いた顔（漢字＋付属）の先頭の漢字の語が、漢語の層の1番（ふつうの語）か。"""
    head = face[:next((i for i, c in enumerate(face) if not _kanji(c)), len(face))]
    if not head:
        return False
    try:
        import kango_tier
        return kango_tier.tier(head) == 1
    except Exception:
        return False


def _katakana_str(text):
    return bool(text) and all('ァ' <= c <= 'ヺ' or c == 'ー' for c in text)


def _to_hira(text):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in text)


def _tok_reading(t):
    r = t.reading if getattr(t, 'has_reading', True) else ''
    return r if r and _kana_str(r) else _to_hira(t.surface)


def _used_entry(e):
    # 本人が使った語の記録か。辞書から取り込んだだけで使っていない語（world 付きで立っていない）は違う
    try:
        from vocabulary import entry_is_solid
        return bool(e.get('surface')) and (entry_is_solid(e) or 'world' not in e)
    except Exception:
        return False


def _her_word(store, reading, surface):
    """本人がこの語（読みと表記）を使ったことがあるか（店の記録）。"""
    try:
        return any(e.get('surface') == surface and _used_entry(e) for e in store.lookup(reading))
    except Exception:
        return False


def _her_faces(store, reading):
    """本人が使った、この読みの語の表記（店の並び順）。"""
    try:
        return [e['surface'] for e in store.lookup(reading) if _used_entry(e) and len(e['surface']) >= 2]
    except Exception:
        return []


def _rare_kango(face):
    """顔の先頭の語が2字の漢語の名詞で、層が 2 以上（珍しい語: 潅漑・如何・定見）か。
    1字の語（考え・撮っ）や、漢字2字から始まる用言（美味しい・勉強する）は違う。"""
    head = face[:next((i for i, c in enumerate(face) if not _kanji(c)), len(face))]
    if len(head) != 2:
        return False
    try:
        import kango_tier
        import morphology
        if kango_tier.tier(head) < 2:
            return False
        first = next(iter(morphology.tokenize(face)), None)
        return first is not None and first.pos == '名詞'
    except Exception:
        return False


def _not_everyday_kango(face):
    """顔の先頭の語が2字の漢語の名詞で、身近さの表に判定が無い（遥遠・浴槽）か、層2以上（医科・嫌忌・按針）か。
    漢語でない語（夏休み・旅先・夕立）は違う（_kango_noun_head）。"""
    head = _kango_noun_head(face)
    if head is None:
        return False
    try:
        import kango_tier
        return kango_tier.known_usage_tier(head) != 1
    except Exception:
        return False


def _kango_reads_as(face, word):
    # 顔の先頭が2字の漢語の名詞なら、解析器がその語をこの読み（word の先頭）で読むか。読みが違う漢語（冊子＝サッシ を
    # ふみ に置く）は、表記が身近でもその読みでは珍しいので置かない。漢語でない顔（踏み・夕立）は見ない（True）
    head = _kango_noun_head(face)
    if head is None:
        return True
    import morphology
    try:
        toks = list(morphology.tokenize(head))
    except Exception:
        return True
    reading = ''.join((_tok_reading(t) or '') for t in toks)
    if not reading:
        return True
    return word.startswith(reading) or reading.startswith(word)


def _unjudged_kango(face):
    """顔の先頭の語が2字の漢語の名詞で、身近さの表（kango_tier）に判定が無い（遥遠・浴槽）か。
    表に在る語（時間 1・医科 2・按針 3）と漢語でない語（夕立・夏休み）は違う。"""
    head = _kango_noun_head(face)
    if head is None:
        return False
    try:
        import kango_tier
        return kango_tier.known_usage_tier(head) is None
    except Exception:
        return False


def _kango_noun_head(face):
    """顔の先頭が2字の漢語の名詞（音読みの語: 時間・医科・玄関）なら、その2字。

    身近さの表（kango_tier）が受け持つのは漢語なので、送りがなの付く語（大好き・夏休み・昼休み）と訓で読む語
    （旅先・夕立・親子）は None（表に無くても、層が付いていても、身近でないとは見ない）。2字の漢字から始まる
    用言（美味しい・勉強する は名詞＋する）も違う。辞書が1語と見ない2字（分注 → 分＋注）は語でない組み立てなので
    2字を返す（身近でない語と同じに扱う）。
    """
    head = face[:next((i for i, c in enumerate(face) if not _kanji(c)), len(face))]
    if len(head) != 2:
        return None
    try:
        import morphology
        first = next(iter(morphology.tokenize(face)), None)
    except Exception:
        return None
    if first is None:
        return None
    reading = getattr(first, 'reading', None) or ''
    if len(first.surface) < 2 or (first.surface == head and not _kana_str(reading)):
        # 辞書が1語と見ない2字（分注 → 分＋注）・辞書に無い2字（聞集: 読みが表記のまま）
        return head
    if first.pos != '名詞' or first.surface != head:
        return None
    if not _on_on_reading(head, reading):
        return None
    return head


def _on_on_reading(head, reading):
    """2字の漢字 head の読みが 音読み＋音読み（漢語の形）と見られるか。

    読みをどこかで2つに切り、どちらも kanji_onkun.is_on_reading（表の印、印が無ければ音読みの形）が通れば漢語。
    どう切っても片方が訓（たび・なつ・ひる・ゆう）なら違う。表が無ければ漢語と見る（表の穴で語を外さない側）。
    """
    try:
        import kanji_onkun
        if not kanji_onkun.available():
            return True
        for i in range(1, len(reading)):
            if kanji_onkun.is_on_reading(head[0], reading[:i]) and kanji_onkun.is_on_reading(head[1], reading[i:]):
                return True
        return False
    except Exception:
        return True


def _restricted_face(face):
    """表記（漢字の部分）が AI の明示的な判定で「稀」とされた語か（現官・安神・呈出・溶存・稀代）。
    表に無いだけの語（看板・電気）は稀としない（kango_tier.is_restricted）。"""
    head = ''.join(c for c in face if _kanji(c))
    if not head:
        return False
    try:
        import kango_tier
        return bool(kango_tier.is_restricted(face) or (head != face and kango_tier.is_restricted(head)))
    except Exception:
        return False


_COMPOUND_CACHE = {}


def _part_faces(reading, store, dict_index, limit=4):
    """組み立ての部品: 本人の語彙と索引（帯を含む）のこの読みの漢字の表記（稀と判定された語は除く）。"""
    faces = list(_own_faces(reading, store))
    for band in (False, True):
        try:
            faces += _kanji_faces(dict_index.surfaces_for_reading(reading, band=band))
        except Exception:
            pass
    out = []
    for f in faces:
        if f not in out and not _restricted_face(f):
            out.append(f)
    return out[:limit]


def _compound_faces(word, store, dict_index):
    """索引に表記の無い長い読み（しゅうがくりょこう: 費用で索引から落ちた語）の表記を、辞書の語2つの読みに割った
    表記の組み合わせ（修学＋旅行・就学＋旅行）のうち、解析器が1語の名詞と読み、読みも一致するもの（修学旅行）から作る。
    語は名指ししない。"""
    if dict_index is None or len(word) < 4 or not _kana_str(word):
        return []
    if word in _COMPOUND_CACHE:
        return list(_COMPOUND_CACHE[word])
    import morphology
    out = []
    for k in range(2, len(word) - 1):
        fa = _part_faces(word[:k], store, dict_index)
        if not fa:
            continue
        fb = _part_faces(word[k:], store, dict_index)
        for x in fa:
            for y in fb:
                face = x + y
                if face in out:
                    continue
                try:
                    toks = list(morphology.tokenize(face))
                except Exception:
                    continue
                if (len(toks) == 1 and toks[0].pos == '名詞' and not toks[0].pos_sub.startswith('固有名詞')
                        and _tok_reading(toks[0]) == word):
                    out.append(face)
    if len(_COMPOUND_CACHE) >= 2048:
        _COMPOUND_CACHE.clear()
    _COMPOUND_CACHE[word] = tuple(out)
    return out


def _best_face_cost(text, s, e_text, word, rest, store, dict_index, limit=6):
    """置く表記に決め手が無いときの、費用の見込み: 並ぶ表記（稀と判定された語は除く）の中で最も安い行の費用。"""
    import morphology
    best = None
    for f in _kanji_choices(word, store, dict_index)[:limit]:
        if _restricted_face(f) or not _face_attaches(f, rest):
            continue
        c = morphology.path_cost(text[:s] + f + rest + text[e_text:])
        if c is not None and (best is None or c < best):
            best = c
    return best


def _inserts_into_her_word(typed, new_reading, s, e, toks, store):
    """1字足した読み直しが、本人の使っている語（IME の顔が漢字の語で、打った読みそのもの: 補正・候補）の中に
    字を足して別の語にする形か（ほせい→ほうせい→方正・こうほ→こうほう→後方）。正しく打てた本人の語は足しで替えない。
    文法で確かな印の文節（閑雅て→考えて）は呼ぶ側が除く。"""
    if len(new_reading) != len(typed) + 1:
        return False
    i = 0
    while i < len(typed) and typed[i] == new_reading[i]:
        i += 1
    off = 0
    for t in toks:
        if t.start < s or t.end > e:
            continue
        r = _tok_reading(t)
        if (r and t.surface and _kanji_seq(t.surface) == t.surface and off < i <= off + len(r)
                and _her_word(store, r, t.surface)):
            return True
        off += len(r)
    return False


def _row_reading(row, line):
    """読み直しの候補（found の行）の、読み直した文節の読み（かなに戻した行の、文節の所）。"""
    s_, e_, text = row[1], row[2], row[3]
    return text[s_:len(text) - (len(line) - e_)]


def _face_rank(row, line, store):
    """並んだ読み直しの候補の、置いた語の一般さの順位（小さいほど先）: 本人の使った語 → AI 判定の段1 → 段2 →
    表に無い語 → 稀と判定された語。"""
    s_, e_, text, got = row[1], row[2], row[3], row[4]
    corrected = got.get('corrected', text)
    new_e = len(corrected) - (len(line) - e_)
    face = corrected[s_:new_e]
    word = got.get('placed_word')
    if word and _her_word(store, *word):
        return -1
    head = ''.join(c for c in face if _kanji(c))[:2]
    if not head:
        return 2
    reading = word[0] if word else None
    if not reading:
        try:
            import morphology
            toks_ = [t for t in morphology.tokenize(face) if _kanji_seq(t.surface)]
            reading = _tok_reading(toks_[0]) if toks_ else None
        except Exception:
            reading = None
    if reading:
        order, _dom = _everyday_order(reading)
        if order and head in order:
            return -0.5 + order.index(head) / (len(order) + 1)   # 表に在る表記は、段の順より先に表の順
    try:
        import kango_tier
        tier = kango_tier.known_usage_tier(head)
    except Exception:
        tier = None
    return {1: 0, 2: 1, None: 2, 3: 3}.get(tier, 2)


def _world_reading(dict_index, reading):
    try:
        return bool(reading) and bool(dict_index.is_world_reading(reading))
    except Exception:
        return False


def _foreign_swaps(toks, dict_index):
    """IME が片仮名の語にした字句のうち、続く接尾の語（屋・店・的…）との組み立て（スパン＋屋）が世の中の語の表
    （辞書の読みの表）に無く、片仮名の語の端の1字を抜いた組み立て（パン＋屋）は表に在るもの
    → {字句の番号: [(抜いた読み, 置く表記)]}。置く表記は抜いた読みの片仮名。

    確定の前に余分な1字を打つと、IME がその字を隣の語の読みに巻き込んで別の片仮名の語（新しい**す**ぱんや→
    新しいスパン屋）にすることがある。片仮名の語は1字抜いても別の片仮名の語になりやすく、並びの費用も読みの
    並びも巻き込んだ語の方を良いと見るので、費用では見つからない。「そういう語は世の中に無い」が決め手。
    語は名指ししない: 辞書の読みの表の有無と端の1字だけで決める。本人の語彙（パン は使った・パンダ は無い）は
    決め手にしない: 初めて使う片仮名の語が、使った語＋1字のとき（パンダを→パンを）に誤るので。
    """
    out = {}
    if dict_index is None:
        return out
    for i, t in enumerate(toks):
        if t.pos != '名詞' or len(t.surface) < 2 or not _katakana_str(t.surface):
            continue
        r = _tok_reading(t)
        u = toks[i + 1] if i + 1 < len(toks) else None
        if not r or u is None or u.pos != '名詞' or not (u.pos_sub or '').startswith('接尾'):
            continue
        tail = _tok_reading(u)
        if not tail or _world_reading(dict_index, r + tail):
            continue
        rows = []
        for k in (0, len(r) - 1):
            if not _kana(r[k]):
                continue
            new_r = r[:k] + r[k + 1:]
            if len(new_r) < 2 or not _world_reading(dict_index, new_r + tail) or not _world_reading(dict_index, new_r):
                continue
            face = ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in new_r)
            if (new_r, face) not in rows:
                rows.append((new_r, face))
        if rows:
            out[i] = rows
    return out


def _absorbed_katakana(toks, dict_index):
    """片仮名の名詞の字句で、直前のかなの字句と直後のかなの字句（付属の語・接尾）と続けた読みが辞書の読みの表に
    無く、片仮名の語の端の1字を抜いて続けた読みは表に在るもの（これ＋カニ＋ら: これかにら は無い・これから は在る）
    → 字句の番号の集合。語は名指ししない: 表の有無と端の1字だけで決める。印を付けるだけで、直しは読み直しが決める。"""
    out = set()
    if dict_index is None:
        return out
    for i, t in enumerate(toks):
        if i == 0 or i + 1 >= len(toks) or len(t.surface) < 2 or not _katakana_str(t.surface):
            continue
        p, u = toks[i - 1], toks[i + 1]
        if not (_kana_str(p.surface) and _kana_str(u.surface)) or p.end != t.start or t.end != u.start:
            continue
        r, pr, ur = _tok_reading(t), _tok_reading(p), _tok_reading(u)
        if not (r and pr and ur) or _world_reading(dict_index, pr + r + ur):
            continue
        for k in (0, len(r) - 1):
            if _kana(r[k]) and _world_reading(dict_index, pr + r[:k] + r[k + 1:] + ur):
                out.add(i)
                break
    return out


def _absorbed_repair(line, retry, dict_index):
    """紫も迷いも無い行で、_absorbed_katakana の片仮名の語（これ＋カニ＋ら）を、端の1字を抜いたかな（これ＋か＋ら）に
    戻して読み直す。採るのは、続けた読みが辞書の読みの表に在り、並びの費用が MIN_PATH_GAIN 以上下がり、読み直しに
    紫も迷いも残らない形だけ。抜く字が両端どちらでも語になるとき（決め手が無い）は採らない。"""
    import morphology
    if dict_index is None:
        return None
    toks = list(morphology.tokenize(line))
    base = morphology.path_cost(line)
    if not toks or base is None:
        return None
    for i in sorted(_absorbed_katakana(toks, dict_index)):
        t, p, u = toks[i], toks[i - 1], toks[i + 1]
        r, pr, ur = _tok_reading(t), _tok_reading(p), _tok_reading(u)
        rows = [r[:k] + r[k + 1:] for k in (0, len(r) - 1)
                if _kana(r[k]) and _world_reading(dict_index, pr + r[:k] + r[k + 1:] + ur)]
        if len(set(rows)) != 1:
            continue
        face = rows[0]
        text = line[:t.start] + face + line[t.end:]
        cost = morphology.path_cost(text)
        if cost is None or base - cost < MIN_PATH_GAIN:
            continue
        got = retry(text)
        if got and _clean(got):
            return text, got, (t.start, t.end, face)
    return None


def _place_kanji(text, s, e_text, clause, typed, store, dict_index, context_vec, surrounding):
    """text[s:e_text] がかなのまま残った文節なら、辞書の形の漢字に置いた
    (置いた行, 置いた顔) を返す。置けなければ None（軽くなるかは呼ぶ側が比べる）。"""
    import morphology
    face = text[s:e_text]
    if not _kana_str(face):
        return None
    parts = _kana_word_split(face, clause, typed, dict_index)
    if not parts:
        return None
    word, rest = parts
    faces = [f for f in _kanji_choices(word, store, dict_index) if _face_attaches(f, rest)]
    # 身近さの表（kango_tier）に判定の無い2字の漢語（遥遠・夕立）は身近でないと見て置かない（本人の語は置く）。
    # 置けなければ読み直した文節はかなのまま残る（うに 10-19: 表に無いものは身近でない。ひらがなで読めるように）
    own_faces = set(_own_faces(word, store))
    faces = [f for f in faces if f in own_faces or (not _not_everyday_kango(f) and _kango_reads_as(f, word))]
    if len(faces) > 1:
        # 明示的に稀と判定された表記（安神・現官・呈出）は、別の語の表記が並んでいれば置く候補から外す。
        # その漢字の一部をかなで書いた表記（旅先 に対する 旅さき・たび先）は同じ語なので、別の語とは見ない
        # （判定が 旅先 を稀としていて、たび先 を置いていた。判定が1語に掛かるだけなら語を選ぶ材料ではない）
        rare = [f for f in faces if _restricted_face(f)]
        if rare:
            def same_word(f):
                return any({c for c in f if _kanji(c)} <= {c for c in r if _kanji(c)} for r in rare)
            plain = [f for f in faces if not same_word(f)]
            if plain:
                faces = plain
    # 同じ語の書き方違い（洗い物/洗いもの・打ち合わせ/打合せ・受け取り/受けとり）は1つにまとめる（先頭 = 一般的な順）。
    # 並んだままだと行の費用が並んで決め手が無く、かなのまま残っていた（2026-10-19）。別の語（受け取り/請取・
    # 飢え/植え）はまとめない
    cost = {}
    if len(faces) > 1:
        for f in faces:
            c = morphology.path_cost(text[:s] + f + rest + text[e_text:])
            if c is not None:
                cost[f] = c
    faces = _merge_spellings(faces, word, cost)
    if len(faces) > 1 and cost:
        # 行の費用が最も軽い形より PLACE_FAR 以上重い表記（河原＋ず・賜べ＋た: 文法の合わない形）は置く候補から
        # 外す。費用の小さな差（暑く/熱く）は書かれた語を映さないが、大きな差は形が合わないことを映す
        floor = min(cost.get(f, 10 ** 9) for f in faces)
        near = [f for f in faces if cost.get(f, 10 ** 9) - floor < PLACE_FAR]
        if near:
            faces = near
    if not faces:
        return None
    kanji = faces[0]
    weak = False
    if len(faces) > 1:
        # 表記が並んだら、周りの語との馴染み（文脈）に決め手があればそれ。無ければ本人の IME、
        # 無ければ行の費用（入口と同じ尺度）で、2番目より PLACE_MARGIN 以上軽い1つ。
        # どれにも決め手が無ければ最も身近な表記（AI 判定の表 everyday_faces → kango_tier の段）に決め、
        # 表がその表記を「身近さで抜けている」と見ていなければ迷いの印（紫）を残す（うに 10-18: 文脈優先、
        # 読み取れなければ最も身近な語（電気）に。迷ったら何もしない はしない）
        words = [w for w in surrounding if w != word]
        kanji = _pick_by_context(faces, context_vec, words)
        if not kanji:
            # 文脈に決め手が無ければ、本人の IME が打ち直しで出す顔（辞書の表記の中だけ）
            kanji = _ime_face(word, rest, faces)
        if not kanji and _morae(word) <= 2:
            # 読みが2拍以下の語は同じ読みの名詞が多く（ちょう: 兆・帳・長・超…）、行の費用の
            # 差はどれが書かれたかを映さない（超された が最安）。文脈に決め手が無ければ、
            # 本人の語彙の表記と、付属の付いた用言の語幹（たべ＋た→食べ・かり＋た→借り）
            # だけを費用で比べる。名詞はそれだけでは置かない（とりの→鶏の を置いた）
            own = set(_own_faces(word, store))
            stems = set()
            # 付属は文節の中（たべ＋た）か、文節のすぐ後ろ（IME が とっ｜た と切った形: text[e_text:]）に在ること。
            # 2拍のかなが た・て・だ・で に直に続くなら用言の語幹（取っ＋た）で、名詞（とりの）ではない
            if rest or text[e_text:e_text + 1] in ('た', 'て', 'だ', 'で'):
                try:
                    stems = set(dict_index.inflected_surfaces_for_reading(word))
                except Exception:
                    stems = set()
                # 付属と合わせて活用した形（取っ＋た・たべ＋た）だけ。基本形に格助詞が付く形（寄る＋に）は語幹ではない
                stems = {f for f in stems if _inflected_stem(f, rest)}
            faces = [f for f in faces if f in own or f in stems]
            if not faces:
                return None
            if len(faces) == 1:
                kanji = faces[0]
        if not kanji and _familiar_order(word, faces, rest)[0]:
            # 表（everyday_faces）に在る語が並ぶとき（2字漢語 電気/伝記/電機・用言 取る/撮る/採る・和語 初め/始め）、
            # 行の費用の差は辞書の癖で書かれた語を映さない。表に在る読みは行の費用より先に身近さで決める。
            # 表がかなの形を身近と見る語（うるさい）は、かなのまま（_most_familiar が読みを返し、下で置かない）
            top, dominant = _most_familiar(word, faces, rest)
            if top:
                scored = sorted((cost[f], f) for f in faces if f in cost)
                agreed = (len(scored) >= 2 and scored[0][1] == top
                          and scored[1][0] - scored[0][0] >= PLACE_MARGIN)
                kanji, weak = top, not (dominant or agreed)
        if not kanji:
            scored = sorted((cost[f], f) for f in faces if f in cost)
            if len(scored) >= 2 and scored[1][0] - scored[0][0] >= PLACE_MARGIN:
                kanji = scored[0][1]
            elif len(scored) == 1:
                kanji = scored[0][1]
            elif scored:
                # 費用が並んだ中に本人の語彙の表記があればそれ（使った回数の多い方）
                close = {f for c, f in scored if c - scored[0][0] < PLACE_MARGIN}
                own = [f for f in _own_faces(word, store) if f in close]
                if own:
                    kanji = own[0]
        if not kanji and faces:
            top, dominant = _most_familiar(word, faces, rest)
            if top:
                kanji, weak = top, not dominant
    if not kanji or kanji == word:
        return None
    if _restricted_face(kanji) and not _her_word(store, word, kanji):
        # 明示的に稀と判定された語（溶存・旅先）がこの読みの唯一の語なら、置くが迷いの印（紫）を残す
        # （判定が誤っていることがある: 旅先 は段3。迷ったら何もしない はしない。並んだら確かな形が先）
        weak = True
    return text[:s] + kanji + rest + text[e_text:], kanji + rest, weak


def _most_familiar(reading, faces, rest=''):
    """並んだ表記の中で最も身近なもの → (表記, 身近さで抜けているか)。

    先に AI 判定の表（everyday_faces: 読み → 身近な順の表記・先頭が抜けているか）。2字漢語（電気/伝記）は読みで、
    用言（取る/撮る/採る）は基本形の読み（取っ＋た → 取る → とる）で、和語の名詞（初め/始め）は読みで引く
    （_familiar_order）。表の先頭がかなの形（うるさい・きれい）なら、かなの形（reading）を返す（呼ぶ側は漢字を置かない）。
    表に無ければ kango_tier の段（段1 → 段2 → 表に無い → 段3）と同梱の表の費用の順で、並びの先頭に決める
    （抜けているとは見ない）。
    """
    if not faces:
        return None, False
    order, dominant, bases = _familiar_order(reading, faces, rest)
    if order:
        for n, f in enumerate(order):
            if _kana_str(f):
                return reading, bool(dominant and n == 0)
            match = [fc for fc in faces
                     if fc == f or bases.get(fc) == f or (_kanji_seq(f) and _kanji_seq(fc) == _kanji_seq(f))]
            if match:
                return match[0], bool(dominant and n == 0)
    if not all(len(f) == 2 and _kanji_seq(f) == f for f in faces):
        # 表に無い読みで、並ぶ表記が2字漢語の名詞だけでなければ（受け取り／請取・返る／変える）、kango_tier の段
        # （漢語の表）では比べられない。並びの先頭（出どころの順: 本人の語彙 → 辞書の索引 → 活用形 → 同梱の表だけ）
        # に決め、抜けているとは見ない（呼ぶ側が迷いの印を残す。かなのまま残さない: 迷ったら何もしない はしない）
        return faces[0], False
    try:
        import kango_tier
        rank = {1: 0, 2: 1, None: 2, 3: 3}
        seed = {f: c for f, c in _seed_surfaces(reading)}
        ordered = sorted(faces, key=lambda f: (rank.get(kango_tier.known_usage_tier(_kanji_seq(f)[:2]), 2),
                                               seed.get(_kanji_seq(f), seed.get(f, 10 ** 6))))
        return ordered[0], False
    except Exception:
        return faces[0], False


def _inflected_stem(face, rest):
    """face＋rest（取っ＋た・食べ＋た・取っ）の先頭が、基本形でない活用の形の用言か。"""
    import morphology
    try:
        toks = list(morphology.tokenize(face + rest))
    except Exception:
        return False
    return bool(toks) and toks[0].pos in ('動詞', '形容詞') and toks[0].infl_form != '基本形' \
        and _kanji_seq(toks[0].surface) == _kanji_seq(face)


def _base_forms(faces, rest):
    """用言の表記（取っ＋た・暑く・植え＋た）→ ({表記: 基本形}, 基本形の読み)（取っ→取る・とる）。
    用言でない表記（上＋た）は入れない。基本形の読みは、辞書で引けた最初の用言のもの。"""
    import morphology
    bases, key = {}, None
    for f in faces:
        try:
            toks = list(morphology.tokenize(f + rest))
        except Exception:
            continue
        if not toks or toks[0].pos not in ('動詞', '形容詞'):
            continue
        base = toks[0].base_form
        if not base or base == '*' or _kanji_seq(toks[0].surface) != _kanji_seq(f):
            continue
        bases[f] = base
        try:
            bt = list(morphology.tokenize(base))
        except Exception:
            bt = []
        k = _tok_reading(bt[0]) if bt else None
        if key is None:
            key = k
        elif k != key:
            # 基本形の読みが分かれる（給ぶ・賜ぶ／食べる）: 1つの表では決めない
            return {}, None
    if len(bases) != len(faces):
        # 用言でない表記（上）が並ぶ読み（うえ: 上／植え）は用言の表では決めない（机の上に を 机の植えに にした）
        return {}, None
    return bases, key


def _familiar_order(reading, faces, rest=''):
    """AI 判定の表（everyday_faces）のこの語の並び → (身近な順の表記, 先頭が抜けているか, {表記: 基本形})。
    読みで引き、無ければ用言の基本形の読み（取っ＋た → 取る → とる）で引く。無ければ ((), False, {})。"""
    bases, key = _base_forms(faces, rest)
    if bases:
        # 用言が並ぶ（取っ＋た・変わら＋ず）: 基本形の読みの表だけ。読みの表は名詞の並び（かわら: 瓦/河原）
        if key:
            order, dominant = _everyday_order(key)
            if order:
                return order, dominant, bases
        return (), False, {}
    order, dominant = _everyday_order(reading)
    if order:
        return order, dominant, {}
    return (), False, {}


def _face_alignments(face, reading, limit=4):
    """表記（漢字とかなの並び）を読みの上に置く置き方の全部（((漢字, (始まり, 終わり)), ...) の並び）。
    かなは読みの同じ字に重なり、漢字1字は読みの1〜limit 字を受け持つ。置き方が無ければ ()。"""
    segs = []
    for c in face:
        k = _kanji(c)
        if segs and not k and not segs[-1][0]:
            segs[-1] = (False, segs[-1][1] + c)
        else:
            segs.append((k, c))
    outs = []

    def rec(i, pos, acc):
        if len(outs) >= 64:
            return
        if i == len(segs):
            if pos == len(reading):
                outs.append(tuple(acc))
            return
        k, s = segs[i]
        if not k:
            if reading.startswith(s, pos):
                rec(i + 1, pos + len(s), acc)
            return
        for ln in range(1, min(limit, len(reading) - pos) + 1):
            acc.append((s, (pos, pos + ln)))
            rec(i + 1, pos + ln, acc)
            acc.pop()
    rec(0, 0, [])
    return tuple(outs)


def _same_spelling(a, b, reading):
    """a と b が同じ語の書き方違い（送りがな・一部をかなで書いた形: 洗い物/洗いもの・打ち合わせ/打合せ）か。
    漢字の並びが同じなら同じ語。違えば、読みの上に置いたとき、一方に在る漢字がもう一方では同じ所に同じ漢字で
    在るか、かなで書かれていること。同じ所に別の漢字が立つ（受け取り/請取・飢え/植え・早い/速い）なら別の語。"""
    if _kanji_seq(a) == _kanji_seq(b):
        return True

    def fits(x, y):
        for s, (p, q) in x:
            hit = [(t, sp) for t, sp in y if sp[0] < q and p < sp[1]]
            if hit and hit != [(s, (p, q))]:
                return False
        return True
    for al_a in _face_alignments(a, reading):
        for al_b in _face_alignments(b, reading):
            if fits(al_a, al_b) and fits(al_b, al_a):
                return True
    return False


def _merge_spellings(faces, reading, cost=None):
    """並んだ表記から、同じ語の書き方違いをまとめて1つだけ残す。別の語は残す。
    残す形は行の費用（cost: 表記 → 費用）が最も軽い形、並べば漢字の多い形、並べば送りがなの多い形、並べば先頭。"""
    groups = []
    for f in faces:
        for g in groups:
            if _same_spelling(f, g[0], reading):
                g.append(f)
                break
        else:
            groups.append([f])
    cost = cost or {}
    out = []
    for g in groups:
        # 行の費用が最も軽い形と PLACE_MARGIN 未満の差の形の中で（費用の小さな差は書かれた形を映さない: 親戚 11419・
        # 親せき 11418）、漢字の多い形（洗い物 > 洗いもの・親戚 > 親せき）、並べば送りがなの多い形、並べば先頭。
        # 大きく重い形（遣り直す・早目: 行の中で珍しい形）は残さない
        floor = min(cost.get(f, 0) for f in g)
        near = [f for f in g if cost.get(f, 0) - floor < PLACE_MARGIN]
        out.append(max(near, key=lambda f: (sum(1 for c in f if _kanji(c)), len(f), -g.index(f))))
    return out


def _everyday_order(reading):
    """AI 判定の身近さの表（everyday_faces）の、読み → (身近な順の漢字の表記, 先頭が抜けているか)。無ければ ((), False)。"""
    try:
        import everyday_faces
        return everyday_faces.order(reading)
    except Exception:
        return (), False


def _tie_by_context(rows, line, e, clauses, store, dict_index, context_vec, surrounding):
    """並んだ読み直しの候補（found の行）から、文脈に馴染む顔を持つ1つを選ぶ。
    かなの顔は漢字に置いた形で比べる（わすれ→忘れ・わかれ→別れ）。決め手が無ければ None。"""
    if context_vec is None or not surrounding:
        return None
    faces = {}
    for row in rows:
        s_, e_, text, got = row[1], row[2], row[3], row[4]
        corrected = got.get('corrected', text)
        new_e = len(corrected) - (len(line) - e_)
        face = corrected[s_:new_e]
        if _kana_str(face):
            typed = next((t for a, b, t in clauses if (a, b) == (s_, e_)), '')
            parts = _kana_word_split(face, line[s_:e_], typed, dict_index)
            if parts:
                kanji = _kanji_for_kana(parts[0], store, dict_index, None, ())
                if kanji:
                    face = kanji + parts[1]
        words = ''.join(c for c in face if _kanji(c) or _kana(c))
        if words and words not in faces:
            faces[words] = row
    if len(faces) < 2:
        return None
    try:
        picked = context_vec.pick_best_by_context(list(faces), [w for w in surrounding])
    except Exception:
        return None
    return faces.get(picked) if picked else None


def _suru_form(toks, i):
    """toks[i] は 述語として使われた する の活用形（追加**し**ました・補正**さ**れない・確認**せ**ず・登録**し**て）か。

    サ変の名詞・助詞・副詞に続き、後ろに助動詞・接続助詞・接尾の動詞が付く形。格助詞が直に続く形
    （仕事**し**に響く: し を抜くと 仕事に）は、余った1字の跡でもあるので語とは見ない。
    """
    t = toks[i]
    if t.pos != '動詞' or t.base_form != 'する' or i == 0 or i + 1 >= len(toks) or '文語' in (t.infl_form or ''):
        return False
    u = toks[i + 1]
    return (toks[i - 1].pos in ('名詞', '助詞', '副詞')
            and ((u.pos == '助動詞' and u.base_form in _PREDICATE_AUXILIARIES)
                 or (u.pos == '動詞' and u.pos_sub.split(':')[0] in ('接尾', '非自立'))
                 or (u.pos == '助詞' and u.pos_sub.startswith('接続助詞'))))


# する の後ろに付く今の文の助動詞（し**ました**・し**た**・し**ない**・し**たい**・し**よう**・せ**ず**）。ん（夕し**ん**ど）は違う
_PREDICATE_AUXILIARIES = ('ます', 'た', 'ない', 'たい', 'う', 'よう', 'ぬ', 'ず', 'まい')


_UNIT_GLUE = ('助詞', '助動詞', '記号')
_LITERARY_AUXILIARIES = ('つ', 'き', 'けり')   # 文語の助動詞（辞書の品詞では 助動詞）。今の文には出ない（べき は今も使う）
_FRAGMENT_NOUN_SUBS = ('一般', 'サ変接続', '固有名詞', '形容動詞語幹', '副詞可能')


def _attested_compound(parts, store):
    """隣り合う名詞の組（文字＋列）は世の中の語（文字列）か。同梱の語の表（読み→表記）か本人の語彙に在れば語。"""
    face = ''.join(t.surface for t in parts)
    try:
        if store is not None and store.reading_of(face) is not None:
            return True
    except Exception:
        pass
    readings = [_tok_reading(t) for t in parts]
    if not all(readings):
        return False
    reading = ''.join(readings)
    return any(f == face for f, _c in _seed_surfaces(reading))


def _clause_fragments(toks, s, e, store=None):
    """文節 [s, e) の中の、語でない切れ端の字句の番号。

    打ち違いの読みを IME が変換すると、正しい語の間に語でない切れ端が残る（しゃ**歯科**を・**うき**前の・
    県**こえ**診断・**沖前**の・保存**なし**ました・や基礎**サバ**を）。正しい複合語（文字列と・タブ移動時に）は
    2語以上に割れても切れ端が無い。語は名指ししない: 字種・品詞・並び・本人の語彙・世の中の語の表の有無で決める。
    """
    out = set()
    idx = [i for i, t in enumerate(toks) if t.start < e and s < t.end]
    first = idx[0] if idx else None
    for i in idx:
        t = toks[i]
        sub = t.pos_sub.split(':')[0]
        p = toks[i - 1] if i > 0 else None
        u = toks[i + 1] if i + 1 < len(toks) else None
        glued = p is not None and p.pos not in _UNIT_GLUE and p.end == t.start
        glued_next = u is not None and u.pos not in _UNIT_GLUE and u.start == t.end
        hira = _kana_str(t.surface) and not _katakana_str(t.surface)
        kata = _katakana_str(t.surface)
        if hira:
            # 別の語に直に（助詞を挟まず）付いたかなの名詞（**しゃ**歯科・**いす**県・移動**あした**・小さ**そく**）。
            # 助詞を挟んで立つかなの名詞（ひとつ**の**行に・あした**は**）は語。非自立（こと・もの・せい）は名詞に直に
            # 付いた形（欄**せい**・薬**の**を）と名詞が直に続く形（の**せい**今日が）だけ、代名詞は動詞・形容詞に直に
            # 付いた形（書く**なん**して）だけ
            if t.pos == '名詞' and ((sub in _FRAGMENT_NOUN_SUBS and (glued or glued_next))
                                   or (sub == '非自立' and ((glued and p.pos == '名詞')
                                                          or (glued_next and u.pos == '名詞')))
                                   or (sub == '代名詞' and glued and p.pos in ('動詞', '形容詞'))):
                out.add(i)
            # 名詞に直に続く短いかなの動詞（県**こえ**診断・保存**なし**ました・運**いん**免許）。する だけは語（勉強する）。
            # 短いかなの動詞に直に続く自立の動詞（**こみ**上ん）
            if (t.pos == '動詞' and sub == '自立' and len(t.surface) <= 3 and t.base_form not in ('する', 'できる', 'なる')
                    and ((glued and p.pos == '名詞')
                         or (len(t.surface) <= 2 and u is not None and u.pos == '動詞'
                             and u.pos_sub.split(':')[0] == '自立' and u.start == t.end))):
                out.add(i)
            # 別の語に直に付いた短いかなの形容詞（**うき**前・**きつ**下・**やす**意味）。ない・よい・いい は語
            if (t.pos == '形容詞' and len(t.surface) <= 2 and t.base_form not in ('ない', 'よい', 'いい')
                    and (glued or glued_next)):
                out.add(i)
            # 1字のかなの自立語・接頭詞・感動詞・フィラー（**す**鋳物・都市**う**ロク・**あ**縦らしい・思う**え**）。
            # 助詞・助動詞・接尾・非自立・お・ご・する の活用形は語
            if (len(t.surface) == 1 and t.pos not in _UNIT_GLUE
                    and not (t.pos == '名詞' and sub in ('接尾', '非自立', '数'))
                    and not (t.pos == '動詞' and sub in ('接尾', '非自立') and glued)
                    and not (t.pos == '接頭詞' and t.surface in ('お', 'ご'))
                    and not _suru_form(toks, i)):
                out.add(i)
            # 形容動詞の語幹に付いた1字の接尾（幸せ**ら**な: ら が付くのは人・代名詞）
            if (t.pos == '名詞' and sub == '接尾' and len(t.surface) == 1 and glued
                    and p.pos == '名詞' and p.pos_sub.split(':')[0] == '形容動詞語幹'):
                out.add(i)
            # 名詞に直に続くフィラー（作業**あの**途中）
            if t.pos == 'フィラー' and glued and p.pos == '名詞':
                out.add(i)
            # 文節の頭の付属語（**れ**研修を・**た**利子んだ・**け**研修を・**や**意味の）: 付く先が無い
            if i == first and u is not None and u.pos not in _UNIT_GLUE and (
                    t.pos == '助動詞'
                    or (t.pos == '動詞' and sub in ('接尾', '非自立'))
                    or (t.pos == '助詞' and sub.startswith(('終助詞', '並立助詞')))):
                out.add(i)
            # 文の途中の終助詞・文語の係助詞 ぞ（**っけ**こん四季・医科**ぞ**しい・夕**ぞ**ん・**け**て書く）: 後ろに語や
            # 接続助詞は続かない（よね・ねと言った は続く）
            if (t.pos == '助詞' and u is not None
                    and ((u.pos not in _UNIT_GLUE and (sub.startswith('終助詞')
                                                      or (sub.startswith('係助詞') and t.surface == 'ぞ')))
                         or (sub.startswith('終助詞') and u.pos == '助詞' and u.pos_sub.startswith('接続助詞')))):
                out.add(i)
            # 体言接続の な（だ）に直に続く名詞でない語（県**な**こうの: な の後ろは名詞か の・ん・だけ）
            if (t.pos == '助動詞' and t.surface == 'な' and t.base_form == 'だ' and u is not None
                    and u.pos in ('副詞', '動詞', '形容詞', '連体詞', 'フィラー', '感動詞', '接頭詞')):
                out.add(i)
            # 文語の助動詞 つ・き・けり（縦いせ**つ**な・夕**し**どんの）
            if t.pos == '助動詞' and t.base_form in _LITERARY_AUXILIARIES:
                out.add(i)
        elif kata and len(t.surface) <= 3:
            # 本人の使っていない短い片仮名が別の語に直に付いた形（**ノリ**餓死て・**イモ**上と・や基礎**サバ**を）と、
            # 片仮名の副詞など（縦か**カッ**た）。本人の語（タブ移動時に の タブ）は語
            known = False
            try:
                known = store is not None and store.reading_of(t.surface) is not None
            except Exception:
                known = False
            if not known and (t.pos != '名詞' or (sub in _FRAGMENT_NOUN_SUBS and (glued or glued_next))):
                out.add(i)
        elif (len(t.surface) == 1 and _kanji(t.surface) and t.pos == '名詞' and sub in _FRAGMENT_NOUN_SUBS
              and u is not None and u.start == t.end and len(u.surface) == 1 and _kanji(u.surface)
              and u.pos == '名詞' and u.pos_sub.split(':')[0] in _FRAGMENT_NOUN_SUBS
              and not _attested_compound([t, u], store)):
            # 世の中に無い1字漢字の組（**沖前**の）。語の組（母子・親子）は語の表に在る
            out.add(i)
            out.add(i + 1)
    return out


def repair_ime_clause(line, result, retry, input_method='kana', decisions=None,
                      dict_index=None, store=None, context_vec=None, surrounding=()):
    """
    IME の文節を打った読みに戻し、1打を戻して読み直す。採れれば
    `(読み直した行, 読み直した結果, (始まり, 終わり, 置く字))`（位置は元の行の上）。
    """
    if (input_method not in ('kana', 'romaji') or dict_index is None or store is None
            or not line or len(line) > MAX_CLAUSE_LINE):
        return None
    import morphology
    import yomigram
    from contextual_repair import key_repairs
    base = morphology.path_cost(line)
    if base is None:
        return None
    done = result.get('corrected', line)
    if done and done != line:
        # 入口がすでに直した行（せ欄たく物→洗濯物）があれば、それより十分に
        # 軽くなる読み直しだけ採る（かなに戻すだけの直しで漢字の直しを潰さない）
        cost_done = morphology.path_cost(done)
        if cost_done is not None:
            base = min(base, cost_done)
    toks = list(morphology.tokenize(line))
    if not toks:
        return None
    spots = _suspect_tokens(toks)
    # ローマ字入力: 文法で付けない所に残った1字の母音・っ（悪いうので・番号うを・っ天気予報）も疑いの印
    stray = _romaji_stray_tokens(toks) if input_method == 'romaji' else {}
    spots |= set(stray)
    # IME が明示的に稀と判定された2字の漢語（稀代・現官）を出した跡も疑いの印（打ち違いの読みを IME が珍しい語に変換した形）
    rare = {i for i, t in enumerate(toks)
            if t.pos == '名詞' and len(t.surface) == 2 and _kanji_seq(t.surface) == t.surface
            and _restricted_face(t.surface)}
    spots |= rare
    sure = _conjugation_mismatch(toks)
    # 本人の使っていない片仮名の語で、端の1字を抜くと本人の語になるもの（印の1つ。費用の線に掛からない）
    swaps = _foreign_swaps(toks, dict_index)
    # 前後のかなと続けた読み（これ＋かに＋ら）が世の中の語に無く、片仮名の語の端の1字を抜くと語になる
    # （これから）ものも疑いの印（余分な1字を IME が片仮名の語に巻き込んだ跡）
    spots |= _absorbed_katakana(toks, dict_index)
    odd = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
    costly = _cost_per_char(line, base) >= CLAUSE_COST
    # 文節をつなぐ読み直し（隣の文節・前のかなの切れ端）は、印（疑いの字句・文法で確かな印・片仮名の巻き込み・
    # 入口の紫の掛かる字句）の在る所だけ
    mark_idx = (set(spots) | set(sure) | set(swaps)
                | {i for i, t in enumerate(toks) if any(a < t.end and t.start < b for a, b in odd)})
    clauses = _ime_clauses(line, toks, dict_index, mark_idx)
    if not clauses:
        return None

    face_end = {(c[0], c[1]): c[3] for c in clauses}
    clauses = [c[:3] for c in clauses]
    # 読みの並びの印（#70）は正しい文にも付いたので使わない（#74）。読みの上の文法で確かな印だけ見る（#80）
    reading_marked = _reading_sure_clauses(line, clauses)
    long_vowel = {}
    if dict_index is not None:
        for c in clauses:
            if _kana_str(c[2]) and any(_kanji(ch) for ch in line[c[0]:c[1]]):
                lv = _katakana_long_vowel_face(c[2], dict_index)
                if lv:
                    long_vowel[(c[0], c[1])] = lv
    reading_marked |= set(long_vowel)

    def local_costly(s, e):
        # 文節だけの費用。長い行では余分な1字（研修あの）が行全体の費用を
        # 上げないので、文節の単位でも疑う。見るのは IME が確定した顔の部分
        # （保存な。辞書が なし と1つに切って文節が伸びても、顔で測る）
        seg = line[s:face_end.get((s, e), e)]
        c = morphology.path_cost(seg) if len(seg) >= 3 else None
        return c is not None and c / len(seg) >= CLAUSE_LOCAL_COST
    if not (spots or odd or costly or swaps or reading_marked or any(local_costly(c[0], c[1]) for c in clauses)):
        return None
    guard = _protected(line, decisions)
    stray_texts = set()   # ローマ字の印の1字を抜いた読み直しの行（並んだら先に採る）

    def marked(s, e):
        return ((s, e) in reading_marked
                or any(toks[i].start < e and s < toks[i].end for i in spots)
                or any(s <= toks[i].start and toks[i].end <= e for i in swaps)
                or any(a < e and s < b for a, b in odd))

    def broken(s, e):
        # 文節の中に語でない切れ端が在る（_clause_fragments）。1語に収まる文節（人も・元に・の判定を・を追加
        # しました）や正しい複合語（文字列と・タブ移動時に・文字列一致は: 2語以上に割れても切れ端が無い）は、
        # 費用が高くても読み直さない（正しく打った語を、本人の語彙で軽くなる別の語 反対を・捩れと・舞台同時に
        # に替えてしまう。2026-10-18）
        return bool(_clause_fragments(toks, s, e, store))
    # 同じ所から始まる文節が重なるとき（本人の IME の 見＝み と 見すらない＝みすらない）は長い方を先に。
    # 長い文節は IME が打った読みを丸ごと変換した跡で、短い方だけ読み直すと語尾が残る（見→編み＋すらない）
    ordered = sorted(clauses, key=lambda c: (not marked(c[0], c[1]), c[0], -(c[1] - c[0])))
    # 印の無い文節は、費用（行全体か文節だけ）が高く、かつ語でない切れ端が在るときだけ。費用だけでは、片仮名や記号の
    # 多い行で正しい文節まで高く見える（の判定を→反対を・の行に→今日に・文字列と→捩れと に替わった。2026-10-18）
    ordered = [c for c in ordered
               if marked(c[0], c[1]) or ((costly or local_costly(c[0], c[1])) and broken(c[0], c[1]))]
    trials = 0
    found = []
    for ci, (s, e, typed) in enumerate(ordered[:CLAUSE_TOKENS]):
        if any(lo < e and s < hi for lo, hi in guard):
            continue
        if trials >= CLAUSE_RETRIES and not any(toks[i].start < e and s < toks[i].end for i in sure):
            # 枠を使い切った後は、文法で確かな印の文節（組み立ての形を持ちうる）だけ見る
            continue
        kana_line = line[:s] + typed + line[e:]
        # 文法で確かな印（活用の形が合わない続き）の掛かる文節では、IME の語を残して余った字だけ抜いた形
        # （新しい**て**スマートフォン→新しいスマートフォン）は、費用の下がりが小さくても試し、入口がその
        # まま通せば採る（て を抜いても janome の費用は 748 しか下がらず CLAUSE_GAIN に届かなかった。
        # 正しい文には出ない形なので、費用の線で守る必要が無い）
        sure_clause = any(toks[i].start < e and s < toks[i].end for i in sure)
        stray_clause = any(toks[i].start < e and s < toks[i].end for i in stray)
        clause_marked = sure_clause or marked(s, e)
        # 稀と判定された語（稀代）の印だけの文節（文法の印・費用の印・紫が無い）: 読み直しが採れても迷いの印（紫）を残す
        rare_only = (clause_marked and not sure_clause
                     and any(toks[i].start < e and s < toks[i].end for i in rare)
                     and not any(toks[i].start < e and s < toks[i].end for i in spots - rare)
                     and not any(s <= toks[i].start and toks[i].end <= e for i in swaps)
                     and not any(a < e and s < b for a, b in odd))
        # 文法で確かな印は「語 W と付属 A の続きが合わない」こと（閑雅＋て）。直しは W を直す（かんが**え**て）か
        # A を直す（寒**す**→寒い: IME の語を残す形）かのどちらか。W も A も同時に捨てる戻し（かんが**い**→潅漑）
        # は、合わない続きの両側を別の語に替えるもので根拠が無い（費用と読みの並びは 潅漑 を良いと見る）
        sure_pairs = []
        for i in sure:
            if i + 1 < len(toks) and s <= toks[i].start and toks[i + 1].end <= e and _kanji_seq(toks[i].surface):
                off = len(''.join(_tok_reading(x) for x in toks if s <= x.start and x.end <= toks[i].start))
                post = ''.join(_tok_reading(x) for x in toks if toks[i + 1].end <= x.start and x.end <= e)
                sure_pairs.append((off, _tok_reading(toks[i]), _tok_reading(toks[i + 1]), post))
        # 文節に掛かる連体詞（行の上で見る: 文節だけ切ると あの はフィラーになる）
        adnominals = [t.surface for i, t in enumerate(toks) if t.pos == '連体詞' and t.start < e and s < t.end
                      and i not in spots]
        y0 = yomigram.logp_parts(kana_line)[0]
        cands = {}
        # 印の1字（番号**う**を）が顔の末尾のかなの中なら、IME の語の読みの末尾と同じ字でも抜く候補にする
        free_del = set()
        for i, p in stray.items():
            if toks[i].pos == '形容詞' and toks[i].infl_form == '連用ゴザイ接続':
                # ウ音便の印（温か**う**飲み物・多**う**なる）は く の k が抜けた跡: 抜く戻し（温か飲み物）ではなく
                # 置き換え（温かい・多く）で直す。抜く候補を印の抜きとして先に採らない
                continue
            if not (s <= p < e):
                continue
            if _kana_str(line[p:e]):
                free_del.add(s + len(typed) - (e - p))      # 顔の末尾がかな: 末尾から数える
            elif p == s or _kana_str(line[s:p]):
                free_del.add(p)                             # 顔の先頭がかな: 先頭から数える
        for text, (op, i) in candidates(kana_line, s, s + len(typed), input_method, free_del).items():
            if not _inside_position(op, i, s, s + len(typed)):
                continue
            if op != 'ins' and i not in free_del and 0 <= i < len(kana_line) and _doubled_at(kana_line, i):
                # 同じかなの重なり（聞く**く**・甘く**く**て）の片方を替える・抜く候補は見ない。同じ字の重なりは
                # 直さない設計（duplicate_repair_disabled）で、読み直しても 聞きく・あまく待て のような形しか作らない
                continue
            cands[text] = (op, i)
        # 打鍵の単位の1打（濁点の付け外し・濁点のキーの巻き込み・2打の字の入れ替わり
        # など、字の単位の戻しでは届かない形）も同じ入口に並べる。抜けは数が多いので
        # 足す候補と同じ枠で絞る
        for row in (key_repairs(typed, line[:s], line[e:]) if input_method == 'kana' else ()):
            # 同じキーの別の面（ょ→よ・え→ぇ）は、字の単位の候補と同じく見ない
            # （小書きと大きい字の入れ替えは直さない方針。候補に並ぶと試行の枠を
            # 使い切り、正しい戻しが後ろに落ちる）
            if row.operation in ('same_reading', 'shift', 'adjacent_shift_pair', 'held_shift_run'):
                continue
            text = line[:s] + row.reading + line[e:]
            if text != kana_line:
                cands.setdefault(text, ('ins' if row.operation == 'omission' else 'key', -1))
        # 漢字の名詞＋かなの接尾（変換＋ちゅう）の接尾だけを別の接尾（ちょう→帳）に替える戻しは、書いた複合語を
        # 別の複合語に替えるだけで、打ち違いの証が無い
        tail = _kana_suffix_tail(toks, s, e, line)
        if tail:
            head = len(typed) - len(tail)
            cands = {text: v for text, v in cands.items()
                     if not (len(text) - len(kana_line) == 0 and text[:s + head] == kana_line[:s + head]
                             and text[s + len(typed):] == kana_line[s + len(typed):]
                             and _suffix_with_function(text[s + head:s + len(typed)]))}
        sokuon_idx = {i for i in free_del if 0 <= i < len(kana_line) and kana_line[i] == 'っ'}
        if sokuon_idx:
            cands = {text: (op, i) for text, (op, i) in cands.items()
                     if not (op in ('sub', 'swap') and i in sokuon_idx)}
        stray_del = {text for text, (op, i) in cands.items() if op == 'del' and i in free_del}
        stray_texts |= stray_del
        # 脱字の戻し（かな: 1字足す、ローマ字: ん・っ を足す／母音の字に子音を足す う→く）は低い優先度（うに 10-19 11:38Z）
        drop_fix = {text for text, (op, i) in cands.items()
                    if op == 'ins' or (input_method == 'romaji' and op == 'sub' and 0 <= i < len(kana_line)
                                       and ((kana_line[i] in 'あいうえお' and text[i] not in 'あいうえお')
                                            or kana_line[i].isascii()
                                            or text[i] in _ROMAJI_CLUSTER_DROP.get(kana_line[i], '')))}
        pool = [(yomigram.logp_parts(text)[0] - y0, text, op, i) for text, (op, i) in cands.items()]
        pool.sort(key=lambda row: (-row[0], row[1]))
        # 足す候補だけは数が多いので読みの並びで上位に絞る。置き換え・入れ替え・削除は全部見る
        ins_rows = [row for row in pool if row[2] == 'ins']
        kept = [row for row in pool if row[2] != 'ins'] + ins_rows[:CLAUSE_TOP]
        # 読みの並びの上位に入らなくても、足した読みが辞書の語（＋手を付けていない付属）になる足し
        # （かんが**え**て→考えて）は残す。足しの候補は数が多く、正しい足しが読みの並びだけでは枠に入らない
        extra = []
        for row in ins_rows[CLAUSE_TOP:]:
            text = row[1]
            # 打った読みよりずっと通りの悪い並び（かんが**へ**て: 文語の形）は残さない
            if row[0] < -CLAUSE_KANA_YOMI:
                break
            if _kana_word_split(text[s:s + len(typed) + 1], line[s:e], typed, dict_index):
                extra.append(row)
                if len(extra) >= CLAUSE_TOP:
                    break
        kept += extra
        # 読みの並びの枠に入らなかった足し（ちょう**へ**いされた→徴兵・むずかしく**し**て）は、枠に入った候補
        # （注意・難しくて）と費用が並んだら退く（並んで決め手が無く、行をそのまま残していた）
        weak_ins = {row[1] for row in extra}
        # 世の中に無い組み立ての片仮名の語（スパン＋屋）を、端の1字を抜いた読みの語（パン＋屋）に替えた形。
        # 文節の残り（屋に）は IME の顔のまま。費用（スパン屋 の方が安い）では並べられないので別に持つ
        vocab_forms = {}
        for i, rows in swaps.items():
            t = toks[i]
            if not (s <= t.start and t.end <= e):
                continue
            r = _tok_reading(t)
            pre = ''.join(_tok_reading(x) for x in toks if s <= x.start and x.end <= t.start)
            post = ''.join(_tok_reading(x) for x in toks if t.end <= x.start and x.end <= e)
            if typed != pre + r + post:
                if typed.count(r) != 1:
                    continue
                pre, post = typed[:typed.index(r)], typed[typed.index(r) + len(r):]
            for new_r, face in rows:
                text = line[:s] + pre + new_r + post + line[e:]
                vocab_forms[text] = (line[:t.start] + face + line[t.end:], line[s:t.start] + face + line[t.end:e])
        if (s, e) in long_vowel:
            face_lv, rest_lv = long_vowel[(s, e)]
            vocab_forms.setdefault(kana_line, (line[:s] + face_lv + rest_lv + line[e:], face_lv + rest_lv))
        if sure_clause and dict_index is not None and _kana_str(typed):
            for k in range(2, len(typed)):
                head, rest = typed[:k], typed[k:]
                if rest not in _RU_VERB_TAILS:
                    continue
                faces = _katakana_only_faces(head, dict_index)
                if len(faces) == 1:
                    vocab_forms.setdefault(kana_line, (line[:s] + faces[0] + rest + line[e:], faces[0] + rest))
        ranked = []
        # 辞書の形の漢字に置いた費用も見る（粗い変換は なつ→夏・よる→夜 のような
        # ふつうの語を漢字にできず、正しい候補が重く見えて試行の枠に入らなかった）。
        # 種表は候補の語をまとめて1回で引く
        splits = {}
        # 同梱の表にしか無い語（電気代）も語の部分と見られるよう、読み4字以上の切り方を先にまとめて引く
        _seed_prefetch([q for _yomi, text, _op, _i in kept
                        for q in _seed_split_queries(text[s:s + len(typed) + len(text) - len(kana_line)],
                                                     line[s:e], typed)])
        for _yomi, text, _op, _i in kept:
            delta = len(text) - len(kana_line)
            parts = _kana_word_split(text[s:s + len(typed) + delta], line[s:e], typed, dict_index)
            if parts:
                splits[text] = parts
        # 種表は1回の展開で引く（読みごとに引くと1回 0.1 秒ほど。IME の語を残す形の語も一緒に）
        own_words = []
        for _yomi, text, _op, _i in kept:
            delta = len(text) - len(kana_line)
            if delta == -1:
                own_words += [w for _h, _r, w in _kept_word_queries(line[s:e], text[s:s + len(typed) + delta])]
            elif delta == 0:
                q = _kept_stem_query(line[s:e], typed, text[s:s + len(typed)], dict_index)
                if q:
                    own_words.append(q[2])
        _seed_prefetch([w for w, _rest in splits.values()] + own_words)
        own_forms = {}
        placed_forms = {}   # 辞書の表記を置いた形（かなに戻した形より先に入口に通す）
        own_relax = set()   # 文法で確かな印の文節で、費用の線を外して試す IME の語を残した形
        for yomi, text, op, i in kept:
            delta = len(text) - len(kana_line)
            new_reading = text[s:s + len(typed) + delta]
            if delta == 1 and not sure_clause and _inserts_into_her_word(typed, new_reading, s, e, toks, store):
                # 本人の使っている語（補正・候補）の中に字を足して別の語にする形（ほうせい→方正・こうほう→後方）は見ない
                continue
            costs = [morphology.path_cost(text)]
            if delta == -1:
                # 1字抜いた読みが IME の顔の語と付属の間の1字を抜いた形の読みなら、語は IME の
                # 漢字のまま余った字だけ抜いた形（保存して）を候補の形にし、その費用で並べる
                info = {}
                own = _ime_word_kept(line[s:e], new_reading, store, dict_index, info=info)
                if not own and input_method == 'romaji':
                    own = _ime_tail_kept(line[s:e], typed, new_reading)
                if not own:
                    own = _ime_head_kept(line[s:e], typed, new_reading, store, dict_index)
                if own:
                    own_line = text[:s] + own + text[s + len(typed) + delta:]
                    own_forms[text] = (own_line, own, bool(info.get('ambiguous')))
                    costs.append(morphology.path_cost(own_line))
            elif delta == 0:
                # 付属の中の1打の戻し（寒**す**→寒い・温か**て**→温かい）も、語幹は IME の漢字のまま
                info = {}
                own = _ime_stem_kept(line[s:e], typed, new_reading, store, dict_index, info=info)
                if not own and input_method == 'romaji':
                    own = _ime_tail_kept(line[s:e], typed, new_reading)
                if own:
                    own_line = text[:s] + own + text[s + len(typed):]
                    own_forms[text] = (own_line, own, bool(info.get('ambiguous')))
                    costs.append(morphology.path_cost(own_line))
            elif delta == 1 and input_method == 'romaji':
                # 脱字の戻し（1字足す）も、足す所が IME の顔のかなの末尾の中なら語の漢字は残す
                own = _ime_tail_kept(line[s:e], typed, new_reading)
                if own:
                    own_line = text[:s] + own + text[s + len(typed) + delta:]
                    own_forms[text] = (own_line, own, False)
                    costs.append(morphology.path_cost(own_line))
            for nth in (0, 1):
                rough = (text[:s] + _rough_convert(new_reading, store, dict_index, nth)
                         + text[s + len(typed) + delta:])
                costs.append(morphology.path_cost(rough))
            ime_tail = _kana_tail(line[s:e])
            if ime_tail and len(ime_tail) < len(new_reading) and new_reading.endswith(ime_tail):
                # IME がかなのまま残した末尾（付属）はかなのまま、語の部分だけ粗く変換した見込みも並べる
                rough = (text[:s] + _rough_convert(new_reading[:-len(ime_tail)], store, dict_index) + ime_tail
                         + text[s + len(typed) + delta:])
                costs.append(morphology.path_cost(rough))
            placed_cost = None
            if text in splits:
                placed = _place_kanji(text, s, s + len(typed) + delta, line[s:e], typed,
                                      store, dict_index, context_vec, surrounding)
                if placed and len(placed) > 2 and placed[2] and not clause_marked:
                    # 印の無い文節（行の重さだけで試した文節）では、表記が並んで身近さで決めた弱い置き方は候補にしない
                    # （異様の判定が先: 正しい 今日中に を きょうちょうに→強調に に替えていた）
                    placed = None
                if placed:
                    placed_cost = morphology.path_cost(placed[0])
                    costs.append(placed_cost)
                    placed_forms[text] = placed
                if len(splits[text][0]) >= 2:
                    # 置く表記に決め手が無くても（玄関/厳寒・掃除/相似）、費用の見込みは表記の中で最も安い形で測る
                    # （置くかは入口と置き方が決める）。見込みが悪いと正しい戻しが試行の枠に入らなかった
                    # （げんかんの・そうじを・てちょうが: 入口は自ら漢字にできる）
                    est = _best_face_cost(text, s, s + len(typed) + delta, splits[text][0], splits[text][1],
                                          store, dict_index)
                    if est is not None:
                        costs.append(est)
            if text in stray_del and text in own_forms:
                # ローマ字の印の字を抜いて IME の語を残す形（難しく**い**て→難しくて・遅く**う**なり→遅くなり）は、
                # 行の費用の下がりが小さくても（い・う が 居る・唸る と読めて元の行が安く見える）試す。印が文法の証拠
                own_relax.add(text)
            if sure_clause and text in own_forms:
                # ただし、かなに戻して辞書の漢字に置いた形（はじめた→始めた）の方が IME の語を残した形
                # （初めた）より CLAUSE_GAIN 以上安ければ、IME の漢字そのものが疑わしいので線は外さない
                own_cost = morphology.path_cost(own_forms[text][0])
                if not (placed_cost is not None and own_cost is not None
                        and placed_cost + CLAUSE_GAIN <= own_cost):
                    own_relax.add(text)
            costs = [c for c in costs if c is not None]
            if not costs:
                continue
            if (sure_pairs and text not in own_forms
                    and not all(a and (new_reading[off:].endswith(a + post) or new_reading[off:].startswith(w + a))
                                for off, w, a, post in sure_pairs)):
                continue
            cost = min(costs)
            need = 1 if text in own_relax else CLAUSE_GAIN
            if base - cost >= need:
                ranked.append((base - cost, yomi, text))
        for text, (vocab_line, _face) in vocab_forms.items():
            cost = morphology.path_cost(vocab_line)
            if cost is None:
                continue
            # 費用の下がりは無くてよい（負でもよい）。読みの並びは並んだときの比べ方のために持つ
            ranked = [row for row in ranked if row[2] != text]
            ranked.append((base - cost, yomigram.logp_parts(text)[0] - y0, text))
        # 組み立てを替えた形は費用に関わらず先に（費用も読みの並びも巻き込んだ語を良いと見る形なので、
        # 費用順に並べると試行の枠に入らない）
        # 試行の枠（3つ）に入れる順は、行の費用の下がり（直した文のよさ）と読みの並びの良さ（打ち違いとして
        # ありそうか）を足して決める。費用だけで並べると、辞書の費用の安い語（危険 8731・発見 10474・拝見 10568）
        # が枠を埋め、正しい戻し（はけん→しけん: 試験 10693・読みの並び +1.6）が試されなかった。読みの並びだけで
        # 枠を1つ入れ替えると、正しい戻し（とりつぎで: 費用 3番目）が落ちた。線（CLAUSE_GAIN）は費用の下がりで見る
        # 文法で確かな印の文節（角**煮ください**）では IME の形が文として成り立たないので、辞書の語が置ける戻し
        # （かくにん→確認）を、かなのまま残る戻し（がくに・いかくに: 費用の下がりはわずかに大きい）より先に試す
        def rare_face(text):
            # IME の語をそのまま残して余った字を抜く形だけ見る。辞書の漢字を置く形（視界・文集: 層2）まで後ろに
            # 回すと、正しい置き方（し医科→視界）が 司会 に負けた
            form = own_forms.get(text)
            return bool(form and _rare_kango(form[1]))
        def keeps_reading_mark(text):
            if (s, e) not in reading_marked:
                return False
            end = s + len(typed) + len(text) - len(kana_line)
            return not _grammar_mark_removed(kana_line, s, s + len(typed), text, s, end)
        ranked.sort(key=lambda row: (row[2] not in vocab_forms,
                                     keeps_reading_mark(row[2]),
                                     row[2] not in stray_del,
                                     sure_clause and row[2] not in placed_forms,
                                     rare_face(row[2]),
                                     -(row[0] + CLAUSE_YOMI_WEIGHT * row[1]), row[2] in drop_fix, row[2]))
        vocab_texts = {v[0] for v in vocab_forms.values()}
        for _gain, yomi, text in ranked:
            if any(row[3] in vocab_texts for row in found):
                break
            if trials >= CLAUSE_RETRIES and text not in vocab_forms:
                break
            if found and _gain < max(row[0] for row in found) - MARGIN:
                # 1つ目が採れた後は、費用の下がりの見込みが採れた形と並ばない（MARGIN 未満）候補は
                # 入口に通さない。見込みは入口を通した後の下がりと同じかそれ以上がほとんど
                # （316行で中央値 0・上回ったのは 10 行）なので、並んで比べる形にはならない。
                # 通し直し 707 回のうち 289 回（時間の 28%）がこれだった（336例で結果は不変）
                break
            own = own_forms.get(text)
            placed_form = placed_forms.get(text)
            variants = [(text, s + len(typed) + len(text) - len(kana_line), None, 'kana')]
            if placed_form:
                # かなに戻した形を入口が通さなかったとき（かなに戻すと前後のかなと長い連なりになり、入口が
                # 別の切り方をして崩れる: にかくにんしてもらった）は、辞書の表記を置いた形（かな→漢字に
                # 決め手のあるもの）も入口に通す。置いた形は IME が変換した行と同じ扱いで入口の門を受ける。
                # かなに戻した形に入口が紫を付け、読みの並びの良さ（yomigram）も足りなければ置かない（添え乳）
                variants.append((placed_form[0], s + len(placed_form[1]), None, 'placed'))
            if own:
                # IME の語を残した形を先に。入口が通さなければ、かなに戻した形も試す
                # （上**う**た: 上た は通らず、うえた が通る）
                variants.insert(0, (own[0], s + len(own[1]), own, 'own'))
            vocab = vocab_forms.get(text)
            if vocab:
                # 世の中に在る組み立てに替えた形（新しいパン屋に）を一番先に。入口がそのまま通せば採る
                variants.insert(0, (vocab[0], s + len(vocab[1]), None, 'vocab'))
            own_row = None
            kana_odd_seen = False
            for trial_text, trial_e, own, kind in variants:
                if trials >= CLAUSE_RETRIES and kind != 'vocab':
                    break
                if kind == 'own' and own and _not_everyday_kango(own[1]) and not sure_clause:
                    # IME の語を残して余った字だけ抜く形も、残す語が身近さの表に無ければ試さない
                    continue
                if kind == 'placed' and kana_odd_seen and yomi < CLAUSE_KANA_YOMI and not sure_clause:
                    # 文法で確かな印の文節（内容を角**煮ください**→かくにんください に紫）では、置いた形（確認ください）
                    # も試す。入口はかなの並びを確かめきれず紫を付けただけで、IME の形は文として成り立たない
                    continue
                if kind != 'kana' and _new_conjugation_mismatch(line, trial_text):
                    # 漢字の形（IME の語を残した形・置いた形）そのものに、元の行に無い活用の形の合わない続き
                    # （多**い**なる・懐かし**なっ**た）があれば入口に通さない（試行の枠を使わない: 後ろの正しい戻し
                    # 多くなる が枠に入る）。かなの形は入口が変換してから見る（かくにんください は切り方が定まらない）
                    continue
                if kind != 'vocab':
                    trials += 1   # 組み立ての形（1文節に高々1つ）は枠を使わない
                got = retry(trial_text)
                if not got:
                    continue
                corrected = got.get('corrected', trial_text)
                if corrected == line:
                    continue
                new_e = len(corrected) - (len(line) - e)
                face = corrected[s:new_e]
                if kind != 'placed' and _new_conjugation_mismatch(line, corrected):
                    # 入口を通っても、元の行に無い活用の形の合わない続きができる形（多**い**なる）は採らない
                    continue
                if input_method == 'romaji' and _sure_mark_left(corrected, s, new_e):
                    # 読み直した文節の中に文法で確かな印が残る形（良いて**い**です→良いてです: 良い＋て が残る）は、
                    # 文節を直せていない（ローマ字入力だけ: かな入力では退けた後の試行で別の誤り 聞くくのは→括のは が通った）
                    continue
                if (kind == 'kana' and any(_kanji(c) for c in face) and _not_everyday_kango(face)
                        and not sure_clause and not _her_word(store, trial_text[s:trial_e], face)):
                    # 入口が自ら置いた漢字が身近さの表に無い語（遥遠・夕立）なら、漢字を置かずかなのまま（迷いの印）
                    # で採る（うに 10-19）。かなの形は下の かな の門（辞書の語であること）を受ける
                    got = dict(got, corrected=trial_text, odd_spans=[], unsure_spans=[], weak_pick=True)
                    corrected = trial_text
                    new_e = trial_e
                    face = corrected[s:new_e]
                # 紫（入口の異様の印）: 漢字に変えた直しに掛かる紫は採らない。かなに戻した文節に掛かる
                # 紫（どようび・てちょう: 入口はかなの並びを確かめきれない）は、辞書の漢字に置けたとき
                # （土曜日）だけ採り、かなのまま残す形にはしない。文節の外の紫は、元の行の同じ所にも
                # あったもの（スマートフォン）だけ許す
                # 紫・迷いの位置は入口に渡した行（trial_text）の上の位置。文節は [s, trial_e)
                odd_got = [(x[0], x[1]) for x in (got.get('odd_spans') or ()) if len(x) >= 2 and x[0] < x[1]]
                kana_odd = False
                if odd_got:
                    if any(not _old_doubt(a, b, s, e, trial_e, result, 'odd_spans')
                           for a, b in odd_got if not (a < trial_e and s < b)):
                        continue
                    if any(a < trial_e and s < b for a, b in odd_got):
                        if not _kana_str(face):
                            continue
                        kana_odd = True
                        kana_odd_seen = True
                # 元の文節にある連体詞（昨日**あの**店・先生**あの**件）は直した文節にも残ること。
                # 連体詞は独立した語で、名詞の直後に来るのもふつう（余った字とは見ない）
                if any(a not in face for a in adnominals):
                    continue
                # 入口が読みの変わる直し（しょうえがを→生姜を・にしんた→にしんだ）を
                # 重ねた結果は採らない（1打の戻しと別の直しが積み重なった形）
                if not _reading_kept(trial_text, s, trial_e, corrected, new_e, result):
                    continue
                unsure = list(got.get('unsure_spans') or ())
                # かなに戻した文節に掛かる「迷い」は、かなに戻した跡（入口はかなの
                # 並びを確かめきれない）なので許す。漢字に変えた直しに迷いが残る、
                # または文節に掛からない迷いがあれば採らない。ただし入口が置いた漢字が
                # IME の元の顔と同じ漢字（約束**ま**の→約束の・連絡**き**して→連絡して）なら、
                # 迷いは IME と同じ変換を入口が確かめきれなかっただけなので許す
                same_kanji = (not _kana_str(face) and _kanji_seq(face)
                              and _kanji_seq(face) == _kanji_seq(line[s:e]))
                # 文節の外の迷いは、元の行にも同じ所に在るもの（腕せが**ぱんぱん**に: ぱんぱん は
                # 元から迷い）なら、この直しが生んだものではないので気にしない
                outside = [(a, b) for a, b in unsure if b <= s or trial_e <= a]
                inside = [(a, b) for a, b in unsure if a < trial_e and s < b]
                if any(not _old_doubt(a, b, s, e, trial_e, result) for a, b in outside):
                    continue
                unsure_face = False
                if inside and not _kana_str(face) and not same_kanji:
                    # 入口が自ら漢字にしたが迷いを残した形（げかかんの→げんかんの→玄関の）: 疑いの印のある文節で、
                    # 戻した読みが打った読みより十分に通りのよい並びで、置いた形が稀な漢語でなければ、迷いの印（紫）
                    # を付けて採る（迷うなら紫: うに 10-18）。印の無い文節・通りの悪い読み・珍しい語では採らない
                    if not (kind == 'kana' and clause_marked and yomi >= CLAUSE_KANA_YOMI
                            and _kanji_seq(face) and _new_kanji(face, line[s:e])
                            and _leading_kana_kept(face, line[s:e]) and not _rare_kango(face)):
                        continue
                    unsure_face = True
                cost = morphology.path_cost(corrected)
                if cost is None:
                    continue
                real = base - cost
                kana_face = _kana_str(face)
                gate_real = real
                if kind == 'placed' and text in splits and len(splits[text][0]) >= 2:
                    # 同じ読みの表記の違い（電気代 17001・電機代 15618）は辞書の費用の癖で、直しの根拠ではない。
                    # 線を割るかは並ぶ表記の中で最も安い形の費用で見る（置く形は置き方が決めた表記のまま）
                    est = _best_face_cost(corrected, s, new_e, splits[text][0], splits[text][1], store, dict_index)
                    if est is not None:
                        gate_real = max(real, base - est)
                # 直した行は疑いの線を割ること（線の上でも大きく軽くなれば採る形は、
                # 99例で 1つ増やす代わりに誤った直しを 3つ増やしたので採らない）
                # 入口が語と認めず、かなのまま残った直しは、読みの並びの良さだけが
                # 支え。打った読みより十分に通りのよい並びでなければ「弱い」
                # （珍しい語の読みに化けるのを止める）。弱い直しが一番なら、
                # 次の候補に落とさず、行をそのまま残す
                # かなのまま残る直しは、辞書に読みの在る語（＋手を付けていない付属）で
                # あること（しはゅうでん→しきゅうでん のように、語でない並びに替えない）
                # 入口がかなに戻した文節を自ら漢字に変換した形（えきまえ→駅前・ことし→今年）は、
                # 行の残り（料理本・去年）の重さでは止めない。字あたりの費用は絶対値では使えず
                # （正しい2字の名詞でも 1200 を超える）、入口の変換は入口の門と共通の最終検査を通る
                # ただし戻した読みが打った読みより通りのよい並び（yomi > CLAUSE_CONVERTED_YOMI）のときだけ。
                # 通りの悪い読み（ひとしと→ことしと: 近所の今年と話した）を入口が漢字にしても、行の重さの門は残す
                # 入口が自ら漢字にした形でも、珍しい2字の漢語（潅漑: 層3）に変換した形は行の重さの門を外さない
                # （どうしたらいいか閑雅て→かんがい→潅漑 を採っていた）
                # 「入口が自ら漢字にした」は、元の文節に無い漢字が顔に在ること（元の漢字が残り、別の語がかなに
                # 戻っただけの顔（設定を＋ともに）は違う）
                converted = ((kind == 'kana' and not kana_face and bool(_kanji_seq(face))
                              and _new_kanji(face, line[s:e]) and _leading_kana_kept(face, line[s:e])
                              and yomi > CLAUSE_CONVERTED_YOMI and not _rare_kango(face))
                             # 辞書の漢字を置いた形（翌日の: よくまじつ→よくじつ）も、戻した読みが打った読みより
                             # 十分に通りのよい並び（CLAUSE_KANA_YOMI 以上）で、置いた語がふつうの語（漢語の層 1:
                             # 翌日・大切・挑戦）なら、行の残り（夜更かし・響く）の重さでは止めない。珍しい語
                             # （如何・定見: 層 2・3）は、読みの並びが良くても置かない（しいか→如何・いてけん→定見）
                             or (kind == 'placed' and not kana_face and bool(_kanji_seq(face))
                                 and yomi >= CLAUSE_KANA_YOMI and _familiar_kango(face))
                             # 文法で確かな印（活用の形が合わない続き: 閑雅**て**）の文節では、IME の形が文として
                             # 成り立たないので、置いた形（考えて）が珍しい漢語でなければ行の残りの重さでは止めない
                             # （どうしたらいいか の字あたりの費用は正しい文でも線を超える）
                             or (kind == 'placed' and not kana_face and bool(_kanji_seq(face))
                                 and sure_clause and not _rare_kango(face))
                             # ローマ字入力の印（文法で付けない所の1字: **っ**天気予報）の文節も同じ（印の字を抜いた
                             # 読みに辞書の語が置けるなら、IME の形は文として成り立たない）
                             or (kind == 'placed' and not kana_face and bool(_kanji_seq(face))
                                 and stray_clause and not _not_everyday_kango(face)))
                grammar_fix = ((s, e) in reading_marked and kana_face and not got.get('unsure_spans') and not got.get('odd_spans')
                               and _grammar_mark_removed(kana_line, s, s + len(typed), corrected, s, new_e))
                # 入口が IME の顔と同じ漢字に戻した形（食べ**タフ**→食べた・猫**鍵**庭→猫が庭: 余った字・語だけが消え、
                # 残る漢字は元の顔のもの）で、戻した読みが打った読みより大きく通りのよい並びなら、行の残り（朝ご飯）の
                # 重さでは止めない（2026-10-21 隣接キーの総当たり 2536件）
                kept_kanji = (kind == 'kana' and not kana_face and bool(_kanji_seq(face)) and not unsure
                              and set(_kanji_seq(face)) <= set(_kanji_seq(line[s:e]))
                              and yomi >= CLAUSE_KEPT_YOMI)
                ok = (not kana_odd and gate_real >= CLAUSE_GAIN
                      and (_cost_per_char(corrected, cost) < CLAUSE_COST
                           or converted or grammar_fix or kept_kanji
                           or (kana_face and _known_kana_word(face, line[s:e], typed, dict_index)))
                      and (not kana_face or grammar_fix
                           or _known_kana_word(face, line[s:e], typed, dict_index, tail=4, inflected=True)))
                if (own and corrected == trial_text and real >= (1 if text in own_relax else CLAUSE_GAIN)
                        and not _rare_kango(own[1])):
                    # IME の語をそのまま残して余った字だけ抜いた形を入口がそのまま通したなら、
                    # 行の残りの重さ（字あたりの費用: 新しいす**パン屋**）では止めない
                    ok = True
                if kind == 'vocab' and corrected == trial_text and not kana_odd:
                    # 世の中に無い組み立ての片仮名の語を在る組み立てに替えた形（スパン屋に→パン屋に）を入口が
                    # そのまま通したなら、費用（スパン屋 の方が 390 安い）では止めない。片仮名の語は1字抜いても
                    # 別の片仮名の語になりやすく、費用も読みの並びも巻き込んだ語を良いと見るので、辞書の表が決め手
                    ok = True
                weak = kana_face and yomi < CLAUSE_KANA_YOMI and not grammar_fix
                if kana_odd and weak:
                    # 入口が紫を付けたかなに漢字を置く形は、戻した読みが打った読みより十分に通りの
                    # よい並み（yomigram）のときだけ（どようび 17）。そうでなければ、辞書にある珍しい
                    # 語（そえじ→添え乳・つながしい→継しい）を紫のかなに置いてしまう
                    continue
                if kana_face:
                    # かなのまま残った語は、IME が漢字に変換していた文節なので辞書の形の
                    # 漢字に置く（辞書で1通り、または文脈か行の費用に決め手があるときだけ。
                    # 軽くならなければかなのまま）。かなの形が門を通るならその上に置くだけ
                    # （漢字の形だけが共通の最終検査で止まったときのために、かなの形を残す）。
                    # かなの形が門を通らないときは、置いた形が漢字の直しと同じ門を通ること
                    placed = _place_kanji(corrected, s, new_e, line[s:e], typed,
                                          store, dict_index, context_vec, surrounding)
                    if placed and _new_conjugation_mismatch(line, placed[0]):
                        # 置いた形が打ち違いの印そのもの（聞き置く＋ながら: 基本形＋ながら）になるなら置かない
                        placed = None
                    if (placed and len(placed) > 2 and placed[2] and not clause_marked
                            and not (ok and not weak)):
                        # 印の無い文節では、表記が並んで身近さで決めた弱い置き方は、かなに戻した形がそれだけで門を
                        # 通る（こうえんに: 行の重さ・読みの並び・辞書の語）ときだけ、その上に置く（公園＋紫）。
                        # かなの形が通らず置いた形の費用だけが支えの形（きょうちょうに→強調に）は置かない
                        placed = None
                    alt_cost = morphology.path_cost(placed[0]) if placed else None
                    if placed and alt_cost is not None and alt_cost < cost:
                        # 線を割るかは、並ぶ表記の中で最も安い形の費用で見る（電気代/電機代: 表記の違いは根拠にしない）
                        parts0 = _kana_word_split(face, line[s:e], typed, dict_index)
                        est = (_best_face_cost(corrected, s, new_e, parts0[0], parts0[1], store, dict_index)
                               if parts0 and len(parts0[0]) >= 2 else None)
                        gate_cost = min(alt_cost, est) if est is not None else alt_cost
                        strict = (base - gate_cost >= CLAUSE_GAIN
                                  and (_cost_per_char(placed[0], gate_cost) < CLAUSE_COST
                                       or (sure_clause and not _rare_kango(placed[1]))))
                        if (ok and not weak) or strict:
                            extra = {'kana_fallback': (corrected, (s, e, face))} if ok and not weak else {}
                            parts = _kana_word_split(face, line[s:e], typed, dict_index)
                            if parts:
                                extra['placed_word'] = (parts[0], placed[1][:len(placed[1]) - len(parts[1])])
                            corrected, face = placed[0], placed[1]
                            new_e = s + len(face)
                            if len(placed) > 2 and placed[2]:
                                extra['weak_pick'] = True
                            got = dict(got, corrected=corrected, **extra)
                            cost, real = alt_cost, base - alt_cost
                            ok, weak = True, False
                if not ok:
                    continue
                if text in weak_ins:
                    got = dict(got, weak_insert=True)
                if kind == 'placed':
                    # 置いた形を先に通したしるし（並んだとき、入口が自ら漢字にした形より退く）
                    got = dict(got, placed_first=True)
                    if text in splits and placed_form:
                        word, rest = splits[text]
                        got['placed_word'] = (word, placed_form[1][:len(placed_form[1]) - len(rest)])
                    if placed_form and len(placed_form) > 2 and placed_form[2]:
                        got['weak_pick'] = True
                if unsure_face:
                    got = dict(got, weak_pick=True)
                if ((kind in ('placed', 'own') or (kind == 'kana' and any(_kanji(c) for c in face)))
                        and _unjudged_kango(face)
                        and not (got.get('placed_word') and _her_word(store, *got['placed_word']))):
                    # 身近さの表に判定の無い2字の漢語（夕立・遥遠）を置く・残す・入口が自ら漢字にするときは、
                    # 迷いの印（紫）を残す（迷うなら紫）
                    got = dict(got, weak_pick=True)
                if (rare_only and kind not in ('own', 'vocab')
                        and not (got.get('placed_word') and _her_word(store, *got['placed_word']))):
                    # 稀な語の印だけの文節（でんな稀代の）の読み直し（近代の・電気代の）は、本人の語でなければ紫を残す
                    got = dict(got, weak_pick=True)
                # 8番目: 辞書の漢字を置いた形か、9番目: IME の語を残して余った字だけ抜いた形か（_ime_word_kept）、
                # 10番目: 紫の付いたかなに置いた形か
                if text in stray_del:
                    # ローマ字の印の字を抜いた形（番号**う**を→番号を）。残した・置いた形も同じ印を受け継ぎ、
                    # 共通の門「同じ字の重なりは直さない」を文節の証明付きで通す（うに 10-19 11:08Z）
                    got = dict(got, stray_del=True)
                if text in drop_fix:
                    got = dict(got, drop_fix=True)   # 脱字の戻し: 並んだら他の戻しに負ける
                if input_method == 'romaji' and not any(ch.isascii() and ch.isalpha() for ch in kana_line):
                    op0 = cands.get(text, (None, None))[0]
                    if op0 == 'del':
                        got = dict(got, kana_del=True)
                    elif op0 == 'edit' and len(text) < len(kana_line):
                        got = dict(got, letter_del=True)
                if kind == 'vocab':
                    got = dict(got, vocab_form=True)   # 世の中の表の組み立てに替えた形（ミスらない・パン屋に）
                found.append((real, s, e, trial_text, got, yomi, weak,
                              'kana_fallback' in got or 'placed_first' in got, kana_face, bool(own), kana_odd))
                if own and own[2] and not kana_odd and own_row is None:
                    # IME の語を残した形が通っても、語の読みに辞書の漢字が複数あって IME に聞けなかった
                    # （雲・CI）なら、かなに戻した形も入口に通す。入口が自ら別の漢字に変換したら
                    # （窓を**開け**たら・雨**上がり**）そちら: 入口は文の中で選ぶが、IME の漢字は余った字の
                    # 入った読み（あけむたら・あめふがり）の変換で選ばれたもの。本人の IME に聞けたときは IME の顔のまま
                    own_row, own_face = len(found) - 1, face
                    continue
                if own_row is not None:
                    # かなに戻した形の方を採るのは、入口が自ら別の漢字に変換したとき（開けたら）か、置いた形の
                    # 行の費用が IME の語を残した形より CLAUSE_GAIN 以上安いとき（雨上がり 対 雨あがり: IME は
                    # あめ だけを 雨 にしたのであって 雨あがり という表記を選んではいない）。それ以外は IME の形
                    if ((kind == 'kana' and not kana_face and _kanji_seq(face)
                         and _kanji_seq(face) != _kanji_seq(own_face))
                            or real >= found[own_row][0] + CLAUSE_GAIN):
                        found.pop(own_row)
                    else:
                        found.pop()
                break
        if found:
            break
        if trials >= CLAUSE_RETRIES and not any(
                toks[i].start < e2 and s2 < toks[i].end for i in sure for s2, e2, _t in ordered[ci + 1:CLAUSE_TOKENS]):
            break
    if not found:
        return None
    found.sort(key=lambda row: -row[0])
    if len(found) > 1 and found[0][0] - found[1][0] < MARGIN:
        # 費用の下がりが並んだら、読みの並びで大きく勝つものだけ採る
        # （わ**す**れて と わ**か**れて→かれて の削除が並ぶ、など）
        close = sorted((row for row in found if found[0][0] - row[0] < MARGIN),
                       key=lambda row: -(row[0] + CLAUSE_YOMI_WEIGHT * row[5]))
        # 入口が紫を付けたかなに辞書の漢字を置いた形（ぶんちゅう→文中に）は、入口が自ら変換した形や
        # IME の語を残した形（文集に）と並んだら退く（紫は入口がその並びを語と認めなかった印）
        firm = [row for row in close if not row[10]]
        if firm and len(firm) < len(close):
            close = firm
        # かなのまま残って読みの並びも足りない弱い形（かんがいて 2.3）は、確かな形（鑑みて -1.6・考えて -0.5）と並んだら
        # 退く（弱い形が一番に残ると行をそのまま残すので、確かな形の並びを先に決める）。ただし弱い形が読みの並びで
        # 大きく勝つ（おくれた 4.9 対 押し切れた -2.0: 打ち違いとして一番ありそうな戻しで、表記だけが決められない）
        # ときは退かない（押し切れた を置いていた）
        steady = [row for row in close if not row[6]]
        if steady and len(steady) < len(close):
            if max(row[5] for row in close if row[6]) - max(row[5] for row in steady) < CLAUSE_YOMI_TIE:
                close = steady
        # 迷いの印を付けて採った形（身近さで決めた表記・入口が迷った漢字・稀な語だけの印の文節）は、確かな形
        # （締め切り）と並んだら退く（締めくくり: 表記が並んで決めた形）
        sure_rows = [row for row in close if not row[4].get('weak_pick')]
        if sure_rows and len(sure_rows) < len(close):
            close = sure_rows
        # IME の語を残して余った字だけ抜いた形（確認して・半分くらい）は、その字を別の字に
        # 置き換えた形（確認にして・半分にくらい）やかなに置いた形（きょうえき）より先。
        # IME が語と付属の間で切った跡がそのまま残る形で、打ち違いは1打多いだけ
        stray_rows = [row for row in close if row[4].get('stray_del')]
        if stray_rows and len(stray_rows) < len(close):
            close = stray_rows
        # ローマ字で英字が残っていない並び: かな1字の抜き（困る・水槽）は英字単位の抜き（決まる・失そう）より先
        if any(row[4].get('kana_del') for row in close) and any(row[4].get('letter_del') for row in close):
            close = [row for row in close if not row[4].get('letter_del')]
        own_rows = [row for row in close if row[9]]
        if own_rows and len(own_rows) < len(close):
            close = own_rows
        firm_ins = [row for row in close if not row[4].get('weak_insert')]
        if firm_ins and len(firm_ins) < len(close):
            close = firm_ins
        # 置いた語が本人の使った語（考え）である形は、使っていない語（鑑み）に置いた形より先
        # （辞書の費用は 鑑み の方が安く、読みの並びの差も小さい。置き方の「並べば本人優先」と同じ）
        hers = [row for row in close
                if row[4].get('placed_word') and _her_word(store, *row[4]['placed_word'])]
        if hers and len(hers) < len(close):
            close = hers
        if len(close) > 1 and close[0][5] - close[1][5] < CLAUSE_YOMI_TIE:
            # 読みの並びでも並んだら: 入口が自分で漢字にした直し（写真をとった→撮った）
            # は、かなに置いた漢字（しとった→湿った）より強い根拠（入口は文脈と文法を
            # 見て変換する）なので、置いた形は退く
            strong = [row for row in close if not row[7] and not row[8]]
            if strong and any(row[7] for row in close):
                close = strong
        if len(close) > 1 and close[0][5] - close[1][5] < CLAUSE_YOMI_TIE:
            # それでも並んだら、周りの語との馴染み（文脈）で決め手が
            # あるものだけ採る（決め手が無ければ行をそのまま残す）
            pick = _tie_by_context(close, line, e, clauses, store, dict_index,
                                   context_vec, surrounding)
            if pick is None:
                # 文脈に決め手が無ければ、置いた語の一般さ（本人の語 → AI 判定の段 → 表に無い語 → 稀）→ 読みの並び
                # の順で1つに決める（「迷ったら何もしない」はしない: うに 10-18）。決めた形には迷いの印（紫）を残す。
                # 一般さの順で比べられるのは同じ読みの語どうし（電気/伝記/電機: 表は同じ読みの表記の身近さ）。
                # 別の読みの語どうし（ちゅうい→注意・ちょうせい→調整）は、本人の語を先に、候補を並べたのと同じ尺度
                # （費用の下がり＋読みの並び×重み）で決める（表の順では 危険 が 試験 に、読みの並びだけでは 調整 が
                # 注意 に勝っていた）
                if len({_row_reading(row, line) for row in close}) == 1:
                    close = sorted(close, key=lambda row: (_face_rank(row, line, store), -row[5]))
                else:
                    close = sorted(close, key=lambda row: (_face_rank(row, line, store) != -1,
                                                           -(row[0] + CLAUSE_YOMI_WEIGHT * row[5])))
                pick = close[0]
                pick = pick[:4] + (dict(pick[4], weak_pick=True),) + pick[5:]
            close = [pick]
        if len(close) > 1 and close[0][5] < max(row[5] for row in close):
            # 尺度の一番（締め切り: 費用 17011・読み -1.8）が読みの並びの一番（締め括り: 15269・2.7）でない: 直した文のよさと
            # 打ち違いのありそうさが割れたので、採る形に迷いの印（紫）を残す
            pick = close[0]
            close = [pick[:4] + (dict(pick[4], weak_pick=True),) + pick[5:]]
        found = close
    _real, s, e, text, got, _yomi, weak, _placed, _kana, _own, _odd = found[0]
    if weak:
        return None
    corrected = got.get('corrected', text)
    new_e = len(corrected) - (len(line) - e)
    if new_e < s:
        return None
    return text, got, (s, e, corrected[s:new_e])


def _mapped_span(text, corrected, a, b):
    """text の [a, b) を corrected の上の位置に写す（手前の直しで長さが変わっても追える）。"""
    import difflib
    ops = difflib.SequenceMatcher(None, text, corrected, autojunk=False).get_opcodes()

    def mapped(p, end):
        for tag, i1, i2, j1, j2 in ops:
            if (i1 < p <= i2) if end else (i1 <= p < i2):
                if tag == 'equal':
                    return j1 + (p - i1)
                return j2 if end else j1
        return len(corrected) if end else 0
    return mapped(a, False), mapped(b, True)


def _fix_in_ime_clause(line, found, dict_index):
    """1打の直し `found` の直した所は、IME が確定した文節（打った読みの残る所）に掛かるか。"""
    try:
        import morphology
        _text, _got, (lo, hi, _face) = found
        toks = list(morphology.tokenize(line))
        return any(s < hi and lo < e for s, e, _typed, _fe in _ime_clauses(line, toks, dict_index))
    except Exception:
        return False


def _suspect_left(found):
    """1打の直し `found`（`repair` の返り）の直した所の前後に、まだ疑いの印（`_suspect_tokens`）が残るか。
    前**お**が→前**え**が（名詞＋1字フィラー）のように、1打の置き換えで紫は消えても語の並びに
    打ち違いの跡が残るなら、IME の文節の読み直し（前が）も試す値がある。"""
    import morphology
    text, got, (lo, hi, _face) = found
    corrected = got.get('corrected', text)
    toks = morphology.tokenize(corrected)
    spots = _suspect_tokens(toks)
    if not spots:
        return False
    a, b = _mapped_span(text, corrected, max(0, lo - 1), min(len(text), hi + 1))
    return any(toks[i].start < b and a < toks[i].end for i in spots)


def _found_cost(found):
    import morphology
    text, got, _span = found
    return morphology.path_cost(got.get('corrected', text))


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

        seen = {}

        def retry(text):
            # 戻した行を入口に通す。入口は離れたキーや2打の滑りをこの上に重ねない
            # （重ねると読みが変わり、通し直しの意味が無い。時間も大半がその探索だった）
            # 同じ行の中で同じ戻しは1度だけ通す（3番目の道が1番目と同じ候補を試すことがある）
            if text in seen:
                return seen[text]
            import contextual_repair
            token = _ACTIVE.set(True)
            slip = contextual_repair.SLIP_REVERTED.set(True)
            try:
                got = corrector.correct_line(text, *args, **kwargs)
            finally:
                contextual_repair.SLIP_REVERTED.reset(slip)
                _ACTIVE.reset(token)
            seen[text] = got
            return got

        if options.get('input_method', 'kana') in ('kana', 'romaji'):
            lv = _long_vowel_katakana_form(line, options.get('dict_index'))
            if lv:
                lo, hi, face = lv
                out = _settle_clause_forms(result, line, [(line[:lo] + face + line[hi:], (lo, hi, face))],
                                           options, decisions)
                if out is not result:
                    return out
        found = repair(line, result, retry,
                       input_method=options.get('input_method', 'kana'),
                       decisions=decisions,
                       dict_index=options.get('dict_index'))
        if not found or _suspect_left(found) or _fix_in_ime_clause(line, found, options.get('dict_index')):
            # 1打の直しが無いとき、直した所にまだ疑いの印が残るとき（前おが→前えが）、または直した所が IME の
            # 文節の中に掛かるとき（夕し**どん**の→夕し**んど**の: 打った読みを IME が変換した文節は丸ごと読み直せる）
            # は、IME の文節の読み直しも試す。1打の直しがあるときは、読み直した行の並びの費用が CLAUSE_GAIN 以上
            # 安いときだけ読み直しの方に替える（前が・友人の）
            # 文脈の材料: 同じ行の内容語 → 直前に確定した語 → 上下の行の語
            surrounding = []
            try:
                from context_vec import extract_content_words
                tokenize_fn = options.get('tokenize_fn')
                if tokenize_fn is not None:
                    surrounding += extract_content_words(tokenize_fn, line)
            except Exception:
                pass
            surrounding += list(options.get('recent_words') or ())
            surrounding += list(options.get('nearby_words') or ())
            alt = repair_ime_clause(line, result, retry,
                                    input_method=options.get('input_method', 'kana'),
                                    decisions=decisions,
                                    dict_index=options.get('dict_index'),
                                    store=options.get('store'),
                                    context_vec=options.get('context_vec'),
                                    surrounding=surrounding)
            if alt and found:
                c_alt, c_found = _found_cost(alt), _found_cost(found)
                if alt[1].get('corrected', alt[0]) == found[1].get('corrected', found[0]):
                    pass   # 同じ行なら文節の形（置く範囲の証明を持つ）で最終検査を受ける
                elif alt[1].get('vocab_form') and not _suspect_left(alt):
                    # 文節の読み直しが世の中の表の組み立て（片仮名の語＋る動詞の語尾: ミスらない）に替えた形は、
                    # 費用では比べない（1打の直し 擦らない の方が安い。片仮名の語は費用で負けやすい）
                    pass
                elif c_alt is None or c_found is None or c_alt + CLAUSE_GAIN > c_found:
                    alt = None
            if alt:
                found = alt
        if not found and options.get('input_method', 'kana') in ('kana', 'romaji'):
            # 3番目の道: 文の組み立てが大きく良くなる1打の置き換え（ごさいます→ございます・ありかとう→ありがとう）。
            # 紫・迷い・費用の高いかなの並びを手掛かりに、読みの並びの表や語の内側の門で止めずに試す（VOUCH_GAIN）
            found = repair(line, result, retry,
                           input_method=options.get('input_method', 'kana'),
                           decisions=decisions,
                           dict_index=options.get('dict_index'), vouch=True)
        if found and _breaks_kana_word(line, found, options.get('dict_index'), result):
            found = None
        if found and _keeps_sure_mark(line, found):
            found = None
        if not found:
            return _mark_rare_clauses(result, line, options)
        text, inner, (lo, hi, face) = found
        forms = [(inner.get('corrected', text), (lo, hi, face))]
        if inner.get('kana_fallback'):
            forms.append(inner['kana_fallback'])
        elif inner.get('unsure_spans') and not inner.get('odd_spans'):
            placed = _place_doubtful_run(inner.get('corrected', text), lo, line, options)
            if placed:
                forms.insert(0, placed)
        return _settle_clause_forms(result, line, forms, options, decisions, weak=bool(inner.get('weak_pick')),
                                    stray=bool(inner.get('stray_del')), doubt=bool(inner.get('yomi_del')))
    return wrapped


def _reading_suspect(line, clauses):
    """IME の顔には印が無くても、打った読みの並びに疑いの字句（きりがないよう**な**も）が在る文節 → [(始まり, 終わり)]。

    顔（霧が内容名も）は語に見えても読みの文法が怪しい: 異様さの印（うに 10-19 17:41Z）。読みはかなだけ・4字以上。
    """
    import morphology
    out = []
    for s, e, typed in sorted({(c[0], c[1]): c[2] for c in clauses}.items(), key=lambda kv: kv[0]) and [
            (k[0], k[1], v) for k, v in sorted({(c[0], c[1]): c[2] for c in clauses}.items())]:
        if not _kana_str(typed) or len(typed) < 4 or not any(_kanji(c) for c in line[s:e]) or e - s < 3:
            continue
        seg_cost = morphology.path_cost(line[s:e])
        if seg_cost is None or seg_cost / (e - s) < CLAUSE_LOCAL_COST:
            continue
        try:
            ktoks = list(morphology.tokenize(line[:s] + typed + line[e:]))
        except Exception:
            continue
        if any(s <= ktoks[i].start and ktoks[i].end <= s + len(typed) for i in _suspect_tokens(ktoks)):
            out.append((s, e))
    return out


_RUN_PARTICLES = ('は', 'が', 'を', 'に', 'の', 'も', 'へ', 'で', 'と')
# る動詞（話し言葉の サボる・ミスる・メモる）の活用語尾
_RU_VERB_TAILS = ('る', 'った', 'って', 'っても', 'ったら', 'ったり', 'らない', 'らず', 'ります', 'りました', 'れば', 'ろう',
                  'れ', 'り', 'ら')


def _long_vowel_katakana_form(line, dict_index):
    """対の無い行で、ー を1つ打ち落とした片仮名の語の読み（しょとかっと・書とかっと）の並び → (始まり, 終わり, 置く形)。
    無ければ None。頭の字句は1字の漢字かひらがな、続きはひらがなだけ。"""
    import morphology
    if dict_index is None or not line:
        return None
    try:
        toks = list(morphology.tokenize(line))
    except Exception:
        return None
    for i, t in enumerate(toks):
        head_kanji = len(t.surface) == 1 and _kanji(t.surface)
        if not (head_kanji or _hira_str(t.surface)):
            continue
        if i > 0 and toks[i - 1].end == t.start and (_hira_str(toks[i - 1].surface) or _kanji(toks[i - 1].surface[-1])):
            continue   # 並びの途中からは始めない
        reading = _tok_reading(t)
        best = None
        for j in range(i + 1, min(len(toks), i + 8)):
            u = toks[j]
            if u.start != toks[j - 1].end or not _hira_str(u.surface):
                break
            reading += _tok_reading(u)
            if not _kana_str(reading):
                break
            lv = _katakana_long_vowel_face(reading, dict_index)
            if lv:
                best = (t.start, u.end, lv[0] + lv[1])
        if best:
            return best
    return None


def _hira_str(s):
    return bool(s) and all('ぁ' <= c <= 'ゖ' for c in s)


def _kana_word_span(text, pos, end, dict_index):
    """text の [pos, end) を含む、ひらがなの並びの中の辞書の語の読み（2字以上）の最長の長さ。無ければ 0。"""
    if dict_index is None:
        return 0
    i = pos
    while i > 0 and 'ぁ' <= text[i - 1] <= 'ゖ':
        i -= 1
    j = max(end, pos)
    while j < len(text) and 'ぁ' <= text[j] <= 'ゖ':
        j += 1
    best = 0
    for a in range(i, pos + 1):
        for b in range(max(end, pos + 1, a + 2), min(j, a + 12) + 1):
            if b - a <= best:
                continue
            try:
                if dict_index.is_world_reading(text[a:b]) or dict_index.surfaces_for_reading(text[a:b]):
                    best = b - a
            except Exception:
                return 0
    # 辞書の索引に無い語（感動詞 ありがとう など）は、字句の解析で1語（読みあり）のものも数える
    try:
        import morphology
        for t in morphology.tokenize(text):
            if (t.start <= pos and max(end, pos + 1) <= t.end and t.has_reading and len(t.surface) >= 2
                    and all('ぁ' <= c <= 'ゖ' for c in t.surface) and t.pos not in ('助詞', '助動詞')):
                best = max(best, len(t.surface))
    except Exception:
        pass
    return best


def _breaks_kana_word(line, found, dict_index, result=None):
    """1打の直し found が、かなの正しい語を崩すか。語の長さや字数では決めず、直す所が「何であるか」で決める
    （うに 10-20: 長い短い・字数の判定は全部は通らない）:
    直した字が活用の続き（動詞＋ます・た）になる直しは通す。元の並びで直す字を含む所が、語の区切りで切れた辞書の語
    そのもの（すいぞくかん・ふゆやすみ・しやくしょ）なら、正しい語なので直さない。そうでなければ、直した後の
    並びがそういう語になる直し、または助詞・助動詞の字を別の助詞・助動詞に替える直しだけ採る。"""
    try:
        text, inner, (lo, hi, face) = found
    except Exception:
        return False
    corrected = inner.get('corrected', text) if isinstance(inner, dict) else text
    hi = max(hi, lo + 1)
    if not (0 <= lo < len(line)) or not all('ぁ' <= c <= 'ゖ' for c in line[lo:hi]):
        return False
    if _verb_chain_at(corrected, lo, lo + max(len(face), 1)):
        return False
    stem = _stem_before_case_particle(line, lo, hi)
    if _bounded_kana_word(line, lo, hi, dict_index) and not stem:
        return True
    # 元の並びが辞書に無く、知っている語＋接尾の語（ふくびき＋けん）としてだけ成り立つときは、直した後の並びが
    # 辞書の語そのもの（ありか＋とう より ありがとう）でなければ崩さない
    compound = not stem and _bounded_kana_word(line, lo, hi, dict_index, compound=True)
    # 元の並びが語でなくても、直した後の並びが区切られた辞書の語（ありかとう→ありがとう・はるおすみ→はるやすみ）
    # にならない直しは、語を語にしていない（とうどつけん→とうとつけん・せいりけん→せいのけん）ので採らない。
    # 直した後の並びは、入口に通す前のかなの行（text）の上で見る（入口が漢字に置いた行は位置がずれる）。
    # 字を抜いた直し（せつ**さ**めい→せつめい）は、抜いた所の前の字で見る
    kana = text if isinstance(text, str) else corrected
    if len(kana) < len(line):
        a, b = max(lo - 1, 0), max(lo, 1)
    else:
        a, b = lo, lo + max(len(face), 1)
    if compound:
        return not _bounded_kana_word(kana, a, b, dict_index, loose=True)
    if _function_word_at(line, lo, hi, dict_index) and _function_word_at(kana, a, b, dict_index):
        # 助詞・助動詞の字を別の助詞・助動詞に替える直し（ようなも→ようにも）は語の中の直しでない
        return False
    return not (_bounded_kana_word(kana, a, b, dict_index, loose=True) or _one_kana_word_token(kana, a, b, dict_index))


def _stem_before_case_particle(text, pos, end):
    """字句の解析で、[pos, end) を含む字句が動詞の未然形で、直後が格助詞か（ふま｜を: 未然形に を は付かない）。
    辞書に読みが在っても、文の中ではその語として成り立っていない。"""
    try:
        import morphology
        toks = list(morphology.tokenize(text))
    except Exception:
        return False
    for k, t in enumerate(toks):
        if t.start <= pos and end <= t.end:
            nxt = toks[k + 1] if k + 1 < len(toks) else None
            return (t.pos == '動詞' and (t.infl_form or '').startswith('未然') and nxt is not None
                    and nxt.pos == '助詞' and (nxt.pos_sub or '').startswith('格助詞') and nxt.start == t.end)
    return False


def _function_word_at(text, pos, end, dict_index=None):
    """字句の解析で、text の [pos, end) が助詞か助動詞の字句の中に在り、その前後の字句が切れ端でないか
    （前後が辞書の読みのある語・活用形・助詞・助動詞・漢字や記号を含む字句。明日**しか**いひ の いひ は切れ端）。"""
    try:
        import morphology
        toks = list(morphology.tokenize(text))
    except Exception:
        return False

    def sound(t):
        return (t.pos in ('助詞', '助動詞', '記号') or not all('ぁ' <= c <= 'ゖ' for c in t.surface)
                or _known_kana_reading(t.surface, dict_index) or bool(_inflected_reading(t.surface, dict_index)))
    for k, t in enumerate(toks):
        if t.start <= pos and end <= t.end and t.pos in ('助詞', '助動詞'):
            return all(sound(u) for u in toks[max(k - 1, 0):k + 2])
    return False


def _inflected_reading(surface, dict_index):
    try:
        return dict_index.inflected_surfaces_for_reading(surface) if dict_index is not None else None
    except Exception:
        return None


def _one_kana_word_token(text, pos, end, dict_index=None):
    """字句の解析が、text の [pos, end) を丸ごと含む1つのかなの語（読みのある2字以上の辞書の語・助詞と助動詞
    でない）と見て、その前後がひらがなの名詞でないか（本当に｜ありがとう・よろしく｜おねがい｜します）。
    隣がひらがなの名詞なら、続けて1つの複合語になりうる（ちゅうせん＋げん）ので語の区切りと見ない。
    字句の解析の切れ端（janome の無い所で ょうていけんに のような字句が出る）も語と見ない。"""
    def compound_side(u):
        return u is not None and u.pos == '名詞' and all('ぁ' <= c <= 'ゖ' for c in u.surface)
    try:
        import morphology
        toks = list(morphology.tokenize(text))
    except Exception:
        return False
    for k, t in enumerate(toks):
        if not (t.start <= pos and end <= t.end):
            continue
        prev = toks[k - 1] if k > 0 else None
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        return (len(t.surface) >= 2 and t.has_reading and all('ぁ' <= c <= 'ゖ' for c in t.surface)
                and t.pos not in ('助詞', '助動詞') and _known_kana_reading(t.surface, dict_index)
                and not compound_side(prev) and not compound_side(nxt))
    return False


_WORD_EDGE = set('はがをにのもへでとや')


def _known_kana_reading(reading, dict_index):
    """辞書の読み（世の中の読みの表・表記の在る読み）か、同梱の語の表に漢字の表記の在る読みか。"""
    if dict_index is None:
        return False
    try:
        if dict_index.is_world_reading(reading) or dict_index.surfaces_for_reading(reading):
            return True
    except Exception:
        return False
    if len(reading) < 3:
        return False
    table = _seed_table()
    hit = _seed_find(table, reading) if table else None
    if not hit:
        return False
    row = table[0][hit[0]:hit[1]].decode('utf-8', 'replace')
    return any(_kanji_seq(cell.split(':')[0]) for cell in row.split('\t')[1:])


def _bounded_kana_word(text, pos, end, dict_index, loose=False, compound=False):
    """text の [pos, end) を含み、両端が語の区切りの辞書の語（2字以上の読み）が在るか。区切りは、ひらがなの
    並びの端か、字句の解析が1字の助詞と見た字（すいぞくかん｜を｜みた。ありか｜と｜う の と は助詞でない）。"""
    if dict_index is None:
        return False
    i = pos
    while i > 0 and 'ぁ' <= text[i - 1] <= 'ゖ':
        i -= 1
    j = max(end, pos)
    while j < len(text) and 'ぁ' <= text[j] <= 'ゖ':
        j += 1

    # 区切りの助詞の字は、字句の解析が1字の助詞と見た所だけ（ありか｜と｜う の と は助詞でない）
    try:
        import morphology
        edges = {t.start for t in morphology.tokenize(text)
                 if t.pos == '助詞' and len(t.surface) == 1 and t.surface in _WORD_EDGE}
    except Exception:
        return False
    # 漢字・片仮名・記号に接する助詞の字（明日**は**・**に**行く）も区切り（字句の解析が かな の並びを崩す行がある）
    for k in (i, j - 1):
        if 0 <= k < len(text) and text[k] in _WORD_EDGE:
            edges.add(k)
    if loose:
        # 直した後の並びを見るとき（語になったかを見る側）は、助詞の字ならどこでも区切りになりうると見る
        # （janome の無い所では しゅうがくりょこう｜に｜いきました の に を字句の解析が助詞と見ない）
        edges |= {k for k in range(i, j) if text[k] in _WORD_EDGE}

    for a in range(i, pos + 1):
        if a != i and (a - 1) not in edges:
            continue
        for b in range(max(end, pos + 1), j + 1):
            if b - a < 2 or (b != j and b not in edges):
                continue
            if _known_kana_reading(text[a:b], dict_index) or (compound and _kana_compound(text[a:b], dict_index)):
                return True
    return False


def _suffix_with_function(run):
    """かなの並びが「接尾の名詞の読み（＋助詞・助動詞）」か（ちゅう・ちゅうです）。"""
    try:
        import suffix_readings
        import morphology
    except Exception:
        return False
    for n in range(len(run), 1, -1):
        if suffix_readings.is_suffix_reading(run[:n]):
            rest = run[n:]
            if not rest or all(t.pos in ('助詞', '助動詞') for t in morphology.tokenize(rest)):
                return True
    return False


def _kana_suffix_tail(toks, s, e, line):
    """文節 [s, e) の終わりが「漢字の名詞＋かなの接尾（＋助詞・助動詞）」のとき、そのかなの並び。"""
    if not _kana_str(line[s:e]) and s < e:
        i = max((k for k, t in enumerate(toks) if s <= t.start and t.end <= e and t.pos == '名詞'
                 and t.surface and _kanji_seq(t.surface) == t.surface), default=None)
        if i is not None and toks[i].end < e:
            run = line[toks[i].end:e]
            if all('ぁ' <= c <= 'ゖ' for c in run) and _suffix_with_function(run):
                return run
    return ''


def _kana_compound(reading, dict_index):
    """読みが「辞書の語（2字以上）＋接尾の名詞」か（ふくびき＋けん・しょうたい＋じょう・ゆうびん＋きょく）。
    元の並びが正しい語かを見るときだけ使う。直した後の並びの決め手にはしない（とうとつ＋けん のように、
    どの名詞にも接尾は付けられるので、語になった証にならない）。"""
    try:
        import suffix_readings
    except Exception:
        return False
    if _sahen_with_suru(reading):
        return False
    for k in range(len(reading) - 1, 1, -1):
        if suffix_readings.is_suffix_reading(reading[k:]) and _known_kana_reading(reading[:k], dict_index):
            return True
    return False


def _sahen_with_suru(reading):
    """読みが「サ変の名詞＋する の活用（＋助詞・助動詞）」とも読めるか（せんたく＋して・へんこう＋した）。
    そう読めるなら、語＋接尾（せんたくし＋て）の組み立ては証にしない（活用は文法で、接尾の当てはめより確か）。"""
    try:
        import morphology
        from reading_segments import native_bare_action_faces
    except Exception:
        return False

    def forms(piece):
        return morphology.dictionary_inflections(piece) or ()

    def function_tail(rest):
        if not rest:
            return True
        return any(any(pos.startswith(('助詞,', '助動詞,')) for pos, *_ in forms(rest[:j])) and function_tail(rest[j:])
                   for j in range(1, len(rest) + 1))

    for k in range(2, len(reading)):
        tail = reading[k:]
        for j in range(1, len(tail) + 1):
            if (any(pos.startswith('動詞,自立') and base == 'する' for pos, form, base, rd in forms(tail[:j]))
                    and function_tail(tail[j:]) and native_bare_action_faces(reading[:k])):
                return True
    return False


def kana_run_is_word(run, keep_tail, dict_index, input_method='kana', whole=True):
    """かな連続 run（末尾の助詞 keep_tail を除く）が、丸ごと正しい語として読めるか（明日は|けいさつしょ|に・
    はなつやすみに の なつやすみ）。頭の1字が助詞の字なら、それを除いた残りでも見る。語として読めるのは、
    辞書の語そのものか、辞書の語＋接尾の名詞（けいさつ＋しょ・たんとう＋しゃ）。接尾の組み立てはどの名詞にも
    付けられるので、かな入力で1キー隣に辞書の語そのものが在る並び（ありか＋とう ← ありがとう）は語と見ない。
    ローマ字入力では組み立てを見ない（隣の打鍵の数え方が違う）。corrector の窓の前では whole=False で語＋接尾の
    組み立てだけを見る（辞書の語そのものの並びも打ち違いのことがあり、迷いの印は前のまま: せい今日）。"""
    if dict_index is None or not run:
        return False
    end = len(run) - len(keep_tail or '')
    starts = [0] + ([1] if run[:1] in _WORD_EDGE else [])
    for a in starts:
        body = run[a:end]
        if len(body) < 2 or not all('ぁ' <= c <= 'ゖ' for c in body):
            continue
        if whole and _known_kana_reading(body, dict_index):
            return True
        # 組み立ては、頭の助詞の字を除いた並びだけで見る（の＋せい を のせ＋い と組まない）
        if (a == starts[-1] and input_method != 'romaji' and _kana_compound(body, dict_index)
                and not _one_key_word(body, dict_index)):
            return True
    return False


def inside_kana_word(text, start, end, dict_index, input_method='kana'):
    """text の [start, end) が、丸ごと正しい語として読めるかなの並び（kana_run_is_word）の一部だけか
    （明日は|けいさつしょ|に の しょ・なつやすみ の やすみ）。語の切れ端に漢字を置かないために使う。"""
    if dict_index is None or not (0 <= start < end <= len(text)):
        return False
    lo, hi = start, end
    while lo > 0 and 'ぁ' <= text[lo - 1] <= 'ゖ':
        lo -= 1
    while hi < len(text) and 'ぁ' <= text[hi] <= 'ゖ':
        hi += 1
    if not all('ぁ' <= c <= 'ゖ' for c in text[start:end]):
        return False
    run = text[lo:hi]
    tail = run[-1:] if run[-1:] in _WORD_EDGE else ''
    if not kana_run_is_word(run, tail, dict_index, input_method):
        return False
    a = lo + (1 if (run[:1] in _WORD_EDGE and kana_run_is_word(run[1:], tail, dict_index, input_method)
                    and not _known_kana_reading(run[:len(run) - len(tail)], dict_index)) else 0)
    b = hi - len(tail)
    if not (a <= start and end <= b and (start, end) != (a, b)):
        return False
    # 名詞の席に在る並びだけ: 後ろが助詞の字で、前が漢字の送り（新しい|しょるい・書いて の かいて）でない
    # （漢字のすぐ後ろから始まる並びは、頭の助詞の字を除けたときだけ）
    if not tail or (lo > 0 and _kanji_seq(text[lo - 1]) and a == lo):
        return False
    # 名詞として読める並びだけ（みた の み に 見 を置くのは活用の語幹で、語の切れ端ではない）
    body = text[a:b]
    try:
        from reading_segments import _native_nominal_reading_faces
        noun = bool(_native_nominal_reading_faces(body))
    except Exception:
        noun = False
    return noun or _seed_noun(body) or _kana_compound(body, dict_index)


def _seed_noun(reading):
    """同梱の語の表で、読みの一番安い漢字の表記が名詞（夏休み）か（みた の 満た は動詞）。"""
    table = _seed_table()
    hit = _seed_find(table, reading) if table else None
    if not hit:
        return False
    row = table[0][hit[0]:hit[1]].decode('utf-8', 'replace')
    face = next((f for f in (cell.split(':')[0] for cell in row.split('\t')[1:]) if _kanji_seq(f)), None)
    if not face:
        return False
    try:
        import morphology
        forms = morphology.dictionary_inflections(face) or ()
    except Exception:
        return False
    return any(pos.startswith('名詞,') and not any(x in pos for x in ('非自立', '接尾', '固有名詞'))
               for pos, *_ in forms)


def _one_key_word(body, dict_index):
    """かな入力で1キー隣（距離 1.0 まで）を押した形か、濁点・半濁点の1打の付け忘れ・付けすぎ（か↔が）に、
    辞書の語そのものが在るか。"""
    try:
        import kana_layout as kl
        from contextual_repair import _key_neighbors, _render
        from morphology import _DAKUTEN_COMPOSE, _HANDAKUTEN_COMPOSE
        keys = tuple(x for c in body for x in kl.keystrokes(c))
    except Exception:
        return False
    pairs = list(_DAKUTEN_COMPOSE.items()) + list(_HANDAKUTEN_COMPOSE.items())
    for i, c in enumerate(body):
        for x, y in pairs:
            for other in ((y,) if c == x else (x,) if c == y else ()):
                if _known_kana_reading(body[:i] + other + body[i + 1:], dict_index):
                    return True
    for i, key in enumerate(keys):
        for other, d in _key_neighbors(key):
            if d <= 1.0 and other not in '゛゜':
                w = _render(keys[:i] + (other,) + keys[i + 1:])
                if w != body and _known_kana_reading(w, dict_index):
                    return True
    return False


def _keeps_sure_mark(line, found):
    """直した所が文法で確かな印（_conjugation_mismatch）に掛かるのに、直した後も同じ所に印が残るか
    （見すらない→編みすらない: 連用形＋すら＋ない のまま）。印を消せない直しは直しになっていない。"""
    import morphology
    try:
        text, inner, (lo, hi, face) = found
        corrected = inner.get('corrected', text) if isinstance(inner, dict) else text
        btoks = list(morphology.tokenize(line))
        atoks = list(morphology.tokenize(corrected))
    except Exception:
        return False
    hi = max(hi, lo + 1)
    had = [i for i in _conjugation_mismatch(btoks)
           if i + 1 < len(btoks) and btoks[i].start < hi and lo < btoks[i + 1].end]
    if not had:
        return False
    ae = lo + max(len(face), 1)
    return any(i + 1 < len(atoks) and atoks[i].start < ae and lo < atoks[i + 1].end
               for i in _conjugation_mismatch(atoks))


def _verb_chain_at(text, pos, end):
    """直した後の並びで、直した字が 動詞か助動詞の語にあり、その動詞に 助動詞（ます・た など）が続くか。
    活用の直し（しまいた→しました・まよました→まよいました・ごさいます→ございます）は語の中の直しと違い通す。"""
    try:
        import morphology
        toks = list(morphology.tokenize(text))
    except Exception:
        return False
    def aux_chain(k):
        # k から続く助動詞の並び。1字の助動詞だけの並び（しょ＋う）は切れ端の読みとして数えない
        chain = []
        while k < len(toks) and toks[k].pos == '助動詞':
            chain.append(toks[k].surface)
            k += 1
        return chain if any(len(c) >= 2 for c in chain) else []

    for k, t in enumerate(toks):
        if t.end <= pos or t.start >= end:
            continue
        if t.pos == '動詞' and aux_chain(k + 1):
            return True
        if t.pos == '助動詞':
            j = k
            while j > 0 and toks[j - 1].pos == '助動詞':
                j -= 1
            if aux_chain(j) and ((j > 0 and toks[j - 1].pos == '動詞') or len(aux_chain(j)) >= 2):
                return True
    return False


def _katakana_long_vowel_face(typed, dict_index):
    """打った読み typed（かな）の頭の部分に長音 ー を1つ足すと、世の中の表で片仮名だけの語（5字以上: 4字の語 カッター・テンキー・コロニー は ふつうの語 買った・天気・頃に の読みと重なる）の読みに1通りに
    なるなら (その語, 残り)。残りは空か助詞1字。無ければ None。"""
    for k in range(len(typed), 2, -1):
        head, rest = typed[:k], typed[k:]
        if rest and rest not in _RUN_PARTICLES:
            continue
        faces = set()
        for i in range(1, len(head) + 1):
            if head[i - 1] in 'ーっん':
                continue
            for f in _katakana_only_faces(head[:i] + 'ー' + head[i:], dict_index):
                if len(f) >= 5:
                    faces.add(f)
        if len(faces) == 1:
            return faces.pop(), rest
        if faces:
            return None
    return None


def _katakana_only_faces(reading, dict_index):
    """世の中の表で、読み reading の表記が片仮名の語だけのとき その表記の並び（重なり無し）。それ以外は空。"""
    try:
        faces = sorted(set(dict_index.surfaces_for_reading(reading)))
    except Exception:
        return []
    return faces if faces and all(_katakana_str(f) for f in faces) else []


def _place_doubtful_run(corrected, lo, line, options):
    """戻した行 corrected の、迷い（unsure）が収まるひらがなの並び [i, j) に、辞書で1通りの漢字の語（＋末尾の助詞1字）
    が置けるなら (置いた行, (始まり, 終わり, 置く語))（位置は元の行の上）。無ければ None。"""
    store, dict_index = options.get('store'), options.get('dict_index')
    if store is None or dict_index is None or not corrected:
        return None
    i = j = min(max(lo, 0), len(corrected) - 1)
    while i > 0 and _hira(corrected[i - 1]):
        i -= 1
    while j < len(corrected) and _hira(corrected[j]):
        j += 1
    if j - i < 3:
        return None
    delta = len(line) - len(corrected)
    for k in range(j, i + 1, -1):
        rest = corrected[k:j]
        if rest and rest not in _RUN_PARTICLES:
            continue
        word = corrected[i:k]
        if len(word) < 3:
            break
        try:
            faces = _kanji_choices(word, store, dict_index)
        except Exception:
            return None
        if len(faces) != 1 or not _kanji_seq(faces[0]) or _kanji_seq(faces[0]) != faces[0] or len(faces[0]) < 2:
            continue
        face = faces[0]
        return corrected[:i] + face + corrected[k:], (i, k + delta, face)
    return None


def _mark_rare_clauses(result, line, options):
    """読み直しが採れなかった行で、IME が明示的に稀と判定された語（稀代・現官）を出した文節は、迷いの印（紫）を
    元の行の上に残す（迷うなら紫: うに 10-18）。紫は「異様の印」で答えは変えない。"""
    if not isinstance(result, dict) or options.get('input_method', 'kana') not in ('kana', 'romaji'):
        return result
    line = result.get('corrected', line) or line
    try:
        import morphology
        toks = list(morphology.tokenize(line))
    except Exception:
        return result
    spans = [(t.start, t.end) for t in toks
             if t.pos == '名詞' and len(t.surface) == 2 and _kanji_seq(t.surface) == t.surface
             and _restricted_face(t.surface)]
    # 文法で確かな印（活用の形が合わない続き: 閑雅**て**・角**煮ください**・初める**た**）は、直せなくても紫を残す
    sure = [(toks[i].start, toks[i + 1].end) for i in sorted(_conjugation_mismatch(toks)) if i + 1 < len(toks)]
    # 打った読みの上の文法で確かな印（きりがないよう**な**も→霧が内容名も）も、直せなければ文節に紫（#80）
    try:
        sure += sorted(_reading_sure_clauses(line, _ime_clauses(line, toks, options.get('dict_index'))))
    except Exception:
        pass
    if not spans and not sure:
        return result
    store = options.get('store')
    spans = [(a, b) for a, b in spans
             if not (store is not None and _her_word(store, _region_reading(line, a, b), line[a:b]))]
    spans += sure
    if not spans:
        return result
    odd = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
    extra = [sp for sp in spans if not any(a <= sp[0] and sp[1] <= b for a, b in odd)]
    if not extra:
        return result
    out = dict(result)
    out['odd_spans'] = list(result.get('odd_spans') or ()) + extra
    return out


def _sure_mark_left(corrected, s, e):
    """直した行 corrected の [s, e) に掛かる、文法で確かな印（_conjugation_mismatch）が残るか。"""
    import morphology
    try:
        toks = list(morphology.tokenize(corrected))
    except Exception:
        return False
    for i in _conjugation_mismatch(toks):
        if i + 1 < len(toks) and toks[i].start < e and s < toks[i + 1].end:
            return True
    return False


def _new_conjugation_mismatch(line, corrected):
    """直した行 corrected に、元の行 line に無い活用の形の合わない続き（_conjugation_mismatch: 聞き置く＋ながら・
    新しい＋て）が生まれたか。読み直しの形は、打ち違いの印そのものになる形には決めない。"""
    import morphology

    def pairs(text):
        try:
            toks = list(morphology.tokenize(text))
        except Exception:
            return set()
        return {(toks[i].surface, toks[i + 1].surface) for i in _conjugation_mismatch(toks)}
    return bool(pairs(corrected) - pairs(line))


def _purple_touches(result, line, lo, hi, options):
    # 戻す範囲 [lo, hi) に、入口の紫（odd_spans）か、ローマ字で残った英字の並び（英字の片割れが出ている時点で紫）が掛かるか
    spans = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
    if options.get('input_method') == 'romaji':
        letters = _letter_span(line)
        if letters:
            spans.append(letters)
    return any(a < hi and lo < b for a, b in spans)


def _settle_clause_forms(result, line, forms, options, decisions, weak=False, stray=False, doubt=False):
    # 読み直しの形を順に共通の最終検査へ通し、最初に通った形を返す
    # （漢字に置いた形→かなのままの形）。どれも通らなければ元の結果のまま
    for corrected, (lo, hi, face) in forms:
        out = _accept_clause_form(result, line, corrected, lo, hi, face, options, decisions, weak=weak, stray=stray,
                                  doubt=doubt)
        if out is not None:
            return out
    return result


def _accept_clause_form(result, line, corrected, lo, hi, face, options, decisions, weak=False, stray=False,
                        doubt=False):
    import corrector
    # 入れ替わりを「足し」と「消し」の2つに見せない
    pieces = corrector._display_spans_for_reanalysis(
        line, corrected, [(lo, hi, face, _method_label(options))])
    # 置く直しは、ほかの直しと同じ共通の最終検査を通す（読み直した行の
    # 中の検査は直した行が相手で、元の行からの直しは見ていない。
    # 適用点を1つでも迂回させると、守りの門を素通りする）
    # 読み直した直しは、置く範囲（文節: し半分を→しんぶんを）の単位で検査を
    # 受ける。差分の切れ端（んぶん・う）で受けると、切れ端自体が語でないために
    # 止まり、文節として正しい直しが落ちる（しめ聞くり→締め切り が通るようになり、
    # 2つの自作文で誤りは増えなかった）。表示の切れ端は見せ方にだけ使う
    if hi > lo and face and (lo, hi, face) != (0, len(line), corrected):
        items = [(lo, hi, face)]
        clause_proof = True
    else:
        items = [(i1, i2, corrected[j1:j2]) for i1, i2, j1, j2 in pieces]
        clause_proof = False
    for i1, i2, piece in items:
        item = (i1, i2, piece, _method_label(options))
        # 文節の形は IME の対（打った読み）の1打を戻した根拠を持つ。元の文節の語は
        # 滑った読みを IME が変換したもので、正しく書けた目的語の証明にはならない
        # （ime_clause_proof。欄全体の第一変換の証明 ime_first_proof と同じ扱い）
        accepted, _reason = corrector._check_replacement(
            line, item, options.get('store'), options.get('tokenize_fn'),
            options.get('dict_index'), decisions, conv_taken=((i1, i2),),
            ime_clause_proof=clause_proof, ime_stray_proof=bool(stray and clause_proof),
            ime_purple_proof=(_purple_touches(result, line, i1, i2, options)
                              or (doubt and any(a < i2 and i1 < b for a, b in
                                                [tuple(x[:2]) for x in (result.get('unsure_spans') or ())]))))
        if accepted is None or tuple(accepted[:3]) != item[:3]:
            return None
    if _new_conjugation_mismatch(line, corrected):
        return None
    blocks = getattr(decisions, 'blocks', None)
    if callable(blocks) and (blocks(line, corrected) or any(
            blocks(line[i1:i2], corrected[j1:j2]) for i1, i2, j1, j2 in pieces)):
        return None
    out = dict(result)
    out.update(
        corrected=corrected,
        changed=corrected != line,
        details=[(line[i1:i2], corrected[j1:j2], _method_label(options))
                 for i1, i2, j1, j2 in pieces],
        spans=[(j1, j2) for _i1, _i2, j1, j2 in pieces],
        original_spans=[(i1, i2) for i1, i2, _j1, _j2 in pieces],
        unsure_spans=[],
        # 一般さで決めた形（並んで文脈に決め手が無い）は、迷いの印（紫）を元の行の置く範囲に残す
        odd_spans=([(i1, i2) for i1, i2, _j1, _j2 in pieces] if weak else []),
    )
    out.pop('_validated_corrected', None)
    out.pop('_validated_repair_ranges', None)
    # 「なぜ異様と見たか」は元の行の理由のまま（直した語の根拠に出る）
    return out

