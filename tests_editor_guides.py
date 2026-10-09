import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import app
from editor_guides import FLASH_COLOR,FLASH_MS


class EditorGuidesTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.geometry('620x280+0+0')
        a=self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);a.root=self.root
        self.owner={};a.session=SimpleNamespace(current=lambda:self.owner)
        a._schedule_session_save=Mock()
        for name in ('editor','result_view'):
            w=tk.Text(self.root,width=1,height=1,wrap='word',font=('Consolas',13),undo=True,
                insertbackground='#123456',insertofftime=415,spacing1=2,spacing3=4)
            w.pack(side='left',fill='both',expand=True)
            w.insert('1.0','長い行です。'*18+'\n次の行\n最後の本文\n\n\n')
            w.edit_reset();w.mark_set('insert','2.1');setattr(a,name,w)
        a.editor_gutter=SimpleNamespace(redraw=Mock());a.result_gutter=SimpleNamespace(redraw=Mock())
        self.root.update();a._install_editor_guides();self.guides=a._editor_guides
        self.guides.can_flash=lambda event:True
        a.editor.focus_force();self.root.update()
    def tearDown(self):
        self.guides.close();self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','guides','root')
    def key(self,sequence):
        self.a.editor.event_generate(sequence);self.root.update()
    def wait_restore(self):
        done=tk.BooleanVar(master=self.root,value=False)
        self.root.after(FLASH_MS+30,lambda:done.set(True));self.root.wait_variable(done)
    def test_rulers_stay_on_logical_rows_and_toggle_independently(self):
        w=self.a.editor;text=w.get('1.0','end-1c');selection=tuple(w.tag_ranges('sel'))
        self.assertTrue(self.a._toggle_ruler());self.root.update_idletasks()
        line=self.guides.lines[w,2];fixed_y=line.winfo_y()
        w.mark_set('insert','1.30');self.a._sync_cursor_line(w,force=True);self.root.update_idletasks()
        self.assertEqual(line.winfo_y(),fixed_y)
        self.assertTrue(self.a._toggle_ruler());self.root.update_idletasks()
        self.assertEqual(self.guides.ruler_rows(),{1,2})
        self.assertEqual(self.guides.lines[w,1].winfo_y(),w.dlineinfo('1.end')[1]+w.dlineinfo('1.end')[3]-1)
        w.mark_set('insert','1.65');self.a._sync_cursor_line(w);self.root.update_idletasks()
        self.assertEqual(line.winfo_y(),fixed_y)
        self.assertFalse(self.a._toggle_ruler());self.root.update_idletasks()
        self.assertEqual(self.guides.ruler_rows(),{2});self.assertTrue(self.guides.enabled)
        self.assertNotIn((w,1),self.guides.lines)
        self.assertEqual(w.get('1.0','end-1c'),text);self.assertEqual(tuple(w.tag_ranges('sel')),selection)
        with self.assertRaises(tk.TclError):w.edit_undo()
        w.mark_set('insert','2.0');self.a._sync_cursor_line(w)
        self.assertFalse(self.a._toggle_ruler());self.root.update_idletasks()
        self.assertFalse(self.guides.enabled);self.assertFalse(self.guides.lines)

    def test_rulers_share_logical_rows_across_panes_and_hide_outside_view(self):
        a=self.a;self.a._toggle_ruler();self.root.update_idletasks()
        a.result_view.focus_force();a.result_view.mark_set('insert','3.0')
        a._sync_cursor_line(a.result_view,force=True);self.root.update_idletasks()
        self.assertTrue(self.guides.lines[a.editor,2].winfo_manager())
        self.assertTrue(self.guides.lines[a.result_view,2].winfo_manager())
        self.a._toggle_ruler();self.root.update_idletasks()
        self.assertEqual(self.guides.ruler_rows(),{2,3})
        a.result_view.insert('end','追加\n'*80);a.result_view.yview_moveto(1)
        self.guides.queue_draw();self.root.update()
        self.assertFalse(self.guides.lines[a.result_view,2].winfo_manager())
        self.assertTrue(self.guides.lines[a.editor,2].winfo_manager())
        a.result_view.yview_moveto(0);self.guides.queue_draw();self.root.update()
        self.assertTrue(self.guides.lines[a.result_view,2].winfo_manager())

    def test_tab_rows_restore_without_following_insert_and_wrap_reflows(self):
        w=self.a.editor;first=self.owner
        self.a._toggle_ruler();w.mark_set('insert','3.0');self.a._sync_cursor_line(w)
        self.a._toggle_ruler();self.root.update_idletasks()
        self.assertEqual(first['ruler_rows'],[2,3])
        self.owner={'ruler_rows':[1]};self.a._sync_cursor_line(w,force=True);self.root.update_idletasks()
        self.assertEqual(self.guides.ruler_rows(),{1});self.assertNotIn((w,2),self.guides.lines)
        self.root.geometry('900x360+0+0');self.root.update()
        self.assertEqual(self.guides.lines[w,1].winfo_y(),w.dlineinfo('1.end')[1]+w.dlineinfo('1.end')[3]-1)
        self.owner=first;self.a._sync_cursor_line(w,force=True);self.root.update_idletasks()
        self.assertEqual(self.guides.ruler_rows(),{2,3});self.assertNotIn((w,1),self.guides.lines)

    def test_navigation_flash_is_solid_then_restores_actual_settings(self):
        w=self.a.editor;before=w.index('insert');self.key('<KeyPress-Right>')
        self.assertNotEqual(w.index('insert'),before)
        self.assertEqual(w.cget('insertbackground'),FLASH_COLOR);self.assertEqual(int(w.cget('insertofftime')),0)
        self.assertIsNotNone(self.guides._restore_job)
        self.wait_restore();self.assertEqual(w.cget('insertbackground'),'#123456')
        self.assertEqual(int(w.cget('insertofftime')),415);self.assertIsNone(self.guides._restore_job)
    def test_repeat_focus_tab_and_close_own_the_flash_timer(self):
        w=self.a.editor;self.key('<KeyPress-Right>');job=self.guides._restore_job
        self.key('<KeyPress-Right>');self.assertNotEqual(self.guides._restore_job,job)
        self.a.result_view.focus_force();self.root.update()
        self.assertEqual(w.cget('insertbackground'),'#123456');self.assertIsNone(self.guides._restore_job)
        w.focus_force();self.root.update();self.key('<KeyPress-Left>')
        self.owner=object();self.a._sync_cursor_line(w,force=True)
        self.assertEqual(w.cget('insertbackground'),'#123456');self.assertIsNone(self.guides._restore_job)
        self.key('<KeyPress-Left>');self.assertIsNotNone(self.guides._restore_job)
        self.guides.close();self.assertEqual(w.cget('insertbackground'),'#123456')
        for name in ('_key_job','_draw_job','_restore_job'):self.assertIsNone(getattr(self.guides,name))
        self.assertNotIn(self.guides.tag,w.bindtags())
    def test_ime_char_no_move_and_widget_break_do_not_steal_navigation(self):
        w=self.a.editor;w.mark_set('insert','1.0');self.key('<KeyPress-Left>')
        self.assertIsNone(self.guides._flash)
        self.guides._key(SimpleNamespace(widget=w,keysym='Right',char='あ'))
        self.assertIsNone(self.guides._key_job)
        with patch('ime_watch.composition_active',return_value=True):
            self.assertFalse(self.a._guide_navigation_allowed(SimpleNamespace(widget=w,keysym='Right',char='',state=0,keycode=39)))
        w.bind('<Control-Right>',lambda e:(w.mark_set('insert','2.0'),'break')[1])
        self.key('<Control-KeyPress-Right>');self.assertEqual(w.index('insert'),'2.0')
        self.assertEqual(w.cget('insertbackground'),FLASH_COLOR)
        self.guides.restore();self.key('<Shift-KeyPress-Right>')
        self.assertTrue(w.tag_ranges('sel'));self.assertEqual(w.cget('insertbackground'),FLASH_COLOR)
    def test_end_rule_is_two_thin_lines_without_row_or_undo_changes(self):
        a=self.a;before={w:w.dlineinfo('4.0') for w in (a.editor,a.result_view)}
        a._configure_end_rule_tag();a._paint_end_rule();self.root.update_idletasks()
        for w in (a.editor,a.result_view):
            first=w._end_rule_line;second=w._end_rule_second_line
            self.assertEqual(first.winfo_height(),1);self.assertEqual(second.winfo_height(),1)
            self.assertEqual(first.winfo_y()-second.winfo_y(),3)
            self.assertEqual(w.dlineinfo('4.0'),before[w])
            with self.assertRaises(tk.TclError):w.edit_undo()

    def test_theme_during_flash_keeps_the_new_color_and_original_blink(self):
        w=self.a.editor;self.key('<KeyPress-Right>')
        self.assertEqual(w.cget('insertbackground'),FLASH_COLOR)
        w.configure(insertbackground='#789abc')
        self.guides.theme_changed()
        self.assertEqual(w.cget('insertbackground'),'#789abc')
        self.assertEqual(int(w.cget('insertofftime')),415)
        self.assertIsNone(self.guides._restore_job)
        self.key('<KeyPress-Right>');self.guides.restore()
        self.assertEqual(w.cget('insertbackground'),'#789abc')

    def test_ruler_forwards_its_pointer_events_to_the_editor(self):
        w=self.a.editor;self.a._toggle_ruler();self.root.update_idletasks()
        line=self.guides.lines[w,2];seen=[]
        w.bind('<ButtonPress-1>',lambda e:(seen.append(('click',e.x,e.y,e.state)),'break')[1])
        w.bind('<MouseWheel>',lambda e:(seen.append(('wheel',e.x,e.y,e.delta,e.state)),'break')[1])
        x,y=20,line.winfo_y()
        event=SimpleNamespace(x_root=w.winfo_rootx()+x,y_root=w.winfo_rooty()+y,state=4,delta=-120)
        self.assertEqual(self.guides._forward(event,'<MouseWheel>',w),'break')
        self.assertEqual(seen.pop(),('wheel',x,y,-120,4))
        self.assertEqual(self.guides._forward(event,'<ButtonPress-1>',w),'break')
        self.assertEqual(seen.pop(),('click',x,y,4))
        self.assertFalse(line.winfo_manager());self.assertIs(self.root.focus_get(),w)

    def test_drag_and_release_delivered_to_the_line_keep_pane_handlers(self):
        w=self.a.editor;self.a._toggle_ruler();self.root.update_idletasks()
        line=self.guides.lines[w,2];seen=[];before=w.get('1.0','end-1c')
        for seq in ('<B1-Motion>','<ButtonRelease-1>','<B3-Motion>','<ButtonRelease-3>'):
            w.bind(seq,lambda e,s=seq:(seen.append((s,e.x,e.y,e.state)),'break')[1])
        for button,mask in ((1,256),(3,1024)):
            self.guides.draw();self.root.update_idletasks()
            line.event_generate('<ButtonPress-%d>'%button,x=20,y=0)
            # An implicit grab may deliver these to the original line even
            # after it has been hidden. Test that exact delivery destination.
            line.event_generate('<B%d-Motion>'%button,x=120,y=0,state=mask)
            line.event_generate('<ButtonRelease-%d>'%button,x=120,y=0,state=mask)
        self.assertEqual([event[0] for event in seen],
            ['<B1-Motion>','<ButtonRelease-1>','<B3-Motion>','<ButtonRelease-3>'])
        self.assertEqual(w.get('1.0','end-1c'),before)
        with self.assertRaises(tk.TclError):w.edit_undo()

    def test_left_drag_selection_matches_direct_text_delivery(self):
        w=self.a.editor;self.a._toggle_ruler();self.root.update_idletasks()
        line=self.guides.lines[w,2]
        x=line.winfo_rootx()-w.winfo_rootx();y=line.winfo_rooty()-w.winfo_rooty()
        line.event_generate('<ButtonPress-1>',x=8,y=0,time=1000)
        line.event_generate('<B1-Motion>',x=100,y=0,state=256,time=1040)
        line.event_generate('<ButtonRelease-1>',x=100,y=0,state=256,time=1080)
        forwarded=tuple(map(str,w.tag_ranges('sel')))
        self.assertTrue(forwarded)
        w.tag_remove('sel','1.0','end')
        w.event_generate('<ButtonPress-1>',x=x+8,y=y,time=2000)
        w.event_generate('<B1-Motion>',x=x+100,y=y,state=256,time=2040)
        w.event_generate('<ButtonRelease-1>',x=x+100,y=y,state=256,time=2080)
        self.assertEqual(tuple(map(str,w.tag_ranges('sel'))),forwarded)

if __name__=='__main__':unittest.main()
