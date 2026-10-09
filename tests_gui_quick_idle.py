# -*- coding: utf-8 -*-
"""An owned initial window prepares Quick resources without blocking input."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path

def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app as work,quick_analysis as Q
    from analysis_worker import Worker
    from session import new_tab
    assert Path('.quick-idle-owned').exists()
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False,unified_autofix=False)),encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='')])),encoding='utf8')
    root=tk.Tk();root.withdraw();a=None;errors=[];sent=[];ticks=[]
    root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
    def forbid(*args,**kwargs):raise AssertionError('No clipboard access')
    root.clipboard_clear=root.clipboard_append=root.clipboard_get=forbid
    original_submit=Worker.submit
    def submitted(worker,task,state=None):
        identifier=original_submit(worker,task,state)
        if a is not None and worker is getattr(a,'_quick_worker',None):
            sent.append((worker,dict(task),state is None,identifier))
        return identifier
    def until(test,seconds=90):
        end=time.monotonic()+seconds
        while True:
            root.update();assert not errors,errors
            if test():return
            assert time.monotonic()<end,('timeout',sent)
            time.sleep(.004)
    def tick():ticks.append(time.monotonic());root.after(20,tick)
    try:
        with patch.object(app,'GlobalHotkeys',return_value=Mock()),\
             patch.object(app.CorrectNoteApp,'_learn_now',lambda *args:None),\
             patch.object(tk.Toplevel,'winfo_pointerxy',return_value=(300,200)),\
             patch.object(Worker,'submit',submitted):
            a=app.CorrectNoteApp(root);root.geometry('1000x500+0+0');root.deiconify()
            until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
            a._open_quick_capture();text=a._quick_text
            until(lambda:any(task['kind']=='warmup' for worker,task,empty,identifier in sent))
            worker,task,empty,identifier=next(row for row in sent if row[1]['kind']=='warmup')
            assert empty and task=={'kind':'warmup'}
            tick();response=[]
            def ready():
                value=worker.poll(identifier)
                if value is not None:response.append(value)
                return bool(response)
            until(ready);assert response==[{'ready':True}],response
            assert len(ticks)>1,'Tk timer did not progress during public preparation'
            assert text.get('1.0','end-1c')==''
            text.insert('1.0','作業が官僚しました。');a._on_quick_change()
            until(lambda:getattr(a,'_quick_job',None) is None and getattr(a,'_quick_units_text',None)==text.get('1.0','end-1c'))
            assert any(task['kind']=='quick' and task['lines']==['作業が官僚しました。'] for worker,task,empty,identifier in sent)
            a._close_quick_capture()
            assert a._quick_prewarm_after_id is None
            assert sum(task['kind']=='warmup' for worker,task,empty,identifier in sent)==1
            print('QUICK_IDLE_GUI_OK public-only request, Tk ticks, actual quick response, close cleanup',flush=True)
    finally:
        if a:
            if getattr(a,'_quick_win',None) is not None:a._close_quick_capture()
            a._on_close()
        else:root.destroy()
    assert not errors,errors

class QuickIdleGuiTests(unittest.TestCase):
    def test_owned_quick_idle_resources_and_input(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-quick-idle-') as folder:
            dest=Path(folder)
            for path in source.iterdir():
                if path.is_file() and (path.suffix=='.py' or path.name in NAMES):shutil.copyfile(path,dest/path.name)
            (dest/'.quick-idle-owned').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=150)
            print(run.stdout,flush=True)
            self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('QUICK_IDLE_GUI_OK',run.stdout)

if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
