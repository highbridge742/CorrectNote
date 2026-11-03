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


def _compact(table):
    """読み取り専用の dict（文字列 → 文字列）を compact_tables の小さな形に（2026-10-31・答えは同じ・
    並びも元のまま。読みの索引も含めて生きている分 35MB → 11MB）。CN_PLAIN_TABLES=1 か、形にできないときは dict のまま。"""
    try:
        import compact_tables
        if compact_tables.enabled():
            return compact_tables.CompactStrings.of(table)
    except (ImportError, ValueError):
        pass
    return table


class Table:
    """分類語彙表の表を、語ごと・組ごとに1つの文字列で持つ（リストの山にすると +90MB になるため）。
    受け取った dict は1つ詰めるごとに手放す（JSON の一時物を早く返す・load_table）。"""

    def __init__(self, words=None, groups=None, readings=None):
        self._fill(dict(words=words, groups=groups, readings=readings))

    @classmethod
    def from_data(cls, data):
        """表のファイルを読んだ dict から作る。words・groups・readings は data から外しながら詰める。"""
        table = cls.__new__(cls)
        table._fill(data)
        return table

    def _fill(self, data):
        # 1つずつ data から外して詰める（JSON の一時物は詰め終わった順に手放す）
        self._words = _compact({w: '|'.join(','.join(e[:4]) for e in entries)
                                for w, entries in (data.pop('words', None) or {}).items()})
        self._groups = _compact({k: '	'.join(v) for k, v in (data.pop('groups', None) or {}).items()})
        self._readings = _compact({w: '|'.join(v) for w, v in (data.pop('readings', None) or {}).items()})
        self._by_reading = None

    def __bool__(self):
        return bool(self._words)

    def words(self):
        """全部の見出しを、(見出し, [[類, 分類番号, 段落, 小段落], …]) の順に返す（補正の semantic_class などが使う）。
        見出しと中身を並べて一度に読む（見出しごとに引き直すと、8万語で 0.5秒あまりかかった・2026-11-01）。"""
        for word, got in self._words.items():
            yield word, [e.split(',') for e in got.split('|')] if got else []

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
            self._by_reading = _compact(index)
        got = self._by_reading.get(reading)
        return got.split('	') if got else []


@lru_cache(maxsize=1)
def load_table():
    """分類語彙表の表（Table）。読めなければ空の表（類語は出ない）。初めて類語を引くときに1回だけ読む。
    表のファイルの形（build_synonyms.py）: words 見出し → [[類, 分類番号, 段落, 小段落], …]・
    groups '分類番号,段落,小段落' → [見出し…]・readings 見出し → [読み…]・license・source。
    詰めた形は控え（COMPACT_CACHE）に書き、次からはそれを読む（_load_compact）。"""
    path = os.path.join(_HERE, TABLE)
    cached = _load_compact(path)
    if cached is not None:
        return cached
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            data = json.load(f)
        if 'words' not in data or 'groups' not in data:
            raise KeyError('words')
        table = Table.from_data(data)
    except Exception:
        return Table()
    _save_compact(table, path)
    return table


# 詰めた形の表の控え（2026-11-01）。表の JSON を読んで詰め直すのに、解析の子の起動ごと（最初の1行）に 1.3秒
# かかっていた。表のファイル（gzip の終わりの CRC・大きさ）と控えの版が同じなら、控えだけを読む。
COMPACT_CACHE = 'wlsp_synonyms_compact.pickle.gz'
COMPACT_CACHE_VERSION = 1


def _compact_cache_path():
    try:
        import reading_lattice
        return os.path.join(os.path.dirname(reading_lattice.default_cache_path()), COMPACT_CACHE)
    except Exception:
        return None


def _table_stamp(path):
    with open(path, 'rb') as f:
        size = os.fstat(f.fileno()).st_size
        f.seek(max(0, size - 8))
        return ('wlsp_synonyms', COMPACT_CACHE_VERSION, size, f.read())


def _load_compact(path):
    try:
        import compact_tables
        import pickle
        cache = _compact_cache_path()
        if not compact_tables.enabled() or not cache or not os.path.exists(cache):
            return None
        with gzip.open(cache, 'rb') as f:
            stamp, state = pickle.load(f)
        if stamp != _table_stamp(path):
            return None
        table = Table.__new__(Table)
        table._words, table._groups, table._readings = (compact_tables.CompactStrings.from_state(state[name])
                                                        for name in ('words', 'groups', 'readings'))
        table._by_reading = None
        return table
    except Exception:
        return None


def _save_compact(table, path):
    try:
        import compact_tables
        import pickle
        cache = _compact_cache_path()
        parts = (table._words, table._groups, table._readings)
        if not cache or not all(isinstance(part, compact_tables.CompactStrings) for part in parts):
            return
        state = dict(zip(('words', 'groups', 'readings'), (part.state() for part in parts)))
        tmp = '%s.%d.tmp' % (cache, os.getpid())     # 解析の子が2つ同時に書くことがある
        with gzip.open(tmp, 'wb', compresslevel=6) as f:
            pickle.dump((_table_stamp(path), state), f, protocol=4)
        os.replace(tmp, cache)
    except Exception:
        pass


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


