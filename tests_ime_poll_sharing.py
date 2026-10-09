# -*- coding: utf-8 -*-
"""The IME timer shares one live editor observation only with pointer display."""
import unittest
from unittest.mock import Mock,patch
import app,ime_watch
import tests_typing_pointer as pointer_fixture


class IMEPollSharingTkTests(unittest.TestCase):
    def setUp(self):
        pointer_fixture.TypingPointerTests.setUp(self)
        a=self.a
        a._ime_comp='';a._ime_comp_reading='';a._ime_first_kana='';a._ime_last_result=''
        a._on_change=Mock();a._remember_ime_pair=Mock();a._ime_reading_tick=Mock()
        self.focus=a.editor;self.timers=[]

    def tearDown(self):
        self.focus=None
        pointer_fixture.TypingPointerTests.tearDown(self)

    def tick(self,active,got):
        def schedule(delay,callback):
            self.timers.append(delay);return 'owned-test-timer'
        with patch.object(self.root,'focus_get',side_effect=lambda:self.focus), \
             patch.object(self.root,'after',side_effect=schedule), \
             patch.object(ime_watch,'composition_active',return_value=active) as status, \
             patch.object(ime_watch,'read_composition',return_value=got) as strings:
            app.CorrectNoteApp._ime_reading_tick(self.a)
        return status.call_args_list,strings.call_args_list

    def test_same_editor_queries_once_per_tick_without_reusing_old_values(self):
        w=self.a.editor
        for text,hidden in (('に',True),('に',False),('にほ',True)):
            calls,strings=self.tick(True,dict(comp=text,comp_reading=text))
            self.assertEqual(len(calls),1);self.assertEqual(len(strings),1)
            self.assertEqual(calls[0].args,(w.winfo_id(),))
            self.assertEqual(strings[0].args,(w.winfo_id(),))
            self.assertEqual(self.pointer.compositions[w],text)
            self.assertEqual(w.cget('cursor'),'none' if hidden else 'xterm')
            self.pointer.restore()
        self.a._remember_ime_pair.assert_not_called()

    def test_idle_unknown_and_failed_read_never_become_commit_evidence(self):
        a=self.a
        calls,strings=self.tick(False,None)
        self.assertEqual(len(calls),1);self.assertEqual(strings,[])
        for active,read_count in ((None,0),(True,1),(False,1)):
            a._ime_comp='資料';a._ime_comp_reading='しりょう'
            with self.subTest(active=active):
                calls,strings=self.tick(active,None)
                self.assertEqual(len(calls),1);self.assertEqual(len(strings),read_count)
                self.assertEqual(a._ime_comp,'資料')
                self.assertEqual(a._ime_comp_reading,'しりょう')
                self.assertEqual(self.timers[-1],a._IME_POLL_ACTIVE_MS)
                a._remember_ime_pair.assert_not_called();a._on_change.assert_not_called()

    def test_each_commit_tick_uses_its_new_result_not_the_previous_preedit(self):
        a=self.a
        self.tick(True,dict(comp='資料',comp_reading='しりょう'))
        calls,strings=self.tick(False,dict(comp='',result='材料',result_reading='ざいりょう'))
        self.assertEqual(len(calls),1);self.assertEqual(len(strings),1)
        a._remember_ime_pair.assert_called_once_with('材料','ざいりょう')
        self.assertEqual(a._ime_comp,'');self.assertEqual(a._ime_comp_reading,'')
        self.assertEqual(self.pointer.compositions[a.editor],'')
        a._on_change.assert_called_once()
        a._remember_ime_pair.reset_mock();a._on_change.reset_mock()
        self.tick(True,dict(comp='資料',comp_reading='しりょう'))
        self.tick(False,dict(comp='',result='',result_reading=''))
        a._remember_ime_pair.assert_called_once_with('資料','しりょう',require_insertion=True)

    def test_other_focus_and_focus_change_during_read_use_their_own_hwnd(self):
        a=self.a;w=a.editor;other=a._quick_text
        for initial_focus in (other,w):
            calls=[];self.focus=initial_focus
            def status(hwnd):calls.append(('status',hwnd));return True
            def strings(hwnd):
                calls.append(('strings',hwnd))
                if hwnd==w.winfo_id():self.focus=other;return dict(comp='本体',comp_reading='ほんたい')
                return dict(comp='別窓',comp_reading='べつまど')
            with self.subTest(initial_focus='editor' if initial_focus is w else 'other'), \
                 patch.object(self.root,'focus_get',side_effect=lambda:self.focus), \
                 patch.object(self.root,'after',return_value='owned-test-timer'), \
                 patch.object(ime_watch,'composition_active',side_effect=status), \
                 patch.object(ime_watch,'read_composition',side_effect=strings):
                app.CorrectNoteApp._ime_reading_tick(a)
                self.assertEqual(calls,[('status',w.winfo_id()),('strings',w.winfo_id()),
                                        ('status',other.winfo_id()),('strings',other.winfo_id())])
                self.assertEqual(self.pointer.compositions[other],'別窓')
                self.assertEqual(a._ime_comp,'本体')
        a._remember_ime_pair.assert_not_called()

    def test_pointer_rejects_wrong_widget_or_replaced_handle_and_skips_readonly(self):
        w=self.a.editor
        for observation in ((self.a._quick_text,w.winfo_id(),True,'別窓'),
                            (w,w.winfo_id()+1,True,'古い窓')):
            with self.subTest(same_widget=observation[0] is w), \
                 patch.object(self.root,'focus_get',return_value=w), \
                 patch.object(ime_watch,'composition_active',return_value=True) as status, \
                 patch.object(ime_watch,'read_composition',return_value={'comp':'現在'}) as strings:
                self.pointer.poll_composition(observation)
                status.assert_called_once_with(w.winfo_id())
                strings.assert_called_once_with(w.winfo_id())
                self.assertEqual(self.pointer.compositions[w],'現在')
        w.configure(state='disabled')
        with patch.object(self.root,'focus_get',return_value=w), \
             patch.object(ime_watch,'composition_active') as status:
            self.pointer.poll_composition((w,w.winfo_id(),True,'未確定'))
            status.assert_not_called();self.assertEqual(self.pointer.compositions[w],'現在')

    def test_unexpected_query_error_keeps_monitor_scheduled_and_does_not_commit(self):
        a=self.a;a._ime_comp='資料';a._ime_comp_reading='しりょう'
        with patch.object(self.root,'after',return_value='owned-test-timer') as timer, \
             patch.object(ime_watch,'composition_active',side_effect=OSError('test lost context')):
            app.CorrectNoteApp._ime_reading_tick(a)
        self.assertEqual(a._ime_comp,'資料');a._remember_ime_pair.assert_not_called()
        timer.assert_called_once();self.assertEqual(a._ime_watch_id,'owned-test-timer')


if __name__=='__main__':unittest.main()
