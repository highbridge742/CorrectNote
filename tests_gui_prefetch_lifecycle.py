"""Isolated native lifecycle probe with ordinary timers and long open documents."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest,os

def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app as work,analysis_worker,tab_analysis
    from session import new_tab
    if os.environ.get('CORRECTNOTE_PREFETCH_BUDGET'):
        import analysis_cache
        analysis_cache.MAX_CACHED_LINES=6
    assert (Path.cwd()/'.ui-test-isolated').exists()
    texts=['用船して補正\n霧が内容名も\n入力茶う\n伝え二言で\nの日っています\n的買い\n纏外\nなどの下場合\nしたあと\n1-2+3\n\n集亜量が\nモーシろょん\nも～所論\n他の行とえ同じ',
           '次の資料を確認します。\n新しい予定を読みます。',
           '\n'.join('資料を確認します。' for _ in range(120)),
           '\n'.join('明日の予定を確認します。' for _ in range(120)),
           '最後のメモです。']
    if os.environ.get('CORRECTNOTE_PREFETCH_IME_EDITS'):
        texts=['先頭の文です。\n'+'\n'.join('資料を確認します。' for _ in range(40))+'\nすきにん\t\n終端の文です。',
               '\n'.join('次の資料を読みます。' for _ in range(18)),
               '\n'.join('別の予定を確認します。' for _ in range(24))]
    if os.environ.get('CORRECTNOTE_PREFETCH_SEARCH'):
        texts=['先頭の文です。\n'+'\n'.join('資料を確認します。' for _ in range(20))
               +'\n検索対象です。\n'+'\n'.join('資料を確認します。' for _ in range(20))
               +'\nすきにん\t\n終端の文です。',
               '\n'.join('次の資料を読みます。' for _ in range(18)),
               '\n'.join('別の予定を確認します。' for _ in range(24))]
    if os.environ.get('CORRECTNOTE_PREFETCH_LARGE'):
        texts=['\n'.join('資料を確認します。' for _ in range(2065)),
               '次の資料を確認します。\n新しい予定を読みます。',
               '\n'.join('明日の予定を確認します。' for _ in range(983)),
               '最後のメモです。']
    if os.environ.get('CORRECTNOTE_PREFETCH_ORDER'):
        texts[2]='次に開く資料を確認します。'
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text=t) for t in texts]),ensure_ascii=False),encoding='utf-8')
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf-8')
    root=tk.Tk();root.withdraw();a=None;errors=[];calls=[];terminated=[];started=time.monotonic()
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    initial_revision=[None]
    original=analysis_worker.Worker.submit
    def submit(worker,task,state=None):
        calls.append((task['kind'],task.get('line')))
        if task['kind']=='prepare' and initial_revision[0] is None:
            initial_revision[0]=a.store.revision()
        background=getattr(a,'_bg',None)
        foreground_worker=worker is getattr(a,'_correction_worker',None)
        background_worker=worker is getattr(a,'_prefetch_worker',None)
        foreground=os.environ.get('CORRECTNOTE_FOREGROUND_RESTART')
        if (foreground and not terminated and task['kind']==foreground
                and foreground_worker and (foreground=='prepare' or getattr(a,'_analyze_pos',0)>=1)):
            finished={i:dict(a.line_results[i]) for i in getattr(a,'_analyze_todo',[])[:getattr(a,'_analyze_pos',0)]}
            terminated.append((worker.process.pid,finished))
            worker.process.terminate();worker.process.join(timeout=2)
            assert not worker.process.is_alive()

        if (os.environ.get('CORRECTNOTE_PREFETCH_RESTART') and not terminated
                and background_worker and background is not None and background['pos']>=1
                and task['kind'] in ('line','units')):
            # Kill only this test's child after one row is safely complete,
            # immediately before its next request enters the transport.
            terminated.append((worker.process.pid,background['owner'],background['results'][0]))
            worker.process.terminate();worker.process.join(timeout=2)
            assert not worker.process.is_alive()
        return original(worker,task,state)
    def done():
        return (not a._foreground_analysis_pending() and a._analyze_text==a.editor_source_text()
            and a._analyze_work==work.token(a) and a._analyze_dependencies==analysis_worker.state_key(a))
    def complete(index):
        tab=a.session.tabs[index]
        return tab_analysis.display_ready(tab_analysis.completed(a,tab['text'],work.owner_for_tab(a,tab)))
    def until(predicate,seconds=300):
        end=time.monotonic()+seconds;last=-1
        while time.monotonic()<end:
            root.update()
            if errors:raise AssertionError(errors)
            if predicate():return
            elapsed=int(time.monotonic()-started)
            if elapsed//15!=last:
                last=elapsed//15
                print('PROGRESS',elapsed,'pending',a._foreground_analysis_pending(),'status',a.status.cget('text'),
                    'ready',[i for i in range(len(texts)) if complete(i)],'jobs',len(calls),flush=True)
            time.sleep(.005)
        raise AssertionError(dict(status=a.status.cget('text'),scope=getattr(a,'_async_context_scope',None),
            bg=getattr(a,'_bg',None),pending=getattr(a,'_async_request',None)))
    with patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None),patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(analysis_worker.Worker,'submit',submit):
        try:
            a=app.CorrectNoteApp(root)
            if os.environ.get('CORRECTNOTE_PREFETCH_ORDER'):
                until(lambda:getattr(a,'_initial_setup',None) is None and getattr(a,'_async_context_scope',None) is not None)
                a._switch_tab(1);until(done)
                foreground_done=time.monotonic()
                until(lambda:complete(2),seconds=60)
                assert not complete(0),'The large previous tab delayed the next tab'
                print('NEXT_TAB_READY_BEFORE_PREVIOUS',round(time.monotonic()-foreground_done,2),flush=True)
                return
            if os.environ.get('CORRECTNOTE_PREFETCH_SWITCH'):
                until(lambda:getattr(a,'_initial_setup',None) is None and getattr(a,'_async_context_scope',None) is not None)
                for index in (2,1,3,1):
                    a._switch_tab(index)
                    root.update()
                a.editor.insert('2.end','\n追記した予定を確認します。')
                a._on_change()
                texts[1]+='\n追記した予定を確認します。'
                until(done)
                assert a.editor_source_text().rstrip('\n')==texts[1]
                until(lambda:all(complete(i) for i in range(len(texts)) if i!=1))
                assert not any(result.get('analysis_error') for result in a.line_results)
                print('INTERRUPTED_SWITCH_PREFETCH_PASSED',round(time.monotonic()-started,2),flush=True)
                return
            until(done)
            if os.environ.get('CORRECTNOTE_PREFETCH_BUDGET'):
                until(lambda:not any((getattr(a,'_bg_start_job',None),getattr(a,'_bg_job',None),getattr(a,'_bg',None),getattr(a,'_bg_texts',None))))
                assert all(complete(i) for i in range(len(texts))),'An open tab lost its completed result'
                before=len(calls)
                for index in range(len(texts)):
                    a._switch_tab(index);until(done)
                assert len(calls)==before,'An unchanged open tab needed new work'
                print('OPEN_TABS_KEEP_COMPLETED_RESULTS',flush=True)
                return
            if os.environ.get('CORRECTNOTE_FOREGROUND_RESTART'):
                assert len(terminated)==1,terminated
                old_pid,finished=terminated[0]
                assert a._correction_worker.process.pid!=old_pid
                assert all(a.line_results[i]==value for i,value in finished.items())
                assert not getattr(a,'_analyze_error_reported',False)
                assert not any(result.get('analysis_error') for result in a.line_results)
                print('FOREGROUND_RECOVERED',os.environ['CORRECTNOTE_FOREGROUND_RESTART'],flush=True)
            print('FOREGROUND_DONE',round(time.monotonic()-started,2),flush=True)
            until(lambda:all(complete(i) for i in range(1,len(texts))))
            print('ALL_PREFETCH_DONE',round(time.monotonic()-started,2),flush=True)
            if os.environ.get('CORRECTNOTE_PREFETCH_SEARCH'):
                doc=a._input_document;at=0
                # Synthetic actual readings on many unchanged rows expose
                # a global undo discard that plain-text cache checks miss.
                for line in doc.text.split('\n'):
                    if line=='資料を確認します。':
                        assert doc.remember(at,at+len(line),line,'しりょうをかくにんします')
                    at+=len(line)+1
                assert len(doc.occurrences)==40
                a._analyze();until(done)
                a.bookmarks.clear();a.bookmarks.update((5,18,35))
                def colored():
                    position=a.editor.search('すきにん','1.0')
                    assert position and 'suspect' in a.editor.tag_names(position),('Trailing color lost',position)
                colored();before=len(calls)
                a._current_pattern=lambda:app.searchlib.build_pattern('検索対象')
                a._find_replacement=tk.StringVar(root,value='検索結果\n追記した行')
                a._find_regex=tk.BooleanVar(root,value=False);a._find_status=Mock()
                a._do_replace_all()
                assert a.bookmarks=={5,18,36},a.bookmarks
                colored();until(done);colored()
                edited=[row for kind,row in calls[before:] if kind=='line']
                from context_vec import NEARBY_RADIUS
                assert len(edited)<=2+2*NEARBY_RADIUS,('Unrelated source rows reanalyzed',edited)
                assert '検索結果' in edited and '追記した行です。' in edited,edited
                assert len(a._input_document.occurrences)==40
                undo_counts=[]
                for operation,marks in ((a.editor.edit_undo,{5,18,35}),(a.editor.edit_redo,{5,18,36})):
                    prior=len(calls);operation();a._on_change()
                    assert a.bookmarks==marks,a.bookmarks
                    assert len(a._input_document.occurrences)==40
                    colored();until(done);colored()
                    count=sum(kind=='line' for kind,row in calls[prior:])
                    assert count<=2+2*NEARBY_RADIUS,('Undo reanalyzed unrelated reading rows',count)
                    undo_counts.append(count)
                until(lambda:all(complete(i) for i in (1,2)))
                before=len(calls);a._switch_tab(1);until(done);a._switch_tab(0);until(done)
                assert len(calls)==before,('Search invalidated prepared tabs',calls[before:])
                colored();assert a.bookmarks=={5,18,36}
                print('SEARCH_RANGES_PRESERVED',dict(reanalyzed=len(edited),undo_redo=undo_counts,retained_readings=len(a._input_document.occurrences),switch_requests=len(calls)-before),flush=True)
                return
            if os.environ.get('CORRECTNOTE_PREFETCH_IME_EDITS'):
                import ctypes as C
                from ctypes import wintypes as W
                import ime_events,ime_watch
                user=C.WinDLL('user32')
                user.SendMessageW.argtypes=[W.HWND,W.UINT,C.c_size_t,C.c_ssize_t]
                user.SendMessageW.restype=C.c_ssize_t
                def event(surface='橋',reading='ﾊｼ'):
                    with patch.object(ime_watch,'read_composition',return_value=dict(result=surface,result_reading=reading)):
                        user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_COMPOSITION,0,0xA00)
                def colored():
                    position=a.editor.search('すきにん','1.0')
                    assert position,'Unedited trailing source disappeared'
                    assert 'suspect' in a.editor.tag_names(position),('Trailing color disappeared',position,a.editor.tag_names(position))
                a.bookmarks.clear();a.bookmarks.update((5,18,35));expected=set(a.bookmarks)
                totals=[]
                for cycle in range(12):
                    before=len(calls)
                    for operation,line in (('insert',2),('delete',9),('insert',9),('delete',2)):
                        if operation=='insert':
                            user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_STARTCOMPOSITION,0,0)
                            a.editor.insert(f'{line}.0','追記した行です。')
                            event('追記した行です。','ﾂｲｷｼﾀｷﾞｮｳﾃﾞｽ')
                            user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_ENDCOMPOSITION,0,0)
                            a.editor.insert(f'{line}.8','\n')
                            a._drain_ime_result_events()
                            at=len(a.editor.get('1.0',f'{line}.0'))
                            assert any(o.start==at and o.end==at+8 and o.surface=='追記した行です。'
                                       and o.reading=='ついきしたぎょうです' for o in a._input_document.occurrences)
                            expected={row+1 if row>=line else row for row in expected}
                        else:
                            a.editor.delete(f'{line}.0',f'{line+1}.0')
                            expected={row-1 if row>line else row for row in expected}
                        a._on_change();event()
                        assert a.bookmarks==expected,(cycle,operation,line,a.bookmarks,expected)
                        colored();root.update();colored()
                        assert not errors,errors
                    until(done)
                    colored()
                    row_jobs=sum(kind=='line' for kind,text in calls[before:])
                    assert row_jobs<18,('A local edit reopened most rows',cycle,row_jobs)
                    totals.append(row_jobs)
                    until(lambda:all(complete(i) for i in (1,2)))
                    switch_before=len(calls)
                    a._switch_tab(1);until(done);a._switch_tab(0);until(done)
                    assert len(calls)==switch_before,('Prepared tab was reanalyzed',calls[switch_before:])
                    assert a.bookmarks==expected
                    assert a.editor_gutter.bookmarks is a.bookmarks and a.result_gutter.bookmarks is a.bookmarks
                    a._capture_session();assert a.session.current()['bookmarks']==sorted(expected)
                    if cycle%3==2:print('IME_EDIT_CYCLES',cycle+1,'row_requests',totals[-3:],flush=True)
                print('IME_EDIT_PREFETCH_BOOKMARK_COLOR_PASSED',sum(totals),flush=True)
                return
            if os.environ.get('CORRECTNOTE_PREFETCH_RESTART'):
                assert len(terminated)==1,terminated
                old_pid,owner,first=terminated[0]
                assert a._prefetch_worker.process.pid!=old_pid
                assert a._prefetch_worker.process.is_alive()
                index=next(i for i,tab in enumerate(a.session.tabs) if work.owner_for_tab(a,tab)==owner)
                saved=tab_analysis.completed(a,a.session.tabs[index]['text'],owner)
                assert saved['results'][0]==first
                assert not getattr(a,'_analyze_error_reported',False)
                print('DEAD_WORKER_RECOVERY_PASSED',flush=True)
            before=len(calls)
            for i in tuple(range(1,len(texts)))+(0,):a._switch_tab(i);until(done)
            assert len(calls)==before,('Prefetched switch restarted worker',calls[before:])
            print('PREFETCH_LIFECYCLE_PASSED',flush=True)
        finally:
            if a is not None:
                try:
                    baseline_revision=initial_revision[0]
                    if baseline_revision is not None and sys.exc_info()[0] is None:
                        assert a.store.revision()==baseline_revision,'Vocabulary grew during initial-state UI check'
                        print('INITIAL_VOCABULARY_UNCHANGED',flush=True)
                finally:a._on_close()
            else:root.destroy()

class PrefetchLifecycleTests(unittest.TestCase):
    def test_search_replacement_preserves_unedited_colors_bookmarks_and_prefetch(self):
        self.run_lifecycle(search=True)

    def test_ime_events_and_repeated_edits_keep_colors_bookmarks_and_prefetch(self):
        self.run_lifecycle(ime_edits=True)

    def test_idle_startup_prepares_every_tab_and_reuses_results(self):
        self.run_lifecycle()

    def test_dead_background_process_recovers_without_losing_finished_rows(self):
        self.run_lifecycle(restart=True)

    def test_open_tabs_keep_completed_results_when_disk_budget_is_small(self):
        self.run_lifecycle(budget=True)

    def test_dead_foreground_preparation_recovers_and_starts_prefetch(self):
        self.run_lifecycle(foreground='prepare')

    def test_dead_foreground_row_recovers_without_losing_completed_rows(self):
        self.run_lifecycle(foreground='line')

    def run_lifecycle(self,restart=False,budget=False,foreground=None,ime_edits=False,search=False):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-prefetch-lifecycle-') as directory:
            dest=Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            env=os.environ.copy()
            if ime_edits:env['CORRECTNOTE_PREFETCH_IME_EDITS']='1'
            if search:env['CORRECTNOTE_PREFETCH_SEARCH']='1'
            if restart:env['CORRECTNOTE_PREFETCH_RESTART']='1'
            if budget:env['CORRECTNOTE_PREFETCH_BUDGET']='1'
            if foreground:env['CORRECTNOTE_FOREGROUND_RESTART']=foreground
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,env=env,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=650)
            print(run.stdout,flush=True)
            self.assertEqual(run.returncode,0,run.stdout)

if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:unittest.main()
