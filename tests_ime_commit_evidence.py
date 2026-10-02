# -*- coding: utf-8 -*-
"""An empty IME composition is not proof of a committed reading."""
import tkinter as tk
from types import SimpleNamespace,MethodType
from unittest.mock import Mock,patch
import unittest
import app,analysis_work_app as W
from analysis_work import Document
from ime_readings import IMEReadings

class IMECommitEvidenceTkTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        a=self.a=SimpleNamespace(root=self.root,editor=tk.Text(self.root,undo=True),ime_readings=IMEReadings(),
            _ime_pairs_dirty=False,_ime_comp='資料',_ime_comp_reading='ｼﾘｮｳ',_ime_first_kana='しりょう',
            _ime_last_result='',_IME_POLL_IDLE_MS=150,_IME_POLL_ACTIVE_MS=30,_on_change=Mock(),_ime_reading_tick=Mock())
        a._remember_ime_pair=MethodType(app.CorrectNoteApp._remember_ime_pair,a)
        a._input_document=Document(W.owner(a),'');W.install(a)
    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root')
    def begin(self,existing=''):
        a=self.a;a.editor.insert('end-1c',existing);a.editor.mark_set('insert','end-1c')
        a._ime_origin_work=W.token(a);a._ime_inserted_range=(None,None)
    def end(self,result='',reading=''):
        with patch('ime_watch.composition_active',return_value=False),patch('ime_watch.read_composition',return_value=dict(comp='',result=result,result_reading=reading)):
            app.CorrectNoteApp._ime_reading_tick(self.a)
    def test_cancel_without_insert_does_not_save(self):
        self.begin();self.end()
        self.assertEqual(self.a.ime_readings.readings_for('資料'),[])
        self.assertFalse(self.a._ime_pairs_dirty)
    def test_old_identical_text_does_not_prove_commit(self):
        self.begin('資料');self.end()
        self.assertEqual(self.a.ime_readings.readings_for('資料'),[])
        self.assertEqual(self.a._input_document.occurrences,())
    def test_per_character_fallback_commit_is_retained(self):
        self.begin('本文：')
        for char in '資料':self.a.editor.insert('insert',char)
        self.end()
        self.assertEqual(self.a.ime_readings.readings_for('資料'),['しりょう'])
        self.assertEqual([(x.start,x.end,x.reading) for x in self.a._input_document.occurrences],[(3,5,'しりょう')])
    def test_old_prefix_cannot_complete_current_result(self):
        self.begin('資');self.a.editor.insert('insert','料');self.end()
        self.assertEqual(self.a.ime_readings.readings_for('資料'),[])
    def test_unrelated_edit_invalidates_fallback(self):
        self.begin('本文：');self.a.editor.insert('insert','資料')
        self.a.editor.insert('1.0','別');self.a.editor.mark_set('insert','end-1c');self.end()
        self.assertEqual(self.a.ime_readings.readings_for('資料'),[])
    def test_explicit_result_before_tk_insert_keeps_pair_without_false_occurrence(self):
        self.begin();self.end('資料','ｼﾘｮｳ')
        self.assertEqual(self.a.ime_readings.readings_for('資料'),['しりょう'])
        self.assertEqual(self.a._input_document.occurrences,())
    def test_fallback_without_observed_origin_is_not_stored(self):
        self.a.editor.insert('insert','資料');self.a._ime_origin_work=None;self.end()
        self.assertEqual(self.a.ime_readings.readings_for('資料'),[])

    def test_undo_redo_is_not_a_new_commit_but_keeps_untouched_current_reading(self):
        self.begin('確認\n');a=self.a
        self.assertTrue(a._input_document.remember(0,2,'確認','かくにん'))
        a.editor.edit_reset();a.editor.insert('insert','資料');a.editor.edit_separator()
        a.editor.edit_undo();a.editor.edit_redo()
        self.assertEqual(a.editor.get('1.0','end-1c'),'確認\n資料')
        self.assertIsNone(a._ime_inserted_range[1]);self.end()
        self.assertEqual(a.ime_readings.readings_for('資料'),[])
        self.assertEqual([(o.surface,o.reading) for o in a._input_document.occurrences],
                         [('確認','かくにん')])
        self.assertEqual(a.editor._correctnote_replay_depth,0)

    def test_event_pairs_survive_an_entire_commit_between_ticks(self):
        a=self.a;a._ime_comp='';a._ime_origin_work=None
        a._ime_result_events=SimpleNamespace(take=lambda:(('資料','ｼﾘｮｳ'),))
        self.end()
        self.assertEqual(a.ime_readings.readings_for('資料'),['しりょう'])
        self.assertEqual(a._input_document.occurrences,())
        a._on_change.assert_called_once()
    def test_queued_different_readings_of_same_surface_keep_order(self):
        a=self.a;a._ime_comp='';a._ime_origin_work=None
        a._ime_result_events=SimpleNamespace(take=lambda:(('行った','ｲｯﾀ'),('行った','ｵｺﾅｯﾀ')))
        self.end()
        self.assertEqual(a.ime_readings.readings_for('行った'),['おこなった','いった'])
    def test_event_from_earlier_commit_cannot_bind_current_identical_text(self):
        self.begin();a=self.a;a.editor.insert('insert','資料');a._ime_comp=''
        a._ime_result_events=SimpleNamespace(take=lambda:(('資料','ｼﾘｮｳ'),))
        self.end()
        self.assertEqual(a.ime_readings.readings_for('資料'),['しりょう'])
        self.assertEqual(a._input_document.occurrences,())

if __name__=='__main__':unittest.main()
