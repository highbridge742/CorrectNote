# -*- coding: utf-8 -*-
"""Regression tests for pending colors, correction actions and tab/toolbar layout."""
import json
import sys
import time
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tkinter as tk
import app


def correction(before='資科を整理します。', after='資料を整理します。'):
    return dict(original=before, corrected=after, changed=True,
                details=[('資科', '資料', 'noun')], original_spans=[(0,2)],
                spans=[(0,2)], odd_spans=[])


def unit(text='資科'):
    return dict(start=0, end=len(text), text=text, base=text, reading='しか',
                prev='', next='', kind='plain', detail=None)


class PendingColorTkTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        a=self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root=self.root;a.editor=tk.Text(self.root);a.result_view=tk.Text(self.root)
        a.store=Mock();a.store._tokenize_fn=lambda text:[];a.choices=Mock();a.choices.lookup.return_value=None
        a._syncing=False;a._units_cache={};a._suspect_units_cache={}
        a.editor_gutter=Mock();a.result_gutter=Mock()
        a._sync_partner_to_line=Mock();a._paint_whitespace=Mock()
        a._units_are_pending=lambda:False;a._known_kana_word=lambda text:False
        a._clear_f2_target=Mock();a._dropdown=None;a.line_texts=[];a._input_document=object()
        a.settings={'show_odd':True,'unified_autofix':False};a.decisions=Mock()
        a._layout_is_unified=lambda:False;a._update_status=Mock();a.status=Mock()
        a._schedule_whitespace_paint=Mock()
        a.line_results=[correction(),correction('資科を読みます。','資料を読みます。')]
        for r in a.line_results:
            u=dict(unit('資料'),kind='fixed',detail=r['details'][0])
            a._units_cache[r['original'],r['corrected']]=(r['corrected'],[u])
        a.editor.insert('1.0','\n'.join(r['original'] for r in a.line_results))
        a._refresh_after_analysis(learn=False)

    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root')

    def test_unchanged_colors_are_not_removed_and_readded(self):
        a=self.a
        with patch.object(a.editor,'tag_remove',wraps=a.editor.tag_remove) as remove, \
             patch.object(a.result_view,'tag_remove',wraps=a.result_view.tag_remove) as result_remove:
            a._refresh_after_analysis(learn=False)
        self.assertFalse(any(c.args[0] in ('suspect','odd') for c in remove.call_args_list))
        self.assertFalse(any(c.args[0] in ('fixed','chosen') for c in result_remove.call_args_list))

    def test_pending_reanalysis_keeps_input_and_result_colors(self):
        a=self.a;before=a.result_view.get('1.0','end-1c')
        expected=tuple(map(str,a.editor.tag_ranges('suspect')))
        a.line_results=[a._blank_result(r['original']) for r in a.line_results]
        a._units_cache={};a._suspect_units_cache={};a._units_are_pending=lambda:True
        a._refresh_after_analysis(learn=False)
        self.assertEqual(a.result_view.get('1.0','end-1c'),before)
        self.assertEqual(tuple(map(str,a.editor.tag_ranges('suspect'))),expected)
        self.assertTrue(a.result_view.tag_ranges('fixed'))
        self.assertTrue(all(r.get('pending') for r in a.line_results))
        self.assertFalse(any(r.get('_display_only') for r in a.line_results))
        self.assertFalse(a._units_cache)
        a._build_editor_units()
        self.assertFalse(a._suspect_units_cache)
        a._layout_is_unified=lambda:True
        a.settings['unified_autofix']=True
        a._autofix_live_records=lambda:[]
        self.assertFalse(a._apply_unified_autofix())

    def test_new_document_does_not_borrow_pending_colors(self):
        a=self.a;a._input_document=object()
        a.line_results=[a._blank_result(r['original']) for r in a.line_results]
        a._refresh_after_analysis(learn=False)
        self.assertFalse(a.editor.tag_ranges('suspect'))
        self.assertFalse(a.result_view.tag_ranges('fixed'))

    def test_inserted_line_moves_existing_display_without_recoloring_it(self):
        a=self.a
        a.editor.insert('1.0','新しい行。\n')
        a.line_results=[a._blank_result(line) for line in a.editor.get('1.0','end-1c').split('\n')]
        a._units_cache={};a._units_are_pending=lambda:True
        a._refresh_after_analysis(learn=False)
        self.assertEqual(a.result_view.get('1.0','end-1c'),'新しい行。\n資料を整理します。\n資料を読みます。')
        self.assertEqual(tuple(map(str,a.result_view.tag_ranges('fixed'))),('2.0','2.2','3.0','3.2'))

    def test_changed_row_updates_tags_without_erasing_the_other_row(self):
        a=self.a
        a.editor.delete('1.0','1.2');a.editor.insert('1.0','資料')
        r=dict(a._blank_result('資料を整理します。'));r.pop('pending',None)
        a.line_results[0]=r;a._units_cache[r['original'],r['corrected']]=(r['original'],[])
        with patch.object(a.result_view,'tag_remove',wraps=a.result_view.tag_remove) as remove:
            a._refresh_after_analysis(learn=False)
        self.assertEqual(tuple(map(str,a.result_view.tag_ranges('fixed'))),('2.0','2.2'))
        self.assertFalse(any(c.args[1:] == ('1.0','end') for c in remove.call_args_list))

    def test_unified_unapplied_and_spanless_split_corrections_have_actions(self):
        a=self.a
        a._editor_changes=[];a._unit_surroundings=lambda *args:[]
        a._odd_run_candidates=lambda *args:[];a._halfwidth_candidates=lambda *args:[]
        a.autofix_span_at=lambda *args:None;a._odd_menu_items=lambda *args:[]
        a._analysis_items=lambda *args,**kwargs:[];a.dict_index=Mock();a.context_vec=None
        a._reject_correction=Mock()
        with patch.object(app,'build_candidates',return_value=[]),patch.object(app,'symbol_candidates',return_value=[]):
            for unified,spanless in ((False,True),(True,False),(True,True)):
                with self.subTest(unified=unified,spanless=spanless):
                    a._layout_is_unified=lambda:unified
                    r=correction()
                    if spanless:r.pop('original_spans')
                    a.line_results[0]=r
                    items=a._editor_dropdown_items(1,unit(),[])
                    self.assertIn('― 自動補正 ―',[label for label,callback in items])
                    callback=next(callback for label,callback in items if '元の入力に戻す' in label)
                    callback();a._reject_correction.assert_called_with('資科','資料')

    def test_unchanged_word_next_to_correction_has_no_automatic_actions(self):
        a=self.a
        items=a._result_correction_menu_items(1,dict(start=3,end=5,text='整理'),source=True)
        self.assertEqual(items,[])

    def test_unicode_result_difference_preserves_neighbor_tags(self):
        a=self.a
        r=correction('😀資科を整理します。','😀資料を整理します。')
        r['original_spans']=[(1,3)];r['spans']=[(1,3)]
        a.line_results=[r];u=dict(unit('資料'),start=1,end=3,kind='fixed',detail=r['details'][0])
        a._units_cache[r['original'],r['corrected']]=(r['corrected'],[u])
        a._render_corrected()
        self.assertEqual(a.result_view.get('1.0+1c','1.0+3c'),'資料')
        expected=tuple(map(str,a.result_view.tag_ranges('fixed')))
        a._render_corrected()
        self.assertEqual(tuple(map(str,a.result_view.tag_ranges('fixed'))),expected)


    def test_cached_ranges_follow_unicode_edits_and_external_tag_changes(self):
        import ui_projection
        w=self.a.editor
        for before,span,old_end,new_prefix,expected in (
                ('前資科後',(1,3),1,'😀','資科'),
                ('😀A資科後',(2,4),2,'甲乙丙','丙資')):
            w.delete('1.0','end');w.insert('1.0',before)
            ranges=[(f'1.0+{span[0]}c',f'1.0+{span[1]}c')]
            ui_projection.update_tag(w,'suspect',ranges,app._stable_text_index)
            w.replace('1.0',f'1.0+{old_end}c',new_prefix)
            for remove in (False,True):
                if remove:w.tag_remove('suspect','1.0','end')
                ui_projection.update_tag(w,'suspect',ranges,app._stable_text_index)
                left,right=w.tag_ranges('suspect')
                self.assertEqual(w.get(app._stable_text_index(w,left),app._stable_text_index(w,right)),expected)

    def test_existing_unified_autofix_colors_are_not_removed(self):
        a=self.a
        a._autofix_pane=lambda w=None:(a.editor,None,None)
        a._autofix_live_records=lambda w=None:[({'spans':[(0,2,'fixed','資科')]},1)]
        a._repaint_autofix_tags()
        with patch.object(a.editor,'tag_remove',wraps=a.editor.tag_remove) as remove:
            a._repaint_autofix_tags()
        self.assertFalse(remove.called)



