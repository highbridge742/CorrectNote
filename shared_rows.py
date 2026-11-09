# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""The same row in another place: a finished answer is taken for a row with the same text and inputs (2026-11-08, speed).

うにさんのタブでは、中身のある行（20字以上）の約1割が、ほかの行と同じ文字列だった（写した段落）。同じ行を、
タブごと・同じタブの中でも、子が初めから解き直していた（重い行は1行で数秒〜十数秒）。

A row is taken only under the conditions row_memo and analysis_context.reuse_rows already use for a row that comes
back: the same text, the same inputs (analysis_context.signature: nearby words, IME readings, calculations, the row
above), a context that does not differ in anything the row read (analysis_context.compatible, which also checks the
attested display words), the same kana state of the tab, and a model state the row is still good for
(analysis_worker.result_compatible). In memory only and small; nothing is written. CN_SHARED_ROWS=0 turns it off.
"""
import os
from collections import OrderedDict

ENABLED = os.environ.get('CN_SHARED_ROWS') != '0'
LIMIT = 1500


class SharedRows:
    def __init__(self):
        self.rows = OrderedDict()
        self._texts = {}

    def clear(self):
        self.rows.clear()
        self._texts.clear()

    def has_text(self, text):
        return text in self._texts

    def _drop(self, place):
        if self.rows.pop(place, None) is not None:
            n = self._texts.get(place[0], 0) - 1
            if n > 0:
                self._texts[place[0]] = n
            else:
                self._texts.pop(place[0], None)

    def put(self, row, context, value, state):
        """A finished answer (not a light one) with its display units."""
        from analysis_cache import reusable_result
        key = (row or {}).get('_input_signature')
        if key is None or not reusable_result(row) or row.get('deferred_stages') or row.get('pending'):
            return
        evidence = row.get('_context_evidence')
        if not isinstance(evidence, dict) or evidence.get('whole'):
            return
        if value.get('corrected_units') is None or value.get('original_units') is None:
            return
        context = context or {}
        place = (row['original'], key)
        self._drop(place)
        # Only what the row read (holding each row's whole context would keep many copies of a long tab's)
        self.rows[place] = (row, {k: context[k] for k in evidence.get('keys', ()) if k in context},
                            value['corrected_units'], value['original_units'], value.get('navigation'), state)
        self._texts[place[0]] = self._texts.get(place[0], 0) + 1
        while len(self.rows) > LIMIT:
            self._drop(next(iter(self.rows)))

    def take(self, app, original, signature, context, attested, tab_kana, state):
        """A value as the child would send it (result, units, navigation), or None."""
        got = self.rows.get((original, signature))
        if got is None:
            return None
        row, read, corrected_units, original_units, navigation, made = got
        from analysis_context import compatible
        from analysis_worker import result_compatible
        if tab_kana is not None and row.get('_tab_has_kana', tab_kana) != tab_kana:
            return None
        if not compatible(row, read, context or {}, attested or {}):
            return None
        if made != state and not result_compatible(app, row, made, state):
            return None
        return dict(result=dict(row), corrected_units=corrected_units, original_units=original_units,
                    navigation=navigation, shared=True)


def for_app(app):
    rows = getattr(app, '_shared_rows', None)
    if rows is None:
        rows = app._shared_rows = SharedRows()
    return rows


def _signature(task):
    from analysis_context import signature
    return signature(task.get('nearby') or (), task.get('readings') or (), task.get('calculations') or (),
                     task.get('previous_line'))


def take_for(app, task, context, attested):
    """For a 'line' task about to be sent: the answer another row with the same inputs already has, or None."""
    if not ENABLED or task.get('kind') != 'line' or task.get('nearby') is None:
        return None
    rows = getattr(app, '_shared_rows', None)
    if not rows or not rows.rows:
        return None
    try:
        from analysis_worker import state_key
        if not rows.has_text(task['line']):
            return None
        return rows.take(app, task['line'], _signature(task), context, attested, task.get('tab_has_kana'), state_key(app))
    except Exception:
        return None


def remember(app, row, value, context, state):
    """A finished answer from the child (row: analysis_context.completed(value)), kept for the same row elsewhere."""
    if not ENABLED or value.get('shared'):
        return
    try:
        for_app(app).put(row, context, value, state)
    except Exception:
        pass
