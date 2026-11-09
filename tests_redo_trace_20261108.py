# -*- coding: utf-8 -*-
"""A large redo of a tab leaves one line in tools_local/scroll_trace/analysis_redo.log (2026-11-08 うにさん「またタブ内全体の
解析がやり直しになることがある」): when, the cause, the counts, the redo labels and the names of the state parts that moved
since the last analysis; never the text. A small redo writes nothing; CN_REDO_TRACE=0 writes nothing."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class RedoTrace(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        self.dir = tempfile.mkdtemp()
        self.fake = SimpleNamespace(REDO_TRACE_MIN_ROWS=30, _STATE_NAMES=app.CorrectNoteApp._STATE_NAMES,
                                    _scroll_trace_dir=self.dir, session=SimpleNamespace(active=2))
        self.states = iter([('a', 1, 2, 3, 4, 5, 6, 7, (), 9), ('a', 2, 2, 3, 4, 5, 6, 7, (), 10),
                            ('a', 2, 2, 3, 4, 5, 6, 7, (), 10), ('a', 2, 2, 3, 4, 5, 6, 7, (), 10)])

    def note(self, *args):
        # the record is a debug tool from 2026-11-09 (off by default): on here
        with patch.object(self.app.analysis_async, 'state_key', lambda _a: next(self.states)), \
                patch.dict(os.environ, {'CN_DEBUG_TOOLS': '1'}):
            self.app.CorrectNoteApp._note_big_redo(self.fake, *args)

    def log(self):
        path = os.path.join(self.dir, 'analysis_redo.log')
        if not os.path.exists(path):
            return ''
        with open(path, encoding='utf-8') as f:
            return f.read()

    def test_large_redo_is_noted_without_text(self):
        self.note('打鍵の差分', 240, 5, '差分 前19行一致')            # the first: small, only remembers the state
        self.note('解き直しの内訳', 240, 120, "{'語彙や記憶': 120}")     # large: the vocabulary and the IME readings moved
        got = self.log()
        self.assertIn('きっかけ=解き直しの内訳', got)
        self.assertIn('本文240行  対象120行', got)
        self.assertIn('動いた状態=語彙・IMEの読み', got)
        self.assertIn('タブ=2', got)
        self.assertEqual(got.count('\n'), 1)

    def test_small_redo_and_switch_off(self):
        self.note('打鍵の差分', 240, 5, 'x')
        self.note('打鍵の差分', 240, 29, 'x')                          # under 30 rows
        self.assertEqual(self.log(), '')
        with patch.dict(os.environ, {'CN_REDO_TRACE': '0'}):
            self.note('解き直しの内訳', 240, 200, 'x')
        self.assertEqual(self.log(), '')


if __name__ == '__main__':
    unittest.main()
