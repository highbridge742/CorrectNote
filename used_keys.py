# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
行の補正が「使った材料のキー」を記録する（裏のタブの解析で、関係する行だけやり直すため・2026-10-24）。

設計: /mnt/project-files/correctnote_20261023_bg_analysis/設計案_関係する行だけやり直す.md（うにさん 10-23 22:35Z「A 関係する行だけ」）。
correction_entry.correct_line の1回ごとに、答えの dict に used_keys を足す:
    used_keys = {'vocab': [...], 'choice': [...], 'recent': bool, 'whole': bool, 'loan': bool}
  vocab   語彙を引いたキー（読みで引いた読み・表記から読みを引いた表記）。語彙の (読み, 表記) が変わったら、
          その読みか表記がここにある行だけやり直す。
  choice  選び直しの記憶を引いたキー（元の表記・読み）。変わった記録の元の表記か読みがここにある行だけやり直す。
  recent  最近使った語を1度でも読んだか（並びの順で重みが変わるので、語ごとには分けない）。
  loan    外来語・英語の表（loanword のカタカナ・英語の語彙の表）を使った。表に入るのは表記がすべてカタカナの語と
          英語の語（読みが en: の語）だけなので、変わった語彙・記憶の表記がカタカナだけか英字を含むとき（読みが en: のとき）だけ
          やり直す（is_loan_change）。表を作り直すかの版の確かめはこれに含め、whole にはしない（2026-10-24）。
  whole   語彙か記憶の全部をなめた（全部の読み・字の木・版の番号で控えを確かめた）。何が変わってもやり直す。
  queries 語彙の全部を相手にする探し（近い読みの探し・打ち違いの読みの探し・語彙が育っていないかの見分け）は、
          中で全部をなめても whole にせず、「何を探したか」と「答えの指紋」を残す（2026-10-31・語彙に1語足すと
          行の半分以上がやり直しになり、別のタブから戻ると約50秒かかっていた）。語彙が変わったら
          queries_unchanged で同じ探しをし直し、答えの指紋が全部同じならその行はやり直さない。
          探しの中の引き（版の番号・字の木・全部の読み）は記録しない（答えの指紋に含まれる）。
  vocab_bloom  語彙のキーは、答えでは一覧ではなくビットの篩（Bloom filter・1件16ビット）にする（2026-10-31・
          打ち違いの直し候補の「無い読み」で1行に千件を超え、子から本体へ送ってタブごとに持つと大きすぎた）。
          照合は keys_hit(used, 'vocab', keys)。誤って当たる（約0.05%）とその行がやり直しになるだけで、
          変わった語を見落とすことは無い。'vocab' は空の一覧になる。
