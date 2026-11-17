# -*- coding: utf-8 -*-
"""元に戻すの区切り（2026-11-17 うにさん「部分的に文字をデリートした後、別の行選択してデリートしてUndoすると、2手戻る」）。
Tk は消すの後の消す（打つの後の打つ）を、場所にかかわらず1手にまとめる。選択を消す時と、前の編集の続きでない所を
編集する時は新しい1手にする。同じ所で続けて消す・続けて打つのは今のまま1手。自分の Tk の窓だけ・作った例文。"""
import os
import tkinter as tk
import unittest
from unittest import mock

from undo_feedback import install

TEXT = '12345\nabcdef\nxyz'


class UndoSeparators(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.w = tk.Text(self.root, undo=True, autoseparators=True)
        self.w.insert('1.0', TEXT)
        self.w.edit_reset()
        self.fb = install(self.w, lambda: '#d6edf5')

    def tearDown(self):
        self.root.update_idletasks()
        self.root.destroy()

    def text(self):
        return self.w.get('1.0', 'end-1c')

    def delete_selection(self, a, b):
        w = self.w
        w.tag_add('sel', a, b)
        w.mark_set('insert', b)
        w.delete('sel.first', 'sel.last')

    def test_selection_delete_after_delete_is_its_own_step(self):
        w = self.w
        w.delete('1.2')                                   # Delete で「3」
        self.delete_selection('2.1', '2.4')               # 別の行を選んで Delete
        w.edit_undo()
        self.assertEqual(self.text(), '1245\nabcdef\nxyz')  # 選択の削除だけが戻る
        w.edit_undo()
        self.assertEqual(self.text(), TEXT)

    def test_delete_elsewhere_is_its_own_step(self):
        w = self.w
        w.delete('1.2')
        w.delete('3.0')                                   # カーソルを飛ばして Delete
        w.edit_undo()
        self.assertEqual(self.text(), '1245\nabcdef\nxyz')

    def test_typing_elsewhere_is_its_own_step(self):
        w = self.w
        w.insert('1.5', 'A')
        w.insert('1.6', 'B')                              # 続けて打つ: 1手
        w.insert('3.0', 'C')                              # 別の所: 新しい1手
        w.edit_undo()
        self.assertEqual(self.text(), '12345AB\nabcdef\nxyz')
        w.edit_undo()
        self.assertEqual(self.text(), TEXT)

    def test_same_place_stays_one_step(self):
        w = self.w
        w.delete('1.2')
        w.delete('1.2')                                   # Delete を続けて
        w.delete('1.1')                                   # BackSpace
        w.edit_undo()
        self.assertEqual(self.text(), TEXT)

    def test_selection_on_screen_does_not_split_backspaces(self):
        w = self.w
        w.tag_add('sel', '3.0', '3.2')                     # よその選択が残っていても
        w.delete('1.4')
        w.delete('1.3')
        w.edit_undo()
        self.assertEqual(self.text(), TEXT)

    def test_switch_back(self):
        w = self.w
        with mock.patch.dict(os.environ, {'CN_UNDO_EDIT_SEP': '0'}):
            w.delete('1.2')
            self.delete_selection('2.1', '2.4')
            w.edit_undo()
        self.assertEqual(self.text(), TEXT)                 # 前の動き: 2手が1度に戻る


class UndoUnderTheInlineTitle(unittest.TestCase):
    """本文の中のタイトル（body_index の訳し）の下で、絵文字の後ろの字を Undo しても、元に戻すの記録（色・タブの控え）が
    捨てられない（2026-11-17 tests_gui_undo_feedback: 訳しの index は文字列で返り、Tk 8.6.9 は絵文字を2列で書いて1列で
    読むので、返った位置を渡し直すと1つ先になり、戻した字が「何も消していない」と測られた）。"""
    def setUp(self):
        import title_inline as TI
        from text_edit import undo_group
        self.undo_group = undo_group
        self.root = tk.Tk()
        self.root.withdraw()
        self.w = tk.Text(self.root, undo=True, autoseparators=True)
        TI.prepare(self.w)
        TI.write(self.w, '試しの題', [])
        self.w.insert('1.0', '元の本文。')
        self.w.edit_reset()
        self.fb = install(self.w, lambda: '#d6edf5')

    def tearDown(self):
        self.root.update_idletasks()
        self.root.destroy()

    def run_steps(self):
        w = self.w
        for text in ('甲\U0001F600', '乙'):
            with self.undo_group(w):
                w.insert('1.end', text)
        w.edit_undo()
        return w.get('1.0', '1.end')

    def test_the_record_is_kept(self):
        self.assertEqual(self.run_steps(), '元の本文。甲\U0001F600')
        self.assertEqual(len(self.fb.redo), 1)                 # 戻した一手が Redo に残る（捨てられていない）
        self.assertEqual(len(self.fb.undo), 1)

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_UNDO_INDEX_ASIS': '0'}):
            self.run_steps()
        self.assertEqual(self.fb.redo, [])                     # 前の動き: 記録が捨てられた


if __name__ == '__main__':
    unittest.main()
