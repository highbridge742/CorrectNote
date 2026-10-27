# -*- coding: utf-8 -*-
"""類語（2026-10-26・うにさん: 候補欄に類語の段を作る）。

分類語彙表（国立国語研究所『分類語彙表増補改訂版データベース』ver.1.0.1・CC BY-NC-SA 3.0）で、
同じ分類番号・段落・小段落にある語を類語とする。表は wlsp_synonyms.json.gz（作り方は
tools_local/synonyms_20261026/build_synonyms.py）。補正には使わない——候補欄に「― 類語 ―」の段を
足すだけ（補正の答え・候補の並びは変わらない）。

    synonyms('大きかった') → [['でかかった', '巨大だった'…], …]   意味ごとの組

類は語の品詞で選ぶ: 名詞 → 体、動詞 → 用、形容詞・副詞・連体詞・形容動詞の語幹 → 相。用言は基本形で引き、
類語を元の活用の形に合わせて返す（五段・一段・形容詞。作れない形・解析し直して同じ語に読めない形は出さない）。
英字を含む語には出さない。

表の読み込みは load_table() の1か所（後で補正の側と同じ表に差し替えられるように）。
"""
import gzip
import json
import os
import re
from functools import lru_cache

TABLE = 'wlsp_synonyms.json.gz'
PER_SENSE = 8
TOTAL = 24

_HERE = os.path.dirname(os.path.abspath(__file__))


class Table:
    """分類語彙表の表を、語ごと・組ごとに1つの文字列で持つ（リストの山にすると +90MB になるため）。"""

    def __init__(self, words=None, groups=None, readings=None):
        self._words = {w: '|'.join(','.join(e[:4]) for e in entries) for w, entries in (words or {}).items()}
        self._groups = {k: '	'.join(v) for k, v in (groups or {}).items()}
        self._readings = {w: '|'.join(v) for w, v in (readings or {}).items()}
        self._by_reading = None

    def __bool__(self):
        return bool(self._words)

    def words(self):
        """全部の見出しを、(見出し, [[類, 分類番号, 段落, 小段落], …]) の順に返す（補正の semantic_class などが使う）。"""
        for word in self._words:
            yield word, self.entries(word)

    def entries(self, word):
        """word の [[類, 分類番号, 段落, 小段落], …]。"""
        got = self._words.get(word)
        return [e.split(',') for e in got.split('|')] if got else []

    def group(self, key):
        got = self._groups.get(key)
        return got.split('	') if got else []

    def readings(self, word):
        got = self._readings.get(word)
        return got.split('|') if got else []

    def by_reading(self, reading):
        if self._by_reading is None:
            index = {}
            for word, got in self._readings.items():
                for r in got.split('|'):
                    index[r] = index[r] + '	' + word if r in index else word
            self._by_reading = index
        got = self._by_reading.get(reading)
        return got.split('	') if got else []


@lru_cache(maxsize=1)
def load_table():
    """分類語彙表の表（Table）。読めなければ空の表（類語は出ない）。初めて類語を引くときに1回だけ読む。
    表のファイルの形（build_synonyms.py）: words 見出し → [[類, 分類番号, 段落, 小段落], …]・
    groups '分類番号,段落,小段落' → [見出し…]・readings 見出し → [読み…]・license・source。"""
    try:
        with gzip.open(os.path.join(_HERE, TABLE), 'rt', encoding='utf-8') as f:
            data = json.load(f)
        return Table(data['words'], data['groups'], data.get('readings'))
    except Exception:
        return Table()


def _hiragana(text):
    return ''.join(chr(ord(ch) - 0x60) if 'ァ' <= ch <= 'ヶ' else ch for ch in text or '')


def available():
    return bool(load_table())


@lru_cache(maxsize=1)
def _tokenizer():
    from janome.tokenizer import Tokenizer
    return Tokenizer()


def _tokens(text):
    try:
        return list(_tokenizer().tokenize(text))
    except Exception:
        return []


def _pos(token):
    parts = (token.part_of_speech.split(',') + ['*', '*'])[:2]
    return parts[0], parts[1]


# 語の品詞 → 分類語彙表の類
def _class_of(token):
    major, sub = _pos(token)
    if major == '名詞':
        if sub == '形容動詞語幹':
            return '相'
        if sub in ('一般', 'サ変接続', '副詞可能'):
            return '体'
        return None         # 代名詞・数・固有名詞・接尾・非自立には出さない
    if major == '動詞' and sub == '自立':
        return '用'
    if major in ('形容詞', '副詞', '連体詞'):
        return '相'
    return None


