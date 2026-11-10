# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""同じ1行の中で、同じ「2か所打ち違いの組」の探索をやり直さない（2026-11-10・全体評価 A2・速さだけ、答えは変えない）。

なぜ
----
contextual_repair.independent_key_pair_repairs(読み, 辞書, 前, 後) は、1行の補正の中で**まったく同じ引数で3〜4回**
呼ばれていた（直す所の判定 resolve が同じ所を何度も開くため）。1回が数秒〜十数秒かかる探索で、作った かなの長い行では
1行 36秒のうち 30秒がこの探索、同じ引数を1度にすれば 9秒で済む（雲の測り）。

どうやって
----------
1回目の探索が出した順番どおりの結果（出した直しと、探索の歩数を数えた所）を、その行の間だけ覚える。同じ引数の2回目からは
覚えた順に出し直す。探索の歩数（contextual_repair._search_step: 1回の resolve で 16,384 まで）は出し直しでも同じ所で
同じだけ数えるので、上限で止まる所も新しく探索した時と同じになる。

答えを変えないための決まり
--------------------------
- 覚えるのは1行の補正（used_keys の1行の記録）の間だけ。行が替われば捨てる（語彙・設定・配列が替わっても古い答えを使わない）。
  記録が無い呼び出し（アプリの外の道具など）では覚えない（元のまま）。
- 引数（読み・前・後）と辞書の物そのものが同じ時だけ使う。
- 1回目が途中で打ち切られた探索（歩数の上限・取り消し・例外）、数え方が組の探索のもの以外に及んだ探索は覚えない
  （毎回元どおり探索する）。
- 呼び手が途中で読むのをやめた探索は、続きを元の探索からそのまま取り出す（結果の順番は新しく探索した時と同じ）。
- 出す直し（ClauseKeyRepair）は書き換えられない形（frozen）なので、同じ物を出し直してよい。

切り替え: CN_PAIR_SEARCH_MEMO=0 で前のまま（install しても包まない）。
"""
import os
import threading

_KINDS = frozenset(('independent_key_pairs', 'independent_omission_prefixes'))
_local = threading.local()
_orig = {}
STATS = {'calls': 0, 'replayed': 0, 'fresh': 0, 'uncacheable': 0}


class _Entry:
    __slots__ = ('events', 'live', 'done', 'bad', 'busy', 'dictionary')

    def __init__(self, dictionary):
        self.events = []        # ('s', 種類, 上限) = 歩数を数えた所 / ('y', 直し) = 出した直し
        self.live = None        # 続きを取り出せる元の探索
        self.done = False       # 元の探索が最後まで行った
        self.bad = False        # 覚えてはいけない（途中で打ち切られた・数え方が外に及んだ）
        self.busy = False
        self.dictionary = dictionary   # 同じ物かを見るため（id の使い回しを防ぐ）


def _scope():
    """いまの行の覚え（dict）。行の記録が無ければ None。行が替わっていれば新しくする。"""
    try:
        import used_keys
        rec = used_keys._ACTIVE.get()
    except Exception:
        return None
    if rec is None:
        return None
    held = getattr(_local, 'held', None)
    if held is None or held[0] is not rec:
        held = _local.held = (rec, {})
    return held[1]


def clear():
    """覚えを捨てる。"""
    _local.held = None


def _recording():
    return getattr(_local, 'recording', None)


def _search_step(kind, limit):
    entry = _recording()
    ok = _orig['_search_step'](kind, limit)
    if entry is not None:
        if kind not in _KINDS or not ok:
            entry.bad = True          # 外の数え方に及んだ・上限で打ち切られた → 覚えない
        else:
            entry.events.append(('s', kind, limit))
    return ok


def _bounded(rows, limit, kind):
    entry = _recording()
    if entry is not None:
        entry.bad = True              # 探索の中で別の数え方をした → 覚えない
    return _orig['_bounded'](rows, limit, kind)


def _pull(entry):
    """元の探索から次の直しを1つ取り出して覚えに足す。もう無ければ None。"""
    previous = _recording()
    _local.recording = entry
    entry.busy = True
    try:
        item = next(entry.live)
    except StopIteration:
        entry.done = True
        entry.live = None
        return None
    except BaseException:
        entry.bad = True              # 取り消し・例外で途切れた → 覚えない
        entry.live = None
        raise
    finally:
        entry.busy = False
        _local.recording = previous
    entry.events.append(('y', item))
    return item


def independent_key_pair_repairs(reading, dictionary, before='', after=''):
    original = _orig['independent_key_pair_repairs']
    if os.environ.get('CN_PAIR_SEARCH') != '1':
        # 2026-11-10: 既定で探索しない（作った誤字 397件で直しを増やさず、重い行の時間の3〜6割を使っていた）。
        # CN_PAIR_SEARCH=1 で前のとおり探索する。
        return
    memo = _scope()
    if memo is None:
        yield from original(reading, dictionary, before, after)
        return
    STATS['calls'] += 1
    key = (reading, before, after, id(dictionary))
    entry = memo.get(key)
    if entry is not None and (entry.bad or entry.busy or entry.dictionary is not dictionary):
        STATS['uncacheable'] += 1
        yield from original(reading, dictionary, before, after)
        return
    if entry is None:
        STATS['fresh'] += 1
        entry = memo[key] = _Entry(dictionary)
        entry.live = original(reading, dictionary, before, after)
    else:
        STATS['replayed'] += 1
    position = 0
    step = _orig['_search_step']
    while True:
        # 覚えた分を、覚えた順に出し直す（歩数は同じ所で同じだけ数える）
        while position < len(entry.events):
            event = entry.events[position]
            position += 1
            if event[0] == 's':
                if not step(event[1], event[2]):
                    return            # 新しく探索しても、ここで上限に当たって止まる
            else:
                yield event[1]
        if entry.done or entry.live is None:
            return
        item = _pull(entry)
        # _pull の間に足された歩数は元の探索が自分で数えた。出し直しで数え直さないよう、その先から続ける
        position = len(entry.events)
        if item is None:
            return
        yield item


def install():
    """包みを掛ける（もう掛かっていれば何もしない）。CN_PAIR_SEARCH_MEMO=0 なら掛けない。"""
    if _orig or os.environ.get('CN_PAIR_SEARCH_MEMO') == '0':
        return bool(_orig)
    import contextual_repair as cr
    for name in ('independent_key_pair_repairs', '_search_step', '_bounded'):
        _orig[name] = getattr(cr, name)
    cr._search_step = _search_step
    cr._bounded = _bounded
    cr.independent_key_pair_repairs = independent_key_pair_repairs
    return True


def uninstall():
    if not _orig:
        return
    import contextual_repair as cr
    for name, fn in _orig.items():
        setattr(cr, name, fn)
    _orig.clear()
    clear()
