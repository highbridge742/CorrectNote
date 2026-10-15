# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
# -*- coding: utf-8 -*-
"""Parts of speech of English words, for the per-POS size and colour only.

2026-10-14 うにさん: English words take the part-of-speech sizes and colours
too. The words are looked up in en_pos.json.gz (built by
tools_local/en_pos/build_en_pos.py; format in its docstring) and a word with
more than one part of speech is settled by its neighbours. English parts of
speech use the existing rows of the dialog (no new rows):

    noun, pronoun -> 名詞   verb -> 動詞   auxiliary/modal -> 助動詞
    adjective -> 形容詞     adverb -> 副詞  preposition -> 助詞
    article/determiner -> 連体詞  conjunction -> 接続詞  interjection -> 感動詞
    number word (one, twenty, hundred) -> 数詞

A word the dictionary does not know (names, code, rare words) keeps 英字.
The text itself and the analysis never change.

2026-10-15 (うにさん: ordinary words such as state or power were その他英字):
the dictionary now also takes its parts of speech from WordNet 3.0 (version
2026-10-15a; WordNet 3.0 Copyright 2006 by Princeton University. All rights
reserved. The WordNet licence is inside en_pos.json.gz under "license"). A
contraction split at the apostrophe (don't, I'm) is looked up whole.
"""
import gzip
import json
import os
import sys
import unicodedata

DICTIONARY = 'en_pos.json.gz'
CATEGORY = {'N': '名詞', 'O': '名詞', 'V': '動詞', 'M': '助動詞', 'J': '形容詞',
            'R': '副詞', 'P': '助詞', 'D': '連体詞', 'C': '接続詞', 'I': '感動詞',
            'U': '数詞'}
UNKNOWN = '英字'
# What the right-click 品詞判定 calls each code (CATEGORY is the colour row).
NAMES = {'N': '名詞', 'O': '代名詞', 'V': '動詞', 'M': '助動詞', 'J': '形容詞',
         'R': '副詞', 'P': '前置詞', 'D': '限定詞', 'C': '接続詞', 'I': '感動詞',
         'U': '数詞'}
ARTICLES = frozenset(('a', 'an', 'the'))

_WORDS = None


def _path():
    base = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, DICTIONARY)


def words():
    """{lowercase word: part-of-speech codes}, loaded once (empty if missing)."""
    global _WORDS
    if _WORDS is None:
        try:
            with open(_path(), 'rb') as handle:
                _WORDS = json.loads(gzip.decompress(handle.read()).decode('utf-8'))['words']
        except Exception:
            _WORDS = {}
    return _WORDS


def available():
    return bool(words())


def _key(word):
    return unicodedata.normalize('NFKC', word).lower()


def codes_for(word):
    return words().get(_key(word), '')


_APOSTROPHES = "'’＇"
_CLITICS = frozenset(('s', 're', 've', 'll', 'd', 'm'))


def _join_contractions(text, spans, found, wholes):
    """``don't`` ``I'm`` ``it's``: the apostrophe splits them into two words.
    Look the whole up (the dictionary has don't, i'm, that's ...). The parts
    take its part of speech, except that before 's 're 've 'll 'd 'm the head
    keeps its own when it has one (I'm = I + am, that's = that + is).
    ``wholes`` gets the whole as written for each part that took it."""
    for index in range(len(spans) - 1):
        (a, z), (b, y) = spans[index], spans[index + 1]
        if b != z + 1 or text[z] not in _APOSTROPHES:
            continue
        head, tail = text[a:z], text[b:y].strip('._．＿')
        if not (head.isalpha() and tail.isalpha()):
            continue
        joined = codes_for(head + "'" + tail)
        if not joined:
            continue
        whole = text[a:b] + tail
        if not (found[index] and _key(tail) in _CLITICS):
            found[index] = joined
            wholes[index] = whole
        found[index + 1] = joined
        wholes[index + 1] = whole


def _choose(codes, previous, previous_word, next_codes):
    """One code for an ambiguous word, from its neighbours."""
    if len(codes) == 1:
        return codes
    following = next_codes[:1]
    # ``is done`` / ``has a cat``: after an auxiliary, or before an object, the
    # verb form is the verb.
    if 'M' in codes and 'V' in codes and (previous == 'M' or following in ('D', 'N', 'J', 'O', 'U')):
        return 'V'
    if 'M' in codes:
        return 'M'
    if 'D' in codes and following in ('N', 'J'):
        return 'D'
    if 'V' in codes and (previous in ('O', 'M') or previous_word == 'to'):
        return 'V'
    # ``a simple way`` ``my spare time``: before a noun, the adjective
    # (checked before the noun rule since 2026-10-15a, when WordNet gave many
    # adjectives a rare noun reading as well)
    if 'J' in codes and previous in ('D', 'J', 'P') and following == 'N':
        return 'J'
    if 'N' in codes and previous in ('D', 'J', 'P'):
        return 'N'
    if 'C' in codes and previous in ('V', 'N', 'O') and 'D' in codes:
        return 'C'
    return codes[0]


def judge(text, spans):
    """``(codes, code, whole)`` for each (start, end) word span of ``text``,
    in order: the dictionary's codes ('' when unknown), the one the
    neighbours chose ('' when unknown) and the contraction it was looked up
    as (``don't``; '' when none). ``categories`` is this, by display row, so
    the right-click 品詞判定 says what the colours show (2026-10-15 うにさん
    「右クリックの品詞判定に、判定した品詞を表示する」).

    Neighbours are the words next to each other with only spaces between
    (a full stop or a Japanese word starts a new phrase)."""
    if not spans:
        return []
    found = []
    for a, z in spans:
        # A full stop after a word (``book.``) is not part of it; one inside
        # (``e.g.``, ``file_name.txt``) makes it not a plain English word.
        word = text[a:z].strip('._．＿')
        found.append(codes_for(word) if word.isalpha() else '')
    wholes = [''] * len(spans)
    _join_contractions(text, spans, found, wholes)
    result = []
    previous = ''
    previous_word = ''
    for index, (a, z) in enumerate(spans):
        codes = found[index]
        joined_before = (index > 0 and not text[spans[index - 1][1]:a].strip()
                         and not text[spans[index - 1][0]:spans[index - 1][1]].endswith(('.', '．')))
        if not joined_before:
            previous, previous_word = '', ''
        next_codes = ''
        if index + 1 < len(spans) and not text[z:spans[index + 1][0]].strip():
            next_codes = found[index + 1]
        if not codes:
            result.append(('', '', wholes[index]))
            previous, previous_word = '', ''
            continue
        code = _choose(codes, previous, previous_word, next_codes)
        result.append((codes, code, wholes[index]))
        previous, previous_word = code, _key(text[a:z].strip('._．＿'))
    return result


def categories(text, spans):
    """Category (display row) for each (start, end) word span of ``text``."""
    return [CATEGORY.get(code, UNKNOWN) if code else UNKNOWN
            for _codes, code, _whole in judge(text, spans)]
