# -*- coding: utf-8 -*-
"""Hidden full-app integration tests; only synthetic data in a temporary copy."""
import json
from pathlib import Path
import shutil,subprocess,sys,tempfile,time,unittest


def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    from types import SimpleNamespace
    import app,analysis_work_app,analysis_worker
    from session import new_tab
    home=Path.cwd().resolve()
    assert (home/'.ui-test-isolated').is_file()
    assert Path(app.__file__).resolve().parent==home
    (home/'settings.json').write_text(json.dumps(dict(layout='unified',input_method='kana',input_method_auto=False)),encoding='utf-8')
    root=tk.Tk();root.withdraw();errors=[]
    import traceback
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    calls=[];blocked=set();hold=[True]
    original_submit=analysis_worker.Worker.submit
    original_poll=analysis_worker.Worker.poll
    later='今日も良い天気です。'
    def submit(worker,task,state=None):
        identifier=original_submit(worker,task,state)
        calls.append((task['kind'],task.get('line'),identifier))
        if task['kind']=='line' and task['line']==later and hold[0]:blocked.add(identifier)
        return identifier
    def poll(worker,identifier):
        if hold[0] and identifier in blocked:return None
        return original_poll(worker,identifier)
    instance=None
    gaps=[];last=[time.monotonic()]
    def tick():
        now=time.monotonic();gaps.append(now-last[0]);last[0]=now
        root.after(20,tick)
    def until(predicate,seconds=65):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update()
            assert not errors,errors
            if predicate():return
            time.sleep(.004)
        pending=getattr(instance,'_async_request',None)
        raise AssertionError(('timeout',pending,getattr(instance,'_analyze_last_error',None),instance.status.cget('text'),calls[-8:]))
    def done():
        return (instance._warmup is None and getattr(instance,'_async_context_scope',None) is None
            and getattr(instance,'_analyze_text',None)==instance.editor_source_text()
            and instance._analyze_pos>=len(instance._analyze_todo)
            and instance._analyze_dependencies==analysis_worker.state_key(instance)
            and instance._analyze_work==analysis_work_app.token(instance))
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None),patch.object(analysis_worker.Worker,'submit',submit),patch.object(analysis_worker.Worker,'poll',poll):
        try:
            instance=app.CorrectNoteApp(root)
            until(done)
            root.after(20,tick);gaps.clear();last[0]=time.monotonic()
            source='寒ぃ日だ。\n'+later+'\nよいでしょぅか。'
            instance.editor.delete('1.0','end');instance.editor.insert('1.0',source)
            for i,line in enumerate(source.split('\n'),1):instance._mark_typed(i,0,len(line))
            instance._sync_typed_shadow()
            work=analysis_work_app.token(instance)
            instance._analyze()
            until(lambda:instance.editor.get('1.0','1.end')=='寒い日だ。' and bool(blocked))
            assert analysis_work_app.token(instance)==work,'Automatic projection became a new input'
            assert not done(),'Expected later rows still pending'
            before=len(calls)
            instance.settings.set('layout','split');instance._apply_layout()
            assert instance.editor.get('1.0','1.end')=='寒ぃ日だ。'
            assert instance.result_view.get('1.0','1.end')=='寒い日だ。'
            instance.settings.set('layout','unified');instance._apply_layout()
            assert instance.editor.get('1.0','1.end')=='寒い日だ。'
            assert analysis_work_app.token(instance)==work
            assert len(calls)==before,'Layout started another engine task'
            # Saving a tab must preserve its owner and completed work.
            instance._capture_session()
            assert analysis_work_app.token(instance)==work
            instance.session.tabs.append(new_tab(text='これは別のタブです。'))
            t=time.monotonic();instance._switch_tab(1);switch_ms=(time.monotonic()-t)*1000
            assert instance.editor.get('1.0','1.end')=='これは別のタブです。'
            until(lambda:instance._analyze_text.startswith('これは別のタブ') and done())
            instance._switch_tab(0)
            until(lambda:bool(instance.line_results) and instance.line_results[0]['original']=='寒ぃ日だ。' and not instance.line_results[0].get('pending'))
            assert sum(k=='line' and line=='寒ぃ日だ。' for k,line,_ in calls)==1,('First row reanalysed',calls)
            hold[0]=False
            until(done)
            assert instance.line_results[0]['corrected']=='寒い日だ。'
            assert instance.line_results[2]['corrected']=='よいでしょうか。'
            # Fully cached tabs restore without another correction call.
            before=sum(k=='line' for k,_,_ in calls)
            instance._switch_tab(1);until(done)
            instance._switch_tab(0);until(done)
            assert sum(k=='line' for k,_,_ in calls)==before,('Cached tab reanalysed',calls)
            instance.settings.set('layout','split');instance._apply_layout()
            # Actual F2 menu construction, both cursor and exact range selection.
            first=next(u for u in instance.line_units[0] if u.get('detail'))
            menus=[]
            def capture(items,x,y):
                menus.append(items);instance._dropdown=Mock()
            with patch.object(instance,'_make_dropdown',capture),patch.object(instance,'_reject_correction') as reject:
                for selected in (False,True):
                    instance._close_dropdown();instance._clear_f2_target();instance._f2_cycle=None
                    instance.result_view.tag_remove('sel','1.0','end')
                    start='1.0+%dc'%first['start'];end='1.0+%dc'%first['end']
                    instance.result_view.mark_set('insert',end)
                    if selected:instance.result_view.tag_add('sel',start,end)
                    instance._on_f2_candidates(SimpleNamespace(widget=instance.result_view,keysym='F2',state=0))
                    assert menus,'F2 did not open a menu'
                    items=menus[-1];labels=[label for label,callback in items]
                    assert '― 自動補正 ―' in labels,labels
                    assert any('「寒ぃ」は今後直さない' in label for label in labels),labels
                    callback=next(cb for label,cb in items if '元の入力に戻す' in label)
                    callback();reject.assert_called_with(first['detail'][0],first['detail'][1])
            # Execute an actual menu action against synthetic stores, then
            # wait for the worker to observe the changed decision ledger.
            instance._reject_correction(first['detail'][0],first['detail'][1])
            until(done)
            assert instance.decisions.is_rejected(first['detail'][0],first['detail'][1])
            assert instance.line_results[0]['corrected']=='寒ぃ日だ。',(first,instance.line_results[0],instance.decisions.rejected_list(),calls[-8:])
            background='これは裏で解析する文章です。'
            instance.session.tabs.append(new_tab(text=background))
            instance._start_background_tabs()
            until(lambda:background in instance._analysis_cache)
            assert background in instance._tab_units_cache
            before=sum(k=='line' for k,_,_ in calls)
            instance._switch_tab(len(instance.session.tabs)-1);until(done)
            assert sum(k=='line' for k,_,_ in calls)==before,'Background cache was corrected again'
            instance._switch_tab(0);until(done)
            # A large tab prepares its context off Tk and can be edited/left
            # while the process is still working. All text here is synthetic.
            large='\n'.join('これは確認用の文章です。'+str(i) for i in range(1200))
            instance.session.tabs.append(new_tab(text=large))
            instance._switch_tab(len(instance.session.tabs)-1)
            until(lambda:bool(getattr(instance,'_async_context_scope',None)))
            old=analysis_work_app.token(instance)
            t=time.monotonic();instance.editor.insert('1.0','追記。');edit_ms=(time.monotonic()-t)*1000
            assert analysis_work_app.token(instance)!=old
            assert instance.editor.get('1.0','1.end').startswith('追記。')
            instance._switch_tab(0);until(done)
            assert edit_ms<250,('Large tab edit blocked',edit_ms)
            assert not getattr(instance,'_analyze_last_error',None),instance._analyze_last_error
            assert max(gaps,default=0)<1.0,('Tk blocked',max(gaps))
            print('UI_ANALYSIS_OK '+json.dumps(dict(tab_switch_ms=round(switch_ms,1),max_tick_gap_ms=round(max(gaps)*1000,1),engine_lines=sum(k=='line' for k,_,_ in calls)),ensure_ascii=False),flush=True)
        finally:
            if instance is not None:instance._on_close()
            else:root.destroy()
    assert not errors,errors


class AnalysisGuiTests(unittest.TestCase):
    def test_partial_projection_tabs_layout_and_f2(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-ui-') as folder:
            dest=Path(folder)
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix=='.py' or entry.name in NAMES):shutil.copy2(entry,dest/entry.name)
            (dest/'.ui-test-isolated').touch()
            result=subprocess.run([sys.executable,'-X','utf8',str(dest/'tests_gui_analysis.py'),'--child'],cwd=folder,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',timeout=150)
            self.assertEqual(result.returncode,0,result.stdout)
            self.assertIn('UI_ANALYSIS_OK ',result.stdout)
            print(result.stdout.strip())

if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:unittest.main()