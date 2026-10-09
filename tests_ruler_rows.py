# -*- coding: utf-8 -*-
import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
from editor_guides import EditorGuides
from session import SessionStore,new_tab
import tests_bookmark_tracking as bookmark_fixture
import analysis_work_app as work

class RulerTrackingTests(unittest.TestCase):
    def setUp(self):
        bookmark_fixture.BookmarkTrackingTkTests.setUp(self)
        self.guides=EditorGuides(self.root,(self.editor,),owner=self.a.session.current,
            on_change=self.a._schedule_session_save)
        self.a._editor_guides=self.guides
        self.guides.set_ruler_rows({3,8,15})
    def tearDown(self):
        self.guides.close();self.guides=None
        bookmark_fixture.BookmarkTrackingTkTests.tearDown(self)
    def test_edits_undo_redo_track_same_original_rows_without_bookmarks(self):
        self.a.bookmarks.clear()
        self.editor.insert('1.0','😀追加行\n');self.editor.edit_separator()
        self.assertEqual(self.guides.ruler_rows(),{4,9,16})
        self.editor.edit_undo();self.assertEqual(self.guides.ruler_rows(),{3,8,15})
        self.editor.edit_redo();self.assertEqual(self.guides.ruler_rows(),{4,9,16})
        self.editor.delete('2.0','3.0');self.editor.insert('8.2','\n')
        self.assertEqual(self.guides.ruler_rows(),{3,8,16})
        self.assertFalse([name for name in self.editor.mark_names() if str(name).startswith('_correctnote_ruler_')])
    def test_marked_line_deletion_projection_and_disabled_editor(self):
        self.editor.delete('8.0','9.0');self.assertEqual(self.guides.ruler_rows(),{3,8,14})
        with work.display_update(self.a):self.editor.insert('1.0','表示専用\n')
        self.assertEqual(self.guides.ruler_rows(),{3,8,14})
        self.editor.configure(state='disabled');self.editor.insert('1.0','不可\n')
        self.assertEqual(self.guides.ruler_rows(),{3,8,14})
        self.assertEqual(self.a.bookmarks,{3,8,14})
    def test_tab_owner_and_synthetic_session_roundtrip(self):
        first=self.a.session.current();second=new_tab(text='別タブ\n本文',ruler_rows=[2])
        self.a.session.add_tab(second);self.guides.cursor_changed(self.editor)
        self.assertEqual(self.guides.ruler_rows(),{2})
        self.a.session.active=0;self.guides.cursor_changed(self.editor)
        self.assertEqual(self.guides.ruler_rows(),{3,8,15})
        replacement=new_tab(text=self.source,ruler_rows=self.guides.ruler_rows())
        self.a.session.update_active(replacement)
        self.assertIs(self.a.session.current(),first)
        with TemporaryDirectory() as folder:
            path=str(Path(folder)/'synthetic_session.json')
            self.assertTrue(self.a.session.save(path));loaded=SessionStore()
            self.assertTrue(loaded.load(path))
            self.assertEqual([t['ruler_rows'] for t in loaded.tabs],[[3,8,15],[2]])
        self.assertEqual(new_tab()['ruler_rows'],[])
        self.assertEqual(new_tab(ruler_rows=[0,-1,True,'2',2,2,None])['ruler_rows'],[2])

if __name__=='__main__':unittest.main()
