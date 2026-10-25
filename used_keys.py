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
キーと真偽だけで、打った文・回数・時刻は残さない。答えは1字も変えない（記録するだけ）。
"""
from contextvars import ContextVar
import functools

_ACTIVE = ContextVar('correctnote_used_keys', default=None)
_IN_LOAN = ContextVar('correctnote_used_keys_loan', default=False)

VOCAB_KEYED = ('lookup', 'has_reading', 'reading_of')
VOCAB_WHOLE = ('revision', 'shape_revision', 'shape_revision_ja', 'english_readings', 'reading_trie',
               'all_surfaces', 'all_readings', 'all_prefixes', 'next_chars', 'iter_surfaces_starting_with',
               'to_list')
CHOICE_KEYED = ('lookup', 'has', 'surface_for_reading', '_reading_of')
CHOICE_WHOLE = ('revision', 'originals', 'readings', 'all_records', '__len__')

_installed = False


class _Record:
    __slots__ = ('vocab', 'choice', 'recent', 'whole', 'loan')

    def __init__(self):
        self.vocab, self.choice, self.recent, self.whole, self.loan = set(), set(), False, False, False

    def answer(self):
        # whole なら何が変わってもやり直すので、キーは要らない。キーは控え（同じ子の2回目の解析）に当たると
        # 引かれずに減るので、whole の行で残すと同じ行の答えが回ごとに違った（2026-10-24・1.16.0 の全体の検査）
        if self.whole:
            return {'vocab': [], 'choice': [], 'recent': self.recent, 'whole': True, 'loan': self.loan}
        return {'vocab': sorted(self.vocab), 'choice': sorted(self.choice),
                'recent': self.recent, 'whole': self.whole, 'loan': self.loan}


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
        if rec is not None:
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
        import last_choice
        for n in CHOICE_KEYED: _wrap(last_choice.LastChoiceStore, n, 'choice', True)
        for n in CHOICE_WHOLE: _wrap(last_choice.LastChoiceStore, n, 'choice', False)
        f = last_choice.frame_revision
        if not getattr(f, '_used_keys', False):
            @functools.wraps(f)
            def frame_revision(*a, **k):
                rec = _ACTIVE.get()
                if rec is not None:
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
                    if rec is None: return f(*a, **k)
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
        if rec is not None: rec.recent = True

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
