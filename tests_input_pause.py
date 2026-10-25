# -*- coding: utf-8 -*-
"""Speculative computation must never publish during the existing input pause."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import analysis_input as scheduling

class Root:
    def __init__(self):self.jobs={};self.serial=0
    def after(self,ms,fn):
        self.serial+=1;self.jobs[self.serial]=(ms,fn);return self.serial
    def after_cancel(self,job):self.jobs.pop(job,None)
    def run(self,job):self.jobs.pop(job)[1]()

class InputPauseTests(unittest.TestCase):
    def setUp(self):
        self.now=10.0
        self.clock=patch.object(scheduling.time,'monotonic',side_effect=lambda:self.now)
        self.clock.start();self.addCleanup(self.clock.stop)
        # The mechanism with the waits it was written for (300 / 100); the defaults are 40 since
        # 2026-10-23 (test_the_defaults_are_40ms)
        for name,value in (('DISPLAY_QUIET_MS',300),('DISPLAY_QUIET_IME_MS',100)):
            waits=patch.object(scheduling,name,value);waits.start();self.addCleanup(waits.stop)
        self.reset_app()
    def reset_app(self):
        self.now=10.0
        self.a=SimpleNamespace(root=Root(),settings={'input_method':'kana'},_work_epoch=0,
            _after_id=None,_view_changing=lambda:False,_analyze_if_changed=Mock(),
            _refresh_after_analysis=Mock(),_queue_status_visibility=Mock(),
            editor_source_text=lambda:'synthetic')
    def accepted(self):
        self.a._analyze_work,self.a._analyze_dependencies=scheduling.identity(self.a)
        self.a._analyze_text='synthetic'
    def test_the_defaults_are_40ms(self):
        # 2026-10-23 うにさん: both waits 40ms; the debug menu keeps the ranges 0-300 / 0-100
        import importlib
        fresh=importlib.reload(importlib.import_module('analysis_input'))
        self.assertEqual((fresh.DISPLAY_QUIET_MS,fresh.DISPLAY_QUIET_IME_MS),(40,40))
        self.assertEqual((fresh.DISPLAY_QUIET_MS_MAX,fresh.DISPLAY_QUIET_IME_MS_MAX),(300,100))
    def test_computation_starts_early_but_display_waits_for_quiet(self):
        a=self.a;scheduling.schedule(a);self.accepted()
        self.assertEqual(a.root.jobs[a._after_id][0],scheduling.COMPUTE_DELAY_MS)
        self.assertLess(scheduling.COMPUTE_DELAY_MS,scheduling.DISPLAY_QUIET_MS)
        self.now+=.08;a.root.run(a._after_id);a._after_id=None
        a._analyze_if_changed.assert_called_once_with()
        self.assertTrue(scheduling.defer_display(a,False))
        ms,callback=a.root.jobs[a._input_display_job]
        self.assertTrue(219<=ms<=221,ms);a._refresh_after_analysis.assert_not_called()
        self.now+=.221;a.root.run(a._input_display_job)
        a._refresh_after_analysis.assert_called_once_with(learn=False)
        self.assertIsNone(a._input_display_job)
    def test_an_ime_commit_waits_less_than_a_single_key(self):
        a=self.a;a._ime_comp='としょかん';scheduling.schedule(a)
        self.assertAlmostEqual(a._input_display_after,10+scheduling.DISPLAY_QUIET_IME_MS/1000)
        self.assertLess(scheduling.DISPLAY_QUIET_IME_MS,scheduling.DISPLAY_QUIET_MS)
        # The watcher's follow-up (reading bound, composition ended, same text)
        # keeps the commit's pause; the next typed text does not.
        a._ime_comp='';a._work_epoch+=1;self.now+=.01;scheduling.schedule(a)
        self.assertAlmostEqual(a._input_display_after,10.01+scheduling.DISPLAY_QUIET_IME_MS/1000)
        a.editor_source_text=lambda:'synthetic+';a._work_epoch+=1;scheduling.schedule(a)
        self.assertAlmostEqual(a._input_display_after,10.01+scheduling.DISPLAY_QUIET_MS/1000)
        self.reset_app();a=self.a;a._ime_comp='';scheduling.schedule(a)
        self.assertAlmostEqual(a._input_display_after,10+scheduling.DISPLAY_QUIET_MS/1000)
    def test_arrow_release_does_not_restart_timer_or_hold_finished_display(self):
        a=self.a;scheduling.schedule(a);before=dict(a.root.jobs);end=a._input_display_after
        self.now+=.06;scheduling.schedule(a)
        self.assertEqual(a.root.jobs,before);self.assertEqual(a._input_display_after,end)
        a.root.run(a._after_id);a._after_id=None
        self.now+=1;scheduling.schedule(a)
        self.assertFalse(a.root.jobs);self.assertFalse(scheduling.defer_display(a,False))
    def test_new_edit_restarts_compute_and_discards_old_display(self):
        a=self.a;scheduling.schedule(a);self.accepted();scheduling.defer_display(a,False)
        old_compute=a._after_id;old_display=a._input_display_job
        late=a.root.jobs[old_display][1]
        self.now+=.1;a._work_epoch+=1;scheduling.schedule(a)
        self.assertNotIn(old_compute,a.root.jobs);self.assertNotIn(old_display,a.root.jobs)
        self.assertAlmostEqual(a._input_display_after,10.4)
        late();a._refresh_after_analysis.assert_not_called()
    def test_late_result_rejected_after_tab_dependency_or_text_change(self):
        for change in ('work','settings','text','plan','closing'):
            with self.subTest(change=change):
                self.reset_app();a=self.a;scheduling.schedule(a);self.accepted()
                scheduling.defer_display(a,True)
                if change=='work':a._work_epoch+=1
                if change=='settings':a.settings['input_method']='romaji'
                if change=='text':a.editor_source_text=lambda:'different'
                if change=='plan':a._analyze_work=('stale',0)
                if change=='closing':a._closing=True
                self.now+=.31;a.root.run(a._input_display_job)
                a._refresh_after_analysis.assert_not_called()
    def test_repeated_refreshes_share_one_timer_and_keep_learning_request(self):
        a=self.a;scheduling.schedule(a);self.accepted()
        scheduling.defer_display(a,False);job=a._input_display_job
        scheduling.defer_display(a,True);scheduling.defer_display(a,False)
        self.assertEqual(a._input_display_job,job)
        self.now+=.31;a.root.run(job)
        a._refresh_after_analysis.assert_called_once_with(learn=True)
    def test_held_view_rechecks_identity_before_deferred_paint(self):
        for held in ('_overview','_drag','_view_changing'):
            with self.subTest(held=held):
                self.reset_app();a=self.a;scheduling.schedule(a);self.accepted()
                scheduling.defer_display(a,True)
                setattr(a,held,object() if held=='_overview' else {'mode':'scroll'} if held=='_drag' else lambda:True)
                self.now+=.31;a.root.run(a._input_display_job)
                a._refresh_after_analysis.assert_not_called()
                self.assertEqual(a.root.jobs[a._input_display_job][0],50)
                setattr(a,held,None if held!='_view_changing' else lambda:False)
                a.root.run(a._input_display_job)
                a._refresh_after_analysis.assert_called_once_with(learn=True)
    def test_overdue_refresh_keeps_the_one_pending_learning_callback(self):
        a=self.a;scheduling.schedule(a);self.accepted();scheduling.defer_display(a,True)
        job=a._input_display_job;self.now+=.31
        self.assertTrue(scheduling.defer_display(a,False))
        self.assertEqual(a._input_display_job,job)
        a.root.run(job);a._refresh_after_analysis.assert_called_once_with(learn=True)
    def test_cancel_removes_callback_but_keeps_current_quiet_deadline(self):
        a=self.a;scheduling.schedule(a);scheduling.defer_display(a,True)
        job=a._input_display_job;deadline=a._input_display_after
        scheduling.cancel_display(a)
        self.assertNotIn(job,a.root.jobs);self.assertIsNone(a._input_display_job)
        self.assertEqual(a._input_display_after,deadline)
        self.assertFalse(a._input_display_learn)
    def test_ime_end_without_a_text_change_keeps_the_full_quiet_period(self):
        a=self.a;scheduling.schedule(a);self.accepted();self.now+=.5
        a._unified_autofix_waiting_ime=True;scheduling.schedule(a)
        self.assertAlmostEqual(a._input_display_after,self.now+.3)
        self.assertTrue(scheduling.defer_display(a,False))
    def test_late_ime_evidence_changes_identity_and_restarts_computation(self):
        a=self.a;scheduling.schedule(a);old=a._after_id
        a._analysis_state_revision=1;scheduling.schedule(a)
        self.assertNotEqual(a._after_id,old)
        self.assertNotIn(old,a.root.jobs)
        self.assertEqual(a.root.jobs[a._after_id][0],scheduling.COMPUTE_DELAY_MS)

class InputResizeTests(unittest.TestCase):
    def test_footer_height_does_not_block_work_but_width_and_root_resize_do(self):
        from app import CorrectNoteApp
        a=CorrectNoteApp.__new__(CorrectNoteApp)
        a.root=Root();a._note_view_change=Mock();a._finish_resize=Mock()
        a._clamp_zoom_to_workarea=Mock();a._window_drag_button_down=lambda:False
        def resize(width,height):
            a._on_resize(SimpleNamespace(widget='editor',width=width,height=height))
        resize(800,600);a._note_view_change.reset_mock()
        resize(800,570);self.assertTrue(a.root.jobs)
        a._note_view_change.assert_not_called()
        resize(810,570);a._note_view_change.assert_called_once_with()
        a._note_view_change.reset_mock()
        a._last_window_rect=(20,20,1000,800)
        a._track_window_position(SimpleNamespace(x=20,y=20,width=1000,height=700))
        a._note_view_change.assert_called_once_with()

if __name__=='__main__':unittest.main()
