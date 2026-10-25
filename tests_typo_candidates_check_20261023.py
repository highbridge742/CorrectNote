# -*- coding: utf-8 -*-
"""The reconversion list's typo candidates that would show purple are left out (2026-10-23 うにさん).

「再変換候補の一覧の『打ち間違いの可能性』の候補: その単語に置き換えた文を解析して紫の判定に
なるなら表示しない」. The list opens at once with a "checking" heading; each candidate's line is
analysed in the background (candidate_check, its own analysis child) and those whose replaced word
is not purple are added in order. Closing the list stops the checks. Here the child is a stand-in
that marks chosen words purple; the real engine is exercised by
tools_local/ime_fix_20261022/probe_candidate_check.py. Withdrawn root; no clipboard."""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk

import app, analysis_worker, candidate_check

PURPLE = {'性角', 'せぃかく'}


class FakeWorker:
    made = 0

    def __init__(self):
        FakeWorker.made += 1
        self.serial = 0; self.answers = {}; self.closed = False
        self.process = SimpleNamespace(is_alive=lambda: True)

    def submit(self, task, state=None):
        self.serial += 1
        if task.get('kind') == 'line':
            line = task['line']
            spans = [(line.index(w), line.index(w) + len(w)) for w in PURPLE if w in line]
            self.answers[self.serial] = dict(result=dict(original=line, corrected=line, changed=False,
                                                         odd_spans=spans))
        return self.serial

    def poll(self, request_id):
        return self.answers.pop(request_id, None)

    def close(self):
        self.closed = True


class TypoCheckTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.patches = [patch.object(analysis_worker, 'Worker', FakeWorker),
                        patch.object(analysis_worker, 'snapshot', lambda app: {}),
                        patch.object(analysis_worker, 'state_key', lambda app: 1)]
        for p in self.patches:
            p.start()
        FakeWorker.made = 0

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.root.update()
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()

    def pump(self, seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update(); time.sleep(.005)
            if until is not None and until():
                return

    def fake_app(self):
        return SimpleNamespace(root=self.root, settings=SimpleNamespace(get=lambda k, d=None: d),
                               _blank_result=lambda line: dict(original=line), decisions=None)

    def test_only_candidates_not_purple_pass_in_order(self):
        check = candidate_check.CandidateCheck(self.fake_app())
        passed, done = [], []
        items = [(5, 7, dict(surface=s)) for s in ('正確', '性角', '生活', 'せぃかく', '精確')]
        check.start('文字入力を性格に反映する', items, lambda c: passed.append(c['surface']),
                    lambda: done.append(True))
        self.assertEqual(passed, [])                       # nothing before the checks
        self.pump(2, lambda: done)
        self.assertEqual(passed, ['正確', '生活', '精確'])
        self.assertEqual(done, [True])
        self.assertEqual(FakeWorker.made, 1)
        check.close()

    def test_closing_stops_the_checks(self):
        check = candidate_check.CandidateCheck(self.fake_app())
        passed, done = [], []
        check.start('文字入力を性格に反映する', [(5, 7, dict(surface='正確'))] * 3,
                    lambda c: passed.append(c), lambda: done.append(True))
        check.cancel()
        self.pump(.3)
        self.assertEqual((passed, done), ([], []))
        check.close()

    def menu_app(self):
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root; a._dropdown = None; a._dropdown_text = ''
        a.settings = SimpleNamespace(get=lambda k, d=None: d); a.decisions = None
        a._attested_surfaces = {}; a._analyze_ctx = None
        a.editor = tk.Text(self.root); a.editor.pack()
        a.editor.insert('1.0', '文字入力を性格に反映する')
        return a

    def open_list(self, a, surfaces):
        items = [('「性格」', None), ('― 同音の語 ―', None), ('  正格', lambda: None)]
        rows = [dict(surface=s, kind='typo') for s in surfaces]
        a._typo_rows_later(items, '打ち間違いの可能性', rows, a.editor, 1, dict(start=5, end=7), lambda c: None)
        items.append(('― かな表記 ―', None)); items.append(('  せいかく', lambda: None))
        with patch.object(app, 'monitor_work_area', return_value=(0, 0, 1920, 1040)):
            a._make_dropdown(items, 100, 100)
        return a._dropdown_parts['lb']

    def labels(self, lb):
        return [lb.get(i) for i in range(lb.size())]

    def test_the_list_opens_first_and_gets_the_checked_candidates(self):
        a = self.menu_app()
        lb = self.open_list(a, ['正確', '性角', '生活'])
        self.assertEqual(self.labels(lb)[3], '― 打ち間違いの可能性（確かめています…） ―')
        self.assertNotIn('  正確', self.labels(lb))           # not yet
        self.pump(2, lambda: '― 打ち間違いの可能性 ―' in self.labels(lb))
        self.assertEqual(self.labels(lb), ['「性格」', '― 同音の語 ―', '  正格', '― 打ち間違いの可能性 ―',
                                           '  正確', '  生活', '― かな表記 ―', '  せいかく'])
        self.assertEqual(len(a._dropdown_parts['items']), lb.size())
        a._close_dropdown(keep_target=True)
        a._typo_check.close()

    def test_candidates_with_their_own_range_show_at_once(self):
        # A particle or contextual choice covers its own range, not the word: it is not checked by
        # replacing the word, so it shows as before; the checked ones come after it
        a = self.menu_app()
        items = [('「性格」', None)]
        rows = [dict(surface='文書には', kind='typo', choice_span=(0, 4)), dict(surface='正確', kind='typo'),
                dict(surface='性角', kind='typo')]
        a._typo_rows_later(items, '打ち間違いの可能性', rows, a.editor, 1, dict(start=5, end=7), lambda c: None)
        self.assertEqual([t for t, _ in items], ['「性格」', '― 打ち間違いの可能性（確かめています…） ―', '  文書には'])
        with patch.object(app, 'monitor_work_area', return_value=(0, 0, 1920, 1040)):
            a._make_dropdown(items, 100, 100)
        lb = a._dropdown_parts['lb']
        self.pump(2, lambda: '― 打ち間違いの可能性 ―' in self.labels(lb))
        self.assertEqual(self.labels(lb), ['「性格」', '― 打ち間違いの可能性 ―', '  文書には', '  正確'])
        a._close_dropdown(keep_target=True)
        a._typo_check.close()
        # Only own-range candidates: nothing to check, the heading as before
        items = [('「性格」', None)]
        a._typo_later = None
        a._typo_rows_later(items, '打ち間違いの可能性', rows[:1], a.editor, 1, dict(start=5, end=7), lambda c: None)
        self.assertEqual([t for t, _ in items], ['「性格」', '― 打ち間違いの可能性 ―', '  文書には'])
        self.assertIsNone(a._typo_later)

    def test_no_heading_when_every_candidate_is_purple(self):
        a = self.menu_app()
        lb = self.open_list(a, ['性角', 'せぃかく'])
        self.pump(2, lambda: lb.size() == 5)
        self.assertEqual(self.labels(lb), ['「性格」', '― 同音の語 ―', '  正格', '― かな表記 ―', '  せいかく'])
        a._close_dropdown(keep_target=True)
        a._typo_check.close()


if __name__ == '__main__':
    unittest.main()
