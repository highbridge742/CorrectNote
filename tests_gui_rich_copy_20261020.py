# -*- coding: utf-8 -*-
"""The app's own copies carry B/I/U/S (rich_copy.py): Ctrl+C and cut in the memo, the menu's
コピー, and Ctrl+C in the correction pane. Runs the app hidden in a copy of the folder and puts
back the Windows clipboard afterwards."""
import json, shutil, subprocess, sys, tempfile, time, traceback, unittest
from pathlib import Path


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app, clipboard_keep
    from session import new_tab
    assert (Path.cwd() / '.ui-test-isolated').exists()
    assert Path(app.__file__).resolve().parent == Path.cwd().resolve()
    Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana',
                                                     input_method_auto=False)), encoding='utf-8')
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[
        new_tab(text='太字の行です。\n普通の行です。')])), encoding='utf-8')
    b = clipboard_keep._backend()
    html, rtf = b.register('HTML Format'), b.register('Rich Text Format')

    def clipboard():
        assert b.open()
        try:
            return {f: b.take(f) for f in b.formats()}
        finally:
            b.close()

    root = tk.Tk(); root.withdraw(); a = None; errors = []
    root.report_callback_exception = lambda *exc: errors.append(''.join(traceback.format_exception(*exc)))

    def until(predicate, seconds=60):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            root.update(); assert not errors, errors
            if predicate():
                return
            time.sleep(.01)
        raise AssertionError('timed out')

    def select(widget, start, end):
        widget.tag_remove('sel', '1.0', 'end'); widget.tag_add('sel', start, end)

    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
            patch.object(app.CorrectNoteApp, '_learn_now', lambda *args: None):
        try:
            a = app.CorrectNoteApp(root); root.update()
            until(lambda: not a._foreground_analysis_pending())
            # As the B and S buttons do; the correction pane gets the same styles
            a.editor._correctnote_text_format.restore({'bold': [[1, 0, 1, 2]], 'overstrike': [[2, 0, 2, 2]]})
            until(lambda: bool(a.result_view.tag_ranges('fmt_bold')))

            # Ctrl+C in the memo: its own binding lets Tk's copy (<<Copy>>) run
            select(a.editor, '1.0', '2.end')
            assert a._on_editor_ctrl_c() is None
            a.editor.event_generate('<<Copy>>'); root.update()
            got = clipboard()
            assert got[13].decode('utf-16-le') == '太字の行です。\r\n普通の行です。\0', got.get(13)
            assert '<b>太字</b>'.encode('utf-8') in got[html], got.get(html)
            assert b'{\\strike ' in got[rtf], got.get(rtf)
            print('CASE ctrl_c', flush=True)

            # The menu's コピー
            select(a.editor, '1.0', '1.4')
            a.editor.focus_set(); root.update()
            a._copy_focused_selection()
            got = clipboard()
            assert html in got and got[13].decode('utf-16-le') == '太字の行\0', got.get(13)
            print('CASE menu', flush=True)

            # A selection without styles: text only, as before
            select(a.editor, '1.3', '1.end')
            a.editor.event_generate('<<Copy>>'); root.update()
            got = clipboard()
            assert html not in got and rtf not in got, sorted(got)
            assert root.clipboard_get() == '行です。'
            print('CASE plain', flush=True)

            # The correction pane shows the same styles; its Ctrl+C copies them too
            if a.result_view.tag_ranges('fmt_bold'):
                first = a.result_view.index('fmt_bold.first')
                select(a.result_view, first, first + ' lineend')
                assert a._copy_selection() == 'break'
                assert html in clipboard()
                print('CASE result', flush=True)
            else:
                print('CASE result_without_styles', flush=True)

            # Cut keeps the styles and removes the text
            select(a.editor, '1.0', '1.2')
            a.editor.event_generate('<<Cut>>'); root.update()
            got = clipboard()
            assert rtf in got and got[13].decode('utf-16-le') == '太字\0'
            assert a.editor.get('1.0', '1.end') == 'の行です。'
            print('CASE cut', flush=True)
            print('RICH_COPY_OK', flush=True)
        finally:
            if a:
                a._on_close()
            else:
                root.destroy()


@unittest.skipUnless(sys.platform == 'win32', 'Windows clipboard')
class RichCopyGuiTests(unittest.TestCase):
    def test_app_copies_carry_styles(self):
        import clipboard_keep
        from bundle_manifest import NAMES
        b = clipboard_keep._backend()
        if not b.open():
            self.skipTest('clipboard busy')
        try:
            formats = b.formats()
            complete = len(formats) == b.u.CountClipboardFormats()
            saved = [(f, b.take(f)) for f in formats if clipboard_keep._keepable(f)]
            complete = complete and all(d is not None for f, d in saved)
        finally:
            b.close()
        if not complete:
            self.skipTest('could not read the whole clipboard to put it back')
        source = Path(__file__).resolve().parent
        try:
            with tempfile.TemporaryDirectory(prefix='correctnote-rich-copy-') as folder:
                dest = Path(folder)
                for p in source.iterdir():
                    if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                        shutil.copy2(p, dest / p.name)
                (dest / '.ui-test-isolated').touch()
                run = subprocess.run([sys.executable, '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                     cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     encoding='utf-8', timeout=300)
                print(run.stdout, flush=True)
                self.assertEqual(run.returncode, 0, run.stdout)
                self.assertIn('RICH_COPY_OK', run.stdout)
        finally:
            if b.open():
                try:
                    b.empty()
                    for f, d in saved:
                        b.put(f, d)
                finally:
                    b.close()


if __name__ == '__main__':
    child() if '--child' in sys.argv else unittest.main()
