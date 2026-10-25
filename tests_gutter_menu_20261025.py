# -*- coding: utf-8 -*-
"""Right-click on the line numbers: a menu for that row (2026-10-25 うにさん).

Top / middle scroll (the cursor stays), a ruler under the row (the same rulers and Ctrl+Z as the button),
a bookmark (the same set as the double click). Both panes' line numbers. Right button + wheel (tab switch)
and a right drag do not open it. A real app in an isolated folder, its window placed off the screen.
"""
from pathlib import Path
import json, shutil, subprocess, sys, tempfile, time, traceback, unittest


def child():
    import tkinter as tk
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    import app, analysis_work_app as work
    from session import new_tab
    assert Path('.gutter-menu-isolated').exists()
    text = '\n'.join('%d 行目の文です。' % n for n in range(1, 81))
    Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False,
                                                     unified_autofix=False)), encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text)])), encoding='utf8')
    root = tk.Tk(); root.withdraw(); a = None; errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))

    def until(fn, seconds=90):
        end = time.monotonic() + seconds
        while True:
            root.update(); assert not errors, errors
            if fn(): return
            assert time.monotonic() < end, 'timeout'; time.sleep(.004)

    def complete():
        until(lambda: not a._foreground_analysis_pending() and a._analyze_work == work.token(a))

    shown = []

    def menu(gutter, line, move=0, wheel=False):
        """Press and release the right button over `line` of `gutter`; the items shown, or None."""
        pane = gutter.target
        pane.see('%d.0' % line); root.update()
        y = pane.dlineinfo('%d.0' % line)[1] + 2
        assert gutter._line_at_y(y) == line, (gutter._line_at_y(y), line)
        shown.clear()
        a._on_gutter_right_press(SimpleNamespace(y=y, x_root=300, y_root=300), gutter)
        a._tab_wheel_used = wheel
        result = a._on_gutter_right_release(SimpleNamespace(y=y, x_root=300 + move, y_root=300), gutter)
        a._tab_wheel_used = False
        return (shown[-1] if shown else None), result

    def pick(items, label):
        found = [cb for text, cb in items if text.strip() == label]
        assert len(found) == 1 and found[0] is not None, (label, [t for t, _ in items])
        found[0](); root.update()

    def top_row(pane):
        return int(pane.index('@0,0').split('.')[0])

    try:
        with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
                patch.object(app.CorrectNoteApp, '_learn_now', lambda *v: None), \
                patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *v: None):
            a = app.CorrectNoteApp(root); root.geometry('1120x660+-6000+-6000'); root.deiconify(); complete()
            a._make_dropdown = lambda items, x, y, **k: shown.append(list(items))
            for gutter in (a.editor_gutter, a.result_gutter):
                assert gutter.bind('<ButtonPress-3>') and gutter.bind('<ButtonRelease-3>')
            original = a.editor_source_text()
            a.editor.mark_set('insert', '3.2'); a.editor.edit_reset(); root.update()
            items, result = menu(a.editor_gutter, 30)
            assert result == 'break'
            assert [t for t, _ in items] == ['― 30 行目 ―', '  この行が上に来る位置にスクロール',
                                             '  この行が中央に来る位置にスクロール', '  行の下にルーラーを入れる',
                                             '  ブックマークを入れる'], items
            assert items[0][1] is None
            # 1. top: row 30 at the top of both panes; the cursor stays on row 3
            pick(items, 'この行が上に来る位置にスクロール')
            assert top_row(a.editor) == 30 and top_row(a.result_view) == 30, (top_row(a.editor), top_row(a.result_view))
            assert a.editor.index('insert') == '3.2'
            # 2. middle: row 40 near the middle of the pane; the cursor stays
            items, _ = menu(a.editor_gutter, 40)
            pick(items, 'この行が中央に来る位置にスクロール')
            info = a.editor.dlineinfo('40.0'); height = a.editor.winfo_height()
            assert info is not None and height * .3 < info[1] < height * .7, (info, height)
            assert a.editor.index('insert') == '3.2'
            # 3. ruler under the row, from the right pane's line numbers too; one Ctrl+Z / Ctrl+Y
            items, _ = menu(a.result_gutter, 12)
            pick(items, '行の下にルーラーを入れる')
            assert a._editor_guides.ruler_rows() == {12}
            items, _ = menu(a.editor_gutter, 12)
            assert '  行の下のルーラーを外す' in [t for t, _ in items]
            a.editor.edit_undo(); root.update(); assert a._editor_guides.ruler_rows() == set()
            a.editor.edit_redo(); root.update(); assert a._editor_guides.ruler_rows() == {12}
            items, _ = menu(a.editor_gutter, 12)
            pick(items, '行の下のルーラーを外す'); assert a._editor_guides.ruler_rows() == set()
            # 4. bookmark: the same set as the double click
            items, _ = menu(a.editor_gutter, 25)
            pick(items, 'ブックマークを入れる'); assert 25 in a.bookmarks
            items, _ = menu(a.result_gutter, 25)
            pick(items, 'ブックマークを外す'); assert 25 not in a.bookmarks
            # no menu: a right drag, or right button + wheel (tab switch)
            items, result = menu(a.editor_gutter, 20, move=12); assert items is None and result is None
            items, result = menu(a.editor_gutter, 20, wheel=True); assert items is None and result is None
            assert a.editor_source_text() == original
            print('GUTTER_MENU_OK: items, top/middle scroll keep the cursor, ruler with undo/redo, bookmark, both panes, '
                  'no menu after a drag or the tab wheel', flush=True)
            a._on_close(); a = None
    finally:
        if a: a._on_close()
        else:
            try: root.destroy()
            except tk.TclError: pass
    assert not errors, errors


class GutterMenuTests(unittest.TestCase):
    def test_line_number_right_click_menu(self):
        from bundle_manifest import NAMES
        src = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-gutter-menu-') as folder:
            dest = Path(folder)
            for p in src.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES): shutil.copyfile(p, dest / p.name)
            (dest / '.gutter-menu-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-u', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8', timeout=210)
            print(run.stdout, flush=True); self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn('GUTTER_MENU_OK', run.stdout)


if __name__ == '__main__':
    child() if '--child' in sys.argv else unittest.main()
