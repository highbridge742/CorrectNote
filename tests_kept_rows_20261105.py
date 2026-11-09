# -*- coding: utf-8 -*-
"""Rows read back from the saved file stay in it when a word moves, marked; the next start shows their answers with no
mark and reads them again when the hands stop (2026-11-05). Made-up text."""
import json, os, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path


def row(text, **more):
    return dict(original=text, corrected=text + '。', changed=True, details=[], spans=[], unsure_spans=[],
                original_spans=[], odd_spans=[], odd_reasons=[], **more)


class FileForm(unittest.TestCase):
    def test_a_kept_row_comes_back_as_kept(self):
        import analysis_cache as C
        kept = C.keep_answer(row('あ'))
        self.assertTrue(C.kept_answer(kept))
        self.assertFalse(C.reusable_result(kept))
        back = C._unpack(json.loads(json.dumps(C._pack(kept))))
        self.assertTrue(C.kept_answer(back))
        self.assertEqual(back['corrected'], 'あ。')
        self.assertFalse(C.kept_answer(C._unpack(json.loads(json.dumps(C._pack(row('い')))))))

    def test_other_waiting_rows_are_not_kept(self):
        import analysis_cache as C
        self.assertFalse(C.kept_answer(row('あ', deferred_stages=['context'])))
        self.assertFalse(C.kept_answer(row('あ', deferred_stages=['restored'], pending=True)))
        self.assertFalse(C.kept_answer(row('あ', deferred_stages=['restored'], analysis_status='incomplete')))

    def test_save_and_load(self):
        import analysis_cache as C
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'c.json')
            self.assertTrue(C.save(p, {'k': 1}, {}, {'あ\nい\nう': [C.keep_answer(row('あ')), row('い'), None]}))
            _, partial = C.load_all(p, {'k': 1})
            rows = partial['あ\nい\nう']
            self.assertTrue(C.kept_answer(rows[0]))
            self.assertTrue(C.reusable_result(rows[1]))
            self.assertIsNone(rows[2])
            # Not a finished tab: a kept row never counts as a completed one
            self.assertTrue(C.save(p, {'k': 1}, {'あ': [C.keep_answer(row('あ'))]}, {'い': [row('い')]}))
            self.assertEqual(C.load_all(p, {'k': 1})[0], {})


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import analysis_cache, app, tab_analysis
    stage = sys.argv[sys.argv.index('--child') + 1]
    root = tk.Tk(); root.withdraw()
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()):
        a = app.CorrectNoteApp(root)
        root.geometry('900x600+40+40'); root.deiconify(); root.update()
        def pump(s):
            end = time.monotonic() + s
            while time.monotonic() < end:
                root.update(); time.sleep(.01)
        def filled():
            return [r for r in a.line_results if r.get('original')]
        def marks():
            e = a.editor
            return [k for k in range(1, int(e.index('end-1c').split('.')[0]) + 1)
                    if e.get(f'{k}.0', f'{k}.end').strip() and a._line_analysis_display_state(k) == 'pending']
        def wait(condition, seconds=150):
            t0 = time.monotonic()
            while time.monotonic() - t0 < seconds and not condition():
                pump(.1)
            assert condition(), 'timed out'
        if stage == '1':        # read all of it, as the file would have it
            wait(lambda: filled() and not a._foreground_analysis_pending())
            pump(3)       # the learning at the end of a pass
            wait(lambda: not a._foreground_analysis_pending())
            a.store.save(); a._save_analysis_cache()
        elif stage == '2':      # read back; a word moves; saved
            pump(.5)
            rows = filled()
            assert rows and all(tab_analysis.restored_without_proof(r) for r in rows), ('not read back', len(rows), sum(1 for r in rows if 'used_keys' in r))
            a.store.add('ずばらしごう', '図原氏号'); a.store.save()
            a._save_analysis_cache()
            saved = json.load(open('analysis_cache.json', encoding='utf-8'))
            kept = sum(1 for t in saved['tabs'] for r in t['results'] if r and r.get('o') and r.get('x'))
            assert kept == len(rows), (kept, len(rows))
        else:                   # a new start: shown with no mark; a second word while waiting; read again
            wait(lambda: filled() and not any(r.get('pending') for r in filled()), 20)     # the context comes from the child
            rows = filled()
            # (those read again already have their record; a new start means nothing else made them)
            assert rows and all(tab_analysis.kept_answer(r) or 'used_keys' in r for r in rows), ('kept rows not read back', len(rows), sum(1 for r in rows if r.get('pending')))
            assert sum(1 for r in rows if tab_analysis.kept_answer(r)) >= len(rows) // 2, 'kept rows not read back'
            answers = {r['original']: r['corrected'] for r in rows}
            assert not marks(), ('marked after the restart', len(marks()))
            a.store.add('ずばらしごうに', '図原氏号二')
            a._analyze(); root.update(); pump(.2)
            assert not marks(), ('marked after a second word', len(marks()))
            a._save_analysis_cache()
            saved = json.load(open('analysis_cache.json', encoding='utf-8'))
            assert sum(1 for t in saved['tabs'] for r in t['results'] if r and r.get('o')) == len(rows), 'rows lost at the second save'
            # Away to another tab and back, while they wait
            from session import new_tab
            a.session.tabs.append(new_tab(text='これは別のタブです。'))
            a._switch_tab(1); pump(.1)
            a._switch_tab(0); root.update(); pump(.6)
            assert not marks(), ('marked after coming back', len(marks()))
            wait(lambda: not any(r.get('deferred_stages') for r in a.line_results) and not a._foreground_analysis_pending())
            assert all(isinstance(r.get('used_keys'), dict) for r in filled()), 'not read again'
            assert {r['original']: r['corrected'] for r in filled()} == answers, 'the answers changed'
        print('KEPT_OK', flush=True)
        os._exit(0)


class Restart(unittest.TestCase):
    def test_restart(self):
        source = Path(__file__).resolve().parent
        sys.path.insert(0, str(source / 'tools_local' / 'heavy_20261027'))
        from probe_heavy import make_copy
        with tempfile.TemporaryDirectory(prefix='correctnote-kept-') as folder:
            dest = make_copy(folder, 'as_is', False)
            for n in ('reading_lattice_compact.pickle.gz', 'reading_lattice_table.pickle.gz', 'janome_entries.pickle.gz', 'wlsp_synonyms_compact.pickle.gz'):
                if (source / n).exists(): shutil.copy2(source / n, dest / n)
            sys.path.insert(0, str(dest))
            from session import new_tab
            text = chr(10).join('今日は天気がよいので%d番目の公園へ歩いて行きました。' % k for k in range(1, 9))
            (dest / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text)]), ensure_ascii=False), encoding='utf-8')
            for name in ('analysis_cache.json',):
                if (dest / name).exists(): (dest / name).unlink()
            (dest / '.ui-test-isolated').touch()
            shutil.copy2(__file__, dest / 'probe_kept.py')
            for stage in '123':
                r = subprocess.run([sys.executable, '-X', 'utf8', str(dest / 'probe_kept.py'), '--child', stage], cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=220)
                self.assertIn('KEPT_OK', r.stdout, (stage, r.stdout[-900:].encode('ascii', 'replace').decode()))


if __name__ == '__main__':
    if '--child' in sys.argv:
        child()
    else:
        unittest.main()