キーと真偽だけで、打った文・回数・時刻は残さない。答えは1字も変えない（記録するだけ）。
"""
from contextvars import ContextVar
import functools
import base64
import hashlib
import json
import math

_ACTIVE = ContextVar('correctnote_used_keys', default=None)
_IN_LOAN = ContextVar('correctnote_used_keys_loan', default=False)
_IN_QUERY = ContextVar('correctnote_used_keys_query', default=False)

# 語彙の全部を相手にする探し（vocabulary の関数）。名前 → 語彙を渡す引数の位置
VOCAB_QUERIES = {'find_similar_readings': 1, 'find_known_readings_flex': 1, 'store_is_young': 0}
_QUERY_ORIG = {}
_STORE_MARK = '\x00store'

VOCAB_KEYED = ('lookup', 'has_reading', 'reading_of')
VOCAB_WHOLE = ('revision', 'shape_revision', 'shape_revision_ja', 'english_readings', 'reading_trie',
               'all_surfaces', 'all_readings', 'all_prefixes', 'next_chars', 'iter_surfaces_starting_with',
               'to_list')
CHOICE_KEYED = ('lookup', 'has', 'surface_for_reading', '_reading_of')
CHOICE_WHOLE = ('revision', 'originals', 'readings', 'all_records', '__len__')

_installed = False


class _Record:
    __slots__ = ('vocab', 'choice', 'recent', 'whole', 'loan', 'queries')

    def __init__(self):
        self.vocab, self.choice, self.recent, self.whole, self.loan = set(), set(), False, False, False
        self.queries = {}

    def answer(self):
        # whole なら何が変わってもやり直すので、キーは要らない。キーは控え（同じ子の2回目の解析）に当たると
        # 引かれずに減るので、whole の行で残すと同じ行の答えが回ごとに違った（2026-10-24・1.16.0 の全体の検査）
        if self.whole:
            return {'vocab': [], 'choice': [], 'recent': self.recent, 'whole': True, 'loan': self.loan,
                    'queries': []}
        return {'vocab': [], 'vocab_bloom': bloom(self.vocab), 'choice': sorted(self.choice),
                'recent': self.recent, 'whole': self.whole, 'loan': self.loan,
                'queries': sorted([k, v] for k, v in self.queries.items())}


BLOOM_BITS_PER_KEY = 16
BLOOM_HASHES = 11


def _bloom_positions(key, m):
    h = hashlib.blake2b(key.encode('utf-8', 'surrogatepass'), digest_size=16).digest()
    h1, h2 = int.from_bytes(h[:8], 'little'), int.from_bytes(h[8:], 'little') | 1
    return [(h1 + i * h2) % m for i in range(BLOOM_HASHES)]


def bloom(keys):
    """キーの集合をビットの篩に。[ビット数, base64]。キーが無ければ None。"""
    keys = [k for k in keys if isinstance(k, str)]
    if not keys: return None
    m = max(64, int(math.ceil(len(keys) * BLOOM_BITS_PER_KEY / 8.0)) * 8)
    bits = bytearray(m // 8)
    for k in keys:
        for p in _bloom_positions(k, m): bits[p >> 3] |= 1 << (p & 7)
    return [m, base64.b64encode(bytes(bits)).decode('ascii')]


def keys_hit(used, kind, keys):
    """変わったキー keys のどれかを、その行が引いたかもしれないか（kind は 'vocab' か 'choice'）。
    篩では誤って当たることがある（やり直しの側に倒れるだけ）。分からない形なら True。"""
    if not keys: return False
    if not isinstance(used, dict): return True
    if kind == 'vocab' and 'vocab_bloom' in used:
        packed = used.get('vocab_bloom')
        if packed is None: return bool(set(keys).intersection(used.get('vocab') or ()))
        try:
            m, data = packed
            bits = base64.b64decode(data)
            return any(all(bits[p >> 3] >> (p & 7) & 1 for p in _bloom_positions(k, m))
                       for k in keys if isinstance(k, str))
        except Exception:
            return True
    return bool(set(keys).intersection(used.get(kind) or ()))


def _digest(value):
    return hashlib.blake2b(repr(value).encode('utf-8', 'surrogatepass'), digest_size=8).hexdigest()


def _query_key(name, args, kwargs, store_at):
    """探しの名前と引数を1つの文字列に。語彙は印に置き換える。文字・数・真偽・None 以外の引数なら None。"""
    if len(args) <= store_at: return None
    plain = list(args)
    plain[store_at] = _STORE_MARK
    def ok(v):
        return v is None or isinstance(v, (str, bool, int, float))
    if not all(ok(v) for v in plain) or not all(isinstance(k, str) and ok(v) for k, v in kwargs.items()):
        return None
    return json.dumps([name, plain, sorted(kwargs.items())], ensure_ascii=False)


def _run_query(f, args, kwargs):
    """探しを1回。答えと、その指紋（例外なら例外の種類の指紋）。"""
    try:
        out = f(*args, **kwargs)
    except Exception as e:
        return None, e, _digest(('raise', type(e).__name__))
    return out, None, _digest(out)


def queries_unchanged(store, queries):
    """語彙が変わったあと、行の残した探し（answer の queries）をいまの語彙でし直し、答えの指紋が全部同じか。
    分からない探しが1つでもあれば False（やり直す）。答えも語彙も変えない。"""
    if not queries: return True
    install()
    token = _IN_QUERY.set(True)
    try:
        for key, digest in queries:
            try:
                name, plain, kw = json.loads(key)
                f = _QUERY_ORIG.get(name)
                store_at = VOCAB_QUERIES.get(name)
                if f is None or store_at is None or plain[store_at] != _STORE_MARK: return False
                args = list(plain); args[store_at] = store
                if _run_query(f, args, dict(kw))[2] != digest: return False
            except Exception:
                return False
        return True
    finally:
        _IN_QUERY.reset(token)


def _wrap_query(mod, name, store_at):
    f = getattr(mod, name, None)
    if f is None or getattr(f, '_used_keys', False): return None
    _QUERY_ORIG[name] = f
    @functools.wraps(f)
    def g(*args, **kwargs):
        rec = _ACTIVE.get()
        if rec is None or _IN_QUERY.get() or _IN_LOAN.get():
            return f(*args, **kwargs)
        key = _query_key(name, args, kwargs, store_at)
        if key is None:
            return f(*args, **kwargs)        # 中の引きがそのまま記録される（whole になりうる）
        token = _IN_QUERY.set(True)
        try:
            out, err, digest = _run_query(f, args, kwargs)
        finally:
            _IN_QUERY.reset(token)
        rec.queries[key] = digest
        if err is not None: raise err
        return out
    g._used_keys = True
    setattr(mod, name, g)
    return g


def is_loan_change(reading=None, surface=None):
    """変わった語（語彙・記憶の読みと表記）が外来語・英語の表に入りうるか（loan の行をやり直すか）。"""
    if reading and str(reading).startswith('en:'): return True
    s = str(surface or '')
    if s and all('ァ' <= c <= 'ヺ' or c == 'ー' for c in s): return True
    return any(c.isascii() and c.isalpha() for c in s)


def _wrap(cls, name, kind, keyed):
    f = getattr(cls, name, None)
    if f is None or getattr(f, '_used_keys', False): return
    @functools.wraps(f)
    def g(self, *args, **kwargs):
        rec = _ACTIVE.get()
        if rec is not None and not _IN_QUERY.get():
            # 外来語・英語の表を作る間の引き（表の作り直しは控えに当たると起きない）は loan だけ。キーや whole に
            # すると、同じ行でも表が先に作られていたか（先読み・前の行）で答えが揺れた（2026-10-24・1.16.0 の検査）
            if _IN_LOAN.get():
                rec.loan = True
            elif keyed and args and isinstance(args[0], str):
                getattr(rec, kind).add(args[0])
            else:
                rec.whole = True
        return f(self, *args, **kwargs)
    g._used_keys = True
    setattr(cls, name, g)


def install():
    """語彙と選び直しの記憶の引き方を包む。何度呼んでも1回だけ。失敗しても補正には触らない。"""
    global _installed
    if _installed: return
    _installed = True
    try:
        from vocabulary import VocabularyStore
        for n in VOCAB_KEYED: _wrap(VocabularyStore, n, 'vocab', True)
        for n in VOCAB_WHOLE: _wrap(VocabularyStore, n, 'vocab', False)
    except Exception:
        pass
    try:
        import sys
        import vocabulary
        for name, store_at in VOCAB_QUERIES.items():
            orig = getattr(vocabulary, name, None)
            g = _wrap_query(vocabulary, name, store_at)
            if g is None: continue
            # 先に `from vocabulary import ...` で取り込んだ所（correction_entry など）も包んだほうに替える
            for mod in list(sys.modules.values()):
                if mod is not None and mod is not vocabulary and getattr(mod, name, None) is orig:
                    try: setattr(mod, name, g)
                    except Exception: pass
    except Exception:
        pass
    try:
        import last_choice
        for n in CHOICE_KEYED: _wrap(last_choice.LastChoiceStore, n, 'choice', True)
        for n in CHOICE_WHOLE: _wrap(last_choice.LastChoiceStore, n, 'choice', False)
        f = last_choice.frame_revision
        if not getattr(f, '_used_keys', False):
            @functools.wraps(f)
            def frame_revision(*a, **k):
                rec = _ACTIVE.get()
                if rec is not None and not _IN_QUERY.get():
                    if _IN_LOAN.get(): rec.loan = True
                    else: rec.whole = True
                return f(*a, **k)
            frame_revision._used_keys = True
            last_choice.frame_revision = frame_revision
    except Exception:
        pass
    try:
        import loanword
        for name in ('_store_revision', '_katakana_vocabulary', '_english_vocabulary'):
            f = getattr(loanword, name, None)
            if f is None or getattr(f, '_used_keys', False): continue
            def mk(f):
                @functools.wraps(f)
                def g(*a, **k):
                    rec = _ACTIVE.get()
                    if rec is None or _IN_QUERY.get(): return f(*a, **k)
                    rec.loan = True
                    token = _IN_LOAN.set(True)
                    try: return f(*a, **k)
                    finally: _IN_LOAN.reset(token)
                g._used_keys = True
                return g
            setattr(loanword, name, mk(f))
    except Exception:
        pass


class RecentWords(tuple):
    """最近使った語の並び。中を読んだら（回す・含むか・番号で取る）その行は recent に依存と記録する。
    空かどうか・長さだけでは記録しない（答えに効かない）。"""
    def _mark(self):
        rec = _ACTIVE.get()
        if rec is not None and not _IN_QUERY.get(): rec.recent = True

    def __iter__(self):
        self._mark(); return tuple.__iter__(self)

    def __contains__(self, x):
        self._mark(); return tuple.__contains__(self, x)

    def __getitem__(self, i):
        self._mark(); return tuple.__getitem__(self, i)


def start():
    """1行の記録を始める。返り値は stop() に渡す。外側の記録の中なら、同じ記録に足す（None を返す）。"""
    if _ACTIVE.get() is not None: return None, _ACTIVE.get()
    rec = _Record()
    return _ACTIVE.set(rec), rec


def stop(token):
    if token is not None: _ACTIVE.reset(token)
