# -*- coding: utf-8 -*-
"""An IME commit in quick input is corrected without a key release, as in the memo.

2026-10-21 うにさん: 「興亜劇」 became 「攻撃」 in the memo but stayed in quick
input. The engine corrected it either way; quick input only started its work on
<KeyRelease>, which an IME commit does not always send. This replays a commit
of a different made-up typo with pseudo clause readings, in an owned copy,
with transparent windows that never take focus and no clipboard."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path

LINE='作業が官僚しました。'
CLAUSES=(('作業が','さぎょうが'),('官僚','かんりょう'),('しました','しました'),('。','。'))
FIXED='作業が完了しました。'


def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app as work
    from analysis_worker import Worker
    from analysis_work import Occurrence
    from session import new_tab
    assert Path('.quick-ime-commit-owned').exists()
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False,
        unified_autofix=False,quick_autofix=True,quick_close_clipboard=False,quick_paste_back=False,
        memory_usage='high')),encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='')])),encoding='utf8')
    root=tk.Tk();root.attributes('-alpha',0.0);root.withdraw();a=None;errors=[];sent=[]
    root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
    def forbid(*args,**kwargs):raise AssertionError('No clipboard access')
    root.clipboard_clear=root.clipboard_append=root.clipboard_get=forbid
    root.tk.eval('rename clipboard {}; proc clipboard {args} {error "No clipboard access"}')
    original_submit=Worker.submit
    def submitted(worker,task,state=None):
        if a is not None and worker is getattr(a,'_quick_worker',None):sent.append(dict(task))
        return original_submit(worker,task,state)
    original_toplevel=tk.Toplevel.__init__
    def transparent(self,*args,**kwargs):
        original_toplevel(self,*args,**kwargs)
        self.attributes('-alpha',0.0)
    def until(test,seconds=120):
        end=time.monotonic()+seconds
        while True:
            root.update();assert not errors,errors
            if test():return
            assert time.monotonic()<end,('timeout',sent[-1:] if sent else None)
            time.sleep(.004)
    try:
        with patch.object(app,'GlobalHotkeys',return_value=Mock()),\
             patch.object(app.CorrectNoteApp,'_learn_now',lambda *args:None),\
             patch.object(app.CorrectNoteApp,'_focus_quick_window',lambda *args,**kwargs:None),\
             patch.object(tk.Toplevel,'winfo_pointerxy',return_value=(300,200)),\
             patch.object(tk.Toplevel,'__init__',transparent),\
             patch.object(Worker,'submit',submitted):
            a=app.CorrectNoteApp(root);root.attributes('-alpha',0.0)
            until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
            a._open_quick_capture();text=a._quick_text;root.update()
            ranges=a._quick_ime_result_events.ranges
            # One IME commit: results first, then the native insertion. No key
            # release follows, and the test never calls _on_quick_change.
            ranges.begin()
            for surface,reading in CLAUSES:ranges.result(surface,reading)
            text.insert('end-1c',LINE)
            ranges.finish()
            until(lambda:text.get('1.0','end-1c')==FIXED,30)
            task=next(t for t in sent if t['kind']=='quick' and t['lines']==[LINE])
            assert Occurrence(3,5,'官僚','かんりょう') in task['readings'][0],task['readings']
            print('QUICK_IME_COMMIT_OK',repr(text.get('1.0','end-1c')),flush=True)
            text.delete('1.0','end');root.update()
            a._close_quick_capture()
    finally:
        if a:
            if getattr(a,'_quick_win',None) is not None:
                a._quick_text.delete('1.0','end');a._close_quick_capture()
            a._on_close()
        else:root.destroy()
    assert not errors,errors


class QuickImeCommitGuiTests(unittest.TestCase):
    def test_commit_without_key_release_is_corrected(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-quick-ime-commit-') as folder:
            dest=Path(folder)
            for path in source.iterdir():
                if path.is_file() and (path.suffix=='.py' or path.name in NAMES):shutil.copyfile(path,dest/path.name)
            (dest/'.quick-ime-commit-owned').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,
                               stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=240)
            print(run.stdout[-4000:],flush=True)
            self.assertEqual(run.returncode,0,run.stdout[-4000:])
            self.assertIn('QUICK_IME_COMMIT_OK',run.stdout)

if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