def _kind(token):
    """類語どうしで揃える品詞の型（名詞・形容動詞語幹・動詞・形容詞・副詞・連体詞）。"""
    major, sub = _pos(token)
    if major == '名詞':
        return '形容動詞語幹' if sub == '形容動詞語幹' else '名詞'
    return major


# ------------------------------------------------------------
# 活用（五段・一段・形容詞）
# ------------------------------------------------------------

_ROWS = {'く': 'かきくけこ', 'ぐ': 'がぎぐげご', 'す': 'さしすせそ', 'つ': 'たちつてと', 'ぬ': 'なにぬねの',
         'ぶ': 'ばびぶべぼ', 'む': 'まみむめも', 'る': 'らりるれろ', 'う': 'わいうえお'}
_ONBIN = {'く': 'い', 'ぐ': 'い', 'す': 'し', 'つ': 'っ', 'る': 'っ', 'う': 'っ', 'ぬ': 'ん', 'ぶ': 'ん', 'む': 'ん'}
_VOICED_ROWS = ('ぐ', 'ぬ', 'ぶ', 'む')     # 連用タ接続の後ろが だ・で になる行


def _godan(base, form):
    end = base[-1:]
    row = _ROWS.get(end)
    if row is None:
        return None
    stem = base[:-1]
    if form == '基本形':
        return base
    if form == '未然形':
        return stem + row[0]
    if form == '未然ウ接続':
        return stem + row[4]
    if form == '連用形':
        return stem + row[1]
    if form == '連用タ接続':
        if base in ('行く', 'いく', '逝く'):
            return stem + 'っ'
        if base in ('問う', '乞う', '請う', '恋う', '訪う', 'こう', 'とう'):
            return stem + 'う'      # 問うた（ウ音便）
        return stem + _ONBIN[end]
    if form in ('仮定形', '命令ｅ'):
        return stem + row[3]
    return None


def _ichidan(base, form):
    if not base.endswith('る'):
        return None
    stem = base[:-1]
    return {'基本形': base, '未然形': stem, '連用形': stem, '連用タ接続': stem, '未然ウ接続': stem + 'よ',
            '仮定形': stem + 'れ', '命令ｙｏ': stem + 'よ', '命令ｒｏ': stem + 'ろ'}.get(form)


def _adjective(base, form):
    if not base.endswith('い'):
        return None
    stem = base[:-1]
    return {'基本形': base, '体言接続': base, '連用タ接続': stem + 'かっ', '連用テ接続': stem + 'く',
            '仮定形': stem + 'けれ', '未然ウ接続': stem + 'かろ', '未然ヌ接続': stem + 'から',
            'ガル接続': stem}.get(form)


def _inflect(base, infl_type, form):
    if infl_type.startswith('五段'):
        return _godan(base, form)
    if infl_type.startswith('一段'):
        return _ichidan(base, form)
    if infl_type.startswith('形容詞'):
        return _adjective(base, form)
    return None


def _target_form(original, candidate_type, tail):
    """元の活用形を、類語の活用型での形に置き直す（一段の 連用形＋た は、五段では 連用タ接続。
    読みます の 連用形 は、どちらでも 連用形）。"""
    form = original.infl_form
    if form in ('連用形', '連用タ接続') and _pos(original)[0] == '動詞':
        if tail[:1] in ('た', 'て', 'だ', 'で'):
            return '連用タ接続' if candidate_type.startswith('五段') else '連用形'
        return '連用形'
    return form


def _retail(tail, candidate_base, candidate_type, form):
    """後ろの た・て を、類語の音便に合わせる（読んだ ↔ 食べた）。"""
    if not tail or tail[0] not in 'たてだで' or form not in ('連用タ接続', '連用形'):
        return tail
    voiced = candidate_type.startswith('五段') and form == '連用タ接続' and candidate_base[-1:] in _VOICED_ROWS
    swap = {'た': 'だ', 'て': 'で'} if voiced else {'だ': 'た', 'で': 'て'}
    return swap.get(tail[0], tail[0]) + tail[1:]


# ------------------------------------------------------------
# 類語
# ------------------------------------------------------------

_LATIN = re.compile(r'[A-Za-zＡ-Ｚａ-ｚ]')


