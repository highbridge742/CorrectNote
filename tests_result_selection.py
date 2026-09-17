# -*- coding: utf-8 -*-
import tkinter as tk
import unittest
from unittest.mock import Mock
import app

class ResultSelectionTkTests(unittest.TestCase):
 def setUp(self):
  self.root=tk.Tk();self.root.withdraw();a=self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
  a.root=self.root;a.editor=tk.Text(self.root);a.result_view=tk.Text(self.root)
  a.store=Mock();a.store._tokenize_fn=lambda text:[];a.choices=None;a._syncing=False
  a.editor_gutter=Mock();a.result_gutter=Mock();a._sync_partner_to_line=Mock();a._paint_whitespace=Mock()
  a._units_are_pending=lambda:False;a._known_kana_word=lambda text:False
  a._clear_f2_target=Mock();a._dropdown=None;a._units_cache={};a.line_texts=[]
  self.set_lines('前の文です。','資料を確認します。');a._render_corrected()
 def tearDown(self):
  self.root.update_idletasks();self.root.destroy()
  from tests_tk_keys import release_tk_fixture
  release_tk_fixture(self,'a','root')
 def set_lines(self,*lines):
  self.a.line_results=[]
  for line in lines:
   self.a.line_results.append(dict(original=line,corrected=line,changed=False,details=[]))
   self.a._units_cache[line,line]=(line,[])
 def select(self):
  a=self.a;w=a.result_view
  w.mark_set('insert','2.2');w.tag_add('sel','2.0','2.2')
  a._keep_candidate_highlight(w,2,dict(start=0,end=2));a._dropdown=Mock()
 def test_unrelated_result_update_preserves_candidate_selection_and_cursor(self):
  a=self.a;self.select();self.set_lines('前の文が変わります。','資料を確認します。');a._render_corrected()
  self.assertEqual(tuple(map(str,a.result_view.tag_ranges('candidate_focus'))),('2.0','2.2'))
  self.assertEqual(tuple(map(str,a.result_view.tag_ranges('sel'))),('2.0','2.2'))
  self.assertEqual(a.result_view.index('insert'),'2.2')
  self.assertIsNotNone(a._dropdown)
 def test_unchanged_result_paint_does_not_rewrite_text(self):
  from analysis_work import observe_text
  a=self.a;edits=[];observe_text(a.result_view,lambda *args:edits.append(args))
  self.select();a._render_corrected()
  self.assertEqual(edits,[])
  self.assertTrue(a.result_view.tag_ranges('candidate_focus'))
 def test_candidate_closes_when_its_target_changes(self):
  a=self.a;self.select();popup=a._dropdown
  self.set_lines('前の文です。','別紙を確認します。');a._render_corrected()
  self.assertIsNone(a._dropdown)
  popup.destroy.assert_called_once()
  self.assertFalse(a.result_view.tag_ranges('candidate_focus'))

 def test_same_visible_word_with_changed_original_closes_old_actions(self):
  a=self.a;self.select();popup=a._dropdown
  line='資料を確認します。';changed='資科を確認します。'
  a.line_results[1]=dict(original=changed,corrected=line,changed=True,details=[('資科','資料','名詞')])
  a._units_cache[changed,line]=(line,[])
  a._render_corrected()
  self.assertEqual(a.result_view.get('2.0','2.end'),line)
  self.assertIsNone(a._dropdown)
  popup.destroy.assert_called_once()

if __name__=='__main__':unittest.main()
