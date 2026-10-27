# -*- coding: utf-8 -*-
"""The re-conversion list keeps what it worked out for a word (dropdown_cache, 2026-10-26 うにさん).

The list is the same with and without the kept part (memo pane and corrected pane), a vocabulary change or an
edit of the line makes it again, and only the newest few dozen are kept. A real app in an isolated folder, its
window off the screen; it prints how long the opens took.
"""
from pathlib import Path
import json, shutil, subprocess, sys, tempfile, time, traceback, unittest

from dropdown_cache import DropdownCache


class DropdownCacheTests(unittest.TestCase):
    def test_kept_value_is_a_copy_and_the_oldest_goes(self):
        cache = DropdownCache(limit=2)
        made = []

        def compute(n):
            return lambda: made.append(n) or [{'surface': str(n)}]
        first = cache.get('a', compute(1))
        first[0]['surface'] = 'changed'
        self.assertEqual(cache.get('a', compute(2)), [{'surface': '1'}])
        cache.get('b', compute(3)); cache.get('c', compute(4))
        self.assertEqual(len(cache), 2)
        cache.get('a', compute(5))
        self.assertEqual(made, [1, 3, 4, 5])
        self.assertEqual(cache.get(None, compute(6)), [{'surface': '6'}])     # no key: never kept
        self.assertEqual(len(cache), 2)


def child():
    import tkinter as tk
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    import app, analysis_work_app as work
    from session import new_tab
    assert Path('.dropdown-cache-isolated').exists()
    text = '今日は会議の資料を作成しました。\n明日のよていを確認してからカレーを食べます。\n機器を点検しました。'
    Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False,
                                                     unified_autofix=False, show_pos_info=True,
                                                     show_reason_info=True)), encoding='utf8')
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

    def labels(items):
        return [t for t, _cb in items]

    def editor_items(row, unit):
        return labels(a._editor_dropdown_items(row, unit, a._units_for_row(row)))

    shown = []

    def result_items(row, unit):
        shown.clear()
        a._open_dropdown(SimpleNamespace(x_root=0, y_root=0), row, unit)
        return labels(shown[-1]) if shown else []

    def fresh(fn, *args):
        saved, a._dropdown_cache = getattr(a, '_dropdown_cache', None), None
        try: return fn(*args)
        finally: a._dropdown_cache = saved

    try:
        with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
                patch.object(app.CorrectNoteApp, '_learn_now', lambda *v: None), \
                patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *v: None):
            a = app.CorrectNoteApp(root); root.geometry('1100x500+-6000+-6000'); root.deiconify(); complete()
            a._make_dropdown = lambda items, x, y, **k: shown.append(list(items))
            words = [(row, u) for row in (1, 2, 3) for u in a._units_for_row(row)
                     if not u.get('functional') and u.get('text', '').strip() not in ('', '。')]
            assert len(words) >= 8, words
            times = []
            for row, unit in words:
                t = time.perf_counter(); first = editor_items(row, unit); t1 = time.perf_counter() - t
                hits = a._dropdown_cache.hits
                t = time.perf_counter(); second = editor_items(row, unit); t2 = time.perf_counter() - t
                assert a._dropdown_cache.hits == hits + 2, (unit['text'], a._dropdown_cache.hits, hits)
                assert first == second == fresh(editor_items, row, unit), (unit['text'], first, second)
                times.append((unit['text'], t1 * 1000, t2 * 1000))
            # the corrected pane
            rwords = [(row, u) for row in (1, 2, 3) for u in a.line_units[row - 1]
                      if not u.get('functional') and u.get('text', '').strip() not in ('', '。')]
            for row, unit in rwords:
                first = result_items(row, unit); hits = a._dropdown_cache.hits
                second = result_items(row, unit)
                assert a._dropdown_cache.hits == hits + 2 and first == second == fresh(result_items, row, unit), unit
            # a vocabulary change makes it again
            row, unit = next((r, u) for r, u in words if u['text'] == 'カレー')
            before = editor_items(row, unit); misses = a._dropdown_cache.misses
            a.store.add('からー', 'カラー', solid=True); a.store.add('くれー', 'クレー', solid=True)
            a.settings.set('input_method', 'romaji')
            after = editor_items(row, unit)
            assert a._dropdown_cache.misses == misses + 2, (a._dropdown_cache.misses, misses)
            assert after == fresh(editor_items, row, unit), (after,)
            # the typo rows are checked in the background (candidate_check) and filled into the open list
            assert before != after and '打ち間違い' in ' '.join(after) and '打ち間違い' not in ' '.join(before), (before, after)
            # an edit of the line makes it again
            a.editor.insert('3.end', 'です'); root.update()        # the line's text alone changes the key
            row, unit = next((3, u) for u in a._units_for_row(3) if u['text'] == '機器')
            misses = a._dropdown_cache.misses
            got = editor_items(3, unit)
            assert a._dropdown_cache.misses == misses + 2 and got == fresh(editor_items, 3, unit)
            assert len(a._dropdown_cache) <= 48
            for word, t1, t2 in times:
                print('OPEN %s first %.1fms kept %.1fms' % (word, t1, t2), flush=True)
            print('DROPDOWN_CACHE_OK: same lists with and without the kept part in both panes, '
                  'remade after a vocabulary change and an edit', flush=True)
            a._on_close(); a = None
    finally:
        if a: a._on_close()
        else:
            try: root.destroy()
            except tk.TclError: pass
    assert not errors, errors


class DropdownCacheAppTests(unittest.TestCase):
    def test_real_app_lists_are_the_same_and_remade_on_change(self):
        from bundle_manifest import NAMES
        src = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-dropdown-cache-') as folder:
            dest = Path(folder)
            for p in src.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES): shutil.copyfile(p, dest / p.name)
            (dest / '.dropdown-cache-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-u', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8', timeout=240)
            print(run.stdout, flush=True); self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn('DROPDOWN_CACHE_OK', run.stdout)


if __name__ == '__main__':
    child() if '--child' in sys.argv else unittest.main()
