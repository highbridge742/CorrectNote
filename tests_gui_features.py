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
        return (a._warmup is None and getattr(a, '_async_context_scope', None) is None
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
            origin = a.session.current()
            with patch.object(root, 'focus_get', return_value=a.editor):
                deliver_key(a.editor, '<F1>', 'F1', 112)
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
