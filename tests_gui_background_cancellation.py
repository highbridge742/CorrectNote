# -*- coding: utf-8 -*-
"""Opening a partly prefetched tab keeps its completed row and cancels the rest."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest


def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_worker,analysis_work_app as work
    from session import new_tab
    assert (Path.cwd()/'.ui-test-isolated').is_file()
    first='最初の資料です。';complete='次の資料です。'
    # Include the editor's normal trailing blank area in the synthetic document,
    # so exact source equality checks all supplied text without trimming it.
    following=complete+'\n処理がじゃのになっていないだろうか'+'\n'*app.CorrectNoteApp.TRAILING_BLANK_LINES
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text=first),new_tab(text=following)]),ensure_ascii=False),encoding='utf8')
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf8')
    root=tk.Tk();root.withdraw();a=None;errors=[];calls=[]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    original=analysis_worker.Worker.submit
    def submit(worker,task,state=None):
        calls.append((worker,dict(task),state is not None))
        return original(worker,task,state)
    def until(predicate,seconds=75):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            root.update();assert not errors,errors
            if predicate():return
            time.sleep(.005)
        raise AssertionError(('condition timed out',a.status.cget('text')))
    def inflight():
        st=getattr(a,'_bg',None)
        return bool(st and st['pos']==1 and getattr(a,'_async_background_request',None))
    def done():
        return (a._warmup is None and getattr(a,'_async_context_scope',None) is None
                and a._analyze_text==a.editor_source_text()
                and a._analyze_pos>=len(a._analyze_todo)
                and a._analyze_dependencies==analysis_worker.state_key(a)
                and a._analyze_work==work.token(a))
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None),patch.object(analysis_worker.Worker,'submit',submit):
        try:
            a=app.CorrectNoteApp(root);until(inflight)
            worker=a._prefetch_worker;process=worker.process
            saved=dict(a._bg['results'][0]);before=len(calls)
            a._switch_tab(1)
            sent=[task for owner,task,state in calls[before:] if owner is worker and task['kind']=='cancel']
            assert sent==[{'kind':'cancel'}],sent
            assert process.is_alive() and a._prefetch_worker is worker
            until(done)
            assert a.editor_source_text()==following,(repr(a.editor_source_text()),repr(following),getattr(a,'_tab_warming',None))
            assert a.line_results[0]==saved,(a.line_results[0],saved)
            first_repeated=[task for owner,task,state in calls[before:] if task['kind']=='line' and task['line']==complete]
            assert not first_repeated,first_repeated
            assert all(row.get('analysis_status')=='complete' for row in a.line_results if row.get('original'))
            assert all(row['original']==line for row,line in zip(a.line_results,following.split('\n')))
            assert not errors,errors
            print('CANCELLED_OBSOLETE_PREFETCH; COMPLETED_ROW_REUSED; CURRENT_TAB_FINISHED',flush=True)
        finally:
            if a is not None:a._on_close()
            else:root.destroy()


def parent():
    from bundle_manifest import NAMES
    source=Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='correctnote-bg-cancel-') as folder:
        dest=Path(folder)
        for p in source.iterdir():
            if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copyfile(p,dest/p.name)
        (dest/'.ui-test-isolated').touch()
        run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',errors='replace',timeout=170)
        print(run.stdout,flush=True)
        assert run.returncode==0,run.stdout


class BackgroundCancellationTkTests(unittest.TestCase):
    def test_opening_inflight_tab_keeps_finished_rows_and_stops_discarded_work(self):parent()


if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:unittest.main()
