# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ---------------------------------------------------------------
# このファイルが読む `kanji_onkun.json` は UniDic から導いたもの。
#   Derived from UniDic.
#   Copyright (c) 2011-2017, The UniDic Consortium.
#   All rights reserved. (modified BSD License)
# **表を作り直しても、この表示は必ず残すこと**（修正BSDの条件）。
# 2026-08-25（項目48-JD）からは、これに **IPAdic の単漢字見出し
# （janome 同梱）と AI の点検**（音訓の割り当て・並び・取捨。
# `tools_local/onkun_ai_batch*.py`）を重ねた表になっている。
# JSON の 'notice' にも両方の出どころが書いてある。
# ---------------------------------------------------------------

"""
**単漢字の読み（音読み・訓読みの印つき）**。

うにさんの指定（2026-08-11）:

「**音読みと訓読みの情報はありませんか？** IMEがどう変換するかを
考えたらよいです。あやまがくしゅうという文字列で変換したら、
別の文字列になります」

**なぜ要るか（実測で分かった穴）**:

    うにさんのメモに出る漢字 632種のうち、
    **284種（44%）は読みが1つも引けなかった**。

`格` `賀` もそこに入っていた。だから

    reading_combos_with_rank('性格') → **候補ゼロ**
    reading_combos_with_rank('賀古') → **候補ゼロ**

で、`性格→正確` `賀古→過去` はそもそも土俵に上がれていなかった。
「関門で止まっている」と思っていたが、**読みが無かった**。

**印は何に使うか**（うにさんの筋道）:

誤変換の文字列は、IMEが**読みから変換した結果**。だから
元の読みは「変換前に打った、ごく普通の読み」であって、
**熟語なら音読みどうし・和語なら訓読みどうし**で揃うのが普通。
`誤学習` は 誤(ご・音)＋学習(音) で **ごがくしゅう**。
janome は 誤 を **あやま**（訓）と読んで
`あやまがくしゅう` にしていた。うにさんの言うとおり、
**その読みでIMEに打っても `誤学習` は出てこない**。

ただし**揃わない語もある**（重箱読み・湯桶読み）。実測で
`待ち外`（＝間違いの誤変換）は **まち(訓)＋がい(音)** だった。
だから印は**順位づけの材料**であって、門にはしない。

    'on'  音読み（UniDic の語種が「漢」）
    'kun' 訓読み（同「和」）
    'gai' 外来語 ／ 'na' 固有名 ／ 'mix' 混種
    '?'   熟語からの引き算で足したもの（印は分からない）

表が無くても動く（今までどおりの読みだけになる）。
表の作り方は `kanji_onkun_build.py`（開発時のみ）。
48-AGPでは公式Unihanの一致する音読みを不足分だけ補う。出典・版・
抽出条件・ライセンスはJSONのsupplemental_sourceへ記録する。
既存の読み順を保ち、補助読みは後ろへ加える。
"""

import json
import os

_TABLE = None
_SUPPLEMENTAL = {}
_MISSING = False


def _load():
    global _TABLE, _SUPPLEMENTAL, _MISSING
    if _TABLE is not None or _MISSING:
        return _TABLE
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, 'kanji_onkun.json'),
                 'kanji_onkun.json'):
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            got = data.get('readings')
            if isinstance(got, dict):
                _TABLE = got
                supplement = data.get('supplemental_readings', {})
                _SUPPLEMENTAL = supplement if isinstance(supplement, dict) else {}
                return _TABLE
        except Exception:
            continue
    _MISSING = True
    return None


def available():
    """表が読めているか（診断用）。"""
    return _load() is not None


def readings_of(ch):
    """その漢字の読み（ひらがな）。**音読みを先に**並べて返す。

    誤変換のもとになる読みは、たいてい熟語の音読み。
    印の分からないもの（'?'）は最後に回す。

    **同じ印の中の並びは JSON に書いた順**（`sorted` は安定・
    項目48-JD）。主要な読みが先・マイナーな読みが後ろになるよう
    AI が並べてある。**JSON のキーを並べ替えないこと。**
    """
    table = _load()
    if table is None:
        return []
    got = table.get(ch, {})
    order = {'on': 0, 'kun': 1, 'gai': 2, 'mix': 3, 'na': 4, '?': 5}
    readings = [r for r, _k in sorted(got.items(),
                                     key=lambda x: order.get(x[1], 9))]
    # 48-AGP: source-backed missing readings follow every existing reading.
    # They prove possible pronunciation, not independent wordhood or error.
    readings.extend(r for r in _SUPPLEMENTAL.get(ch, {}) if r not in got)
    return readings


