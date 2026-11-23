"""控えから戻したタブで表示準備中に1字打っても、残りの行を補正からやり直さない（2026-11-20 うにさん「全体的な再解析が
あった」「打った字で新しい語が増えるとは何か？」「他の行を見る作りは無しにしたはず」）。
・残りの「組むだけ」の行は、打鍵の新しい段取りでも組むだけ（app._units_only_rows・CN_UNITS_ONLY_CARRY=0 で前の形）
・控えから戻した行にも、タブ全体の語（文脈）のどの鍵を読んだかの記録を残し、読んでいない行は文脈が動いても答えのまま
  （analysis_cache の 'ce'・CN_RESTORED_CONTEXT_PROOF=0 で前の形）
直しの前後で、補正のやり直しの数が減り、全部の行の答えが同じことを数字で確かめる。作り物のタブ・写しのフォルダの中だけ。"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile, time, traceback, unittest

ROWS = ['きょうはあめがふっているのでかさをもってでかけます。', '会議の資料を作成して、明日までに送ります。',
        'えいがをみにいったらとてもおもしろかった。', 'あしたのてんきはどうなるでしょうか。', '駅前の本屋で新しい本を買いました。']
N = 60


def child(phase):
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app, analysis_async
    from session import new_tab
    assert Path('.units-carry-isolated').exists()
    if phase == 'first':
        Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)),
                                         encoding='utf8')
        body = chr(10).join(ROWS[i % len(ROWS)] + str(i) for i in range(N))
        Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=body)])), encoding='utf8')
    sent = []
    orig = analysis_async.Worker.submit

    def submit(self, task, state=None):
        sent.append(task.get('kind'))
        return orig(self, task, state)
    analysis_async.Worker.submit = submit
    root = tk.Tk()
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *v: None):
        a = app.CorrectNoteApp(root)
        root.geometry('900x600+0+0')
        root.deiconify()

        def pump(sec, stop=None):
            end = time.monotonic() + sec
            while time.monotonic() < end:
                root.update()
                time.sleep(0.005)
                if stop is not None and stop():
                    return True
            return False

        def finished():
            return not a._foreground_analysis_pending() and a._analyze_pos >= len(a._analyze_todo)
        if phase == 'first':
            assert pump(170, finished)
            pump(1)
            a._save_analysis_cache()                    # 控えを直に書き出してから閉じる（毎回、控えから戻る形にする）
            assert os.path.getsize('analysis_cache.json') > 0
        else:
            assert pump(20, lambda: getattr(a, '_analyze_units_only', False)), 'not restored from the cache'
            sent.clear()
            a.editor.insert('1.0', 'あ')                  # 表示準備中に1字打つ（新しい語が増える字）
            a._on_change()
            assert pump(170, finished)
            pump(1)
            answers = hashlib.sha256('\n'.join(str((r or {}).get('corrected')) for r in a.line_results[1:])
                                     .encode('utf8')).hexdigest()[:12]
            print('RESULT full=%d units=%d answers=%s' % (sent.count('line'), sent.count('units'), answers), flush=True)
        a._on_close()
    print('CARRY_OK', phase, flush=True)


def run_mode(fixed):
    from bundle_manifest import NAMES
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='correctnote-carry-') as folder:
        dest = Path(folder)
        for p in source.iterdir():
            if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                shutil.copyfile(p, dest / p.name)
        (dest / '.units-carry-isolated').touch()
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        if not fixed:
            env['CN_UNITS_ONLY_CARRY'] = '0'
            env['CN_RESTORED_CONTEXT_PROOF'] = '0'
        out = ''
        for phase in ('first', 'second'):
            run = subprocess.run([sys.executable, '-B', '-u', '-X', 'utf8', str(dest / Path(__file__).name), '--child',
                                  phase], cwd=dest, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf8', timeout=200)
            out += run.stdout
            if run.returncode != 0 or ('CARRY_OK ' + phase) not in run.stdout:
                raise AssertionError(run.stdout[-3000:])
        line = [l for l in out.splitlines() if l.startswith('RESULT ')][0]
        parts = dict(p.split('=') for p in line.split()[1:])
        return int(parts['full']), int(parts['units']), parts['answers']


class UnitsOnlyCarry(unittest.TestCase):
    def test_fewer_redone_rows_and_the_same_answers(self):
        old_full, old_units, old_answers = run_mode(False)
        new_full, new_units, new_answers = run_mode(True)
        print('FULL before=%d after=%d' % (old_full, new_full), flush=True)
        self.assertGreaterEqual(old_full, N // 2)            # 前の動き: 残りの行が全部補正からやり直し
        self.assertLessEqual(new_full, 6)                    # 打った行（とその周り）だけ
        self.assertEqual(new_answers, old_answers)           # 打った行のほかの答えは、直しの前後で同じ


if __name__ == '__main__':
    if '--child' in sys.argv:
        child(sys.argv[-1])
    else:
        unittest.main()
