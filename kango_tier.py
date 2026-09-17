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

**稀語だけで異様とは判定しない。** 「異様か」は別の判定が行う。
2026-09-12の版付きusage_judgmentsは、辞書費用の抽出範囲を越えて
日常の入力可能性をAIで評価する。候補順位と、全かなを未編集の普通語と
説明する肯定証拠に共有する。辞書にある稀語だけでは普通の読みと認定しない。
既に書かれた専門用語の綴りや利用者の明示選択は、この表だけで変更しない。

旧tier()の未収録=3は旧順位の互換用。known_usage_tier()は未評価をNoneと
返す。明示的な稀語の判断と、旧表に収録されていないだけの語を混同しない。
"""
import json
import os

_TABLE = None
_RELATIONS = None
_MISSING = False
_USAGE = {}
_READING_USAGE = {}


def _load():
    global _TABLE, _RELATIONS, _MISSING, _USAGE, _READING_USAGE
    if _TABLE is not None or _MISSING:
        return _TABLE
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, 'kango_tier.json'), 'kango_tier.json'):
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            _TABLE = data.get('tiers') or {}
            _RELATIONS = data.get('compound_relations') or []
            _USAGE = {word: group['tier']
                for group in data.get('usage_judgments',{}).get('groups',())
                if group.get('tier') in (1,2,3)
                for word in group.get('words',())}
            _READING_USAGE = {(word,reading):group['tier']
                for group in data.get('usage_judgments',{}).get('reading_groups',())
                if group.get('tier') in (1,2,3)
                for word,readings in group.get('readings',{}).items()
                for reading in readings}
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
        if surface in _USAGE:
            return _USAGE[surface]
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


def known_usage_tier(surface):
    """AI judged usage tier, or None when no positive/negative judgment exists.

    Unlike tier(), absence of a cost-filtered dictionary entry is not tier 3
    evidence. Explicit newer judgments override the older positive roster.
    """
    _load()
    if surface in _USAGE:
        return _USAGE[surface]
    value=tier(surface)
    if value in (1,2):
        return value
    # semantic_roles already classifies these as ordinary nouns. It is the
    # authoritative roster; do not duplicate one-character nouns here.
    from semantic_roles import NOUN_ROLES
    if surface in NOUN_ROLES:
        return 2
    return None



def usage_tier_for_reading(surface, reading):
    """48-AAW: an ordinary spelling does not make all its readings ordinary."""
    _load()
    return _READING_USAGE.get((surface,reading),known_usage_tier(surface))


def is_restricted(surface):
    """An explicit AI judgment of restricted use, never a missing-data guess."""
    return known_usage_tier(surface)==3


def _explicit_reading_faces():
    """Native readings of all explicit usage judgments; no guessed readings."""
    _load()
    from morphology import dictionary_inflections
    result={}
    # 48-ABX: older positive usage judgments are equally authoritative.
    # A cost-filtered spelling table can omit even 優先 while retaining 有線.
    # Derive readings from the same judged roster and native dictionary,
    # rather than copying missing words into a second positive word list.
    # 48-AII: the ordinary semantic roster already supplies usage evidence.
    # Its exact native readings must also reach this same shared index.
    from semantic_roles import NOUN_ROLES
    judged=(set(_USAGE)|{word for word,reading in _READING_USAGE}
            |{word for word,value in (_TABLE or {}).items() if value in (1,2)})
    for word in judged | set(NOUN_ROLES):
        for pos,form,lemma,reading in dictionary_inflections(word) or ():
            # 48-AIN: a semantic role alone does not promote a one-kana
            # reading to the free lexical index. short_role_noun_faces
            # already supplies these readings inside a proved case frame.
            if pos.startswith('名詞,') and (word in judged or len(reading)>1):
                result.setdefault(reading,set()).add(word)
    return result


from functools import lru_cache as _usage_cache
_explicit_reading_faces = _usage_cache(maxsize=1)(_explicit_reading_faces)


@_usage_cache(maxsize=8192)
def reading_is_explicitly_restricted(reading):
    """Only restricted noun senses are evidenced, with no ordinary/unknown rival.

    This cannot declare an anomaly. It only prevents the old world-reading
    guard from treating an explicitly restricted alternative as sufficient
    proof that an otherwise unexplained kana input is ordinary.
    """
    faces=set(_explicit_reading_faces().get(reading,()))
    if not faces or not any(usage_tier_for_reading(word,reading)==3 for word in faces):
        return False
    from corrector import table_surfaces_for_reading
    from morphology import dictionary_inflections
    for word in table_surfaces_for_reading(reading,limit=12):
        if any(pos.startswith('名詞,') and rd==reading
               for pos,form,lemma,rd in dictionary_inflections(word) or ()):
            faces.add(word)
    return all(usage_tier_for_reading(word,reading)==3 for word in faces)


def prefer_ordinary_spelling(reading, preferred):
    """Compare same-reading noun spellings when the old choice is explicitly rare.

    Neither user vocabulary strength nor missing usage coverage proves
    ordinary use. Existing ordinary alternatives come from the shared
    dictionary; exact native readings and noun roles must agree. A user's
    explicit last choice remains authoritative. No vocabulary is written.
    """
    if not preferred or usage_tier_for_reading(preferred,reading)!=3:
        return preferred
    from last_choice import surface_for_reading
    if surface_for_reading(reading)==preferred:
        return preferred
    from corrector import table_surfaces_for_reading, _table_cost
    from morphology import dictionary_inflections
    ordinary=[word for word in table_surfaces_for_reading(reading,limit=12)
        if usage_tier_for_reading(word,reading) in (1,2)
        and any(pos.startswith('名詞,') and rd==reading
                and not any(kind in pos for kind in ('固有名詞','接尾','非自立'))
                for pos,form,lemma,rd in dictionary_inflections(word) or ())]
    return min(ordinary,key=lambda word:(known_usage_tier(word),
        _table_cost(word) if _table_cost(word) is not None else 10**9,word)) if ordinary else preferred


def prefer_predicate_spelling(reading, preferred, tail):
    """48-AAZ: rank same-reading candidates using their actual predicate tail.

    A native positive connection can outrank a cheaper noun homophone.
    This never changes an original spelling or invents an anomaly. If no
    ordinary rival has the complete grammatical tail, keep the old choice.
    """
    if not preferred or not tail:
        return preferred
    from last_choice import surface_for_reading
    if surface_for_reading(reading)==preferred:
        return preferred
    from morphology import dictionary_inflections
    from contextual_repair import _allows_grammatical_tail, _productive_predicate
    def accepts(word):
        forms=dictionary_inflections(word) or ()
        return (_allows_grammatical_tail(forms,tail,reading,word)
                and _productive_predicate(word+tail,word))
    if accepts(preferred):
        return preferred
    from corrector import table_surfaces_for_reading, _table_cost
    ordinary=[word for word in table_surfaces_for_reading(reading,limit=12)
        if usage_tier_for_reading(word,reading) in (1,2) and accepts(word)]
    return min(ordinary,key=lambda word:(usage_tier_for_reading(word,reading),
        _table_cost(word) if _table_cost(word) is not None else 10**9,word)) if ordinary else preferred
