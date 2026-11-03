# -*- coding: utf-8 -*-
"""The last-line button in a short document: the text stays, so typing afterwards does not scroll (2026-11-03)."""
import tkinter as tk
import unittest
from unittest import mock

import app as app_module

App = app_module.CorrectNoteApp


class Harness:
    _goto_document_edge = App._goto_document_edge
    _document_edge_line = App._document_edge_line
    _edge_stamp = App._edge_stamp
    _line_above_middle = App._line_above_middle
    _goto_line = App._goto_line
    _clear_navigation_padding = App._clear_navigation_padding
    _center_navigation_line = App._center_navigation_line
    _mask_navigation_margins = App._mask_navigation_margins
    _unmask_navigation_margins = App._unmask_navigation_margins
    _syncing = False

    def __init__(self, root, rows):
        self.root = root
        self.editor = tk.Text(root, font=('Meiryo', 11))
        self.result_view = tk.Text(root, font=('Meiryo', 11))
        self.editor.pack(side='left', fill='both', expand=True)
        self.result_view.pack(side='left', fill='both', expand=True)
        body = chr(10).join('行%d' % k for k in range(rows)) + chr(10) * 41
        for w in (self.editor, self.result_view):
            w.insert('1.0', body)
        self.body = chr(10).join('行%d' % k for k in range(rows))
        gutter = mock.Mock()
        self.editor_gutter = self.result_gutter = gutter
        self.v_scrollbar = mock.Mock()

    def editor_source_text(self):
        return self.editor.get('1.0', 'end-1c')

    def _close_dropdown(self): pass
    def _drop_pending_scroll(self): pass
    def _forget_bracket_cycle(self): pass
    def _flush_paper(self): pass
    def _update_header_visibility(self, first): pass
    def _on_view_moved(self): pass


class LastLine(unittest.TestCase):
    def make(self, rows):
        self.root = tk.Tk()
        self.root.attributes('-alpha', 0)
        self.root.geometry('700x600+10000+10000')
        self.addCleanup(self.root.destroy)
        strip = Harness(self.root, rows)
        self.root.update()
        return strip

    def test_short_document_stays_at_the_top(self):
        a = self.make(6)
        a._goto_document_edge(True)
        self.root.update()
        self.assertEqual(a.editor.yview()[0], 0.0)
        self.assertEqual(a.result_view.yview()[0], 0.0)
        self.assertEqual(a.editor.index('insert'), '7.0')
        self.assertFalse(getattr(a, '_navigation_padding_active', False))
        self.assertEqual(a.editor.tag_ranges('navigation_head'), ())

    def test_typing_then_does_not_move_the_text(self):
        a = self.make(6)
        a._goto_document_edge(True)
        self.root.update()
        before = a.editor.dlineinfo('1.0')
        a.editor.insert('insert', 'あ')
        a._clear_navigation_padding()       # what an edit does (analysis_work_app)
        self.root.update()
        self.assertEqual(a.editor.dlineinfo('1.0')[1], before[1])

    def test_a_long_document_is_still_centred(self):
        a = self.make(200)
        a._goto_document_edge(True)
        self.root.update()
        self.assertTrue(a._navigation_padding_active)
        self.assertGreater(a.editor.yview()[0], 0.0)

    def test_the_first_line_button_is_unchanged(self):
        a = self.make(200)
        a._goto_document_edge(True)
        self.root.update()
        a._goto_document_edge(False)
        self.root.update()
        self.assertEqual(a.editor.yview()[0], 0.0)
        self.assertEqual(a.editor.index('insert'), '1.0')


if __name__ == '__main__':
    unittest.main()
