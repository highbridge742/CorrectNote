# -*- coding: utf-8 -*-
"""Exercise the requested editor features through a real isolated application."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest


def child():
    import tkinter as tk
    import tkinter.font as tkfont
    from unittest.mock import Mock, patch
    import app
    import analysis_work_app as work
    import analysis_worker
    from session import new_tab
    from tests_tk_keys import deliver_key
    here = Path.cwd().resolve()
    assert (here / '.ui-features-test-isolated').is_file()
    assert Path(app.__file__).resolve().parent == here
    texts = ['一行目\n前😀置換対象後\n三行目\n四行目', '引用する資料\n別の資料']
    (here / 'settings.json').write_text(json.dumps(dict(layout='split',
        input_method='kana', input_method_auto=False, editor_font_size=16,
        unified_autofix=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0,
        tabs=[new_tab(text=t) for t in texts]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); root.withdraw(); a = None; errors = []
    root.report_callback_exception = lambda *exc: errors.append(''.join(traceback.format_exception(*exc)))
    def until(predicate, seconds=100):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update()
            assert not errors, errors
            if predicate(): return
            time.sleep(.005)
        raise AssertionError('Application did not settle: '+str(getattr(a, '_analyze_last_error', None)))
    def done():
        return (not a._foreground_analysis_pending()
                and a._analyze_text == a.editor_source_text()
                and a._analyze_pos >= len(a._analyze_todo)
                and a._analyze_dependencies == analysis_worker.state_key(a)
                and a._analyze_work == work.token(a))
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
            patch.object(app.CorrectNoteApp, '_learn_now', lambda *args: None):
        try:
            a = app.CorrectNoteApp(root); root.withdraw(); until(done)
            assert tkfont.Font(font=a.editor.cget('font')).actual('size') == 16
            assert a.pick_mode_btn.cget('text') == 'クリックして引用'
            assert a.pick_mode_btn.bind('<Enter>') and a.pick_mode_btn.bind('<Leave>')
            assert 'フォント' in [b.cget('text') for b in a._menu_buttons]
            a._choose_editor_font(size=18); root.update()
            a._overview_fonts(5); root.update()
            a._overview_fonts(None); root.update()
            assert tkfont.Font(font=a.editor.cget('font')).actual('size') == 18

            w = a.editor
            w.mark_set('insert', '2.0+2c')
            deliver_key(w, '<Shift-space>', 'space', 32, state=1)
            deliver_key(w, '<Shift-Down>', 'Down', 40, state=1)
            assert w.get('sel.first', 'sel.last') == '前😀置換対象後\n三行目'
            deliver_key(w, '<Shift-Up>', 'Up', 38, state=1)
            assert w.get('sel.first', 'sel.last') == '前😀置換対象後'
            deliver_key(w, '<KeyRelease-Shift_L>', 'Shift_L', 16, state=1, event_type=3)

            w.tag_remove('sel', '1.0', 'end')
            w.tag_add('sel', '2.0+2c', '2.0+6c')
            selected = w.get('sel.first', 'sel.last')
            origin = a.session.current()
            with patch.object(root, 'focus_get', return_value=a.editor):
                deliver_key(a.editor, '<F1>', 'F1', 112)
            assert a._pick_mode is None
            assert root.clipboard_get() == selected
            a.pick_mode_btn.invoke()
            assert a._pick_mode == 'f1'
            deliver_key(a.editor, '<Control-Tab>', 'Tab', 9, state=4); until(done)
            assert a.editor.cget('cursor') == 'xterm'
            assert a.result_view.cget('cursor') == 'xterm'
            assert a.session.active == 1
            a.editor.mark_set('insert','1.0')
            deliver_key(a.editor, '<<LineStart>>', 'Home', 36)
            # Withdrawn windows have no display-line width. Use the actual
            # logical text-edge shortcut rather than native display-line End.
            deliver_key(a.editor, '<Control-Shift-Right>', 'Right', 39, state=5)
            assert a.editor.get('sel.first','sel.last') == '引用する資料', repr(a.editor.get('sel.first','sel.last'))
            deliver_key(a.editor, '<KeyPress>', 'Return', 13)
            assert a.session.current() is origin
            assert a.editor_source_text().rstrip('\n') == '一行目\n前😀引用する資料後\n三行目\n四行目'
            until(done)

            a.open_find_dialog(False)
            a._find_query.set('資料'); a._find_regex.set(False)
            a._do_find_all_tabs()
            until(lambda: a._all_tab_search_job is None)
            assert len(a._all_tab_hits) == 3
            a._all_tab_tree.selection_set('3')
            a._open_all_tab_hit(); until(done)
            assert a.session.active == 1
            assert a.editor.get('sel.first', 'sel.last') == '資料'
            a._close_all_tab_results(); a._close_find_dialog()

            path = here / 'synthetic-source.txt'
            raw = '保存する資料\r\n次の行\n\n'.encode('cp932')
            path.write_bytes(raw)
            a._open_paths([str(path)]); until(done)
            a._refresh_file_format_menu()
            assert a._encoding_var.get() == 'cp932'
            assert a._write_to_file(str(path))
            assert path.read_bytes() == raw
            a._choose_file_encoding('utf-8-sig')
            assert a._dirty
            a._switch_tab(0); until(done)
            a._switch_tab(2); until(done)
            a._refresh_file_format_menu()
            assert a._encoding_var.get() == 'utf-8-sig'
            assert a._write_to_file(str(path))
            assert path.read_bytes() == b'\xef\xbb\xbf' + '保存する資料\r\n次の行\n\n'.encode()
            for layout,automatic in (('split',False),('unified',False),('unified',True)):
                a.settings.set('unified_autofix',automatic)
                a._choose_layout(layout);until(done)
                for button,expression,answer in ((False,'12+3*4','24'),(True,'１２÷４','3')):
                    a._replace_editor_text('前😀後');until(done)
                    w=a.editor;w.tag_remove('sel','1.0','end');w.mark_set('insert','1.0+2c')
                    if button:a.pick_mode_btn.invoke()
                    else:deliver_key(w,'<Control-c>','c',67,state=4)
                    assert a._pick_mode=='f1' and a._pick_calculate
                    for char in expression:
                        deliver_key(w,'<KeyPress>',char,0,char=char)
                        deliver_key(w,'<KeyRelease>',char,0,event_type=3,char=char)
                    until(done)
                    source=a.editor_source_text()
                    deliver_key(w,'<KeyPress>','KP_Enter' if button else 'Return',13,char='\r')
                    until(done)
                    assert a._pick_mode is None
                    expected='前😀'+answer+'後'
                    assert a.line_results[0]['corrected']==expected,(layout,automatic,a.line_results[0])
                    assert a.editor_source_text()==source,(layout,automatic,repr(a.editor_source_text()),repr(source))
                    shown=w.get('1.0','1.end')
                    assert shown==(expected if automatic else source.split('\n')[0]),(layout,automatic,shown)
                    if layout=='split':assert a.result_view.get('1.0','1.end')==expected
                    # Returning to the same tab retains this explicit result.
                    origin=a.session.active
                    a._switch_tab(0 if origin else 1);until(done)
                    a._switch_tab(origin);until(done)
                    assert a.line_results[0]['corrected']==expected
                    if layout=='unified' and automatic:
                        a.unified_autofix_var.set(False);a._on_toggle_unified_autofix();until(done)
                        assert w.get('1.0','1.end')==source.split('\n')[0]
                        a.unified_autofix_var.set(True);a._on_toggle_unified_autofix();until(done)
                        assert w.get('1.0','1.end')==expected
                        # Use the existing correction Undo action and decision gate.
                        record=a._autofix_record_for_row(1)
                        span=next(span for span in record['spans'] if span[3]==expression)
                        a._undo_autofix(1,span);until(done)
                        assert w.get('1.0','1.end')==source.split('\n')[0]
                        assert not any(d[2]=='計算' for d in a.line_results[0]['details'])
                        a.decisions.unreject(expression,answer)
                    if layout=='split' and not button:
                        # Same source in a new tab has no explicit calculation.
                        a.session.tabs.append(new_tab(text=source))
                        a._switch_tab(len(a.session.tabs)-1);until(done)
                        assert not any(d[2]=='計算' for d in a.line_results[0]['details'])
                        assert a.line_results[0]['corrected']!=expected
                        a._switch_tab(origin);until(done)
                        assert a.line_results[0]['corrected']==expected

            # Quick input uses its existing auto-correction option too.
            with patch.object(a,'_set_window_icons_win32',side_effect=lambda win:win.withdraw()), \
                    patch.object(a,'_place_quick_window'),patch.object(a,'_focus_quick_window'):
                a._open_quick_capture()
            q=a._quick_text
            from tests_ime_context import assert_quick_context_isolation
            assert_quick_context_isolation(a)
            for automatic in (False,True):
                a.settings.set('quick_autofix',automatic)
                a._quick_autofix_records=[];q.replace('1.0','end-1c','前後');q.mark_set('insert','1.1')
                deliver_key(q,'<Control-c>','c',67,state=4)
                for char in '8*5':
                    deliver_key(q,'<KeyPress>',char,0,char=char)
                    deliver_key(q,'<KeyRelease>',char,0,event_type=3,char=char)
                deliver_key(q,'<KeyPress>','Return',13,char='\r')
                until(lambda: getattr(a,'_quick_after_id',None) is None)
                assert a._pick_mode is None
                assert q.get('1.0','end-1c')==('前40後' if automatic else '前8*5後')
                if not automatic:assert a._quick_results[0]['corrected']=='前40後'
                else:
                    a.choices.remember('40','四十')
                    a._analyze_quick()
                    assert q.get('1.0','end-1c')=='前40後'

            # Close and reopen without sending synthetic text or touching the clipboard.
            q.delete('1.0','end');a._close_quick_capture()
            assert a._quick_himc is None and a._quick_himc_hwnds==()
            with patch.object(a,'_set_window_icons_win32',side_effect=lambda win:win.withdraw()), \
                    patch.object(a,'_place_quick_window'),patch.object(a,'_focus_quick_window'):
                a._open_quick_capture()
            assert_quick_context_isolation(a)
            a._close_quick_capture()

            # Direct choice setup above needs the same invalidation as the UI.
            a._invalidate_units_cache();a._analyze();until(done)
            # Identical numeric text can have different explicit calculation state.
            a._choose_layout('split');until(done)
            def open_new(text):
                a.session.tabs.append(new_tab(text=text))
                a._switch_tab(len(a.session.tabs)-1);until(done)
                return a.session.active
            ordinary=open_new('40')
            assert a.result_view.get('1.0','1.end')=='四十'
            calculated=open_new('');w=a.editor;w.mark_set('insert','1.0')
            deliver_key(w,'<Control-c>','c',67,state=4)
            for char in '40':
                deliver_key(w,'<KeyPress>',char,0,char=char)
                deliver_key(w,'<KeyRelease>',char,0,event_type=3,char=char)
            until(done)
            deliver_key(w,'<KeyPress>','Return',13,char='\r');until(done)
            assert a.result_view.get('1.0','1.end')=='40'
            open_new('40')
            assert a.result_view.get('1.0','1.end')=='四十', 'Calculated display units leaked into a plain identical tab'
            a._switch_tab(calculated);until(done)
            assert a.result_view.get('1.0','1.end')=='40'
            a._switch_tab(ordinary);until(done)
            assert a.result_view.get('1.0','1.end')=='四十'

            # The formula still belongs to source text if normal number choices
            # have already changed the unified display before Enter.
            a.unified_autofix_var.set(True);a._on_toggle_unified_autofix()
            a._choose_layout('unified');until(done)
            open_new('前😀後');w=a.editor;w.mark_set('insert','1.0+2c')
            deliver_key(w,'<Control-c>','c',67,state=4)
            for char in '40':
                deliver_key(w,'<KeyPress>',char,0,char=char)
                deliver_key(w,'<KeyRelease>',char,0,event_type=3,char=char)
            until(done)
            assert w.get('1.0','1.end')=='前😀四十後', 'Expected the existing number choice to be displayed first'
            deliver_key(w,'<KeyPress>','Return',13,char='\r');until(done)
            assert a._pick_mode is None, 'A projected number prevented calculation confirmation'
            assert w.get('1.0','1.end')=='前😀40後'
            assert a.editor_source_text().split('\n')[0]=='前😀40後'

            with patch.object(a,'_set_window_icons_win32',side_effect=lambda win:win.withdraw()), \
                    patch.object(a,'_place_quick_window'),patch.object(a,'_focus_quick_window'):
                a._open_quick_capture()
            q=a._quick_text
            q.delete('1.0','end');q.mark_set('insert','1.0')
            deliver_key(q,'<Control-c>','c',67,state=4)
            for char in '40':
                deliver_key(q,'<KeyPress>',char,0,char=char)
                deliver_key(q,'<KeyRelease>',char,0,event_type=3,char=char)
            until(lambda:getattr(a,'_quick_after_id',None) is None)
            assert q.get('1.0','end-1c')=='40', 'Number choices must wait while the formula is being entered'
            for char in '+2':
                deliver_key(q,'<KeyPress>',char,0,char=char)
                deliver_key(q,'<KeyRelease>',char,0,event_type=3,char=char)
            until(lambda:getattr(a,'_quick_after_id',None) is None)
            assert q.get('1.0','end-1c')=='40+2'
            deliver_key(q,'<KeyPress>','Return',13,char='\r')
            until(lambda:getattr(a,'_quick_after_id',None) is None)
            assert a._pick_mode is None, 'A quick-input number choice prevented calculation confirmation'
            assert q.get('1.0','end-1c')=='42'
            q.delete('1.0','end');q.mark_set('insert','1.0')
            deliver_key(q,'<Control-c>','c',67,state=4)
            for char in '40':
                deliver_key(q,'<KeyPress>',char,0,char=char)
                deliver_key(q,'<KeyRelease>',char,0,event_type=3,char=char)
            until(lambda:getattr(a,'_quick_after_id',None) is None)
            assert q.get('1.0','end-1c')=='40'
            deliver_key(q,'<KeyPress>','Escape',27)
            until(lambda:getattr(a,'_quick_after_id',None) is None)
            assert a._pick_mode is None and q.get('1.0','end-1c')=='四十'
            q.delete('1.0','end');q.mark_set('insert','1.0')
            deliver_key(q,'<Control-c>','c',67,state=4)
            assert a._pick_mode=='f1'
            a._close_quick_capture()
            assert a._pick_mode is None and a._quick_after_id is None

            assert not errors, errors
            print('EDITOR_FEATURES_INTEGRATION_PASSED', flush=True)
        finally:
            if a is not None: a._on_close()
            else: root.destroy()


class FeaturesApplicationTests(unittest.TestCase):
    def test_real_application_navigation_font_search_and_file_format(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-features-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-features-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8',
                str(dest / 'tests_gui_features.py'), '--child'], cwd=dest,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding='utf-8', errors='replace', timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn('EDITOR_FEATURES_INTEGRATION_PASSED', run.stdout)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
