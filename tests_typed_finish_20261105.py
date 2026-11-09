# -*- coding: utf-8 -*-
"""The end of a pass for a typed row paints only that row. What is on screen must be what a whole paint would give,
and the learning at the end of a pass is still asked for (2026-11-05). Opens a window, in a copy. Made-up text."""
import json, os, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    root = tk.Tk(); root.withdraw()
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()):
        a = app.CorrectNoteApp(root)
        root.geometry('1000x600+40+40'); root.deiconify(); root.update()
        e, r = a.editor, a.result_view
        def pump(s):
            end = time.monotonic() + s
            while time.monotonic() < end:
                root.update(); time.sleep(.005)
        def settle(limit=60):
            t0 = time.monotonic()
            while time.monotonic() - t0 < limit:
                pump(.1)
                if not a._foreground_analysis_pending() and not any(x.get('deferred_stages') for x in a.line_results):
                    pump(.3)
                    if not a._foreground_analysis_pending():
                        return
            raise AssertionError(('never settled', a._foreground_analysis_pending(), a._analyze_pos, len(a._analyze_todo), [(i, x.get('deferred_stages')) for i, x in enumerate(a.line_results) if x.get('deferred_stages')][:5], getattr(a,'_heavy_redo_job',0), getattr(a,'_after_id',0), getattr(a,'_input_display_job',0), getattr(a,'_async_context_scope',None) is not None, 'REQ', str(getattr(a,'_async_request',None))[:70].encode('ascii','replace').decode(), 'JOB', getattr(a,'_analyze_job',0), a._view_changing(), a._interacting(), getattr(a,'_heavy_redo',None), time.monotonic()-t0))
        settle()
        def picture():
            return dict(left=e.get('1.0', 'end-1c'), right=r.get('1.0', 'end-1c'),
                        suspect=tuple(map(str, e.tag_ranges('suspect'))), odd=tuple(map(str, e.tag_ranges('odd'))),
                        fixed=tuple(map(str, r.tag_ranges('fixed'))), chosen=tuple(map(str, r.tag_ranges('chosen'))),
                        units=[[u['start'] for u in row] for row in a.line_units])
        full = []
        real_render = a._render_corrected
        def render():
            full.append(1)
            return real_render()
        a._render_corrected = render
        learned = []
        real_learn = a._schedule_learning
        a._schedule_learning = lambda text: learned.append(text) or real_learn(text)
        print('T start', flush=True)
        for source in ('寒ぃ日が続いています', '今日は天気がいいです', 'よろしくおねがいしまう'):
            for row in (5, 9):
                full.clear(); learned.clear()
                a.editor.focus_force()
                e.mark_set('insert', '%d.end' % row)
                for ch in source:
                    e.insert('insert', ch)
                    e.event_generate('<KeyRelease>', keysym='a')
                    root.update()
                t1 = time.monotonic(); settle(); print('T settled_in', round(time.monotonic() - t1, 1), flush=True)
                got = picture()
                assert learned, 'the end of the pass asked for no learning'
                # A whole paint now must change nothing
                a._display_state = None
                a._refresh_after_analysis(learn=False)
                pump(.2)
                again = picture()
                for name in got:
                    assert got[name] == again[name], (source, row, name)
        print('T full paints in the last pass', len(full), flush=True)
        print('TYPED_FINISH_OK', flush=True)
        os._exit(0)


class Typed(unittest.TestCase):
    def test_a_typed_row_ends_as_a_whole_paint_would(self):
        source = Path(__file__).resolve().parent
        sys.path.insert(0, str(source / 'tools_local' / 'heavy_20261027'))
        from probe_heavy import make_copy
        with tempfile.TemporaryDirectory(prefix='correctnote-typed-') as folder:
            dest = make_copy(folder, 'as_is', False)
            for n in ('reading_lattice_compact.pickle.gz', 'reading_lattice_table.pickle.gz', 'janome_entries.pickle.gz', 'wlsp_synonyms_compact.pickle.gz'):
                if (source / n).exists(): shutil.copy2(source / n, dest / n)
            sys.path.insert(0, str(dest))
            from session import new_tab
            text = chr(10).join('今日は天気がよいので%d番目の公園へ歩いて行きました。' % k for k in range(1, 30))
            (dest / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text)]), ensure_ascii=False), encoding='utf-8')
            if (dest / 'analysis_cache.json').exists(): (dest / 'analysis_cache.json').unlink()
            (dest / '.ui-test-isolated').touch()
            shutil.copy2(__file__, dest / 'probe_typed.py')
            r = subprocess.run([sys.executable, '-X', 'utf8', str(dest / 'probe_typed.py'), '--child'], cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=200)
            self.assertIn('TYPED_FINISH_OK', r.stdout, r.stdout[-900:].encode('ascii', 'replace').decode())


if __name__ == '__main__':
    child() if '--child' in sys.argv else unittest.main()