def _head(text):
    """text の中で類語を引く語（最初の内容語）と、その前後の文字。無ければ None。"""
    toks = _tokens(text)
    at = 0
    for token in toks:
        if _class_of(token):
            return text[:at], token, text[at + len(token.surface):]
        major, _sub = _pos(token)
        if major not in ('接頭詞', '記号'):
            return None
        at += len(token.surface)
    return None


def _headwords(word, reading, wanted_class):
    """表の見出しのうち word に当たるもの。表に無ければ、読みが同じで類も同じ見出し（嬉しい → うれしい）。"""
    table = load_table()
    if any(e[0] == wanted_class for e in table.entries(word)):
        return [word]
    return [w for w in table.by_reading(reading) if any(e[0] == wanted_class for e in table.entries(w))]


def _senses(word, wanted_class):
    table = load_table()
    seen = []
    for entry in table.entries(word):
        klass, code, para, sub = entry[:4]
        if klass != wanted_class:
            continue
        key = '%s,%s,%s' % (code, para, sub)
        if key not in seen:
            seen.append(key)
    return [table.group(key) for key in seen]


def _shape(candidate, original, head, tail):
    """類語 candidate（見出しの形）を、元の語の形・前後に合わせた文字列にする。合わせられなければ None。"""
    toks = _tokens(candidate)
    if not toks or ''.join(t.surface for t in toks) != candidate:
        return None
    if _kind(original) == '名詞':
        # 名詞は活用しないので、いくつかの語でできていても（本会議）終わりが名詞ならよい
        return head + candidate + tail if _pos(toks[-1])[0] == '名詞' else None
    if len(toks) != 1:
        return None
    cand = toks[0]
    if _kind(cand) != _kind(original):
        return None
    if _pos(original)[0] in ('動詞', '形容詞'):
        form = _target_form(original, cand.infl_type, tail)
        stem = _inflect(cand.base_form, cand.infl_type, form)
        if stem is None:
            return None
        new_tail = _retail(tail, cand.base_form, cand.infl_type, form)
        text = head + stem + new_tail
        # 解析し直して、同じ語・同じ活用形に読めるものだけ
        again = _tokens(text)
        at = len(head)
        pos = 0
        for token in again:
            if pos == at:
                # janome は サ行の し（飛ばして）を 連用タ接続 ではなく 連用形 と言う
                if (token.surface != stem or token.base_form != cand.base_form
                        or token.infl_form not in ((form, '連用形') if form == '連用タ接続' else (form,))):
                    return None
                break
            pos += len(token.surface)
        else:
            return None
        return text
    return head + candidate + tail


_CACHE = {}


def synonyms(text, per_sense=PER_SENSE, total=TOTAL):
    """text（候補欄の語）の類語を、意味ごとの組の並びで返す。[[語…], …]。無ければ []。"""
    if not text or _LATIN.search(text) or not available():
        return []
    key = (text, per_sense, total, id(load_table()))
    got = _CACHE.get(key)
    if got is None:
        got = _CACHE[key] = _synonyms(text, per_sense, total)
        while len(_CACHE) > 512:
            _CACHE.pop(next(iter(_CACHE)))
    return [list(words) for words in got]


def _synonyms(text, per_sense, total):
    found = _head(text)
    if found is None:
        return []
    head, token, tail = found
    wanted = _class_of(token)
    base = token.base_form if _pos(token)[0] in ('動詞', '形容詞') else token.surface
    reading = _hiragana(getattr(token, 'reading', '') or '')
    if _pos(token)[0] in ('動詞', '形容詞'):
        # 活用した形の読みでは見出しを引けないので、基本形の読みで（嬉しかった → うれしい）
        again = _tokens(base)
        reading = _hiragana(again[0].reading) if len(again) == 1 and again[0].reading != '*' else ''
    names = _headwords(base, reading, wanted)
    # 同じ読みの書き分け（早い／はやい／速い）は類語ではない——同音の段に出る
    table = load_table()
    same = set(table.readings(base)) | {_hiragana(base)}
    for name in names:
        same |= set(table.readings(name)) | {name}
    out, used = [], {text}
    groups = []
    for name in names:
        for group in _senses(name, wanted):
            if group not in groups:
                groups.append(group)
    for group in groups:
        words = []
        for word in group:
            if word == base or word in names or same & set(table.readings(word) or (word,)):
                continue
            shaped = _shape(word, token, head, tail)
            if shaped is None or shaped in used:
                continue
            used.add(shaped)
            words.append(shaped)
            if len(words) >= per_sense or len(used) - 1 >= total:
                break
        if words:
            out.append(words)
        if len(used) - 1 >= total:
            break
    return out
