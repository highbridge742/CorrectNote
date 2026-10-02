# -*- coding: utf-8 -*-
"""Bookmark lines follow actual edits independently of analysis timing."""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import analysis_work_app as work
from session import SessionStore,new_tab

class BookmarkTrackingTkTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        self.editor=tk.Text(self.root,undo=True)
        self.source='\n'.join('同じ内容の行です。' for _ in range(20))
        self.editor.insert('1.0',self.source);self.editor.edit_reset()
        session=SessionStore();session.tabs=[new_tab(text=self.source)]
        self.a=SimpleNamespace(editor=self.editor,root=self.root,session=session,bookmarks={3,8,15},
            editor_gutter=Mock(),result_gutter=Mock(),_schedule_session_save=Mock(),
            editor_source_text=lambda:self.editor.get('1.0','end-1c'))
        work.select_document(self.a,self.source);work.install(self.a)
    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','editor','root')
    def test_repeated_line_delete_before_analysis(self):
        self.editor.delete('1.0','2.0');self.assertEqual(self.a.bookmarks,{2,7,14})
    def test_separated_edits_keep_middle_bookmarks(self):
        self.editor.delete('2.0','3.0');self.editor.insert('10.0','新しい行\n新しい行\n')
        self.assertEqual(self.a.bookmarks,{2,7,16})
    def test_split_at_start_follows_original_line(self):
        self.editor.insert('8.0','追加の行\n');self.assertEqual(self.a.bookmarks,{3,9,16})
    def test_split_inside_keeps_marked_start(self):
        self.editor.insert('8.2','\n');self.assertEqual(self.a.bookmarks,{3,8,16})
    def test_delete_marked_line_attaches_to_remaining_line(self):
        self.editor.delete('8.0','9.0');self.assertEqual(self.a.bookmarks,{3,8,14})
    def test_multiple_delete_ranges(self):
        self.editor.tk.call(self.editor._w,'delete','2.0','3.0','10.0','11.0')
        self.assertEqual(self.a.bookmarks,{2,7,13})
    def test_undo_redo_without_analysis(self):
        self.editor.insert('1.0','😀新しい行\n');self.editor.edit_separator()
        self.assertEqual(self.a.bookmarks,{4,9,16})
        self.editor.edit_undo();self.assertEqual(self.a.bookmarks,{3,8,15})
        self.editor.edit_redo();self.assertEqual(self.a.bookmarks,{4,9,16})
    def test_projection_ignores_bookmarks(self):
        with work.display_update(self.a):self.editor.insert('1.0','表示専用\n')
        self.assertEqual(self.a.bookmarks,{3,8,15})
    def test_identical_replacement_and_disabled_editor(self):
        self.editor.replace('1.0','end-1c',self.source);self.assertEqual(self.a.bookmarks,{3,8,15})
        self.editor.configure(state='disabled');self.editor.insert('1.0','変更しない\n')
        self.assertEqual(self.a.bookmarks,{3,8,15})
    def test_error_leaves_no_anchor_marks(self):
        with self.assertRaises(tk.TclError):self.editor.insert('invalid index','x')
        self.assertEqual(self.a.bookmarks,{3,8,15})
        self.assertFalse([m for m in self.editor.mark_names() if str(m).startswith('_correctnote_bookmark_')])

if __name__=='__main__':unittest.main()
