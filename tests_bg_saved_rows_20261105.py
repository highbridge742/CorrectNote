# -*- coding: utf-8 -*-
"""The background goes on from the rows the saved file holds for a tab not yet opened, instead of reading them again
from the first row (2026-11-05: 35 of the 35 rows sent in the first minute were in the file). Made-up text."""
import json, os, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class SavedPartial(unittest.TestCase):
    def values(self, partial, previous, current):
        import tab_analysis as T
        app = SimpleNamespace(_analysis_partial={'あ\nい\nう': partial}, _analysis_partial_state=previous, _analysis_stale=())
        with patch.object(T, 'state_key', return_value=current), patch.object(T, 'same_model_state', return_value=True), \
                patch.object(T, '_readings', return_value=()), patch.object(T, '_calculations', return_value=()):
            return T.saved_partial(app, 'あ\nい\nう', 'owner')

    def test_finished_rows_are_used_while_nothing_has_moved(self):
        done = dict(original='あ', corrected='あ')
        got = self.values([done, None, None], 1, 1)
        self.assertEqual(got['results'], [done, None, None])
        self.assertEqual(got['skip'], set())

    def test_a_kept_row_waits_for_the_tab_to_open(self):
        import analysis_cache as C
        got = self.values([C.keep_answer(dict(original='あ', corrected='あ')), None, None], 1, 1)
        self.assertEqual(got['results'], [None, None, None])
        self.assertEqual(got['skip'], {0})

    def test_after_a_move_the_rows_wait_too(self):
        got = self.values([dict(original='あ', corrected='あ'), None, None], 1, 2)
        self.assertEqual(got['results'], [None, None, None])
        self.assertEqual(got['skip'], {0})

    def test_a_row_of_other_text_is_not_used(self):
        self.assertEqual(self.values([dict(original='ん', corrected='ん'), None, None], 1, 1), {})


def child():
    import tkinter as tk
    from unittest.mock import Mock
    import analysis_cache, analysis_worker, app, tab_analysis
    stage = sys.argv[sys.argv.index('--child') + 1]
    sent = []
    orig = analysis_worker.Worker.submit
    def submit(worker, task, state=None):
        if task.get('kind') == 'line':
            sent.append(task.get('line'))
        return orig(worker, task, state)
    analysis_worker.Worker.submit = submit
    root = tk.Tk(); root.withdraw()
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *v: None):
        a = app.CorrectNoteApp(root)
        root.geometry('900x600+40+40'); root.deiconify(); root.update()
        def pump(s):
            end = time.monotonic() + s
            while time.monotonic() < end:
                root.update(); time.sleep(.01)
        def wait(condition, seconds=120):
            t0 = time.monotonic()
            while time.monotonic() - t0 < seconds and not condition():
                pump(.1)
            assert condition(), 'timed out'
        filled = lambda: [r for r in a.line_results if r.get('original')]
        if stage == '1':
            wait(lambda: filled() and not a._foreground_analysis_pending())
            fp = a._analysis_cache_payload()[0]
            key = a._analysis_key(a.editor_source_text())
            rows = [r if r.get('original') and i % 2 else None for i, r in enumerate(a.line_results)][:len(key.split(chr(10)))]
            analysis_cache.save(app.ANALYSIS_CACHE_FILE, fp, {}, {key: rows})
            json.dump({r['original']: r['corrected'] for r in filled()}, open('answers.json', 'w', encoding='utf-8'), ensure_ascii=False)
        else:
            answers = json.load(open('answers.json', encoding='utf-8'))
            lines = a.session.tabs[1]['text'].split(chr(10))
            kept = {line for i, line in enumerate(lines) if i % 2 and line}
            rest = {line for i, line in enumerate(lines) if not i % 2 and line}
            assert a._analysis_partial, 'the file was not read'
            wait(lambda: rest <= set(sent))
            assert not (kept & set(sent)), ('rows in the file were read again', len(kept & set(sent)))
            wait(lambda: a._bg is None and not a._bg_texts)
            before = len(sent)
            a._switch_tab(1); root.update()
            wait(lambda: filled() and not a._foreground_analysis_pending())
            e = a.editor
            shown = [k for k in range(1, len(lines) + 1) if e.get(f'{k}.0', f'{k}.end').strip()]
            assert not [k for k in shown if a._line_analysis_display_state(k) == 'pending'], 'marked'
            assert len(sent) == before, ('opening read rows again', len(sent) - before)
            assert {r['original']: r['corrected'] for r in filled()} == answers, 'the answers changed'
        print('BG_SAVED_OK', flush=True)
        os._exit(0)


class Restart(unittest.TestCase):
    def test_background_goes_on_from_the_file(self):
        source = Path(__file__).resolve().parent
        sys.path.insert(0, str(source / 'tools_local' / 'heavy_20261027'))
        from probe_heavy import make_copy
        with tempfile.TemporaryDirectory(prefix='correctnote-bgsaved-') as folder:
            dest = make_copy(folder, 'as_is', False)
            for n in ('reading_lattice_compact.pickle.gz', 'reading_lattice_table.pickle.gz', 'janome_entries.pickle.gz', 'wlsp_synonyms_compact.pickle.gz'):
                if (source / n).exists(): shutil.copy2(source / n, dest / n)
            sys.path.insert(0, str(dest))
            from session import new_tab
            text = chr(10).join('今日は天気がよいので%d番目の公園へ歩いて行きました。' % k for k in range(1, 9))
            tabs = [new_tab(text='短い文です。'), new_tab(text=text)]
            def write(active):
                (dest / 'session.json').write_text(json.dumps(dict(version=1, active=active, tabs=tabs), ensure_ascii=False), encoding='utf-8')
            if (dest / 'analysis_cache.json').exists(): (dest / 'analysis_cache.json').unlink()
            (dest / '.ui-test-isolated').touch()
            shutil.copy2(__file__, dest / 'probe_bg_saved.py')
            for stage, active in (('1', 1), ('2', 0)):
                write(active)
                r = subprocess.run([sys.executable, '-X', 'utf8', str(dest / 'probe_bg_saved.py'), '--child', stage], cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=170)
                self.assertIn('BG_SAVED_OK', r.stdout, (stage, r.stdout[-700:].encode('ascii', 'replace').decode()))


if __name__ == '__main__':
    if '--child' in sys.argv:
        child()
    else:
        unittest.main()
