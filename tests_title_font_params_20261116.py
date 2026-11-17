# -*- coding: utf-8 -*-
"""タイトル・目次の字の大きさをデバッグのパラメータに（2026-11-16 うにさん）。既定は今の大きさ（タイトル 26pt・目次は本文
の字から決める＝0）。変えたらその場で付け直し、左右の行の高さもそろったまま。自分の Tk の窓だけ・作った例文。"""
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import debug_menu
import title_inline as TI
import title_toc as T
from tests_title_inline_20261115 import Inline


class Params(unittest.TestCase):
    def test_defaults_are_the_current_sizes(self):
        self.assertIn('title_size', debug_menu.KEYS)
        self.assertIn('toc_size', debug_menu.KEYS)
        self.assertEqual(debug_menu.default('title_size'), 26)
        self.assertEqual(debug_menu.default('toc_size'), 0)            # 0 は本文の字から決める（今の決め方）
        self.assertEqual(debug_menu.maximum('title_size'), T.TITLE_SIZE_MAX)
        self.assertEqual(debug_menu.maximum('toc_size'), T.TOC_POINT_MAX)

    def test_broken_or_default_values_are_not_kept(self):
        app = NS()
        got = debug_menu.normalize({'title_size': 'big', 'toc_size': 999, 'tab_name_min': 12}, app)
        self.assertNotIn('title_size', got)
        self.assertNotIn('toc_size', got)
        self.assertNotIn('tab_name_min', got)                            # 既定と同じ値は持たない


class LiveSizes(unittest.TestCase):
    setUp = Inline.setUp
    row = Inline.row

    def font_size(self, widget, tag):
        font = widget.tk.call(widget._cn_body_raw, 'tag', 'cget', tag, '-font')
        return int(widget.tk.splitlist(font)[1])

    def heights(self):
        out = []
        for r in range(1, TI.head_rows(self.editor) + 2):
            a = self.editor.tk.call(self.editor._cn_body_raw, 'dlineinfo', '%d.0' % r)
            b = self.result.tk.call(self.result._cn_body_raw, 'dlineinfo', '%d.0' % r)
            out.append(((int(a[1]), int(a[3])), (int(b[1]), int(b[3]))))
        return out

    def test_changing_the_sizes_applies_at_once_on_both_sides(self):
        before_title = self.editor.tk.call(self.editor._cn_body_raw, 'dlineinfo', '1.0')
        self.assertEqual(self.font_size(self.editor, TI.TAG_TITLE), 26)
        with mock.patch.object(T, 'TITLE_SIZE', 34), mock.patch.object(T, 'TOC_POINT', 16):
            self.toc.refresh_sizes()                                     # debug_menu.apply の終わりが呼ぶ
            self.root.update()
            self.assertEqual(self.font_size(self.editor, TI.TAG_TITLE), 34)
            self.assertEqual(self.font_size(self.result, TI.TAG_TITLE_BLANK), 34)
            link_font = self.editor.tk.splitlist(self.editor.tk.call(self.editor._cn_body_raw, 'tag', 'cget',
                                                                    TI.TAG_LINK, '-font'))
            self.assertEqual(int(link_font[1]), 16)
            after_title = self.editor.tk.call(self.editor._cn_body_raw, 'dlineinfo', '1.0')
            self.assertGreater(int(after_title[3]), int(before_title[3]))
            for left, right in self.heights():
                self.assertEqual(left, right)                            # 分割の右の空きも同じ高さ
        self.toc.refresh_sizes()
        self.root.update()
        self.assertEqual(self.font_size(self.editor, TI.TAG_TITLE), 26)

    def test_debug_apply_calls_the_refresh(self):
        called = []
        app = NS(settings=NS(get=lambda key, default=None: {}), _title_toc=NS(refresh_sizes=lambda: called.append(1)))
        debug_menu.apply(app, {})
        self.assertEqual(called, [1])


if __name__ == '__main__':
    unittest.main()
