# -*- coding: utf-8 -*-
"""Wheel navigation through actual bindings in an isolated, non-learning app."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app,analysis_worker
    from session import new_tab
    assert (Path.cwd()/'.ui-test-isolated').is_file()
    sources=['最初の資料です。','次の資料です。','最後の資料です。']
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text=s) for s in sources]),ensure_ascii=False),encoding='utf-8')
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf-8')
    root=tk.Tk();root.withdraw();root.attributes('-alpha',0);a=None;errors=[];cases=[]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    def until(predicate,seconds=120):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update();assert not errors,errors
            if predicate():return
            time.sleep(.005)
        raise AssertionError(('timeout',getattr(a,'_analyze_last_error',None)))
    def done():
        return (not a._foreground_analysis_pending() and a._analyze_text==a.editor_source_text()
            and a._analyze_pos>=len(a._analyze_todo) and a._analyze_dependencies==analysis_worker.state_key(a)
            and a._analyze_work==analysis_work_app.token(a))
    def emit(widget,event,wheel_time=None,**values):
        values.update(x=4,y=4,rootx=widget.winfo_rootx()+4,rooty=widget.winfo_rooty()+4)
        if wheel_time is not None:
            with patch.object(app,'time',Mock(wraps=time,monotonic=Mock(return_value=wheel_time))):
                widget.event_generate(event,**values)
        else:
            if event=='<MouseWheel>':time.sleep(.31)
            widget.event_generate(event,**values)
        root.update();assert not errors,errors
    def expect(name,condition):
        assert condition,name;cases.append(name)
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None):
        try:
            a=app.CorrectNoteApp(root);root.attributes('-alpha',0);root.deiconify();until(done)
            revision=a.store.revision()
            label=a._tab_widgets[0]['label'];clock=time.monotonic()
            emit(label,'<MouseWheel>',delta=-120,wheel_time=clock)
            expect('first_notch_moves_immediately',a.session.active==1)
            emit(label,'<MouseWheel>',delta=-120,wheel_time=clock+.02)
            expect('rapid_repeat_waits',a.session.active==1)
            emit(label,'<MouseWheel>',delta=120,wheel_time=clock+.04)
            expect('reverse_rebound_ignored',a.session.active==1)
            emit(label,'<MouseWheel>',delta=1080,wheel_time=clock+.10)
            expect('large_reverse_rebound_ignored',a.session.active==1)
            emit(label,'<MouseWheel>',delta=-120,wheel_time=clock+.151)
            expect('previous_interval_now_waits',a.session.active==1)
            emit(label,'<MouseWheel>',delta=-120,wheel_time=clock+.201)
            expect('held_rotation_moves_after_interval',a.session.active==2)
            emit(label,'<MouseWheel>',delta=-1080,wheel_time=clock+.402)
            expect('large_delta_moves_only_one',a.session.active==0)
            emit(label,'<MouseWheel>',delta=-60,wheel_time=clock+.61)
            expect('excess_not_carried_to_next_rotation',a.session.active==0)
            emit(label,'<MouseWheel>',delta=60,wheel_time=clock+.62)
            expect('fine_reverse_rebound_ignored',a.session.active==0)
            emit(label,'<MouseWheel>',delta=-60,wheel_time=clock+.63)
            expect('rebound_keeps_valid_partial_rotation',a.session.active==1)
            emit(label,'<MouseWheel>',delta=120,wheel_time=clock+.64)
            expect('second_reverse_rebound_ignored',a.session.active==1)
            emit(label,'<MouseWheel>',delta=60,wheel_time=clock+.929)
            expect('reverse_waits_before_guard_boundary',a.session.active==1)
            emit(label,'<MouseWheel>',delta=60,wheel_time=clock+.931)
            expect('ignored_rebound_does_not_accumulate',a.session.active==1)
            emit(label,'<MouseWheel>',delta=60,wheel_time=clock+.95)
            expect('intentional_fine_reverse_moves',a.session.active==0)
            emit(label,'<MouseWheel>',delta=-120,wheel_time=clock+1.10)
            expect('opposite_rebound_also_ignored',a.session.active==0)
            emit(label,'<MouseWheel>',delta=-120,wheel_time=clock+1.251)
            expect('intentional_full_reverse_moves',a.session.active==1)
            emit(label,'<MouseWheel>',delta=-120,wheel_time=clock+1.40)
            expect('suppressed_rotation_not_applied',a.session.active==1)
            emit(label,'<MouseWheel>',delta=-120,wheel_time=clock+1.452)
            expect('suppression_does_not_extend_interval',a.session.active==2)
            emit(label,'<MouseWheel>',delta=-60,wheel_time=clock+1.66)
            emit(label,'<MouseWheel>',delta=60,wheel_time=clock+1.76)
            expect('intentional_reversal_clears_partial',a.session.active==2)
            emit(label,'<MouseWheel>',delta=60,wheel_time=clock+1.78)
            expect('intentional_reversal_accumulates',a.session.active==1)
            with patch.object(a,'_on_wheel_units'):
                emit(a.editor,'<MouseWheel>',delta=-120)
            a._switch_tab(0);until(done)
            with patch.object(a,'_open_dropdown') as result_menu,patch.object(a,'_open_editor_dropdown') as editor_menu:
                emit(a.editor,'<ButtonPress-3>')
                emit(a.editor,'<MouseWheel>',delta=-60,state=0x0400)
                expect('right_hold_half_notch_waits',a.session.active==0)
                emit(a.editor,'<ButtonRelease-3>',state=0x0400)
                expect('partial_right_wheel_release_quiet',not result_menu.called and not editor_menu.called)
            with patch.object(a,'_on_wheel_units'):
                emit(a.editor,'<MouseWheel>',delta=-120)
            emit(label,'<MouseWheel>',delta=-60)
            expect('ordinary_scroll_clears_partial_tab_wheel',a.session.active==0)
            emit(label,'<MouseWheel>',delta=-60)
            expect('tab_wheel_restarts_after_body_scroll',a.session.active==1)
            # All tab surfaces use actual Tk wheel bindings, including the close glyph.
            for key in ('label','frame','close'):
                widget=a._tab_widgets[0][key];start=a.session.active
                emit(widget,'<MouseWheel>',delta=-120)
                expect('tab_'+key+'_down',a.session.active==(start+1)%3)
                emit(widget,'<MouseWheel>',delta=120)
                expect('tab_'+key+'_up',a.session.active==start)
            for widget in (a.tab_bar,a._tab_viewport,a._tab_plus):
                start=a.session.active;emit(widget,'<MouseWheel>',delta=-120)
                expect('tab_strip_down_'+str(widget),a.session.active==(start+1)%3)
            a._switch_tab(2);emit(a._tab_widgets[2]['label'],'<MouseWheel>',delta=-120)
            expect('right_wrap',a.session.active==0)
            emit(a._tab_widgets[0]['label'],'<MouseWheel>',delta=120)
            expect('left_wrap',a.session.active==2)
            emit(a._tab_widgets[0]['label'],'<MouseWheel>',delta=0)
            expect('zero_delta',a.session.active==2)
            # Right-held wheel never scrolls the destination or opens candidates on release.
            for pane in (a.editor,a.result_view,a.editor_gutter,a.result_gutter):
                a._switch_tab(0);until(done)
                with patch.object(a,'_on_wheel_units') as scroll,patch.object(a,'_open_dropdown') as result_menu,patch.object(a,'_open_editor_dropdown') as editor_menu:
                    emit(pane,'<ButtonPress-3>')
                    time.sleep(.31);clock=time.monotonic()
                    emit(pane,'<MouseWheel>',delta=-120,state=0x0400,wheel_time=clock)
                    expect('right_hold_down_'+str(pane),a.session.active==1)
                    emit(pane,'<MouseWheel>',delta=120,state=0x0400,wheel_time=clock+.02)
                    expect('right_hold_rebound_ignored_'+str(pane),a.session.active==1)
                    emit(pane,'<MouseWheel>',delta=120,state=0x0400)
                    expect('right_hold_reverse_after_pause_'+str(pane),a.session.active==0)
                    emit(pane,'<MouseWheel>',delta=-120,state=0x0400)
                    expect('right_hold_forward_after_reverse_'+str(pane),a.session.active==1)
                    emit(pane,'<MouseWheel>',delta=120,state=0x0400)
                    expect('right_hold_second_reverse_after_pause_'+str(pane),a.session.active==0)
                    emit(pane,'<ButtonRelease-3>',state=0x0400)
                    expect('right_release_quiet_'+str(pane),not result_menu.called and not editor_menu.called and not scroll.called and not getattr(a,'_tab_wheel_used',False))
                    released=time.monotonic()
                    emit(pane,'<MouseWheel>',delta=-120,state=0x0400,wheel_time=released+.02)
                    expect('stale_right_state_rebound_ignored_'+str(pane),a.session.active==0)
                    emit(a._tab_widgets[0]['label'],'<MouseWheel>',delta=-120,wheel_time=released+.04)
                    expect('released_rebound_ignored_'+str(pane),a.session.active==0)
                    time.sleep(.10)
                    emit(a._tab_widgets[0]['label'],'<MouseWheel>',delta=-120)
                    expect('new_rotation_after_release_guard_'+str(pane),a.session.active==1)
            # Missing release notification: the first buttonless tab wheel
            # starts the release guard instead of undoing the last tab switch.
            a._switch_tab(0);until(done)
            emit(a.editor,'<ButtonPress-3>')
            time.sleep(.31);clock=time.monotonic()
            emit(a.editor,'<MouseWheel>',delta=-120,state=0x0400,wheel_time=clock)
            expect('lost_release_start',a.session.active==1)
            emit(a._tab_widgets[0]['label'],'<MouseWheel>',delta=120,wheel_time=clock+.40)
            expect('lost_release_rebound_ignored',a.session.active==1)
            emit(a._tab_widgets[0]['label'],'<MouseWheel>',delta=120,wheel_time=clock+.701)
            expect('lost_release_guard_expires',a.session.active==0)
            emit(a.editor,'<ButtonRelease-3>',state=0)
            # A fresh press must reset a gesture whose release happened outside the window.
            a._switch_tab(0);until(done)
            emit(a.editor,'<ButtonPress-3>')
            emit(a.editor,'<MouseWheel>',delta=-120,state=0x0400)
            expect('lost_release_first_direction',a.session.active==1)
            # Tk cannot synthesize a second press without a matching release;
            # enter the same fresh-press handler directly to model an OS-lost release.
            a._drag_press(type('Press',(),{'x':4,'y':4})(),a.editor,False)
            expect('fresh_press_clears_used',not a._tab_wheel_used)
            time.sleep(.31)
            emit(a.editor,'<MouseWheel>',delta=120,state=0x0400)
            expect('fresh_press_resets_stale_direction',a.session.active==0)
            emit(a.editor,'<ButtonRelease-3>',state=0x0400)
            # A normal right click still reaches the same tab menu, on release.
            label=a._tab_widgets[1]['label']
            with patch.object(a,'_make_dropdown') as menu:
                emit(label,'<ButtonPress-3>');expect('tab_menu_waits_for_release',not menu.called)
                emit(label,'<ButtonRelease-3>');expect('ordinary_tab_menu',menu.call_count==1)
                menu.reset_mock();emit(label,'<ButtonPress-3>')
                emit(label,'<MouseWheel>',delta=-120,state=0x0400)
                emit(label,'<ButtonRelease-3>',state=0x0400)
                expect('tab_right_wheel_no_menu',not menu.called)
            # A suppressed reverse notch in a fresh right press is still a wheel gesture.
            time.sleep(.40);a._switch_tab(0);until(done)
            first=a._tab_widgets[0]['label']
            emit(first,'<ButtonPress-3>')
            emit(first,'<MouseWheel>',delta=-120,state=0x0400)
            expect('quick_new_gesture_first_step',a.session.active==1)
            emit(first,'<ButtonRelease-3>',state=0x0400)
            released=time.monotonic();second=a._tab_widgets[1]['label']
            with patch.object(a,'_make_dropdown') as menu:
                emit(second,'<ButtonPress-3>')
                emit(second,'<MouseWheel>',delta=120,state=0x0400,wheel_time=released+.02)
                expect('quick_new_gesture_reverse_suppressed',a.session.active==1)
                emit(second,'<ButtonRelease-3>',state=0x0400)
                expect('suppressed_wheel_has_no_tab_menu',not menu.called)
            with patch.object(a,'_on_wheel_units') as scroll:
                start=a.session.active;emit(a.editor,'<MouseWheel>',delta=-120)
                expect('ordinary_body_wheel',a.session.active==start and scroll.call_args.args==(1,))
            # Focus-routed Windows wheel still recognizes a pointer over the strip.
            start=a.session.active;label=a._tab_widgets[0]['label']
            a.editor.event_generate('<MouseWheel>',delta=-120,rootx=label.winfo_rootx()+4,rooty=label.winfo_rooty()+4)
            root.update();expect('focus_routed_hover',a.session.active==(start+1)%3)
            button=a._menu_buttons[0];start=a.session.active
            emit(button,'<MouseWheel>',delta=-120,state=0x0400)
            expect('main_controls_right_wheel',a.session.active==(start+1)%3)
            emit(button,'<ButtonRelease-3>',state=0x0400)
            expect('main_controls_release_quiet',not getattr(a,'_tab_wheel_used',False))
            # A fresh physical press on a top control starts a new interval.
            time.sleep(.40);a._switch_tab(0);until(done)
            emit(button,'<ButtonPress-3>')
            control_start=time.monotonic()
            emit(button,'<MouseWheel>',delta=-120,state=0x0400,wheel_time=control_start)
            expect('quick_control_first_step',a.session.active==1)
            emit(button,'<ButtonRelease-3>',state=0x0400)
            emit(button,'<ButtonPress-3>')
            emit(button,'<MouseWheel>',delta=-120,state=0x0400,wheel_time=control_start+.04)
            expect('quick_control_new_press_first_step',a.session.active==2)
            emit(button,'<ButtonRelease-3>',state=0x0400)
            a._switch_tab(0);until(done)
            with patch.object(a,'_on_wheel_units') as scroll:
                emit(a.editor,'<ButtonPress-3>')
                emit(a.editor,'<Button-5>',state=0x0400)
                expect('right_button5_switches_tab',a.session.active==1)
                emit(a.editor,'<Button-4>',state=0x0400)
                expect('right_button4_rebound_ignored',a.session.active==1)
                emit(a.editor,'<ButtonRelease-3>',state=0x0400)
                expect('button_wheel_does_not_scroll',not scroll.called)
                emit(a._tab_widgets[0]['label'],'<Button-4>')
                expect('button_wheel_release_rebound_ignored',a.session.active==1)
                guard=a._tab_wheel_release_guard
                expect('button_wheel_release_guard_started',guard is not None)
                time.sleep(max(0.0,guard[0]+.35-time.monotonic()))
                emit(a._tab_widgets[0]['label'],'<Button-4>')
                expect('button_wheel_release_guard_expires',a.session.active==0)
            with patch.object(a,'_on_wheel_units') as scroll:
                emit(a.editor,'<Button-5>')
                expect('ordinary_button5_scrolls',scroll.call_args.args==(3,))
                expect('ordinary_button5_keeps_tab',a.session.active==0)
            time.sleep(.31)
            emit(a._tab_widgets[0]['label'],'<Button-5>')
            expect('tab_button5_switches',a.session.active==1)
            # A slow tab switch can delay the second delivery of one notch.
            time.sleep(.31);a._switch_tab(0);until(done)
            label=a._tab_widgets[0]['label'];clock=time.monotonic()
            emit(label,'<MouseWheel>',delta=-120,time=51000,wheel_time=clock)
            emit(label,'<Button-5>',time=51010,wheel_time=clock+.45)
            expect('delayed_dual_wheel_one_switch',a.session.active==1)
            # A second physical notch 250 ms later must still move a tab.
            time.sleep(.31);a._switch_tab(0);until(done)
            label=a._tab_widgets[0]['label'];clock=time.monotonic()
            emit(label,'<MouseWheel>',delta=-120,time=52000,wheel_time=clock)
            emit(label,'<Button-5>',time=52250,wheel_time=clock+.25)
            expect('separate_physical_notch_switches',a.session.active==2)
            # Some devices deliver one notch in both Tk wheel formats.
            time.sleep(.31);a._switch_tab(0);until(done)
            label=a._tab_widgets[0]['label'];clock=time.monotonic()
            emit(label,'<MouseWheel>',delta=-120,wheel_time=clock)
            emit(label,'<Button-5>',wheel_time=clock+.01)
            expect('dual_tab_wheel_one_switch',a.session.active==1)
            time.sleep(.31);a._switch_tab(0);until(done)
            with patch.object(a,'_on_wheel_units') as scroll:
                emit(a.editor,'<ButtonPress-3>')
                clock=time.monotonic()
                emit(a.editor,'<MouseWheel>',delta=-120,state=0x0400,wheel_time=clock)
                emit(a.editor,'<Button-5>',state=0x0400,wheel_time=clock+.01)
                expect('dual_right_wheel_one_switch',a.session.active==1)
                emit(a.editor,'<Button-4>',state=0x0400,wheel_time=clock+.02)
                expect('dual_right_reverse_ignored',a.session.active==1)
                emit(a.editor,'<ButtonRelease-3>',state=0x0400)
                expect('dual_right_does_not_scroll',not scroll.called)
            time.sleep(.31)
            button=a._menu_buttons[0];start=a.session.active
            emit(button,'<ButtonPress-3>')
            emit(button,'<Button-5>',state=0x0400)
            expect('control_right_button5_switches',a.session.active==(start+1)%3)
            emit(button,'<Button-4>',state=0x0400)
            expect('control_right_button4_rebound_ignored',a.session.active==(start+1)%3)
            emit(button,'<ButtonRelease-3>',state=0x0400)
            expect('control_button_release_quiet',not getattr(a,'_tab_wheel_used',False))
            time.sleep(.31);a._switch_tab(0);until(done)
            label=a._tab_widgets[0]['label']
            with patch.object(a,'_make_dropdown') as menu:
                emit(label,'<ButtonPress-3>')
                emit(a.editor,'<Button-5>',state=0x0400)
                expect('cross_widget_right_button5_switches',a.session.active==1)
                emit(a._menu_buttons[0],'<ButtonRelease-3>',state=0x0400)
                expect('cross_widget_release_quiet',not getattr(a,'_tab_wheel_used',False) and not menu.called)
                released=time.monotonic()
                emit(label,'<Button-4>',wheel_time=released+.02)
                expect('cross_widget_release_rebound_ignored',a.session.active==1)
            until(done)
            a._set_layout_unified();until(done)
            start=a.session.active
            emit(a.editor,'<ButtonPress-3>')
            emit(a.editor,'<MouseWheel>',delta=-120,state=0x0400)
            emit(a.editor,'<ButtonRelease-3>',state=0x0400)
            expect('unified_right_wheel',a.session.active==(start+1)%3 and a._dropdown is None)
            until(done)
            a.editor.mark_set('insert','1.0');a.toggle_pick_mode()
            mode=a._pick_mode;start=a.session.active
            emit(a.editor,'<MouseWheel>',delta=-120,state=0x0400)
            emit(a.editor,'<ButtonRelease-3>',state=0x0400)
            expect('quote_mode_survives_wheel',bool(mode) and a._pick_mode==mode and a.session.active==(start+1)%3)
            a._end_pick_mode();until(done)
            a._capture_session()
            expect('sources_preserved',[t['text'] for t in a.session.tabs]==sources)
            tabs=a.session.tabs;active=a.session.active
            try:
                a.session.tabs=[tabs[active]];a.session.active=0
                emit(a._tab_widgets[0]['label'],'<MouseWheel>',delta=-120)
                emit(a._tab_widgets[0]['label'],'<MouseWheel>',delta=120)
                expect('one_tab_no_change',a.session.active==0)
            finally:a.session.tabs=tabs;a.session.active=active
            expect('learning_stopped',a.store.revision()==revision)
            print('TAB_WHEEL_REPORT '+json.dumps(dict(passed=True,cases=cases),ensure_ascii=False),flush=True)
        finally:
            if a is not None:a._on_close()
            else:root.destroy()

def parent():
    source=Path(__file__).resolve().parent
    from bundle_manifest import NAMES
    with tempfile.TemporaryDirectory(prefix='correctnote-tab-wheel-') as folder:
        dest=Path(folder)
        for p in source.iterdir():
            if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
        (dest/'.ui-test-isolated').touch()
        result=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',timeout=300)
        print(result.stdout,flush=True)
        assert result.returncode==0,result.stdout
        report=json.loads(next(line[len('TAB_WHEEL_REPORT '):] for line in result.stdout.splitlines() if line.startswith('TAB_WHEEL_REPORT ')))
        assert report['passed'];return report

class TabWheelTkTests(unittest.TestCase):
    def test_wheel_tabs_and_right_release_use_existing_switch(self):
        report=parent();self.assertGreaterEqual(len(report['cases']),20)

if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:unittest.main()
