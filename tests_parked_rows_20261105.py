# -*- coding: utf-8 -*-
"""Rows a tab has already read in the background survive the vocabulary moving (2026-11-05 うにさん「次のタブを開くと、解析が
1行目から始まることが時々ある」: every finished tab's learning moves the vocabulary). Made-up text."""
import json, os, shutil, subprocess, sys, tempfile, time, traceback, unittest
from pathlib import Path


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app, analysis_work_app as W
    from session import new_tab
    Path('settings.json').write_text(json.dumps(dict(memory_usage='high', layout='split')), encoding='utf-8')
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[
        new_tab(text='\n'.join('タブ%dの今日は天気がよいので%d番目の公園へ歩いて行きました。' % (t, k) for k in range(n)))
        for t, n in enumerate((10, 200, 200))])), encoding='utf-8')
    root = tk.Tk(); root.withdraw()
    root.report_callback_exception = lambda *x: (traceback.print_exception(*x), sys.stdout.flush(), os._exit(3))
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *v: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1000x600+0+0'); root.deiconify(); root.update()

        def pump(s):
            end = time.monotonic() + s
            while time.monotonic() < end:
                root.update(); time.sleep(.01)

        def done():
            return sum(1 for r in (a.line_results or ()) if r and r.get('original') and not r.get('pending'))
        t0 = time.monotonic()
        while time.monotonic() - t0 < 60 and not (a._prev_lines and a._analyze_pos >= len(a._analyze_todo) and not a._foreground_analysis_pending()):
            pump(.2)
        # Tab 1 has never been open: only the background has read part of it. The view goes to tab 2, which parks them.
        owner = W.owner_for_tab(a, a.session.tabs[1])
        t0 = time.monotonic()
        while time.monotonic() - t0 < 80:
            pump(.2)
            st = getattr(a, '_bg', None)
            if st and st.get('owner') == owner and sum(1 for r in st.get('results') or () if r) >= 3:
                break
        a._switch_tab(2); pump(.5)
        parked = getattr(a, '_bg_parked', {}).get(owner)
        assert parked, 'nothing parked'
        kept = sum(1 for r in parked['results'] if r)
        assert kept >= 3, kept
        assert owner not in getattr(a, '_fg_parked', {}), 'it was open after all'
        # the vocabulary moves, as a finished tab's learning does
        a.store.add('ずばらしごう', '図原氏号二')
        a._switch_tab(1); root.update(); pump(.5)
        got = done()
        assert got >= kept, ('rows lost', kept, got)
        print('PARKED_ROWS_OK', flush=True)
        os._exit(0)


class TraceWindow(unittest.TestCase):
    def test_the_record_shows_counts_and_reasons(self):
        from types import SimpleNamespace as NS
        import debug_menu
        self.assertEqual(debug_menu.trace_text(NS()), '記録はまだありません。')
        self.assertEqual(debug_menu.trace_text(NS(_analyze_trace=['12:00:00  きっかけ=解き直しの内訳  本文10行  対象9行'])),
                         '12:00:00  きっかけ=解き直しの内訳  本文10行  対象9行')


class ParkedRows(unittest.TestCase):
    def test_kept_when_the_vocabulary_moved(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-parked-') as directory:
            dest = Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copy2(p, dest / p.name)
            (dest / '.ui-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'], cwd=dest,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=170)
            self.assertIn('PARKED_ROWS_OK', run.stdout, run.stdout[-900:])

    def test_previous_values_reads_the_parked_rows(self):
        from types import SimpleNamespace as NS
        from unittest import mock
        import tab_analysis as T
        rows = [dict(original='文', corrected='文')]
        parked = dict(results=rows, lines=['文'], ctx={'c': 1}, dependencies=('d',), units={'u': 1}, suspect_units={'s': 1})
        app = NS(_fg_parked={}, _bg_parked={'o': parked})
        with mock.patch.object(T, '_registry', return_value={}):
            got = T.previous_values(app, 'o')
        self.assertEqual(got['results'], rows)
        self.assertEqual(got['suspect'], {'s': 1})
        self.assertEqual(got['ctx'], {'c': 1})
        app._bg_parked = {'o': dict(parked, ctx=None)}
        with mock.patch.object(T, '_registry', return_value={}):
            self.assertIsNone(T.previous_values(app, 'o'))


if __name__ == '__main__':
    if '--child' in sys.argv:
        try:
            child()
        except BaseException:
            traceback.print_exc(); sys.stdout.flush(); sys.stderr.flush(); os._exit(2)
    else:
        unittest.main()
