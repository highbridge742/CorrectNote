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
"""
**2字の漢字の名詞の「一般的さの段」**（項目48-OJ・2026-09-02）。

うにさんの指定（2026-08-28）「**一般的か、自然か、もっともらしいか、
このような主観の判断は AI の能力を活かす**」——表の数字では
**どちらが日常的かは決まらない**（実測）:

    IPAdic のコスト（新聞由来）   過大 4798 < 課題 5329 ・ 高率 5065 < 効率 5462
    SudachiDict の費用             参向 101 < 参考 103 ・ 山行 93 < 参考 103

だから **AI の判断を表に焼いた**（`kango_tier.json`・Claude Fable 5.1・
2026-09-02。材料は janome 辞書の2字漢字の名詞でコスト 5600 まで＝15,897語）。

    段 1  日常語（メモ・会話・仕事の連絡でごく普通に使う）  課題・効率・参考・移動
    段 2  一般語（書籍・新聞で普通に見るが、日常の頻度は低い） 過大・異動・端午
    段 3  それ以外（専門・法令・文語・稀語）。**表に載せない**   参向・鑽孔・馘首

使う所:
  ・`dict_index` が、同じ読みの表記を **段 → コスト** の順に並べる
  ・`corrector._index_face` が「異様と判定したあと、優先度の高い1つに
    決める」ときの順位（CLAUDE.md ★★「候補が複数あっても、優先度の
    高い1つに決めて補正する」）
  ・異様な長い読みに対し、普通名詞2語の候補同士の意味的な結び付きを
    比べる（`compound_relations`）。誤入力と正解の対は保存しない

**判定には使わない。** 「異様か」は別の判定（oddness・pos_grammar）が
決める。ここは**決まったあとの順位**だけ。表が無ければ全部 段3
（＝索引の順はコストのまま・`_index_face` は何も決めない）。
"""
import json
import os

_TABLE = None
_RELATIONS = None
_MISSING = False


def _load():
    global _TABLE, _RELATIONS, _MISSING
    if _TABLE is not None or _MISSING:
        return _TABLE
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, 'kango_tier.json'), 'kango_tier.json'):
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            _TABLE = data.get('tiers') or {}
            _RELATIONS = data.get('compound_relations') or []
            return _TABLE
        except Exception:
            continue
    _MISSING = True
    return None


def available():
    return bool(_load())


def tier(surface):
    """その表記の段（1・2）。既存表と版付き一般語分類に無ければ3。"""
    t = _load()
    if not t:
        return 3
    try:
        value = int(t.get(surface, 3))
        # 費用閾値で抽出した旧表に無い語も、版付きの一般語分類を参照する。
        # 分類は意味関係の同じ名簿を共有し、語を別の表へ二重登録しない。
        for relation in (_RELATIONS or ()):
            ordinary = relation.get('ordinary_tier')
            if ordinary in (1, 2) and (surface in relation.get('heads', ())
                                      or surface in relation.get('tails', ())):
                value = min(value, ordinary)
        return value
    except Exception:
        return 3


def affinity(left, right):
    """AIが分類した一般語の意味群から、2語の結び付き（0～2）を返す。"""
    _load()
    for relation in (_RELATIONS or ()):
        if (left in relation.get('heads', ())
                and right in relation.get('tails', ())):
            return 2
    return 0
