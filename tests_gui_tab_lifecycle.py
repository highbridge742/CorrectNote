# -*- coding: utf-8 -*-
"""Long-lived initial-state tab cache probe; learning is replaced with a no-op."""
import json,sys,time,traceback,unittest
from pathlib import Path

def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app as input_work,analysis_worker
    from session import new_tab
    assert (Path.cwd()/'.ui-test-isolated').is_file()
    sources=['最初の資料です。']+['確認用の文書です。番号'+str(i)+'。' for i in range(1,15)]
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text=s) for s in sources]),ensure_ascii=False),encoding='utf-8')
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf-8')
    root=tk.Tk();root.withdraw();errors=[];calls=[];a=None;events=[]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    original=analysis_worker.Worker.submit
    def submit(worker,task,state=None):
        calls.append((task['kind'],task.get('line'),time.monotonic()))
        return original(worker,task,state)
    def until(predicate,seconds=100):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update();assert not errors,errors
            if predicate():return
            time.sleep(.005)
        raise AssertionError(('timeout',getattr(a,'_bg',None),getattr(a,'_bg_texts',None),getattr(a,'_async_request',None)))
    def done():
        return (a._warmup is None and getattr(a,'_async_context_scope',None) is None
            and a._analyze_text==a.editor_source_text() and a._analyze_pos>=len(a._analyze_todo)
            and a._analyze_dependencies==analysis_worker.state_key(a) and a._analyze_work==input_work.token(a))
    def quiet():return a._bg_job is None and a._bg is None and not a._bg_texts
    def record(name,ok,**values):
        item=dict(name=name,ok=bool(ok),**values);events.append(item)
        print('CASE '+json.dumps(item,ensure_ascii=False),flush=True)
    def count(kind):return sum(k==kind for k,_,_ in calls)
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None),patch.object(analysis_worker.Worker,'submit',submit):
        try:
            a=app.CorrectNoteApp(root);until(done)
            initial_store=a.store.revision()
            # Never call _start_background_tabs here: the normal finish path must do it.
            until(lambda:any(line==sources[1] for kind,line,_ in calls if kind=='line'))
            until(quiet)
            analyzed={line for kind,line,_ in calls if kind=='line'}
            record('automatic_background_visits_all_open_tabs',all(s in analyzed for s in sources),analyzed=len(analyzed),cached=len(a._analysis_cache))
            before=(count('line'),count('units'),count('prepare'))
            a._switch_tab(1);until(done);a._switch_tab(0);until(done)
            delta=[count(k)-n for k,n in zip(('line','units','prepare'),before)]
            record('completed_tabs_restore_without_recomputing',delta==[0,0,0],calls=delta)
            # Occurrence readings remain volatile; no vocabulary growth or saved IME pair.
            a.editor.mark_set('insert','1.5')
            assert input_work.remember(a,'資料','しりょう')
            a._analyze_if_changed();until(done)
            assert input_work.has_readings(a)
            before=(count('line'),count('units'),count('prepare'))
            a._switch_tab(1);until(done);a._switch_tab(0);until(done)
            delta=[count(k)-n for k,n in zip(('line','units','prepare'),before)]
            record('ime_occurrence_tab_restores_without_recomputing',delta==[0,0,0],calls=delta,reading_retained=input_work.has_readings(a))
            record('store_remains_initial',a.store.revision()==initial_store)
            print('TAB_REPORT '+json.dumps(events,ensure_ascii=False),flush=True)
        finally:
            if a is not None:a._on_close()
            else:root.destroy()

def parent():
    import shutil,tempfile,subprocess
    source=Path(__file__).resolve().parent
    sys.path.insert(0,str(source));from bundle_manifest import NAMES
    with tempfile.TemporaryDirectory(prefix='correctnote-tabs-') as folder:
        dest=Path(folder)
        for p in source.iterdir():
            if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
        shutil.copy2(__file__,dest/'tests_gui_tab_lifecycle.py');(dest/'.ui-test-isolated').touch()
        result=subprocess.run([sys.executable,'-X','utf8',str(dest/'tests_gui_tab_lifecycle.py'),'--child'],cwd=dest,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',timeout=240)
        print(result.stdout,flush=True)
        if result.returncode:raise AssertionError(result.stdout)
        report=json.loads(next(line[len('TAB_REPORT '):] for line in result.stdout.splitlines() if line.startswith('TAB_REPORT ')))
        return report
class TabLifecycleTkTests(unittest.TestCase):
    def test_many_completed_tabs_and_live_ime_resume_automatically(self):
        report=parent()
        self.assertEqual(len(report),4)
        self.assertTrue(all(item['ok'] for item in report),report)

if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:unittest.main()