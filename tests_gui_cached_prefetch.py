# -*- coding: utf-8 -*-
"""Native Tk regression: cached corrections are ready to display before tab entry."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest


def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_worker,analysis_work_app as work,tab_analysis
    from session import new_tab
    assert (Path.cwd()/'.ui-test-isolated').exists()
    assert Path(app.__file__).resolve().parent==Path.cwd().resolve()
    texts=['最初のメモです。','資料を確認します。\n\n明日の予定です。']
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,
        tabs=[new_tab(text=t) for t in texts]),ensure_ascii=False),encoding='utf-8')
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',
        input_method_auto=False)),encoding='utf-8')
    root=tk.Tk();root.withdraw();a=None;errors=[];calls=[];enabled=[False]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    original_poll=analysis_worker.Worker.poll
    identifiers={};display_lines=[];pause_after_first=[False]
    original_submit=analysis_worker.Worker.submit
    original_queue=app.CorrectNoteApp._queue_background_tabs
    def submit(worker,task,state=None):
        calls.append(task['kind'])
        identifier=original_submit(worker,task,state)
        identifiers[identifier]=task
        if task['kind']=='units':display_lines.append(task.get('line'))
        return identifier
    def poll(worker,identifier):
        value=original_poll(worker,identifier)
        task=identifiers.get(identifier,{})
        if value is not None and pause_after_first[0] and task.get('kind')=='units':
            a._last_interaction=time.monotonic()
            pause_after_first[0]=False
        return value
    def queue(instance,*args,**kwargs):
        if enabled[0]:return original_queue(instance,*args,**kwargs)
    def done():
        return (a._warmup is None and getattr(a,'_async_context_scope',None) is None
            and a._analyze_text==a.editor_source_text() and a._analyze_pos>=len(a._analyze_todo)
            and a._analyze_work==work.token(a) and a._analyze_dependencies==analysis_worker.state_key(a))
    def until(predicate,seconds=40):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update()
            if errors:raise AssertionError(errors)
            if predicate():return
            time.sleep(.005)
        raise AssertionError(dict(status=a.status.cget('text'),calls=calls,
            pending=getattr(a,'_async_request',None),background=getattr(a,'_bg',None)))
    with patch.object(app,'GlobalHotkeys',return_value=Mock()), \
            patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None), \
            patch.object(app.CorrectNoteApp,'_queue_background_tabs',queue), \
            patch.object(analysis_worker.Worker,'submit',submit), \
            patch.object(analysis_worker.Worker,'poll',poll):
        try:
            a=app.CorrectNoteApp(root);until(done)
            a._switch_tab(1);until(done)
            owner=work.owner_for_tab(a,a.session.tabs[1])
            original=list(tab_analysis.completed(a,texts[1],owner)['results'])
            a._switch_tab(0);until(done)
            # Keep exactly the correction values that disk-cache restoration
            # supplies. Display/context caches are volatile and start empty.
            a._completed_tabs.pop(owner,None)
            a._tab_units_cache={};a._async_contexts={}
            a._bg_parked={};a._analysis_cache[texts[1]]=original
            a._analysis_cache_dependencies[texts[1]]=analysis_worker.state_key(a)
            assert tab_analysis.text_results(a,texts[1],owner)==original
            before=len(calls);enabled[0]=True;a._start_background_tabs()
            until(lambda:tab_analysis.display_ready(tab_analysis.completed(a,texts[1],owner)))
            assert 'line' not in calls[before:], 'Saved corrections were recomputed'
            assert 'units' in calls[before:], 'No display work was performed'
            ready=tab_analysis.completed(a,texts[1],owner)
            assert ready['results']==original
            a.status.config(text='解析中… 42/1538 行')
            before=len(calls);a._switch_tab(1);until(done)
            assert a.status.cget('text')=='', 'Completed cached tab retained the previous tab analysis status'
            assert len(calls)==before, 'Opening the prefetched tab submitted extra work'
            assert a.result_view.get('1.0','end-1c').rstrip('\n')=='\n'.join(r['corrected'] for r in original)
            # Open the tab after one display row is complete. Foreground work
            # must take those prepared units even though full text values exist.
            a._switch_tab(0);until(done)
            a._stop_background_tabs();a._completed_tabs.pop(owner,None)
            a._tab_units_cache={};a._async_contexts={};a._bg_parked={}
            a._analysis_cache[texts[1]]=original
            a._analysis_cache_dependencies[texts[1]]=analysis_worker.state_key(a)
            start=len(display_lines);pause_after_first[0]=True;a._last_interaction=0
            a._start_background_tabs()
            until(lambda:a._bg is not None and a._bg['owner']==owner and a._bg['pos']>0)
            first=texts[1].split('\n')[0]
            assert display_lines[start:].count(first)==1
            a._switch_tab(1)
            assert a.status.cget('text').startswith('表示準備中'), 'Cached display work showed correction analysis on tab entry'
            until(done)
            assert display_lines[start:].count(first)==1, 'Opening a partially prefetched cached tab rebuilt its finished display row'
            # A different, uncached tab must not display the previous tab's progress.
            a.session.tabs.append(new_tab(text='未見の新しい資料です。'))
            a.status.config(text='解析中… 42/1538 行')
            a._switch_tab(len(a.session.tabs)-1)
            assert a.status.cget('text')!='解析中… 42/1538 行', 'New tab retained old tab progress'
            until(done)
            print('CACHED_RESULTS_PREFETCH_DISPLAY_PASSED',flush=True)
        finally:
            if a is not None:a._on_close()
            else:root.destroy()


class CachedPrefetchGuiTests(unittest.TestCase):
    def test_cached_results_get_display_prepared_before_tab_entry(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-cached-prefetch-') as folder:
            dest=Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            result=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child'],
                cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=150)
            self.assertEqual(result.returncode,0,result.stdout)
            self.assertIn('CACHED_RESULTS_PREFETCH_DISPLAY_PASSED',result.stdout)


if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:unittest.main()
