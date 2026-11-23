"""統合表示の自動反映を、打っていない行（版が上がって解き直した行・控えから戻した行）にも掛ける（2026-11-18 うにさん
「統合モードでアップデートが掛かると、補正表示になるだけで補正されない。ひとつにまとめる表示の自動反映するチェックが
オンなら、補正して文字を置き換える」）。作り物のタブ・写しのフォルダの中だけで動かす。"""
from pathlib import Path
import json, os, shutil, subprocess, sys, tempfile, time, traceback, unittest

TYPO = 'もじにゆうりょくのれんしゅう'


def child(on):
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    assert Path('.unified-reanalysis-isolated').exists()
    Path('settings.json').write_text(json.dumps(dict(layout='unified', input_method='kana', input_method_auto=False,
                                                     unified_autofix=True)), encoding='utf8')
    body = '\n'.join(['一行目です。', TYPO, '三行目です。'])
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=body)])), encoding='utf8')
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *v: None):
        a = app.CorrectNoteApp(root)
        root.geometry('900x500+0+0')
        root.deiconify()
        a.editor.mark_set('insert', '1.0')
        end = time.monotonic() + 120
        while time.monotonic() < end:
            root.update()
            time.sleep(0.01)
            if (not a._foreground_analysis_pending() and a._analyze_pos >= len(a._analyze_todo)
                    and len(a.line_results) > 1 and a.line_results[1].get('corrected') not in (None, TYPO)):
                for _ in range(100):
                    root.update()
                    time.sleep(0.01)
                break
        row2 = a.editor.get('2.0', '2.end')
        fixed = a.line_results[1].get('corrected')
        print('ROW2', row2 == fixed, row2 == TYPO, 'answer_differs', fixed != TYPO, flush=True)
        assert fixed and fixed != TYPO                                  # 補正の答えは直しを持つ（中身は補正の側で決まる）
        if on:
            assert row2 == fixed, (row2 == TYPO)
            a.editor.event_generate('<<Undo>>')
            for _ in range(30):
                root.update()
            assert a.editor.get('2.0', '2.end') == TYPO                 # 1まとまりで戻せる
        else:
            assert row2 == TYPO, row2                                   # 前の動き: 色だけ
        a._on_close()
    assert not errors, errors
    print('UNIFIED_REANALYSIS_OK', on, flush=True)


def child_restart(phase, keep):
    """自動反映を Ctrl+Z で戻して閉じ、起動し直しても、戻した行をまた置き換えない（2026-11-18・戻した印はメモリだけ）。"""
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    assert Path('.unified-reanalysis-isolated').exists()
    if phase == 'first':
        Path('settings.json').write_text(json.dumps(dict(layout='unified', input_method='kana', input_method_auto=False,
                                                         unified_autofix=True)), encoding='utf8')
        Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=chr(10).join(
            ['一行目です。', TYPO, '三行目です。']))])), encoding='utf8')
    root = tk.Tk()
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()),             patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *v: None):
        a = app.CorrectNoteApp(root)
        root.geometry('900x500+0+0')
        root.deiconify()

        def pump(sec, stop=None):
            end = time.monotonic() + sec
            while time.monotonic() < end:
                root.update()
                time.sleep(0.01)
                if stop is not None and stop():
                    return True
            return False
        a.editor.mark_set('insert', '1.0')
        if phase == 'first':
            assert pump(120, lambda: a.editor.get('2.0', '2.end') != TYPO)
            a.editor.event_generate('<<Undo>>')
            pump(1)
            assert a.editor.get('2.0', '2.end') == TYPO
            a.editor.mark_set('insert', '3.0')
            pump(4)
            assert a.editor.get('2.0', '2.end') == TYPO
            a._autofix_live_records()
            a._store_active_tab() if hasattr(a, '_store_active_tab') else None
        else:
            pump(25, lambda: a.editor.get('2.0', '2.end') != TYPO)
            row2 = a.editor.get('2.0', '2.end')
            print('RESTART_ROW2_KEPT', row2 == TYPO, flush=True)
            assert (row2 == TYPO) == keep, (row2 == TYPO)
        a._on_close()
    print('RESTART_OK', phase, flush=True)


class UnifiedReanalysis(unittest.TestCase):
    def run_child(self, on):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-unified-') as folder:
            dest = Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copyfile(p, dest / p.name)
            (dest / '.unified-reanalysis-isolated').touch()
            env = dict(os.environ)
            env.pop('PYTHONPATH', None)
            if not on:
                env['CN_UNIFIED_AUTOFIX_REANALYSIS'] = '0'
            run = subprocess.run([sys.executable, '-B', '-u', '-X', 'utf8', str(dest / Path(__file__).name), '--child',
                                  '1' if on else '0'], cwd=dest, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf8', timeout=200)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            self.assertIn('UNIFIED_REANALYSIS_OK', run.stdout)

    def test_untyped_row_is_replaced_when_autofix_is_on(self):
        self.run_child(True)

    def test_undone_row_stays_after_restart(self):
        self.run_restart(True)

    def test_without_the_kept_rows_it_is_replaced_again(self):
        self.run_restart(False)

    def run_restart(self, keep):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-unified-') as folder:
            dest = Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copyfile(p, dest / p.name)
            (dest / '.unified-reanalysis-isolated').touch()
            env = dict(os.environ)
            env.pop('PYTHONPATH', None)
            if not keep:
                env['CN_AUTOFIX_DECLINED_KEEP'] = '0'
            for phase in ('first', 'second'):
                run = subprocess.run([sys.executable, '-B', '-u', '-X', 'utf8', str(dest / Path(__file__).name), '--restart',
                                      phase, '1' if keep else '0'], cwd=dest, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, encoding='utf8', timeout=200)
                self.assertEqual(run.returncode, 0, run.stdout[-3000:])
                self.assertIn('RESTART_OK ' + phase, run.stdout)

    def test_switch_back_only_colours_it(self):
        self.run_child(False)


if __name__ == '__main__':
    if '--child' in sys.argv:
        child(sys.argv[-1] == '1')
    elif '--restart' in sys.argv:
        child_restart(sys.argv[-2], sys.argv[-1] == '1')
    else:
        unittest.main()
