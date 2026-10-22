"""Own Tk text: modifier cycles, asynchronous IME commits and the bracket key (F2 since 2026-10-22)."""
import ctypes,time,unittest
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk
import app,ime_watch


class BracketCompositionTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        self.editor=tk.Text(self.root,undo=True);self.editor.pack()
        self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.root=self.root;self.a.editor=self.editor
        self.tab={};self.a.session=SimpleNamespace(current=lambda:self.tab)
        self.a._work_epoch=0;self.a._f2_focus_target=None
        self.a._on_change=lambda *args:None
        self.a._close_dropdown=lambda:None;self.a._clear_f2_target=lambda:None
        self.editor.insert('1.0','前後');self.editor.mark_set('insert','1.1')
        self.errors=[]
        self.root.report_callback_exception=lambda *exc:self.errors.append(exc)

    def tearDown(self):
        self.root.update()
        for job in self.root.tk.call('after','info'):self.root.after_cancel(job)
        self.root.destroy()
        self.assertFalse(self.errors)

    def press(self,state=0):
        self.a._on_f5_brackets(SimpleNamespace(widget=self.editor,keysym='F2',char='',state=state))

    def wait(self,predicate):
        end=time.monotonic()+2
        while time.monotonic()<end:
            self.root.update()
            if predicate():return
            time.sleep(.005)
        self.fail(self.editor.get('1.0','end-1c'))

    def text(self):return self.editor.get('1.0','end-1c')

    def test_every_modifier_advances_instead_of_removing(self):
        # 2026-10-22: Alt+F2 places a pair at the cursor and Ctrl+F2 wraps the last conversion;
        # with neither a selection nor a conversion both start from the first pair.
        for state,first,second in ((0,'（）','「」'),(4,'（）','「」'),(1,'『』','【】'),
                                   (0x20000,'（）','「」'),(5,'“”','（）')):
            with self.subTest(state=state),patch.object(ime_watch,'composition_active',return_value=False):
                self.editor.delete('1.0','end');self.editor.insert('1.0','前後')
                self.editor.mark_set('insert','1.1');self.a._forget_bracket_cycle()
                self.press(state);self.assertEqual(self.text(),'前'+first+'後')
                self.press(state);self.assertEqual(self.text(),'前'+second+'後')
                self.assertTrue(self.a._cancel_bracket_cycle());self.assertEqual(self.text(),'前後')

    def test_pending_text_is_wrapped_and_rapid_repeat_is_retained(self):
        for state,pair in ((0,('（','）')),(4,('（','）')),(1,('『','』')),
                           (5,('“','”'))):           # Alt+F2: see test_alt_places_a_pair_after_the_commit
            for repeated in (False,True):
                with self.subTest(state=state,repeated=repeated):
                    self.editor.delete('1.0','end');self.editor.insert('1.0','前後');self.editor.mark_set('insert','1.1')
                    self.a._forget_bracket_cycle();active=[True]
                    def commit():
                        def insert():
                            self.editor.insert('insert','入力中の文字');active[0]=False
                        self.root.after(30,insert);return True
                    with patch.object(ime_watch,'composition_active',side_effect=lambda hwnd:active[0]),\
                         patch.object(ime_watch,'read_composition',return_value={'comp':'入力中の文字'}),\
                         patch.object(ime_watch,'complete_composition',side_effect=lambda hwnd:commit()):
                        self.press(state)
                        if repeated:self.press(state)
                        self.wait(lambda:getattr(self.a,'_pending_bracket_composition',None) is None)
                    if repeated:pair=self.a.BRACKET_STYLES[(self.a.BRACKET_STYLES.index(pair)+1)%5]
                    self.assertEqual(self.text(),'前'+pair[0]+'入力中の文字'+pair[1]+'後')
                    self.assertEqual(self.editor.index('insert'),self.editor.index(f'1.0+{len(self.text())-1}c'))
                    with patch.object(ime_watch,'composition_active',return_value=False):self.press(state)
                    self.assertIn('入力中の文字',self.text());self.assertTrue(self.a._cancel_bracket_cycle())
                    self.assertEqual(self.text(),'前入力中の文字後')

    def test_alt_places_a_pair_after_the_commit(self):
        # 2026-10-22 うにさん「Alt+F2を　カーソル位置に括弧を置く」: converting text is committed first
        active=[True]
        def commit(hwnd):
            self.root.after(30,lambda:(self.editor.insert('insert','入力中'),active.__setitem__(0,False)));return True
        with patch.object(ime_watch,'composition_active',side_effect=lambda hwnd:active[0]),\
             patch.object(ime_watch,'read_composition',return_value={'comp':'入力中'}),\
             patch.object(ime_watch,'complete_composition',side_effect=commit):
            self.press(0x20000);self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertEqual(self.text(),'前入力中（）後')
        self.assertEqual(self.editor.index('insert'),'1.5')

    def test_ascii_pending_text_uses_halfwidth_parens(self):
        active=[True]
        def commit(hwnd):self.editor.insert('insert','abc');active[0]=False;return True
        with patch.object(ime_watch,'composition_active',side_effect=lambda hwnd:active[0]),\
             patch.object(ime_watch,'read_composition',return_value={'comp':'abc'}),\
             patch.object(ime_watch,'complete_composition',side_effect=commit):
            self.press(4);self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertEqual(self.text(),'前(abc)後')

    def test_tab_switch_does_not_wrap_unrelated_text(self):
        with patch.object(ime_watch,'composition_active',return_value=True),\
             patch.object(ime_watch,'read_composition',return_value={'comp':'文字'}),\
             patch.object(ime_watch,'complete_composition',return_value=True):
            self.press();self.tab={};self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertEqual(self.text(),'前後')

    def test_result_readback_waits_for_native_delivery_without_second_insertion(self):
        for synchronous in (False,True):
            for state in (0,4,1):
                with self.subTest(synchronous=synchronous,state=state):
                    self.editor.delete('1.0','end');self.editor.insert('1.0','前後')
                    self.editor.mark_set('insert','1.1');self.a._forget_bracket_cycle()
                    active=[True]
                    def complete(expected):
                        def native_insert():
                            self.editor.insert('insert','入力中の文字');active[0]=False
                        if synchronous:native_insert()
                        else:self.root.after(30,native_insert)
                        return True,(('入力中の文字',''),)
                    self.a._ime_result_events=SimpleNamespace(complete_current=complete)
                    self.a._drain_ime_result_events=lambda:False
                    with patch.object(ime_watch,'composition_active',side_effect=lambda hwnd:active[0]), \
                         patch.object(ime_watch,'read_composition',return_value={'comp':'入力中の文字'}):
                        self.press(state)
                        if not synchronous:self.assertEqual(self.text(),'前後')
                        self.wait(lambda:self.a._pending_bracket_composition is None)
                    pair={0:('（','）'),4:('（','）'),1:('『','』')}[state]
                    self.assertEqual(self.text(),'前'+pair[0]+'入力中の文字'+pair[1]+'後')
                    self.assertTrue(self.a._cancel_bracket_cycle())
                    self.assertEqual(self.text(),'前入力中の文字後')
        self.a._ime_result_events=None

    def test_readback_alone_never_inserts_or_wraps_unreceived_text(self):
        self.a._ime_result_events=SimpleNamespace(
            complete_current=lambda expected:(True,(('入力中',''),)))
        with patch.object(ime_watch,'composition_active',return_value=True), \
             patch.object(ime_watch,'read_composition',return_value={'comp':'入力中'}):
            self.press();self.assertEqual(self.text(),'前後')
            self.a._pending_bracket_composition['until']=0
            self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertEqual(self.text(),'前後')
        self.assertIsNone(self.a._live_bracket_cycle())

    def test_native_receiver_scope_and_cleanup(self):
        self.a._pending_bracket_composition={'tab':self.tab}
        self.a._start_bracket_ime_chars()
        tag=self.a._bracket_ime_tag
        self.assertEqual(self.editor.bindtags()[0],tag)
        self.assertEqual(self.a._on_bracket_ime_char('-1','v'),'')
        self.assertEqual(self.a._on_bracket_ime_char('-3','\x1b'),'')
        self.tab={}
        self.assertEqual(self.a._on_bracket_ime_char('-3','a'),'')
        self.assertEqual(self.text(),'前後')
        self.a._clear_pending_bracket_composition()
        self.assertNotIn(tag,self.editor.bindtags())
        self.assertEqual(self.a._on_bracket_ime_char('-3','a'),'')

    def test_late_reading_updates_keep_cycle_but_changed_document_does_not(self):
        doc=self.a._input_document=SimpleNamespace(owner='tab',text=self.text())
        self.a._on_change=lambda *args:setattr(doc,'text',self.text())
        with patch.object(ime_watch,'composition_active',return_value=False):
            self.press(4)
            self.a._work_epoch+=1
            self.assertIsNotNone(self.a._live_bracket_cycle())
            self.press(4)
            self.assertEqual(self.text(),'前「」後')
            doc.text+='追加'
            self.assertIsNone(self.a._live_bracket_cycle())

    @unittest.skipUnless(ime_watch.HAS_SUPPORT,'Windows only')
    def test_physical_bracket_key_reaches_tk_without_a_hook(self):
        # 2026-10-22: brackets moved to F2 and no PC-wide keyboard hook
        # (native_f5) takes the key first; Tk's own binding receives it.
        self.root.geometry('1x1+10000+10000');self.root.deiconify()
        self.editor.focus_force();self.root.update()
        received=[];self.editor.bind('<F2>',lambda e:received.append(e.keysym))
        user=ctypes.WinDLL('user32');user.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
        user.PostMessageW(self.editor.winfo_id(),0x100,0x71,0x003c0001)
        user.PostMessageW(self.editor.winfo_id(),0x101,0x71,0xc03c0001)
        self.wait(lambda:bool(received))
        self.assertEqual(received,['F2'])

if __name__=='__main__':unittest.main()
