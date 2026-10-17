# -*- coding: utf-8 -*-
"""The edit observer keeps the whole text between edits; every read equals Tk's own.

With the part-of-speech colours a 3000-row pane holds ~70,000 tag ranges and
one whole-text read cost ~16 ms; one refresh read it ~10 times (2026-10-16).
"""
import random
import tkinter as tk
import unittest
from analysis_work import observe_text


class WholeTextCacheTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.text = tk.Text(self.root, undo=True, autoseparators=True)
        self.edits = []
        observe_text(self.text, lambda content, discard, edit: self.edits.append(content))
        self.raw = self.text._w + '_correctnote_work'

    def tearDown(self):
        self.root.destroy()

    def native(self):
        return str(self.text.tk.call(self.raw, 'get', '1.0', 'end-1c'))

    def same(self):
        self.assertEqual(self.text.get('1.0', 'end-1c'), self.native())

    def test_reads_follow_every_kind_of_edit(self):
        t = self.text
        rnd = random.Random(7)
        words = ['資料', 'を', '確認', 'します。', '\n', '😀', '👍🏽', 'abc', '\t', '']
        t.insert('1.0', '前の行\n資料を確認します。\n次の行')
        for step in range(400):
            kind = rnd.choice(['insert', 'delete', 'replace', 'undo', 'redo', 'tag', 'read', 'sep'])
            end = int(t.index('end-1c').split('.')[0])
            row = rnd.randint(1, end)
            col = rnd.randint(0, 6)
            at = '%d.%d' % (row, col)
            try:
                if kind == 'insert':
                    t.insert(at, rnd.choice(words))
                elif kind == 'delete':
                    t.delete(at, '%s+%dc' % (at, rnd.randint(0, 4)))
                elif kind == 'replace':
                    t.replace(at, '%s+%dc' % (at, rnd.randint(0, 3)), rnd.choice(words))
                elif kind == 'undo':
                    t.edit_undo()
                elif kind == 'redo':
                    t.edit_redo()
                elif kind == 'tag':
                    t.tag_add('x%d' % (step % 5), at, '%s+2c' % at)
                elif kind == 'sep':
                    t.edit_separator()
            except tk.TclError:
                pass
            with self.subTest(step=step, kind=kind):
                self.same()
                self.same()      # the second read comes from the kept copy

    def test_edit_made_inside_an_edit_callback_is_seen(self):
        t = self.text
        observe_text(t, on_edit=lambda content, discard, edit: (
            t.insert('end', '!') if content.endswith('x') else None))
        t.insert('1.0', 'abx')
        self.assertEqual(self.native(), 'abx!')
        self.same()

    def test_read_inside_an_edit_is_never_served_from_the_copy(self):
        t = self.text
        t.insert('1.0', 'abc')
        self.same()
        seen = []
        observe_text(t, on_edit=lambda content, discard, edit: seen.append(t.get('1.0', 'end-1c')))
        t.insert('1.0', 'X')
        self.assertEqual(seen, ['Xabc'])
        self.same()

    def test_failed_edit_forgets_the_copy(self):
        t = self.text
        t.insert('1.0', 'abc')
        self.same()
        with self.assertRaises(tk.TclError):
            t.insert('no-such-index', 'x')
        self.assertIsNone(t._correctnote_whole_text['text'])
        self.same()

    def test_edit_callback_still_gets_the_true_before_and_after(self):
        t = self.text
        t.insert('1.0', 'abc')
        t.get('1.0', 'end-1c')     # keep a copy
        self.edits.clear()
        t.insert('1.1', 'Z')
        self.assertEqual(self.edits, ['aZbc'])
        self.same()


if __name__ == '__main__':
    unittest.main()
