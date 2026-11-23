# -*- coding: utf-8 -*-
"""本体が固まった時の記録（freeze_log・2026-11-23 うにさん「まだ入力後に4秒ほど固まるのがあります」）。
・1秒以上止まると、その時の Python の呼び出しの並び（ファイル名・行番号・関数名）が出る
・止まりの長さと、その間の Tk の命令ごとの回数・合計時間の1行が出る
・本文の字は書かない（行数・カーソルの行番号・その行の字数だけ）
・番犬の掛け直しは1回 1ms 未満
CN_FREEZE_LOG=0 で入れない。アプリを試しの写しで子として起こす。作った文だけ。run_on_desktop で回す。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SECRET = '秘密の本文の字です'

CHILD = r'''
import json, os, sys, time, traceback
from pathlib import Path
def main():
    here = Path.cwd().resolve()
    assert not (here / 'vocabulary.json').exists()
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    text = chr(10).join('%d行目は会議の資料を確認するための作った文です。' % i for i in range(1, 40))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk()
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.003)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1100x700+40+40')
        pump(3)
        ed = a.editor
        def block():
            ed.insert('end', os.environ['SECRET'])
            for _ in range(50):
                ed.count('1.0', 'end', 'displaylines')
            time.sleep(1.6)
        root.after(10, block)
        pump(2.5)
        ed.configure(insertwidth=7); pump(0.3)
        ed.configure(insertwidth=2); pump(0.3)
        log = getattr(a, '_freeze_log', None)
        out['installed'] = log is not None
        out['path'] = log.path if log is not None else None
        out['arm_ms'] = sorted(log.arm_ms)[len(log.arm_ms) // 2] if log is not None and log.arm_ms else None
        out['arm_max'] = max(log.arm_ms) if log is not None and log.arm_ms else None
        a._on_close() if False else None
        if log is not None:
            log.close()
        out['text'] = Path(log.path).read_text(encoding='utf-8', errors='replace') if log is not None and Path(log.path).exists() else ''
        open('child_out.json', 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False))
        os._exit(0)
if __name__ == '__main__':
    try:
        main()
    except Exception:
        open('child_out.json', 'w', encoding='utf-8').write(json.dumps({'error': traceback.format_exc()}))
        os._exit(1)
'''


def run_child(case, env_extra=None):
    here = Path(__file__).resolve().parent
    if here == Path(r'C:\CorrectNote') or (here / 'vocabulary.json').exists():
        case.skipTest('写しの中で回す')
    d = Path(tempfile.mkdtemp(prefix='cn-freezelog-'))
    for e in here.iterdir():
        if e.is_file() and e.name not in ('settings.json', 'session.json', 'vocabulary.json', 'last_choice.json'):
            shutil.copy2(e, d / e.name)
    (d / 'zz_child.py').write_text(CHILD, encoding='utf-8')
    env = dict(os.environ); env.pop('PYTHONPATH', None); env.update(env_extra or {}); env['SECRET'] = SECRET
    with open(d / 'child_err.txt', 'w', encoding='utf-8', errors='replace') as err:
        r = subprocess.run([sys.executable, '-B', '-X', 'utf8', 'zz_child.py'], cwd=d, env=env, timeout=200,
                           stdout=subprocess.DEVNULL, stderr=err)
    if not (d / 'child_out.json').exists():
        case.fail('child rc=%s %s' % (r.returncode, (d / 'child_err.txt').read_text(encoding='utf-8', errors='replace')[-3000:]))
    got = json.loads((d / 'child_out.json').read_text(encoding='utf-8'))
    shutil.rmtree(d, ignore_errors=True)
    case.assertNotIn('error', got, got.get('error'))
    return got


class FreezeLogInTheApp(unittest.TestCase):
    def test_a_freeze_is_logged_without_the_text(self):
        # 試験の写しには開発の印（freeze_log.enable）が無いので、CN_FREEZE_LOG=1 で入れる。呼び出しの並び（CN_FREEZE_LOG_STACK=1）
        # は、他のスレッドが動いている最中に書き出すとときどき落ちるので既定で取らない（ここでも試さない・2026-11-24）
        got = run_child(self, {'CN_FREEZE_LOG': '1'})
        self.assertTrue(got['installed'], got)
        text = got['text']
        self.assertIn('freeze ', text, text[-2000:])                          # 止まりの1行
        lines = [l for l in text.splitlines() if l.startswith('freeze ')]
        line = max(lines, key=lambda l: int(l.split('gap_ms=')[1].split()[0]))   # 起こした止まり（起動の止まりもある）
        gap = int(line.split('gap_ms=')[1].split()[0])
        self.assertGreaterEqual(gap, 1400, line)
        self.assertIn('count displaylines', line, line)                        # 止まりの間の Tk の命令（名前・回数・合計）
        self.assertNotIn('Thread 0x', text)                                    # 呼び出しの並びは既定で書かない
        self.assertNotIn(SECRET, text)                                        # 本文の字は書かない
        self.assertNotIn('会議の資料', text)
        self.assertLess(got['arm_ms'], 1.0, got)                              # 番犬の掛け直しは軽い
        self.assertIn('caret ', text)                                          # 入力カーソルの見え方が変わった時刻と値
        self.assertIn('width=7', text)
        self.assertIn('idlelag ', text)                                        # 暇が来る（画面が描かれる）までの遅れ
        self.assertIn('cbsum=', text)                                          # その間の手続きの合計

    def test_switch_off(self):
        got = run_child(self, {'CN_FREEZE_LOG': '0'})
        self.assertFalse(got['installed'], got)

    def test_off_without_the_dev_marker(self):
        # 公開版・試験の写し（開発の印が無い）では入らない（2026-11-24）
        got = run_child(self, {'CN_FREEZE_LOG': ''})                         # 切り替えの指定なし（空）
        self.assertFalse(got['installed'], got)

    def test_enabled_rules(self):
        import freeze_log
        d = Path(tempfile.mkdtemp(prefix='cn-flmark-'))
        self.assertFalse(freeze_log.enabled({}, frozen=False, folder=str(d)))         # 印が無い: 入れない
        (d / freeze_log.MARKER).write_text('', encoding='utf-8')
        self.assertTrue(freeze_log.enabled({}, frozen=False, folder=str(d)))          # 開発の PC（印あり）
        self.assertFalse(freeze_log.enabled({}, frozen=True, folder=str(d)))          # EXE は入れない
        self.assertFalse(freeze_log.enabled({'CN_FREEZE_LOG': '0'}, frozen=False, folder=str(d)))
        self.assertTrue(freeze_log.enabled({'CN_FREEZE_LOG': '1'}, frozen=True, folder=str(d)))
        self.assertFalse(freeze_log.stack_on({}))                                      # 呼び出しの並びは既定で取らない
        shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