def _whole_reading(text):
    """text の全体の読み（ひらがな）。読めない語があれば空。"""
    toks = _tokens(text)
    if not toks or any(not t.reading or t.reading == '*' for t in toks):
        return ''
    return _hiragana(''.join(t.reading for t in toks))


def _base_reading(token):
    """活用した語の基本形の読み。基本形だけを解析し直すと別の読みになる語があるので、この語自身の読みから作る
    （読みの終わりの送り仮名を、基本形の送り仮名に置き換える）。作れなければ空。"""
    surface, base = token.surface, token.base_form
    reading = _hiragana(token.reading or '')
    if not reading or token.reading == '*':
        return ''
    same = 0
    while same < min(len(surface), len(base)) and surface[same] == base[same]:
        same += 1
    tail = _hiragana(surface[same:])
    if not same or not reading.endswith(tail):
        return ''
    return reading[:len(reading) - len(tail)] + _hiragana(base[same:])


def same_reading_forms(text, spellings_of, limit=6):
    """活用した語の、同じ読みの書き分け（2026-11-02 うにさん「送り仮名を合わせる」）。

    語彙・辞書が持つのは基本形なので、活用した形の読み全体では同音の語を引けない。text の中の動詞・形容詞の
    基本形の読みで書き分けを引き（spellings_of(読み) → 基本形の表記の並び）、元の活用の形に合わせる。
    全体の読みが元と同じもの、つまり漢字だけが替わって送り仮名が同じものだけを返す（読みの違う語は類語の段）。"""
    found = _head(text)
    if found is None:
        return []
    head, token, tail = found
    if _pos(token)[0] not in ('動詞', '形容詞'):
        return []
    whole = _whole_reading(text)
    reading = _base_reading(token)
    if not whole or not reading:
        return []
    out = []
    for word in spellings_of(reading):
        if word == token.base_form or not any('一' <= ch <= '鿿' for ch in word):
            continue
        shaped = _shape(word, token, head, tail)
        if shaped is None or shaped == text or shaped in out or _whole_reading(shaped) != whole:
            continue
        out.append(shaped)
        if len(out) >= limit:
            break
    return out


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


def _kana_tail(word):
    """語の終わりの送り仮名（最後の漢字のあと）。"""
    at = len(word)
    while at and '\u3041' <= word[at - 1] <= '\u3096':
        at -= 1
    return word[at:]


def _fit_verb(word, original, readings):
    """類語の動詞 word を、元の語 original の活用の型へ（2026-11-03 うにさん「類語候補の送り仮名は揃って
    いなかった」）。readings は元の語の基本形の読み。戻り値は (使う語, 後ろへ回すか)。使えなければ (None, False)。

    元の語の送り仮名に付け替えた語が在れば、それが対（離れる→離す）。対が元の語と同じ読みなら同音の語の段に
    あるので類語には出さない。対が無くて型が違うものは後ろへ。サ変（破壊する）は自他を送り仮名に持たない。"""
    tail = _kana_tail(original.base_form)
    if tail and word == _kana_tail(word):
        # かなだけの語: 元の語の語幹の読みで始まれば同じ語の別の形（こわれる←壊す）
        for reading in readings:
            root = reading[:len(reading) - len(tail)] if reading.endswith(tail) else ''
            if root and word.startswith(root) and word != reading:
                return None, False
    toks = _tokens(word)
    if len(toks) != 1 or _pos(toks[0])[0] != '動詞':
        return word, False
    cand = toks[0]
    if cand.infl_type == original.infl_type or cand.infl_type.startswith('サ変'):
        return word, False
    own = _kana_tail(word)
    stem = word[:len(word) - len(own)]
    if not tail or not own or not stem:
        return word, True
    paired = stem + tail
    again = _tokens(paired)
    if (len(again) != 1 or again[0].surface != paired or _pos(again[0])[0] != '動詞'
            or again[0].infl_type != original.infl_type):
        return word, True
    known = set(load_table().readings(paired) or ()) | {_whole_reading(paired)}
    if paired == original.base_form or known & set(readings):
        return None, False
    return paired, False


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
    verb = _pos(token)[0] == '動詞'
    later = []
    readings = (set(table.readings(base) or ()) | {reading, _base_reading(token)}) - {''}
    for group in groups:
        words = []
        for word in group:
            if word == base or word in names or same & set(table.readings(word) or (word,)):
                continue
            behind = False
            if verb:
                word, behind = _fit_verb(word, token, readings)
                if word is None:
                    continue
            shaped = _shape(word, token, head, tail)
            if behind:
                if shaped is not None and shaped not in used and shaped not in later:
                    later.append(shaped)
                continue
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
    room = total - (len(used) - 1)
    if later and room > 0:
        out.append(later[:room])
    return out