def child():
    import analysis_work_app as work,analysis_worker
    from session import new_tab
    assert (Path.cwd()/'.ui-test-isolated').is_file()
    source='寒ぃ日だ。\n'+'\n'.join('よいでしょぅか。' for _ in range(9))
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False,show_odd=True,unified_autofix=False)),encoding='utf-8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text=source),new_tab(text='別の文書です。')]),ensure_ascii=False),encoding='utf-8')
    root=tk.Tk();root.withdraw();a=None;errors=[];reports=[]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    def until(predicate,seconds=100):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update();assert not errors,errors
            if predicate():return
            time.sleep(.004)
        raise AssertionError(('timeout',getattr(a,'_analyze_last_error',None)))
    def done():
        return (a._warmup is None and getattr(a,'_async_context_scope',None) is None
                and a._analyze_text==a.editor_source_text()
                and a._analyze_pos>=len(a._analyze_todo)
                and a._analyze_dependencies==analysis_worker.state_key(a)
                and a._analyze_work==work.token(a))
    def hover(button, enter):
        sequence='<Enter>' if enter else '<Leave>'
        assert button.bind(sequence),'Missing bookmark pointer binding'
        button.event_generate(sequence)
    def check(name,fn):
        try:fn();reports.append(dict(name=name,ok=True))
        except Exception:reports.append(dict(name=name,ok=False,error=traceback.format_exc()))
        print('CHECK '+json.dumps(reports[-1],ensure_ascii=False),flush=True)
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *args:None):
        try:
            a=app.CorrectNoteApp(root);until(done)
            until(lambda:a._bg is None and a._bg_job is None and not a._bg_texts)
            def toolbar():
                # Crossing events require mapped widgets. Keep this test window invisible.
                root.overrideredirect(True);root.attributes('-alpha',0)
                root.deiconify();root.update()
                texts=[]
                for widget in a.pick_mode_btn.master.winfo_children():
                    try:texts.append(widget.cget('text'))
                    except tk.TclError:pass
                assert '開く' not in texts and '保存' not in texts,texts
                assert not any('行番号ダブルクリック' in t for t in texts),texts
                a.editor.yview_moveto(0);a._update_header_visibility(0)
                before=a.editor_header.cget('text')
                for button in (a.bookmark_prev_btn,a.bookmark_next_btn):
                    hover(button,True)
                    shown=a.editor_header.cget('text')
                    assert 'ダブルクリック' in shown and 'Alt+↑' in shown and 'Alt+↓' in shown,shown
                    a._update_header_visibility(.4);assert a.editor_header.cget('text')==shown
                    hover(button,False);a._update_header_visibility(0)
                    assert a.editor_header.cget('text')==before
                a._set_layout_unified();until(done)
                a._start_pick_mode(False)
                quote=a.editor_header.cget('text')
                hover(a.bookmark_prev_btn,True)
                assert 'Alt+↑' in a.editor_header.cget('text')
                hover(a.bookmark_prev_btn,False)
                assert a.editor_header.cget('text')==quote
                a._end_pick_mode();a._set_layout_split();until(done)
            check('toolbar_buttons_and_hover_help',toolbar)
            root.withdraw()
            def cached():
                expected=a.editor.tag_ranges('suspect');assert expected
                a._switch_tab(1);until(done)
                a._switch_tab(0)
                assert a.editor.tag_ranges('suspect'),'First returned frame lost colors'
                assert a.result_view.tag_ranges('fixed'),'First returned result lost colors'
                assert done(),'Completed cache was deferred to idle'
            check('cached_tab_color_visible_before_idle',cached)
            def unified_menu():
                a._set_layout_unified();until(done)
                assert not a.unified_autofix_on()
                menus=[]
                def capture(items,*args,**kw):menus.append(items);a._dropdown=Mock()
                with patch.object(a,'_make_dropdown',capture):
                    a.editor.mark_set('insert','1.2');a._f2_cycle=None
                    a._on_f2_candidates(SimpleNamespace(widget=a.editor,keysym='F2',state=0))
                    assert menus and any(label=='― 自動補正 ―' for label,cb in menus[-1]),menus
                a._close_dropdown();a._set_layout_split();until(done)
            check('unified_f2_unapplied_auto_correction',unified_menu)
            def pending():
                samples=[];refresh=a._refresh_after_analysis
                def inspect(*args,**kwargs):
                    value=refresh(*args,**kwargs)
                    if any(r.get('pending') for r in a.line_results):
                        samples.append(bool(a.editor.tag_nextrange('suspect','2.0','2.end')))
                    return value
                with patch.object(a,'_refresh_after_analysis',inspect):
                    a._reject_correction('寒ぃ','寒い');until(done)
                assert samples and all(samples),samples
                assert not a.editor.tag_nextrange('suspect','1.0','1.end')
            check('judgment_reanalysis_keeps_other_rows_colored',pending)
            def resized_tabs():
                a._stop_background_tabs()
                tabs=a.session.tabs;active=a.session.active
                try:
                    a.session.tabs=[new_tab(text='',title='文書'+str(i)) for i in range(16)]
                    a.session.active=13;a._refresh_tab_bar()
                    viewport=a._tab_viewport;viewport.pack_forget()
                    for width,index in ((900,13),(430,13),(300,15),(430,0),(600,8)):
                        a.session.active=index;viewport.place(x=16,y=40,width=width,height=29)
                        a._refresh_tab_bar();root.update_idletasks()
                        frame=a._tab_widgets[index]['frame'];left=viewport.canvasx(0)
                        assert left-2<=frame.winfo_x(),(width,index,left,frame.winfo_x())
                        assert frame.winfo_x()+frame.winfo_width()<=left+width+2,(width,index,left,frame.winfo_x(),frame.winfo_width())
                finally:a.session.tabs=tabs;a.session.active=active
            check('selected_tab_visible_after_width_changes',resized_tabs)
            print('REFRESH_REPORT '+json.dumps(reports,ensure_ascii=False),flush=True)
            assert all(r['ok'] for r in reports),reports
        finally:
            if a is not None:a._on_close()
            else:root.destroy()


class RefreshApplicationTkTests(unittest.TestCase):
    def test_registered_controls_pending_colors_and_cached_tabs(self):
        import tempfile,shutil,subprocess
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-refresh-') as folder:
            dest=Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):
                    shutil.copy2(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            run=subprocess.run([sys.executable,'-X','utf8',str(dest/'tests_gui_refresh.py'),'--child'],
                cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',timeout=240)
            print(run.stdout,flush=True)
            self.assertEqual(run.returncode,0,run.stdout)


if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:unittest.main()

