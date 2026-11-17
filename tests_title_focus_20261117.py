"""本文の中のタイトルの行のカーソルを、裏の仕事が本文へ移さない（2026-11-17 うにさん「タイトルにカーソルを置いていた
のに、本文にフォーカスが意図せず移るときがある」）。解析の答えの反映（_refresh_after_analysis）がカーソルを置き直し、
見えないカーソルが本文の1行目へ移って、次の打鍵が本文へ入っていた。作り物のタブ・写しのフォルダの中だけで動かす。"""
from pathlib import Path
import json, os, shutil, subprocess, sys, tempfile, time, traceback, unittest


def child(keep):
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    assert Path('.title-focus-isolated').exists()
    Path('settings.json').write_text(json.dumps(dict(layout='unified', input_method='kana', input_method_auto=False,
                                                     unified_autofix=True)), encoding='utf8')
    body = '\n'.join('これは試しの%d行目です。きょうはいいてんきですね。' % i for i in range(60))
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=body), new_tab(text='別の本文。')])),
                                    encoding='utf8')
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *v: None):
        a = app.CorrectNoteApp(root)
        root.geometry('900x600+0+0')
        root.deiconify()

        def pump(sec):
            end = time.monotonic() + sec
            while time.monotonic() < end:
                root.update()
                time.sleep(0.01)
        pump(2)
        toc = a._title_toc
        toc.set_title('試しの題')
        pump(0.5)
        moved = []
        seen = {'n': 0}
        original = a._refresh_after_analysis

        def refresh(*args, **kw):
            seen['n'] += 1
            result = original(*args, **kw)
            if toc._active and toc._raw_row(a.editor) != 1:
                moved.append(seen['n'])
            return result
        a._refresh_after_analysis = refresh
        toc.enter_title(2)
        for ch in 'あいう':
            toc.title.insert('insert', ch)
            toc._sync_soon()
            a._on_change()
            pump(0.3)
        pump(6)
        print('REFRESHES', seen['n'], 'MOVED', len(moved), 'ACTIVE', toc._active, 'ROW', toc._raw_row(a.editor), flush=True)
        assert seen['n'] > 0
        if keep:
            assert not moved, moved
            assert toc._active and toc._raw_row(a.editor) == 1
        else:
            assert moved, 'the old behaviour should move the caret'
        a._on_close()
    assert not errors, errors
    print('TITLE_FOCUS_OK', keep, flush=True)


class TitleFocus(unittest.TestCase):
    def run_child(self, keep):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-title-focus-') as folder:
            dest = Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copyfile(p, dest / p.name)
            (dest / '.title-focus-isolated').touch()
            env = dict(os.environ)
            env.pop('PYTHONPATH', None)
            if not keep:
                env['CN_TITLE_KEEP_FOCUS'] = '0'
            run = subprocess.run([sys.executable, '-B', '-u', '-X', 'utf8', str(dest / Path(__file__).name), '--child',
                                  '1' if keep else '0'], cwd=dest, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf8', timeout=180)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            self.assertIn('TITLE_FOCUS_OK', run.stdout)

    def test_background_refresh_keeps_the_title_caret(self):
        self.run_child(True)

    def test_switch_back_shows_the_old_move(self):
        self.run_child(False)


if __name__ == '__main__':
    if '--child' in sys.argv:
        child(sys.argv[-1] == '1')
    else:
        unittest.main()
