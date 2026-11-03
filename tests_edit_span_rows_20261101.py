# -*- coding: utf-8 -*-
"""行をまたぐ置き換えのあと、そのあいだの行も品詞の大きさを引き直す（2026-11-01 うにさん「フォントサイズに差が
出てました。スクロールしても変わりません」）。

補正欄は描き直しで本文を1回の replace で入れ替える（ui_projection.replace_text）。37行目と41行目が変わると
37〜41行目がまとめて入れ直され、あいだの行は字が同じでもタグ（品詞の大きさ）を失う。編集の印
（_correctnote_last_edit）が「始まりの行と行数の増減」だけだったので、描いた控え（_painted）はあいだの行を
描き済みのまま持ち、二度と描かなかった。印に「取った最後の行」を足し、そこまでを描き直す。"""
import tkinter as tk
import unittest

import boundary_colors
from analysis_work import observe_text


class EditSpanRowsTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.text = tk.Text(self.root)
        observe_text(self.text)
        self.text._correctnote_observers.setdefault('changed', []).append(lambda args=None: None)
        self.text.insert('1.0', '\n'.join('行%d' % i for i in range(1, 11)))

    def tearDown(self):
        self.root.destroy()

    def test_a_replace_across_rows_names_its_last_row(self):
        self.text.replace('3.0', '7.end', '行3。\n行4\n行5\n行6\n行7。')
        self.assertEqual(self.text._correctnote_last_edit, (3, 0, 7))
        self.text.insert('9.0', 'あ')
        self.assertEqual(self.text._correctnote_last_edit, (9, 0, 9))

    def test_rows_between_are_painted_again(self):
        colors = boundary_colors.BoundaryColors.__new__(boundary_colors.BoundaryColors)
        colors._painted = {r: ('行%d' % r, 'plan') for r in range(1, 11)}
        colors._last_plans, colors._marker_indices, colors.lines = {}, {}, {}
        colors._follow_edit(3, 0, 7)
        self.assertEqual(sorted(colors._painted), [1, 2, 8, 9, 10])
        colors._follow_edit(2, 1)                          # 2行目で改行（従来どおり）
        self.assertEqual(sorted(colors._painted), [1, 9, 10, 11])


if __name__ == '__main__':
    unittest.main()
