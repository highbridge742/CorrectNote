# -*- coding: utf-8 -*-
import tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import tkinter as tk
import app
from settings import Settings
from scroll_inertia import ScrollInertia,install


class InertiaTimingTests(unittest.TestCase):
    def setUp(self):
        self.now=0.;self.jobs={};self.number=0;self.owner=object();self.pixels=[]
        def after(delay,call):
            self.number+=1;self.jobs[self.number]=(self.now+delay/1000.,call);return self.number
        root=SimpleNamespace(after=after,after_cancel=lambda key:self.jobs.pop(key,None))
        self.scroll=ScrollInertia(root,lambda n:self.pixels.append(n),lambda:self.owner,lambda:self.now)

    def advance(self,seconds):
        end=self.now+seconds
        while self.jobs:
            key,(at,call)=min(self.jobs.items(),key=lambda item:item[1][0])
            if at>end:break
            self.now=at;del self.jobs[key];call()
        self.now=end

    def test_wheel_glides_then_stops_at_requested_distance_with_one_timer(self):
        self.scroll.wheel(80);self.assertEqual(len(self.jobs),1)
        self.advance(.024);self.assertTrue(0<sum(self.pixels)<80)
        self.advance(.8);self.assertEqual(sum(self.pixels),80)
        self.assertFalse(self.jobs);self.assertIsNone(self.scroll.kind)

    def test_repeated_notches_add_and_reversal_drops_old_direction(self):
        self.scroll.wheel(50);self.advance(.024);self.scroll.wheel(50)
        self.assertEqual(len(self.jobs),1);self.advance(.8);self.assertEqual(sum(self.pixels),100)
        self.scroll.wheel(100);self.advance(.024);before=len(self.pixels)
        self.scroll.wheel(-30);self.advance(.8)
        self.assertTrue(all(value<0 for value in self.pixels[before:]))
        self.assertEqual(sum(self.pixels[before:]),-30)

    def test_other_tab_cancellation_and_close_do_not_replay_old_ticks(self):
        self.scroll.wheel(100);callback=next(iter(self.jobs.values()))[1]
        self.owner=object();self.advance(.2);self.assertEqual(self.pixels,[])
        self.scroll.wheel(50);self.scroll.cancel();callback();self.advance(.2)
        self.assertEqual(self.pixels,[])
        self.scroll.wheel(50);self.scroll.close();self.advance(.5)
        self.assertEqual(self.pixels,[]);self.assertFalse(self.jobs)

    def test_drag_release_uses_recent_velocity_and_slow_or_paused_drag_stops(self):
        for delta in (0,10,10,10):
            self.scroll.sample_drag(delta);self.advance(.02)
        self.scroll.release_drag();self.assertEqual(self.scroll.kind,'drag')
        self.advance(.8);self.assertTrue(40<sum(self.pixels)<70)
        self.pixels=[]
        for delta in (0,10,10):self.scroll.sample_drag(delta);self.advance(.02)
        self.advance(.15);self.scroll.release_drag();self.assertFalse(self.jobs)
        for delta in (0,.2,.2):self.scroll.sample_drag(delta);self.advance(.03)
        self.scroll.release_drag();self.assertFalse(self.jobs)

    def test_drag_direction_change_and_document_end_do_not_leave_a_tail(self):
        for delta in (0,20,20,-10,-10):self.scroll.sample_drag(delta);self.advance(.02)
        self.scroll.release_drag();self.advance(.8)
        self.assertTrue(self.pixels and all(value<0 for value in self.pixels))
        self.scroll.scroll=lambda pixels:False
        self.scroll.wheel(300);self.advance(.012);self.assertFalse(self.jobs)

    def test_two_saved_switches_default_on_and_remain_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'synthetic-settings.json');settings=Settings(path)
            self.assertTrue(settings.get('wheel_inertia'));self.assertTrue(settings.get('right_drag_inertia'))
            settings.set('wheel_inertia',False);settings.save();loaded=Settings(path)
            self.assertFalse(loaded.get('wheel_inertia'));self.assertTrue(loaded.get('right_drag_inertia'))


class InertiaTkTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.geometry('700x400');self.errors=[]
        self.root.report_callback_exception=lambda *exc:self.errors.append(exc)
        a=self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);a.root=self.root
        self.owner={};a.session=SimpleNamespace(current=lambda:self.owner)
        a.settings=Settings();a._syncing=False
        for name in ('editor','result_view'):
            widget=tk.Text(self.root,width=20,height=15,wrap='none',undo=True)
            widget.pack(side='left',fill='both',expand=True)
            widget.insert('1.0',''.join('合成行%03d\n'%n for n in range(100)))
            widget.edit_reset();setattr(a,name,widget)
        a.editor_gutter=tk.Canvas(self.root);a.result_gutter=tk.Canvas(self.root)
        a.editor_gutter.sync_yview=Mock();a.result_gutter.sync_yview=Mock()
        a.v_scrollbar=SimpleNamespace(set=Mock());a._update_header_visibility=Mock()
        a._release_navigation_padding=Mock();a._layout_is_unified=lambda:False
        a._get_line_height=lambda:20;a._sync_partner_to_line=lambda src,dst:dst.yview_moveto(src.yview()[0])
        self.root.update();a.editor.yview_moveto(.3);a.result_view.yview_moveto(.3)
        self.before=a.editor.get('1.0','end-1c');self.controller=install(a)

    def tearDown(self):
        self.controller.close();self.root.destroy();self.assertFalse(self.errors)

    def pump(self,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:self.root.update();time.sleep(.004)

    def test_real_pixels_are_smooth_synchronized_and_do_not_edit_or_add_undo(self):
        before=self.a.editor.yview()[0];self.a._wheel_scroll(4)
        self.pump(.035);middle=self.a.editor.yview()[0]
        self.pump(.8);after=self.a.editor.yview()[0]
        self.assertTrue(before<middle<after)
        self.assertAlmostEqual(after,self.a.result_view.yview()[0],places=5)
        self.assertEqual(self.a.editor.get('1.0','end-1c'),self.before)
        with self.assertRaises(tk.TclError):self.a.editor.edit_undo()
        self.assertIsNone(self.controller.job)

    def test_option_off_moves_immediately_and_key_binding_break_still_cancels(self):
        self.a.settings.set('wheel_inertia',False);before=self.a.editor.yview()[0]
        self.a._wheel_scroll(2);self.assertGreater(self.a.editor.yview()[0],before)
        self.assertIsNone(self.controller.job)
        self.a.settings.set('wheel_inertia',True);self.a._wheel_scroll(20)
        self.a.editor.bind('<Right>',lambda event:'break')
        self.a.editor.focus_force();self.root.update()
        self.a.editor.event_generate('<Right>');self.root.update()
        at=self.a.editor.yview();self.pump(.2);self.assertEqual(self.a.editor.yview(),at)
        self.assertIsNone(self.controller.job)


class InertiaAppBoundaryTests(unittest.TestCase):
    def test_only_right_drag_without_overview_or_tab_wheel_can_coast(self):
        for button, enabled, overview, tab_wheel, expected in (
                (3,True,False,False,True), (1,True,False,False,False),
                (None,True,False,False,False), (3,False,False,False,False),
                (3,True,True,False,False), (3,True,False,True,False)):
            with self.subTest(button=button,enabled=enabled,overview=overview,tab_wheel=tab_wheel):
                a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);pane=object()
                a._drag=dict(widget=pane,mode='scroll');a._tab_wheel_used=tab_wheel
                a._overview=object() if overview else None
                a._overview_exit=Mock();a._finish_tab_wheel_gesture=Mock()
                a._restore_pointer=Mock();a._scroll_cursor_restore=Mock()
                a._scroll_inertia=Mock();a.settings=SimpleNamespace(get=lambda key:enabled)
                self.assertTrue(a._drag_release(SimpleNamespace(num=button),pane))
                self.assertEqual(a._scroll_inertia.release_drag.call_count,int(expected))
                self.assertEqual(a._scroll_inertia.cancel.call_count,int(not expected))
                self.assertIsNone(a._drag)

    def test_option_off_preserves_legacy_fractional_notch_rounding(self):
        a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.settings=SimpleNamespace(get=lambda key:False);a._scroll_inertia=Mock()
        a._on_wheel_units=Mock(return_value='break')
        for delta,expected in ((-.5,0),(.5,1),(-1,-1),(1,1)):
            self.assertEqual(a._wheel_scroll(delta),'break')
            a._on_wheel_units.assert_called_with(expected)
        a._scroll_inertia.wheel.assert_not_called()

    def test_native_menu_entry_cancels_even_when_it_returns_break(self):
        a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a._scroll_inertia=Mock();a._native_menu_active=True
        self.assertEqual(a._post_menu_bar(SimpleNamespace(widget=object())),'break')
        a._scroll_inertia.cancel.assert_called_once()


if __name__=='__main__':unittest.main()
