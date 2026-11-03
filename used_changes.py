# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Which keys of the vocabulary and of the choice memory changed, in memory only (2026-10-24・裏のタブの解析で
関係する行だけやり直す・used_keys と対で使う).

Each store mutation that moves the store's revision is noted as (revision before, revision after, keys): the
reading and the surface for the vocabulary, the original, the chosen spelling and the reading for the choice
memory. `changed(obj, rev_from, rev_to)` gives the keys that changed between two revisions, or None when that
is not known: a revision moved by anything not noted here (a load, a direct edit) or a note pushed out by the
limit. None means every row is redone. Nothing is written anywhere; no text, times or counts."""
import functools

LIMIT = 4000                     # notes kept per store; older ones go and their revisions become unknown
_LOGS = {}                       # id(store) -> [(rev_before, rev_after, frozenset(keys))]
_installed = False


def _note(obj, before, after, keys):
    if after == before:
        return
    log = _LOGS.setdefault(id(obj), [])
    log.append((before, after, frozenset(k for k in keys if isinstance(k, str) and k)))
    if len(log) > LIMIT:
        del log[:len(log) - LIMIT]


def _wrap(cls, name, keys_of):
    f = getattr(cls, name, None)
    if f is None or getattr(f, '_used_changes', False):
        return

    @functools.wraps(f)
    def g(self, *args, **kwargs):
        # the attribute, not revision(): used_keys counts a call to revision() as reading the whole store
        before = getattr(self, '_revision', 0)
        try:
            return f(self, *args, **kwargs)
        finally:
            try:
                _note(self, before, getattr(self, '_revision', 0), keys_of(*args, **kwargs))
            except Exception:
                _LOGS.pop(id(self), None)        # unknown keys: the whole range becomes unknown
    g._used_changes = True
    setattr(cls, name, g)


def _record_keys(rec):
    """一覧の1件（last_choice.all_records）を消すときに変わる鍵。前後の語ごとの記録（context）は、その語と
    選んだ語だけ（前後の語そのものは変わらない。入れると、前後の語を引いた行まで巻き込んでいた・2026-11-01）。"""
    rec = rec or {}
    if rec.get('kind') == 'context':
        key = tuple(rec.get('key') or ())
        if len(key) == 3:
            pv, og, nx = key
            shown = rec.get('chosen') or ''
            chosen = shown[len(pv):len(shown) - len(nx)] if shown.startswith(pv) and shown.endswith(nx) else shown
            return (og, chosen)
    return tuple(rec.get(name) for name in ('original', 'reading', 'chosen', 'surface'))


def install():
    """Note the mutations of VocabularyStore and LastChoiceStore. Once; answers are not touched."""
    global _installed
    if _installed:
        return
    _installed = True
    try:
        from vocabulary import VocabularyStore
        _wrap(VocabularyStore, 'add', lambda reading, surface, *a, **k: (reading, surface))
        _wrap(VocabularyStore, 'remove', lambda reading, surface, *a, **k: (reading, surface))
    except Exception:
        pass
    try:
        import last_choice
        S = last_choice.LastChoiceStore
        _wrap_record(S)
        _wrap(S, 'remember', lambda original, chosen, reading=None, *a, **k: (original, chosen, reading))
        _wrap(S, 'forget_reading', lambda reading, *a, **k: (reading,))
        _wrap(S, 'forget_unit', lambda original, *a, **k: (original,))
        # 前後の語ごとの記録も消す口（2026-11-01）。中で forget_unit を呼ぶので、外側の記録が中を覆う
        _wrap(S, 'forget', lambda original, *a, **k: (original,))
        _wrap(S, 'forget_all', lambda original, *a, **k: (original,))
        _wrap(S, 'forget_record', lambda rec, *a, **k: _record_keys(rec))
    except Exception:
        pass
    try:
        # 補正の判断（2026-11-01 うにさん「判断をひとつ消すと、すべての解析がやり直しになる」）。
        # 鍵は判断の語（直さない置換の両側・触らない語・紫を付けない語）。その語を含む行だけやり直す
        import decisions
        D = decisions.DecisionStore
        _wrap(D, 'reject', lambda original, corrected, *a, **k: (original, corrected))
        _wrap(D, 'unreject', lambda original, corrected, *a, **k: (original, corrected))
        _wrap(D, 'protect', lambda word, *a, **k: (word,))
        _wrap(D, 'unprotect', lambda word, *a, **k: (word,))
        _wrap(D, 'leave_odd_alone', lambda word, *a, **k: (word,))
    except Exception:
        pass


CONTEXT = '\0context\0'


def context_key(prev, original, next_word):
    return CONTEXT + '\0'.join((prev or '', original, next_word or ''))


def split_context_keys(keys):
    """(前後の語ごとの選び直しの並び [その行に現れる字], 残りのキー)。"""
    found = [''.join(k[len(CONTEXT):].split('\0')) for k in keys if k.startswith(CONTEXT)]
    return found, frozenset(k for k in keys if not k.startswith(CONTEXT))


def _wrap_record(cls):
    """同音の語の選び直し（買える→変える）は前後の語ごとに覚える（last_choice.record）ので、変わるのはその
    前後の並びだけ。語や読みを鍵にすると、同じ語を含む行がみな解き直しになっていた（2026-11-03 うにさん「最終
    行で再変換すると無関係の上の行が解析し直しになる」）。"""
    f = getattr(cls, 'record', None)
    if f is None or getattr(f, '_used_changes', False):
        return

    @functools.wraps(f)
    def g(self, original, chosen, reading=None, prev=None, next=None):
        before = getattr(self, '_revision', 0)
        try:
            return f(self, original, chosen, reading, prev, next)
        finally:
            try:
                if self._is_homophone_swap(original, chosen, reading):
                    keys = (context_key(prev, original, next),)
                else:
                    keys = (original, chosen, reading)
                _note(self, before, getattr(self, '_revision', 0), keys)
            except Exception:
                _LOGS.pop(id(self), None)
    g._used_changes = True
    cls.record = g


def changed(obj, rev_from, rev_to):
    """The keys that changed from rev_from to rev_to, or None when not every step is known."""
    if rev_from == rev_to:
        return frozenset()
    if obj is None or rev_to < rev_from:
        return None
    notes = [n for n in _LOGS.get(id(obj), ()) if n[1] > rev_from and n[0] < rev_to]
    if any(before < rev_from or after > rev_to for before, after, _ in notes):
        return None                               # a note reaching outside the range
    keys = set()
    at = rev_from
    # a call inside another one is noted first (it ends first): cover the range in the order of the starts,
    # and take the keys of every note inside it
    for before, after, items in sorted(notes, key=lambda n: (n[0], -n[1])):
        if before > at:
            return None                           # a step nobody noted
        keys |= items
        at = max(at, after)
    return frozenset(keys) if at == rev_to else None
