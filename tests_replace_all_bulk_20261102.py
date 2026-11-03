# -*- coding: utf-8 -*-
"""置換のすべてを1回の描き直しで（analysis_work.bulk_edits・app._replace_editor_text・2026-11-02）。
1,000件で窓が 8.1秒、5,000件で 62秒止まっていた → 1.2秒・6.6秒。1件ずつ直す形は変えない（書式・読み・Undo を保つ）ので、
字・書式のタグ・Undo・文書の字が今までと同じことを、本物の Text で確かめる。"""
import tkinter as tk
import unittest

from analysis_work import bulk_edits, observe_text


class BulkEditsTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.text = tk.Text(self.root, undo=True, autoseparators=False)
        self.edits = []
        observe_text(self.text, lambda text, discard, edit: self.edits.append((text, discard, edit)))
        self.changed = []
        self.text._correctnote_observers.setdefault('changed', []).append(lambda args=None: self.changed.append(args))

    def tearDown(self):
        self.root.destroy()

    def replace_all(self, source, word, new, hint=True):
        self.text.insert('1.0', source); self.text.edit_reset(); self.edits.clear(); self.changed.clear()
        spots = []
        at = source.find(word)
        while at >= 0:
            spots.append(at); at = source.find(word, at + 1)
        self.text.edit_separator()
        with bulk_edits(self.text):
            for start in reversed(spots):
                first, last = f'1.0+{start}c', f'1.0+{start + len(word)}c'
                if hint:
                    self.text._correctnote_bulk_hint = (start, start + len(word), new)
                self.text.replace(first, last, new)
        self.text.edit_separator()
        return source.replace(word, new)

    def test_text_and_document_match_tk(self):
        for source, word, new in (('あのいのう\nかの\n', 'の', 'ノ'),
                                  ('😀の😀の\n👍🏽の', 'の', 'ノノ'),
                                  ('一の二\n三の四', 'の', '\n'),
                                  ('ののの', 'の', '')):
            self.text.delete('1.0', 'end')
            want = self.replace_all(source, word, new)
            self.assertEqual(self.text.get('1.0', 'end-1c'), want)
            self.assertEqual(self.edits[-1][0], want)
            self.assertEqual(self.text.get('1.0', 'end-1c'), self.text._correctnote_whole_text['text'] or want)

    def test_presentation_hears_once_at_the_end(self):
        self.replace_all('のかのかのかの', 'の', 'ノ')
        self.assertEqual(len(self.edits), 4)            # 文書は1件ずつ
        self.assertEqual(len(self.changed), 1)          # 描き直しは1回
        self.assertIsNone(self.text._correctnote_last_edit)

    def test_tags_elsewhere_stay_and_one_undo_restores(self):
        source = '太字の行\n別の行'
        self.text.insert('1.0', source)
        self.text.delete('1.0', 'end')
        want = None
        self.text.tag_configure('bold')
        self.text.insert('1.0', source); self.text.tag_add('bold', '1.0', '1.2'); self.text.edit_reset()
        self.text.edit_separator()
        with bulk_edits(self.text):
            for start in reversed([source.find('の'), source.rfind('の')]):
                self.text._correctnote_bulk_hint = (start, start + 1, 'ノ')
                self.text.replace(f'1.0+{start}c', f'1.0+{start + 1}c', 'ノ')
        self.text.edit_separator()
        self.assertEqual(self.text.get('1.0', 'end-1c'), source.replace('の', 'ノ'))
        self.assertEqual([str(i) for i in self.text.tag_ranges('bold')], ['1.0', '1.2'])
        self.text.edit_undo()
        self.assertEqual(self.text.get('1.0', 'end-1c'), source)

    def test_wrong_offsets_are_caught_at_the_end(self):
        self.text.insert('1.0', 'あいうえお'); self.text.get('1.0', 'end-1c')
        with bulk_edits(self.text):
            self.text._correctnote_bulk_hint = (0, 1, 'か')      # 実際は別の場所を直す
            self.text.replace('1.3', '1.4', 'か')
        self.assertEqual(self.edits[-1][0], self.text.get('1.0', 'end-1c'))


if __name__ == '__main__':
    unittest.main()