def kind_of(ch, reading):
    """その読みが音読みか訓読みか。分からなければ '?'。"""
    table = _load()
    if table is None:
        return '?'
    return (table.get(ch) or {}).get(reading,
        _SUPPLEMENTAL.get(ch, {}).get(reading, '?'))


#: 音読みの尻に立てる字（漢音・呉音の入声・撥音の名残と、熟語の
#: 促音便）。**閉じた類**。`っ` は熟語の中でしか出ない形
#: （一体＝いっ＋たい・出発＝しゅっ＋ぱつ）＝音読みの印そのもの。
_ON_TAIL = frozenset('んういくきつちっ')

#: 拗音（音読みの2字目に立つ小書き）。
_ON_SMALL = frozenset('ゃゅょ')

#: 音読みの頭に立たない字（小書き・促音・長音・撥音）。
_ON_HEAD_NG = frozenset('ぁぃぅぇぉゃゅょっーん')


def is_on_shape(reading):
    """
    **その読みは「音読みの形」をしているか**（項目48-MQ・2026-08-31）。

    `kanji_onkun.json` の印（`on` / `kun` / `?`）は**穴が多い**——
    `効` の こう・`力` の りょく・`形` の けい・`致` の ち は、
    どれも音読みなのに `'?'` のまま。印だけを見ると、
    `効率`（こうりつ）も `形態`（けいたい）も「漢語ではない」に
    なってしまう（実測。`巨` `析` は読みそのものが1つも無い）。

    **印の穴は、形で埋められる。** 日本語の音読みは、字音の作りから
    **1〜3拍の閉じた形**しか取らない:

        [頭の1字][拗音?][ん・う・い・く・き・つ・ち?]

        こう ／ りょく ／ けい ／ ち ／ だい ／ しょう ／ かく ／
        にん ／ じ ／ きょ ／ ぶん ／ そつ

    訓読みはこの形に収まらない（かたち・ちから・おお・みと・
    あざな・まつむろ）。**語を並べた表ではなく、形の決まり。**

    1字の読みだけは形で分けられない（`じ`＝音／`こ`＝訓）ので、
    **そこだけ印を見る**（`kun` と `na` は落とす）——呼ぶ側の仕事。
    """
    r = reading or ''
    n = len(r)
    if not (1 <= n <= 3):
        return False
    if r[0] in _ON_HEAD_NG:
        return False
    if not all('ぁ' <= c <= 'ゖ' for c in r):
        return False
    if n == 1:
        return True
    if n == 2:
        return r[1] in _ON_SMALL or r[1] in _ON_TAIL
    # 3字は「頭＋拗音＋尻」だけ（りょく・しょう・きゃく）
    return r[1] in _ON_SMALL and r[2] in _ON_TAIL


def is_on_reading(ch, reading):
    """
    その漢字のその読みを、**音読みとして扱ってよいか**（項目48-MQ）。

    印が `kun`・`na`・`gai` なら落とす（表がはっきり訓だと言っている）。
    残り（`on` と `?`）のうち、**音読みの形**をしているものを採る。
    表に無い漢字（`巨` `析`）でも、形が合えば通る——**表の穴を
    形で埋める**のがこの関数の仕事。
    """
    if not reading or not is_on_shape(reading):
        return False
    return kind_of(ch, reading) not in ('kun', 'na', 'gai')


def kinds_of_word(text, reading_per_char):
    """
    漢字ごとの読みの並びから、音訓の並びを返す（診断・順位づけ用）。

    reading_per_char: [(漢字, 読み), ...]
    """
    return [kind_of(c, r) for c, r in reading_per_char]


def mixed_reading(kinds):
    """
    音読みと訓読みが混ざっているか（重箱読み・湯桶読み）。

    **混ざっていること自体は誤りではない**（待ち外＝まち＋がい）。
    順位を下げる材料として使うだけで、門にはしないこと。
    """
    seen = {k for k in kinds if k in ('on', 'kun')}
    return len(seen) > 1


