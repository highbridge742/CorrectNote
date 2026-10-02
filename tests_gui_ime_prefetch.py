"""Native edit/IME/prefetch lifecycle with synthetic data and ordinary timers."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path


def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    from types import SimpleNamespace
    import app,analysis_worker,analysis_work_app as work,tab_analysis
    from session import new_tab
    assert (Path.cwd()/'.ui-test-isolated').exists()
    assert Path(app.__file__).resolve().parent==Path.cwd().resolve()
    source='\n'.join(['資料を確認します。','寒ぃ日だ。','よいでしょぅか。']*10)
    next_text='\n'.join('次の資料を読みます。' for _ in range(12))
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf-8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text=s) for s in (source,next_text)]),ensure_ascii=False),encoding='utf-8')
    root=tk.Tk();root.withdraw();a=None;errors=[];calls=[];hold=[True];phase=['startup'];report=[]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    original_submit=analysis_worker.Worker.submit;original_poll=analysis_worker.Worker.poll
    def submit(worker,task,state=None):
        st=getattr(a,'_bg',None)
        background=worker is getattr(a,'_prefetch_worker',None)
        calls.append(dict(phase=phase[0],kind=task['kind'],line=task.get('line'),
                          background=background,pos=st['pos'] if background and st is not None else None))
        return original_submit(worker,task,state)
    def poll(worker,identifier):
        background=worker is getattr(a,'_prefetch_worker',None)
        pending=getattr(a,'_async_background_request',None) if background else None
        st=getattr(a,'_bg',None)
        if hold[0] and pending and pending[0][0]=='background' and st and st['pos']>=2:return None
        return original_poll(worker,identifier)
    def done():
        return (not a._foreground_analysis_pending() and a._analyze_text==a.editor_source_text()
                and a._analyze_work==work.token(a) and a._analyze_dependencies==analysis_worker.state_key(a))
    def waiting():
        st=getattr(a,'_bg',None)
        return st is not None and st['pos']==2 and st['dependencies']==analysis_worker.state_key(a)
    def until(predicate,seconds=100):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update();assert not errors,errors
            if predicate():return
            time.sleep(.005)
        raise AssertionError((phase[0],a.status.cget('text'),getattr(a,'_async_request',None),getattr(a,'_async_background_request',None)))
    def emit(**values):
        report.append(dict(phase=phase[0],**values));print('CASE',json.dumps(report[-1]),flush=True)
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *args:None),patch.object(analysis_worker.Worker,'submit',submit),patch.object(analysis_worker.Worker,'poll',poll):
        try:
            a=app.CorrectNoteApp(root);until(done);initial=a.store.revision()
            # Normal editing should use its usual 300 ms callback; no manual
            # _analyze/_start_background_tabs calls can mask a lost timer.
            phase[0]='plain_edit';a.editor.insert('15.end','1');a._on_change();until(done)
            count=sum(c['phase']==phase[0] and c['kind']=='line' and not c['background'] for c in calls)
            assert count==1,(phase[0],count);emit(reanalyzed=count)
            until(waiting)
            first_two=[dict(r) for r in a._bg['results'][:2]]
            for surface,reading in [('校閲','こうえつ'),('点検','てんけん'),('整理','せいり')]:
                phase[0]='ime_'+surface;start=len(calls)
                a.editor.mark_set('insert','15.end');a._ime_origin_work=work.token(a);a._ime_inserted_range=(None,None)
                a.editor.insert('insert',surface);a._remember_ime_pair(surface,reading);a._ime_origin_work=None;a._on_change()
                until(done);until(waiting)
                count=sum(c['kind']=='line' and not c['background'] for c in calls[start:])
                repeated=[c for c in calls[start:] if c['kind']=='line' and c['background'] and c['pos']<2]
                assert count<=5,(phase[0],count)
                assert not repeated,repeated
                assert a._bg['results'][:2]==first_two
                # Distant correction colors survive the pending edit.
                assert a.editor.tag_nextrange('suspect','2.0','2.end')
                emit(reanalyzed=count,repeated_prefetch_rows=len(repeated))
            # A cursor key and a real edit returning to the same source must
            # leave the normal resumption path alive as well.
            phase[0]='arrow_and_restored_source';start=len(calls)
            a._on_change(SimpleNamespace(keysym='Left',type='3'));until(lambda:a._after_id is None)
            a.editor.insert('1.0','x');a.editor.delete('1.0','1.1');a._on_change();until(done);until(waiting)
            assert not [c for c in calls[start:] if c['kind']=='line' and not c['background']]
            emit(reanalyzed=0)
            phase[0]='prefetch_complete';hold[0]=False
            owner=work.owner_for_tab(a,a.session.tabs[1])
            until(lambda:tab_analysis.display_ready(tab_analysis.completed(a,next_text,owner)))
            before=len(calls);a._switch_tab(1);until(done)
            assert len(calls)==before,'Opening the prepared next tab restarted work'
            emit(new_requests_on_switch=0)
            # Once complete, an unrelated pair must not invalidate another tab.
            phase[0]='completed_tab_after_ime';a._switch_tab(0);until(done)
            a.editor.mark_set('insert','15.end');a._ime_origin_work=work.token(a);a._ime_inserted_range=(None,None)
            a.editor.insert('insert','記録');a._remember_ime_pair('記録','きろく');a._ime_origin_work=None;a._on_change();until(done)
            assert tab_analysis.display_ready(tab_analysis.completed(a,next_text,owner))
            before=len(calls);a._switch_tab(1);until(done);assert len(calls)==before
            assert a.store.revision()==initial
            emit(new_requests_on_switch=0)
            print('IME_PREFETCH_OK',json.dumps(report,ensure_ascii=False),flush=True)
        finally:
            if a is not None:a._on_close()
            else:root.destroy()


class ImePrefetchGuiTests(unittest.TestCase):
    def test_typing_keeps_incremental_rows_and_next_tab_progress(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-ime-prefetch-') as folder:
            dest=Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            run=subprocess.run([sys.executable,'-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=300)
            print(run.stdout,flush=True)
            self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('IME_PREFETCH_OK',run.stdout)


if __name__=='__main__':
    child() if '--child' in sys.argv else unittest.main()
