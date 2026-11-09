# -*- coding: utf-8 -*-
"""Select text and press Alt+I: the all-tab search runs with the selection even when the search window is not open
(2026-11-08 うにさん「選択してAlt+Iは、検索ウィンドウが開いてなくても、全タブ検索を実行する」), in the memo pane and
in the correction pane. With nothing selected nothing happens. An isolated copy, made-up text."""
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
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    from tests_tk_keys import deliver_key
    here = Path.cwd().resolve()
    assert (here / '.ui-alt-i-test-isolated').is_file()
    tabs = [new_tab(text='会議の資料を作る。\n資料は明日まで。'), new_tab(text='別の資料を読む。'), new_tab(text='関係のない行。')]
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=tabs), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); root.withdraw(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))

    def pump(seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
            if until is not None and until(): return True
        return False
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        pump(2.0, lambda: bool(a.result_view.get('1.0', 'end-1c').strip()))
        source = a.editor_source_text()
        # nothing selected: nothing happens
        a.editor.tag_remove('sel', '1.0', 'end')
        deliver_key(a.editor, '<Alt-i>', 'i', 73, state=0x20000)
        pump(0.3)
        out['no_selection_dialog'] = getattr(a, '_find_dialog', None) is not None
        # the memo pane: the selection, the search window was not open
        a.editor.tag_add('sel', '1.3', '1.5')                     # 資料
        deliver_key(a.editor, '<Alt-i>', 'i', 73, state=0x20000)
        pump(2.0, lambda: len(getattr(a, '_all_tab_hits', {}) or {}) >= 3)
        out['memo_query'] = a._find_query.get()
        out['memo_hits'] = len(a._all_tab_hits)
        out['memo_text_same'] = a.editor_source_text() == source
        # the correction pane, with the search window open now: another word
        a._close_find_dialog()
        a.result_view.tag_remove('sel', '1.0', 'end')
        a.result_view.tag_add('sel', '2.3', '2.5')                # 明日
        deliver_key(a.result_view, '<Alt-I>', 'I', 73, state=0x20001)
        pump(2.0, lambda: getattr(a, '_find_query', None) is not None and a._find_query.get() == '明日'
             and len(getattr(a, '_all_tab_hits', {}) or {}) >= 1)
        out['result_query'] = a._find_query.get()
        out['result_hits'] = len(a._all_tab_hits)
        # the quick input window (always on top): the search and result windows come on top of it
        a._close_find_dialog()
        with patch.object(a, '_set_window_icons_win32', side_effect=lambda win: win.withdraw()),                 patch.object(a, '_place_quick_window'), patch.object(a, '_focus_quick_window'):
            a._open_quick_capture()
        q = a._quick_text
        q.insert('1.0', '別の資料メモ'); q.tag_add('sel', '1.2', '1.4')      # 資料
        deliver_key(q, '<Alt-i>', 'i', 73, state=0x20000)
        pump(2.0, lambda: a._find_query.get() == '資料' and len(getattr(a, '_all_tab_hits', {}) or {}) >= 3)
        out['quick_query'] = a._find_query.get()
        out['quick_hits'] = len(a._all_tab_hits)
        out['quick_topmost'] = [bool(int(d.attributes('-topmost'))) for d in (a._find_dialog, a._all_tab_dialog)]
        out['quick_text_same'] = q.get('1.0', 'end-1c') == '別の資料メモ'
        # the windows raised for the quick window go back to ordinary windows when it closes, while they stay open
        q.delete('1.0', 'end'); a._close_quick_capture(); pump(0.2)
        out['after_close_topmost'] = [bool(int(d.attributes('-topmost'))) for d in (a._find_dialog, a._all_tab_dialog)]
        # Alt+I from the memo pane afterwards: ordinary windows
        a.editor.tag_remove('sel', '1.0', 'end'); a.editor.tag_add('sel', '1.3', '1.5')
        deliver_key(a.editor, '<Alt-i>', 'i', 73, state=0x20000); pump(1.0)
        out['memo_after_topmost'] = [bool(int(d.attributes('-topmost'))) for d in (a._find_dialog, a._all_tab_dialog)]
        # nothing selected in the quick window: nothing happens
        a._close_find_dialog()
        with patch.object(a, '_set_window_icons_win32', side_effect=lambda win: win.withdraw()),                 patch.object(a, '_place_quick_window'), patch.object(a, '_focus_quick_window'):
            a._open_quick_capture()
        q = a._quick_text
        deliver_key(q, '<Alt-i>', 'i', 73, state=0x20000); pump(0.3)
        out['quick_no_selection_dialog'] = getattr(a, '_find_dialog', None) is not None
        a._close_quick_capture()
        # The IME on, full width (2026-11-08 うにさん「全角でAlt+Iすると、文字入力で上書きされる」): Alt+I comes as a
        # KeyPress with the full-width ｉ (に with kana input) and Alt held, then sometimes the same character again
        # without Alt. Neither replaces the selection; Alt+I searches. A later ordinary commit is text as before.
        a._close_find_dialog()
        before = a.editor_source_text()
        a.editor.tag_remove('sel', '1.0', 'end'); a.editor.tag_add('sel', '1.3', '1.5')      # 資料
        deliver_key(a.editor, '<KeyPress>', 'I', 73, state=0x20000, char='ｉ')
        deliver_key(a.editor, '<KeyPress>', 'I', 73, state=0, char='ｉ')          # the echo
        pump(1.5, lambda: getattr(a, '_find_query', None) is not None and a._find_query.get() == '資料'
             and len(getattr(a, '_all_tab_hits', {}) or {}) >= 3)
        out['ime_text_same'] = a.editor_source_text() == before
        out['ime_query'] = a._find_query.get()
        out['ime_hits'] = len(a._all_tab_hits)
        a._close_find_dialog()
        a.editor.tag_remove('sel', '1.0', 'end'); a.editor.tag_add('sel', '2.0', '2.2')      # 資料 (row 2)
        deliver_key(a.editor, '<KeyPress>', 'k', 73, state=0x20000, char='に')    # kana input: the I key is に
        pump(1.5, lambda: len(getattr(a, '_all_tab_hits', {}) or {}) >= 3)
        out['kana_text_same'] = a.editor_source_text() == before
        out['kana_hits'] = len(a._all_tab_hits)
        a._close_find_dialog()
        time.sleep(0.6); pump(0.1)
        a.editor.focus_set(); a.editor.tag_remove('sel', '1.0', 'end'); a.editor.mark_set('insert', '1.end')
        deliver_key(a.editor, '<KeyPress>', 'k', 0, state=0, char='に')           # an ordinary commit later
        pump(0.3)
        out['later_commit'] = a.editor.get('1.0', '1.end').endswith('に')
        assert not errors, errors
        print('ALT_I', json.dumps(out, ensure_ascii=False), flush=True)
        a._on_close()


class AltIAllTabs(unittest.TestCase):
    def test_selection_runs_the_all_tab_search(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-alt-i-') as directory:
            dest = Path(directory).resolve()
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.ui-alt-i-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            line = [l for l in run.stdout.splitlines() if l.startswith('ALT_I ')]
            self.assertTrue(line, run.stdout[-3000:])
            got = json.loads(line[0][len('ALT_I '):])
            self.assertFalse(got['no_selection_dialog'], got)
            self.assertEqual(got['memo_query'], '資料', got)
            self.assertEqual(got['memo_hits'], 3, got)            # 2 in the first tab, 1 in the second
            self.assertTrue(got['memo_text_same'], got)
            self.assertEqual(got['result_query'], '明日', got)
            self.assertEqual(got['result_hits'], 1, got)
            self.assertEqual(got['quick_query'], '資料', got)
            self.assertEqual(got['quick_hits'], 3, got)
            self.assertEqual(got['quick_topmost'], [True, True], got)
            self.assertTrue(got['quick_text_same'], got)
            self.assertFalse(got['quick_no_selection_dialog'], got)
            self.assertEqual(got['after_close_topmost'], [False, False], got)
            self.assertEqual(got['memo_after_topmost'], [False, False], got)
            self.assertTrue(got['ime_text_same'], got)
            self.assertEqual(got['ime_query'], '資料', got)
            self.assertEqual(got['ime_hits'], 3, got)
            self.assertTrue(got['kana_text_same'], got)
            self.assertEqual(got['kana_hits'], 3, got)
            self.assertTrue(got['later_commit'], got)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