# --------------------------------------------------------------------
#  **重箱読み・湯桶読み・訓訓読みの表**（項目48-PD・2026-09-03）
# --------------------------------------------------------------------
#
# うにさんの提案（2026-09-03）:
#
# > 「漢字の重箱読み、湯桶読みの一覧を作っておいて、そこに一致する
# >   単語はそのルールで読み、一致しないものは音音読みで分析する」
#
# 下見（`tools_local/probe_reading_patterns.py`）で、2字の漢字の名詞
# 15,897語（IPAdic・コスト5600まで）を音訓の印と音読みの形の決まり
# （`is_on_shape`・項目48-MQ）で分けると:
#
#     音音 **13,071（82%）** ／ 訓訓 715 ／ 湯桶 528 ／ 重箱 397 ／
#     割れない 1,186
#
# **音音が既定でよい**（うにさんの見立てどおり）。混ざる型は閉じた表に
# 収まる大きさ。ただし機械の分けかたには印のノイズが混じる
# （簡単・政権 が「重箱」、温度・漢語 が「湯桶」に落ちる）ので、
# **AI が検品した**（Claude Fable 5.1・2026-09-03・1,640語）:
#
#     機械の「重箱」397 → 本当の重箱 **121** ／ 「湯桶」528 → **132**
#     機械の「訓訓」715 → **683**
#
# 残ったものが `reading_patterns.json`（**1,057語**＝訓訓801・湯桶131・
# 重箱125。**音音は載せない＝既定**）。材料と判定は
# `tools_local/reading_patterns_src/`。
#
# **門にはしない**（`mixed_reading` の注記と同じ理由）。使うのは
# `kanji_guess.reading_combos_with_rank` の**順位**だけ:
#
#     素帰任 → 確認     ②で要るのは **すきにん**（素=す は訓）。
#                       音音だけにすると そきにん → 責任 が先に立つ
#     待ち外 → 間違い   まち(訓)＋がい(音)＝湯桶
#     田部井号して      た(訓)ぶ(音)い(訓)——3字の混読み
#
# どれも**混読みが的**。落とすと死ぬので、**下げるだけ**にする。

_PATTERNS = None
_PATTERNS_MISSING = False


def _load_patterns():
    global _PATTERNS, _PATTERNS_MISSING
    if _PATTERNS is not None or _PATTERNS_MISSING:
        return _PATTERNS
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, 'reading_patterns.json'),
                 'reading_patterns.json'):
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            got = data.get('patterns')
            if isinstance(got, dict):
                _PATTERNS = got
                return _PATTERNS
        except Exception:
            continue
    _PATTERNS_MISSING = True
    return None


def patterns_available():
    """重箱・湯桶の表が読めているか（診断用・`tests_mock` の見張り）。"""
    return _load_patterns() is not None


def pattern_of(surface):
    """
    その表記の**読みの型**（`'重箱'` / `'湯桶'` / `'訓訓'`）。
    **表に無ければ `None`**（＝音音が既定、または載せていない語）。
    """
    table = _load_patterns()
    if not table:
        return None
    return table.get(surface)


def on_or_kun(ch, reading):
    """
    その読みを**音・訓のどちらとして扱うか**（`'on'` / `'kun'`）。

    印が `'?'` のものは**音読みの形の決まり**（項目48-MQ）で決める
    ——`is_on_reading` にそのまま聞く。**同じ判定を2度書かない。**
    """
    return 'on' if is_on_reading(ch, reading) else 'kun'


#: 音訓の並び → 型の名前（`reading_patterns.json` の値と同じ言葉）。
_PATTERN_NAMES = {
    ('on', 'on'): '音音',
    ('on', 'kun'): '重箱',
    ('kun', 'on'): '湯桶',
    ('kun', 'kun'): '訓訓',
}


def pattern_name(kinds):
    """音訓の並び（2つ）を型の名前にする。2字以外は `None`。"""
    return _PATTERN_NAMES.get(tuple(kinds))


# 48-AGP / 2026-09-15: Japanese orthographic variants, not homophones.
# Reviewed against primary sources. These pairs supply dictionary lookup
# evidence only; callers retain the original spelling and character offsets.
ORTHOGRAPHIC_VARIANT_SOURCES = (
    ('灌潅', 'https://www.kanjipedia.jp/kanji/0001142200'),
    ('諫諌', 'https://eprints.lib.hokudai.ac.jp/repo/huscap/all/65755/Li_Yuan_summary.pdf'),
    ('繫繋', 'https://www.kanjipedia.jp/kanji/0001821100'),
    ('鷗鴎', 'https://www.kanjipedia.jp/kanji/0000542500'),
)
_ORTHOGRAPHIC_VARIANTS = {ch: group for group, source in ORTHOGRAPHIC_VARIANT_SOURCES for ch in group}


def orthographic_variants(surface):
    """Bounded alternate spellings; none is itself lexical evidence."""
    if not surface or not any(ch in _ORTHOGRAPHIC_VARIANTS for ch in surface):
        return ()
    options = ['']
    for ch in surface:
        group = _ORTHOGRAPHIC_VARIANTS.get(ch, ch)
        if len(options) * len(group) > 16:
            return ()
        options = [head + tail for head in options for tail in group]
    return tuple(word for word in options if word != surface)
