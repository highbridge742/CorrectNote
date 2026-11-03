# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Finished answers of rows that just changed, to take back when the same row returns (2026-11-03).

Undo, Backspace and the Esc of re-input conversion bring a row back to the text it had a moment ago, and it was
then worked out again from nothing (a long row: tens of seconds). In memory only, for the open tab and the current
model state, and small; no history is kept. A row comes back only under the conditions of analysis_context.reuse_rows:
the same text, the same inputs (signature), and a context that does not differ in anything the row read."""
from collections import OrderedDict

from analysis_cache import reusable_result
from analysis_context import compatible

LIMIT = 300


class RowMemo:
    def __init__(self):
        self.rows = OrderedDict()
        self.owner = self.state = None

    def clear(self):
        self.rows.clear()

    def check(self, owner, state):
        """Another tab or another model state: nothing here holds any more."""
        if owner != self.owner or state != self.state:
            self.rows.clear()
            self.owner, self.state = owner, state

    def put(self, row, context):
        key = (row or {}).get('_input_signature')
        if key is None or not reusable_result(row):
            return
        place = (row['original'], key)
        self.rows.pop(place, None)
        # Only what the row read: holding each row's whole context would keep hundreds of copies of a long tab's.
        evidence = row.get('_context_evidence')
        if not isinstance(evidence, dict) or evidence.get('whole'):
            return
        context = context or {}
        self.rows[place] = (row, {k: context[k] for k in evidence.get('keys', ()) if k in context})
        while len(self.rows) > LIMIT:
            self.rows.popitem(last=False)

    def texts(self):
        return {place[0] for place in self.rows}

    def take_back(self, results, todo, signatures, context, attested, tab_kana=None):
        """The rows of todo that are still to do; the others have their answer back."""
        if not self.rows:
            return todo
        remaining = []
        for index in todo:
            got = self.rows.get((results[index]['original'], signatures.get(index)))
            if (got is not None and compatible(got[0], got[1], context or {}, attested)
                    and (tab_kana is None or got[0].get('_tab_has_kana', tab_kana) == tab_kana)):
                results[index] = dict(got[0])
            else:
                remaining.append(index)
        return remaining


def for_app(app):
    """このタブと今の状態の控え。"""
    import analysis_async
    import analysis_work_app
    memo = getattr(app, '_row_memo', None)
    if memo is None:
        memo = app._row_memo = RowMemo()
    try:
        memo.check(analysis_work_app.owner(app), analysis_async.state_key(app))
    except (AttributeError, TypeError):
        memo.clear()        # 状態が分からなければ何も使わない
    return memo
