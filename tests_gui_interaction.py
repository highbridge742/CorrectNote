# -*- coding: utf-8 -*-
"""Exercise actual Tk bindings and popups in an isolated synthetic application."""
import json,sys,time,traceback,unittest
from pathlib import Path

def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    from types import SimpleNamespace
    import app,analysis_work_app,analysis_worker
    assert (Path.cwd()/'.ui-test-isolated').is_file()
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf-8')
    root=tk.Tk();root.withdraw();errors=[];cases=[];a=None
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    def until(predicate,seconds=65):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update()
            assert not errors,errors
            if predicate():return
            time.sleep(.004)
        raise AssertionError(('timeout',getattr(a,'_async_request',None),getattr(a,'_analyze_last_error',None)))
    def done():
        return (a._warmup is None and getattr(a,'_async_context_scope',None) is None
            and getattr(a,'_analyze_text',None)==a.editor_source_text()
            and a._analyze_pos>=len(a._analyze_todo)
            and a._analyze_dependencies==analysis_worker.state_key(a)
            and a._analyze_work==analysis_work_app.token(a))
    def check(name,fn):
        try:
            fn();assert not errors,errors
            cases.append(dict(name=name,ok=True))
        except Exception:
            cases.append(dict(name=name,ok=False,error=traceback.format_exc()))
        finally:
            a._pick_mode=None;a._drag=None
            a._close_dropdown();a._f2_cycle=None
            a.editor.tag_remove('sel','1.0','end');a.result_view.tag_remove('sel','1.0','end')
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None):
        try:
            a=app.CorrectNoteApp(root);until(done)
            source='寒ぃ日だ。\nよいでしょぅか。\n'+ '\n'.join('確認用の文章です。' for _ in range(35))
            a.editor.insert('1.0',source);a._analyze();until(done)
            # The real app's widget B1 binding must remove stale hover tags.
            def drag_hover():
                a._pick_mode='f1'
                for widget in (a.editor,a.result_view):
                    widget.tag_add('hover','1.0','1.2')
                    widget.tag_add('sel','1.1','1.4')
                    # Observe the app binding before Text's native drag updates
                    # selection coordinates (the hidden window has no layout boxes).
                    observed=[];tags=widget.bindtags();probe='InteractionDragProbe'
                    edge=tags.index(str(widget))+1
                    widget.bindtags(tags[:edge]+(probe,)+tags[edge:])
                    widget.bind_class(probe,'<B1-Motion>',lambda e:observed.append(
                        (tuple(widget.tag_ranges('hover')),tuple(widget.tag_ranges('sel')))))
                    try:widget.event_generate('<B1-Motion>',x=35,y=20,state=256)
                    finally:
                        widget.bindtags(tags);widget.unbind_class(probe,'<B1-Motion>')
                    assert observed and not observed[-1][0],(str(widget),observed)
                    assert observed[-1][1],'App drag binding removed selection'
                a._pick_mode=None
            check('quote_drag_widget_binding',drag_hover)
            def left_margin():
                w=a.result_view;a._pick_mode=None
                with patch.object(a,'_on_wheel_units') as wheel,patch.object(a,'_scroll_cursor_hide') as hide,patch.object(a,'_edge_warp'):
                    w.event_generate('<ButtonPress-1>',x=600,y=20)
                    w.event_generate('<B1-Motion>',x=600,y=65,state=256)
                    assert not (a._drag or {}).get('mode')=='scroll',a._drag
                    assert not wheel.called and not hide.called
            check('left_result_margin_selects_without_pan',left_margin)
            def search_transfer():
                a.open_find_dialog(False);a._find_query.set('検索の文字')
                a.open_find_dialog(True)
                assert a._find_replacement.get()=='検索の文字',a._find_replacement.get()
                assert a._find_query.get()=='検索の文字','Query must remain usable for replacement'
                a._find_replacement.set('別の置換内容');a.open_find_dialog(True)
                assert a._find_replacement.get()=='別の置換内容','Repeated Ctrl+H lost edited replacement'
                a._close_find_dialog()
            check('search_to_replace_transfer_once',search_transfer)
            def split_input_actions():
                original=next(u for u in a._editor_line_units(1) if u.get('detail'))
                menus=[]
                def capture(items,*args,**kwargs):menus.append(items);a._dropdown=Mock()
                with patch.object(a,'_make_dropdown',capture),patch.object(a,'_reject_correction') as reject:
                    for selected in (False,True):
                        a._close_dropdown();a._f2_cycle=None
                        a.editor.mark_set('insert',f"1.0+{original['end']}c")
                        if selected:a.editor.tag_add('sel',f"1.0+{original['start']}c",f"1.0+{original['end']}c")
                        a._on_f2_candidates(SimpleNamespace(widget=a.editor,keysym='F2',state=0))
                        labels=[label for label,cb in menus[-1]]
                        assert '― 自動補正 ―' in labels,labels
                        assert any('「寒ぃ」は今後直さない' in label for label in labels),labels
                        cb=next(cb for label,cb in menus[-1] if '元の入力に戻す' in label)
                        cb();reject.assert_called_with('ぃ','い')
                        assert '  い' not in labels,'One-character correction became a whole-word replacement'
                        a.editor.tag_remove('sel','1.0','end')
                    # Right-click goes through press/release bindings, no F2 selection helper.
                    a._close_dropdown();a._f2_cycle=None
                    with patch.object(a,'_editor_unit_under_pointer',return_value=(1,original)):
                        a.editor.event_generate('<ButtonPress-3>',x=20,y=20)
                        a.editor.event_generate('<ButtonRelease-3>',x=20,y=20)
                    assert '― 自動補正 ―' in [label for label,cb in menus[-1]]
            check('split_input_f2_and_right_click_correction_actions',split_input_actions)
            def popup_highlight():
                for w,opener,units in ((a.editor,a._open_editor_dropdown,a._editor_line_units(1)),
                        (a.result_view,a._open_dropdown,a.line_units[0])):
                    a._close_dropdown();unit=next(u for u in units if u.get('detail'))
                    w.tag_add('hover',f"1.0+{unit['start']}c",f"1.0+{unit['end']}c")
                    opener(SimpleNamespace(x_root=0,y_root=0),1,unit)
                    w.event_generate('<Leave>');root.update_idletasks()
                    assert a._dropdown is not None
                    assert w.tag_ranges('candidate_focus'),'Popup word lost its background after Leave'
                    a._close_dropdown()
                    assert not w.tag_ranges('candidate_focus'),'Popup highlight survived close'
            check('candidate_popup_keeps_word_highlight',popup_highlight)
            def registered_control_keys():
                from tests_tk_keys import deliver_key
                for widget in (a.editor,a.result_view):
                    original=widget.get('1.0','end-1c')
                    try:
                        with analysis_work_app.display_update(a):
                            widget.config(state='normal');widget.replace('1.0','end-1c','前😀半\n途中😀\n終端😀\n\n次の塊\n末尾')
                        if widget is a.result_view:widget.config(state='disabled')
                        widget.mark_set('insert','1.0+3c')
                        deliver_key(widget,'<Control-Down>','Down',40,4)
                        assert widget.get('3.0','insert')=='終端😀',widget.index('insert')
                        deliver_key(widget,'<Control-Down>','Down',40,4)
                        assert widget.index('insert')=='5.3',widget.index('insert')
                        widget.mark_set('insert','1.1')
                        deliver_key(widget,'<Control-Shift-Down>','Down',40,5)
                        assert (widget.index('sel.first'),widget.index('sel.last'))==('1.1','3.1')
                        deliver_key(widget,'<Control-Up>','Up',38,4)
                        assert widget.index('insert')=='1.1' and not widget.tag_ranges('sel')
                    finally:
                        with analysis_work_app.display_update(a):
                            widget.config(state='normal');widget.replace('1.0','end-1c',original)
                        if widget is a.result_view:widget.config(state='disabled')
            check('registered_ctrl_keys_use_block_edges_and_selection',registered_control_keys)
            def registered_alt_keys():
                from tests_tk_keys import deliver_key
                a.bookmarks={1,3,5}
                for widget in (a.editor,a.result_view):
                    a.editor.mark_set('insert','1.0');widget.mark_set('insert','3.0')
                    deliver_key(widget,'<Alt-Down>','Down',40,0x20000)
                    assert widget.index('insert')=='5.0',widget.index('insert')
                    deliver_key(widget,'<Alt-Up>','Up',38,0x20000)
                    assert widget.index('insert')=='3.0',widget.index('insert')
            check('registered_alt_keys_use_focused_pane_bookmarks',registered_alt_keys)
            print('INTERACTION_REPORT '+json.dumps(cases,ensure_ascii=False),flush=True)
            assert all(c['ok'] for c in cases),[c for c in cases if not c['ok']]
        finally:
            if a is not None:a._on_close()
            else:root.destroy()

def run_interaction():
    import tempfile,subprocess,shutil
    from bundle_manifest import NAMES
    source=Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='correctnote-interaction-') as folder:
        dest=Path(folder)
        for p in source.iterdir():
            if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
        (dest/'.ui-test-isolated').touch()
        r=subprocess.run([sys.executable,'-X','utf8',str(dest/'tests_gui_interaction.py'),'--interaction-child'],cwd=dest,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',timeout=150)
        print(r.stdout,flush=True)
        if r.returncode:raise AssertionError('Interaction child failed')
        return json.loads(next(line[len('INTERACTION_REPORT '):] for line in r.stdout.splitlines() if line.startswith('INTERACTION_REPORT ')))

class InteractionTkTests(unittest.TestCase):
    def test_actual_mouse_bindings_and_candidate_windows(self):
        cases=run_interaction();self.assertEqual(len(cases),7)

if __name__=='__main__':
    if '--interaction-child' in sys.argv:child()
    else:unittest.main()