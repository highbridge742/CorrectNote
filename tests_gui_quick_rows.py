# -*- coding: utf-8 -*-
"""Real Quick edits invalidate only still-owned rows on an isolated desktop."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from copy import deepcopy
from pathlib import Path

def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app as work,quick_ime
    from analysis_worker import Worker
    from session import new_tab
    assert Path('.quick-rows-owned').exists()
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False,unified_autofix=False,quick_autofix=False)),encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='')])),encoding='utf8')
    root=tk.Tk();root.withdraw();a=None;errors=[];sent=[];clipboard=[]
    root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
    def forbid(*args,**kwargs):
        clipboard.append(True);raise AssertionError('No clipboard access')
    root.clipboard_clear=root.clipboard_append=root.clipboard_get=forbid
    root.tk.eval('rename clipboard {}; proc clipboard {args} {error "No clipboard access"}')
    original_submit=Worker.submit
    def submitted(worker,task,state=None):
        identifier=original_submit(worker,task,state)
        if a is not None and worker is getattr(a,'_quick_worker',None) and task['kind']=='quick':sent.append(deepcopy(task))
        return identifier
    def until(test,seconds=90):
        end=time.monotonic()+seconds
        while True:
            root.update();assert not errors,errors
            if test():return
            assert time.monotonic()<end,('timeout',[(s['lines'],list(s.get('reuse',{}))) for s in sent])
            time.sleep(.004)
    def settled(after):
        until(lambda:len(sent)>after and getattr(a,'_quick_job',None) is None
              and getattr(a,'_quick_after_id',None) is None
              and getattr(a,'_quick_units_text',None)==a._quick_text.get('1.0','end-1c'))
        assert all(r is None or r['analysis_status']=='complete' for r in a._quick_results)
    try:
        with patch.object(app,'GlobalHotkeys',return_value=Mock()),\
             patch.object(app.CorrectNoteApp,'_learn_now',lambda *args:None),\
             patch.object(tk.Toplevel,'winfo_pointerxy',return_value=(300,200)),\
             patch.object(quick_ime,'foreground_fullwidth_mode',return_value=0),\
             patch.object(Worker,'submit',submitted):
            a=app.CorrectNoteApp(root);root.geometry('1000x500+0+0');root.deiconify()
            until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
            main_before=a.editor.get('1.0','end-1c')
            a._show_quick_capture(incoming_mode=0,selection=None);text=a._quick_text
            text.insert('1.0','資料を保存しました。\n本を読む。\n橋を渡る。');a._on_quick_change();settled(0)
            first=deepcopy(a._quick_results);count=len(sent)
            text.replace('2.0','2.end','予定を確認します。');a._on_quick_change();settled(count)
            assert sorted(sent[-1].get('reuse',{}))==[0,2],sent[-1]
            assert a._quick_results[0]==first[0] and a._quick_results[2]==first[2]
            count=len(sent)
            text.replace('2.0','2.end','別の文');text.replace('2.0','2.end','予定を確認します。')
            a._on_quick_change();settled(count)
            assert sorted(sent[-1].get('reuse',{}))==[0,2],sent[-1]
            count=len(sent);text.insert('2.0','記録を残します。\n');a._on_quick_change();settled(count)
            assert sorted(sent[-1].get('reuse',{}))==[0],sent[-1]
            assert [r['original'] for r in a._quick_results]==text.get('1.0','end-1c').split('\n')
            count=len(sent);a.settings.set('quick_autofix',True)
            text.replace('2.0','2.end','寒ぃ日だ。');a._on_quick_change();settled(count)
            assert text.get('2.0','2.end')=='寒い日だ。',text.get('1.0','end-1c')
            changes=sent[count:]
            assert any(s['lines'][1]=='寒ぃ日だ。' and sorted(s.get('reuse',{}))==[0,2,3] for s in changes),changes
            assert any(s['lines'][1]=='寒い日だ。' and 1 not in s.get('reuse',{}) for s in changes),changes
            assert a.editor.get('1.0','end-1c')==main_before
            text.delete('1.0','end');a._close_quick_capture()
            assert a._quick_row_reuse is None and a._quick_text is None
            print('QUICK_ROWS_GUI_OK changed row, A-B-A, newline shifts, projection, close',flush=True)
    finally:
        if a:
            if getattr(a,'_quick_text',None) is not None:
                a._quick_text.delete('1.0','end');a._close_quick_capture()
            a._on_close()
        else:root.destroy()
    assert not errors and not clipboard,(errors,clipboard)

class QuickRowsGuiTests(unittest.TestCase):
    def test_owned_changed_row_and_automatic_projection(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-quick-rows-') as folder:
            dest=Path(folder)
            for path in source.iterdir():
                if path.is_file() and (path.suffix=='.py' or path.name in NAMES):shutil.copyfile(path,dest/path.name)
            (dest/'.quick-rows-owned').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=180)
            print(run.stdout,flush=True)
            self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('QUICK_ROWS_GUI_OK',run.stdout)

if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
