# -*- coding: utf-8 -*-
"""PageUp / PageDown with nowhere further to go; the first / last row button and Ctrl+Home / End pressed twice (2026-11-04)."""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest import mock

from tests_last_line_short_20261103 import App, Harness


class Strip(Harness):
    _document_edge_line = App._document_edge_line
    _edge_stamp = App._edge_stamp
    _on_page_key_edge = App._on_page_key_edge
    session = None
    _last_editor_change_at = 0.0


class Base(unittest.TestCase):
    def make(self, rows):
        self.root = tk.Tk()
        self.root.attributes('-alpha', 0)
        self.root.geometry('700x600+10000+10000')
        self.addCleanup(self.root.destroy)
        a = Strip(self.root, rows)
        self.root.update()
        return a

    def page(self, a, widget, forward, extend=False):
        return a._on_page_key_edge(SimpleNamespace(widget=widget), forward, extend)


class PageKeys(Base):
    def test_short_tab_up_and_down(self):
        a = self.make(6)
        a.editor.mark_set('insert', '3.2')
        self.assertEqual(self.page(a, a.editor, True), 'break')
        self.assertEqual(a.editor.index('insert'), '7.0')
        self.assertEqual(self.page(a, a.editor, False), 'break')
        self.assertEqual(a.editor.index('insert'), '1.0')

    def test_the_correction_pane_too(self):
        a = self.make(6)
        a.editor.pack_forget()      # the fixture's first pane takes the whole width
        self.root.update()
        a.result_view.mark_set('insert', '3.2')
        self.assertEqual(self.page(a, a.result_view, True), 'break')
        self.assertEqual(a.result_view.index('insert'), '7.0')
        self.assertEqual(self.page(a, a.result_view, False), 'break')
        self.assertEqual(a.result_view.index('insert'), '1.0')

    def test_shift_selects_to_the_edge(self):
        a = self.make(6)
        a.editor.mark_set('insert', '3.0')
        self.assertEqual(self.page(a, a.editor, True, True), 'break')
        self.assertEqual(a.editor.index('sel.first'), '3.0')
        self.assertEqual(a.editor.index('sel.last'), '7.0')
        self.assertEqual(a.editor.index('insert'), '7.0')

    def test_shift_up_selects_to_the_first_row(self):
        a = self.make(6)
        a.editor.mark_set('insert', '3.0')
        self.assertEqual(self.page(a, a.editor, False, True), 'break')
        self.assertEqual(a.editor.index('sel.first'), '1.0')
        self.assertEqual(a.editor.index('sel.last'), '3.0')

    def test_a_plain_page_key_clears_the_selection(self):
        a = self.make(6)
        a.editor.tag_add('sel', '2.0', '3.0')
        self.page(a, a.editor, True)
        self.assertFalse(a.editor.tag_ranges('sel'))

    def test_long_tab_still_pages_while_there_is_more(self):
        a = self.make(400)
        a.editor.yview('100.0')
        self.root.update()
        self.assertIsNone(self.page(a, a.editor, True))
        self.assertIsNone(self.page(a, a.editor, False))

    def test_long_tab_at_the_ends(self):
        a = self.make(400)
        a.editor.yview('1.0')
        self.root.update()
        a.editor.mark_set('insert', '5.0')
        self.assertEqual(self.page(a, a.editor, False), 'break')
        self.assertEqual(a.editor.index('insert'), '1.0')
        a.editor.yview('395.0')
        self.root.update()
        self.assertEqual(self.page(a, a.editor, True), 'break')
        self.assertEqual(a.editor.index('insert'), '401.0')

    def test_other_widget_is_left_alone(self):
        a = self.make(6)
        self.assertIsNone(self.page(a, object(), True))


class Twice(Base):
    def at(self, a, cursor, top):
        a.editor.mark_set('insert', cursor)
        a.editor.yview(top)
        a.result_view.yview(top)
        self.root.update()

    def test_first_row_twice_comes_back_then_goes_again(self):
        a = self.make(400)
        self.at(a, '200.3', '190.0')
        a._goto_document_edge(False)
        self.root.update()
        self.assertEqual(a.editor.index('insert'), '1.0')
        a._goto_document_edge(False)
        self.root.update()
        self.assertEqual(a.editor.index('insert'), '200.3')
        self.assertEqual(a.editor.index('@0,0').split('.')[0], '190')
        self.assertEqual(a.result_view.index('@0,0').split('.')[0], '190')
        a._goto_document_edge(False)
        self.root.update()
        self.assertEqual(a.editor.index('insert'), '1.0')

    def test_last_row_twice_comes_back(self):
        a = self.make(400)
        self.at(a, '50.2', '45.0')
        a._goto_document_edge(True)
        self.root.update()
        self.assertEqual(a.editor.index('insert'), '401.0')
        a._goto_document_edge(True)
        self.root.update()
        self.assertEqual(a.editor.index('insert'), '50.2')
        self.assertEqual(a.editor.index('@0,0').split('.')[0], '45')

    def test_a_move_between_does_not_come_back(self):
        a = self.make(400)
        self.at(a, '200.3', '190.0')
        a._goto_document_edge(False)
        a.editor.mark_set('insert', '2.0')
        a._goto_document_edge(False)
        self.assertEqual(a.editor.index('insert'), '1.0')

    def test_a_scroll_between_does_not_come_back(self):
        a = self.make(400)
        self.at(a, '200.3', '190.0')
        a._goto_document_edge(False)
        self.root.update()
        a.editor.yview('30.0')
        self.root.update()
        a._goto_document_edge(False)
        self.assertEqual(a.editor.index('insert'), '1.0')

    def test_an_edit_between_does_not_come_back(self):
        a = self.make(400)
        self.at(a, '200.3', '190.0')
        a._goto_document_edge(False)
        a.editor.insert('300.0', '字')
        a._goto_document_edge(False)
        self.assertEqual(a.editor.index('insert'), '1.0')

    def test_the_release_of_the_key_is_not_an_edit(self):
        # _on_change runs at every key's release and notes the time
        a = self.make(400)
        self.at(a, '200.3', '190.0')
        a._goto_document_edge(False)
        a._last_editor_change_at = 5.0
        self.root.update()
        a._goto_document_edge(False)
        self.assertEqual(a.editor.index('insert'), '200.3')

    def test_the_other_edge_is_a_new_press(self):
        a = self.make(400)
        self.at(a, '200.3', '190.0')
        a._goto_document_edge(False)
        self.root.update()
        a._goto_document_edge(True)
        self.root.update()
        self.assertEqual(a.editor.index('insert'), '401.0')
        a._goto_document_edge(True)
        self.root.update()
        self.assertEqual(a.editor.index('insert'), '1.0')

    def test_another_tab_does_not_come_back(self):
        a = self.make(400)
        tabs = [object(), object()]
        a.session = SimpleNamespace(current=lambda: tabs[0])
        self.at(a, '200.3', '190.0')
        a._goto_document_edge(False)
        a.session = SimpleNamespace(current=lambda: tabs[1])
        a._goto_document_edge(False)
        self.assertEqual(a.editor.index('insert'), '1.0')

    def test_already_there_nothing_to_come_back_to(self):
        a = self.make(400)
        self.at(a, '1.0', '1.0')
        a._goto_document_edge(False)
        a._goto_document_edge(False)
        self.assertEqual(a.editor.index('insert'), '1.0')


if __name__ == '__main__':
    unittest.main()
