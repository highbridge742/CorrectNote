# -*- coding: utf-8 -*-
"""Whether the file tab has kana goes with every row's analysis (2026-10-26 うにさん「半角のまま打った文を全角に補正する
のは、ファイルタブ内に平仮名か片仮名が1文字以上ある場合だけ」).

The app asks analysis_work.tab_has_kana (tab_context, when it is there) about the whole tab and puts the answer in
the row's task; the analysis child passes it to correct_line when correct_line takes it; a row made under the other
answer is made again; the saved analysis keeps the answer per tab. tab_context is stood in for here (the real one
belongs to the correction side): any hiragana or katakana.
"""
from pathlib import Path
import json, shutil, subprocess, sys, tempfile, time, traceback, types, unittest
from unittest.mock import patch

import analysis_work

STAND_IN = '''# stand-in for the tests (tests_tab_kana_wiring_20261026)
def tab_has_kana(text):
    return any('\\u3041' <= c <= '\\u3096' or '\\u30a1' <= c <= '\\u30fa' for c in text or '')
'''


def stand_in_module():
    module = types.ModuleType('tab_context')
    exec(STAND_IN, module.__dict__)
    return module


class TabHasKanaTests(unittest.TestCase):
    def setUp(self):
        analysis_work._TAB_KANA_LAST[:] = [None, None]

    def tearDown(self):
        analysis_work._TAB_KANA_LAST[:] = [None, None]

    def test_answers_with_tab_context(self):
        with patch.dict(sys.modules, {'tab_context': stand_in_module()}):
            for text, want in (('abc def\nx = 1', False), ('abc\nあ', True), ('😀 smile', False),
                               ('😀あ', True), ('ＡＢＣ', False), ('カタカナ only', True)):
                analysis_work._TAB_KANA_LAST[:] = [None, None]
                self.assertIs(analysis_work.tab_has_kana(text), want, text)

    def test_none_without_tab_context(self):
        with patch.dict(sys.modules, {'tab_context': None}):
            self.assertIsNone(analysis_work.tab_has_kana('abc あ'))
        self.assertIsNone(analysis_work.tab_has_kana(None))


class WorkerPassesTests(unittest.TestCase):
    def run_line(self, correct_line, tab_kana):
        import analysis_worker, correction_entry
        seen = {}

        class Stop(Exception):
            pass

        def fake(*args, **kwargs):
            seen.update(kwargs)
            raise Stop()
        fake.__signature__ = __import__('inspect').signature(correct_line)
        runtime = analysis_worker.Runtime()
        runtime.store = runtime.decisions = runtime.context_vec = runtime.index = None
        with patch.object(correction_entry, 'correct_line', fake):
            with self.assertRaises(Stop):
                runtime._line_task(dict(kind='line', line='abc', context={}, input_method='kana', keyboard=None,
                                        nearby=(), readings=(), calculations=(), tab_has_kana=tab_kana))
        return seen

    def test_passed_when_correct_line_takes_it(self):
        def new_style(line, store, tab_has_kana=None, **kwargs):
            pass
        self.assertIs(self.run_line(new_style, False).get('tab_has_kana'), False)
        self.assertIs(self.run_line(new_style, True).get('tab_has_kana'), True)
        self.assertNotIn('tab_has_kana', self.run_line(new_style, None))

    def test_not_passed_to_an_older_correct_line(self):
        def old_style(line, store, context_vocab=None, decisions=None, input_method='kana', context_vec=None,
                      dict_index=None, nearby_words=(), recent_words=(), occurrence_readings=(),
                      occurrence_calculations=(), occurrence_strokes=()):
            pass
        self.assertNotIn('tab_has_kana', self.run_line(old_style, True))


class SavedAnalysisTests(unittest.TestCase):
    def test_kept_per_tab_and_not_used_under_another_answer(self):
        import analysis_cache
        result = dict(original='abc', corrected='abc', changed=False, details=[], spans=[], original_spans=[],
                      unsure_spans=[], odd_spans=[], analysis_status='complete')
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / 'analysis_cache.json')
            fingerprint = {'x': 1}
            with patch.object(analysis_cache, '_tab_kana', lambda text: False):
                if not analysis_cache.save(path, fingerprint, {'abc': [dict(result)]}):
                    self.skipTest('this result is not one the saved analysis keeps')
                self.assertEqual(list(analysis_cache.load(path, fingerprint)), ['abc'])
            with open(path, encoding='utf-8') as f:
                self.assertIs(json.load(f)['tabs'][0]['tab_has_kana'], False)
            with patch.object(analysis_cache, '_tab_kana', lambda text: True):
                self.assertEqual(analysis_cache.load(path, fingerprint), {})


def child():
    import tkinter as tk
    from unittest.mock import Mock
    assert Path('.tab-kana-isolated').exists() and Path('tab_context.py').exists()
    import app, analysis_work_app as work, analysis_async
    from session import new_tab
    text = 'hello world\nx = 1 + 2\nsmile 😀'
    Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False,
                                                     unified_autofix=False)), encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text)])), encoding='utf8')
    root = tk.Tk(); root.withdraw(); a = None; errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    sent = []
    original_request = analysis_async._request

    def watch(app_, task, scope, background=False):
        if task.get('kind') == 'line':
            sent.append((task['line'], task.get('tab_has_kana')))
        return original_request(app_, task, scope, background=background)

    def until(fn, seconds=90):
        end = time.monotonic() + seconds
        while True:
            root.update(); assert not errors, errors
            if fn(): return
            assert time.monotonic() < end, 'timeout'; time.sleep(.004)

    def complete():
        until(lambda: not a._foreground_analysis_pending() and a._analyze_work == work.token(a))
    try:
        with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
                patch.object(app.CorrectNoteApp, '_learn_now', lambda *v: None), \
                patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *v: None), \
                patch.object(analysis_async, '_request', watch):
            a = app.CorrectNoteApp(root); root.geometry('900x400+-6000+-6000'); root.deiconify(); complete()
            english = [k for line, k in sent if line.strip()]
            assert english and all(k is False for k in english), sent
            assert a.line_results[0].get('_tab_has_kana') is False, a.line_results[0]
            sent.clear()
            a.editor.insert('2.end', ' あ'); a._on_change(); complete()
            redone = {line: k for line, k in sent}
            assert redone.get('hello world') is True, sent        # an untouched row is made again
            assert a.line_results[0].get('_tab_has_kana') is True, a.line_results[0]
            print('TAB_KANA_WIRING_OK: English tab False, a kana makes every row again with True', flush=True)
            a._on_close(); a = None
    finally:
        if a: a._on_close()
        else:
            try: root.destroy()
            except tk.TclError: pass
    assert not errors, errors


class TabKanaAppTests(unittest.TestCase):
    def test_real_app_sends_the_tab_answer_and_remakes_rows(self):
        from bundle_manifest import NAMES
        src = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-tab-kana-') as folder:
            dest = Path(folder)
            for p in src.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES): shutil.copyfile(p, dest / p.name)
            # The real tab_context (correction side, 2026-10-26) is used when it is here — the stand-in has no
            # tab_kana(), which correction_entry needs; the stand-in only fills in for a tree without it.
            if not (dest / 'tab_context.py').exists():
                (dest / 'tab_context.py').write_text(STAND_IN, encoding='utf-8')    # this copy only
            (dest / '.tab-kana-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-u', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8', timeout=240)
            print(run.stdout, flush=True); self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn('TAB_KANA_WIRING_OK', run.stdout)


if __name__ == '__main__':
    child() if '--child' in sys.argv else unittest.main()
