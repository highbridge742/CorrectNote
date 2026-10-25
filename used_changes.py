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
        _wrap(S, 'record', lambda original, chosen, reading=None, *a, **k: (original, chosen, reading))
        _wrap(S, 'remember', lambda original, chosen, reading=None, *a, **k: (original, chosen, reading))
        _wrap(S, 'forget_reading', lambda reading, *a, **k: (reading,))
        _wrap(S, 'forget_unit', lambda original, *a, **k: (original,))
        _wrap(S, 'forget_record', lambda rec, *a, **k: tuple(
            v for key in ('original', 'reading', 'chosen', 'surface') for v in [(rec or {}).get(key)])
            + tuple((rec or {}).get('key') or ()))
    except Exception:
        pass


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
