# -*- coding: utf-8 -*-
"""The app's side of the 1.16 correction bundle (2026-10-24):
  - the keys typed for each IME commit (stroke_keys → the commit's Occurrence → occurrence_strokes for
    correction_entry.correct_line). In memory only, moved and dropped with the reading.
  - how the correction stages were used (usage_counts): a child's numbers come with its answer, are added once
    in the main process and written to usage_counts.json with ENGINE_STAMP (another stamp: from 0).
The keys and the Shift presses: shift_slip.ShiftStrokeClock. Windows are the test's own Tk only (transparent and off the screen)."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk

import app, analysis_worker, debug_menu, stroke_keys, usage_counts
from analysis_work import Document, Occurrence


class _HiddenTop(tk.Toplevel):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.attributes('-alpha', 0)
        self.geometry('+10000+100')


class KeyTests(unittest.TestCase):
    def test_virtual_keys_are_the_unshifted_jis_characters(self):
        k = stroke_keys.key_of_keycode
        self.assertEqual([k(0x41), k(0x5A), k(0x31), k(0x30)], ['a', 'z', '1', '0'])
        self.assertEqual([k(0xC0), k(0xBA), k(0xBB), k(0xDE), k(0xDC), k(0xE2)], ['@', ':', ';', '^', '¥', '\\'])
        self.assertIsNone(k(0x10))           # Shift
        self.assertIsNone(k(0x0D))           # Enter

    def test_the_keys_go_to_one_commit_or_to_none(self):
        s = stroke_keys.Strokes()
        c = s.clock
        for at, code in ((0, 0x51), (40, 0x57)):     # converting: Tk gives 229 for the press
            c.press(229, now_ms=at)
            c.release(code, now_ms=at + 30)
        c.press(16, now_ms=50); c.release(16, now_ms=60)  # a Shift with nothing in it (shift_slip)
        self.assertEqual(s.for_commits(1), ((('q', 0), ('w', 40)), ((50, 60),)))
        self.assertEqual(s.for_commits(1), ((), ()))  # taken
        c.press(229, now_ms=100); c.release(0x45, now_ms=120)
        self.assertEqual(s.for_commits(2), ((), ()))  # two commits at once: nobody can tell which key went where
        self.assertEqual(c.strokes, [])

    def test_keys_of_no_commit_are_dropped_while_nothing_is_converted(self):
        s = stroke_keys.Strokes()
        s.clock.press(0x41, now_ms=0)                # typed with the IME off
        s.clock.press(0x42, now_ms=5000)
        s.clock.shifts = [(100, 200), (5100, 5200)]
        s.idle(composing=True, now_ms=9000)
        self.assertEqual(len(s.clock.strokes), 2)    # converting: kept
        s.idle(composing=False, now_ms=6000)
        self.assertEqual(s.clock.strokes, [('b', 5000)])
        self.assertEqual(s.clock.shifts, [(5100, 5200)])


class OccurrenceTests(unittest.TestCase):
    def test_the_keys_ride_on_the_commit_and_move_and_go_with_it(self):
        doc = Document('memo', '今日は晴れ')
        keys = (('k', 0.0), ('y', 30.0))
        self.assertTrue(doc.remember(3, 5, '晴れ', 'はれ', keys, ((10.0, 20.0),)))
        self.assertEqual((doc.occurrences[0].strokes, doc.occurrences[0].shifts), (keys, ((10.0, 20.0),)))
        doc.update('明日、今日は晴れ')                 # typed before it: it moves with its keys
        self.assertEqual((doc.occurrences[0].start, doc.occurrences[0].strokes), (6, keys))
        doc.update('明日、今日は晴れ', edited=True)    # undo / replace to the same text: gone
        self.assertEqual(doc.occurrences, ())
        self.assertEqual(Occurrence(0, 1, 'a', 'あ').strokes, ())    # the old form still works

    def test_the_worker_hands_correct_line_the_commits_with_keys(self):
        keys = (('k', 0.0), ('y', 30.0))
        readings = (Occurrence(0, 2, '晴れ', 'はれ', keys, ((1.0, 2.0),)), Occurrence(3, 5, '曇り', 'くもり'))
        self.assertEqual(analysis_worker.occurrence_strokes(readings),
                         [(0, 2, '晴れ', 'はれ', keys, ((1.0, 2.0),))])
        self.assertEqual(analysis_worker.occurrence_strokes(()), [])


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(usage_counts.COUNTS)
        usage_counts.COUNTS.clear()
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'usage_counts.json')
        self.patch = patch.object(app, 'USAGE_COUNTS_FILE', self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        usage_counts.COUNTS.clear()
        usage_counts.COUNTS.update(self.saved)
        self.dir.cleanup()

    def test_a_childs_numbers_are_added_once(self):
        result = dict(result={}, usage={'段A': [3, 2, 1]})
        analysis_worker.merge_usage(result)
        analysis_worker.merge_usage(result)          # the same answer again: nothing more
        self.assertNotIn('usage', result)
        self.assertEqual(usage_counts.COUNTS['段A'], [3, 2, 1])
        analysis_worker.merge_usage(dict(usage=None))
        analysis_worker.merge_usage(None)
        self.assertEqual(usage_counts.COUNTS['段A'], [3, 2, 1])

    def test_saved_with_the_engine_stamp_and_read_back(self):
        from analysis_cache import ENGINE_STAMP
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a._load_usage_counts()                       # no file yet
        a._save_usage_counts()
        self.assertFalse(os.path.exists(self.path))  # no numbers: nothing written
        usage_counts.merge({'段A': [3, 2, 1], '段B': [5, 0, 0]})
        a._save_usage_counts()
        with open(self.path, encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data['engine_stamp'], ENGINE_STAMP)
        self.assertEqual(data['counts']['段A'], [3, 2, 1])
        self.assertEqual(set(data), {'engine_stamp', 'counts'})     # numbers only
        usage_counts.COUNTS.clear()
        b = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        b._load_usage_counts()
        self.assertEqual(usage_counts.COUNTS['段B'], [5, 0, 0])
        # another engine: counted from 0
        data['engine_stamp'] = 'older'
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        usage_counts.COUNTS.clear()
        b._load_usage_counts()
        self.assertEqual(usage_counts.COUNTS, {})

    def test_the_debug_window_shows_the_three_kinds(self):
        usage_counts.merge({'段A': [3, 2, 1], '段B': [5, 4, 0], '段C': [7, 0, 0]})
        text = debug_menu.usage_text()
        for heading in debug_menu.USAGE_HEADINGS:
            self.assertIn(heading, text)
        self.assertLess(text.index('段A'), text.index('段B'))
        self.assertLess(text.index('段B'), text.index('段C'))
        root = tk.Tk(); root.withdraw()
        try:
            with patch.object(debug_menu.tk, 'Toplevel', _HiddenTop):
                dlg = debug_menu.open_usage_window(SimpleNamespace(root=root))
                root.update()
                self.assertIn('段C', dlg._usage_text.get('1.0', 'end'))
                self.assertEqual(str(dlg._usage_text.cget('state')), 'disabled')
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
