"""Native Cut/Paste before debounce, across tabs, with synthetic input only."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path


def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_worker,analysis_work_app as work,tab_analysis
    from session import new_tab
    assert (Path.cwd()/'.ui-test-isolated').exists()
    assert Path(app.__file__).resolve().parent==Path.cwd().resolve()
    lines=['資料を確認します。番号%s'%i for i in range(40)]
    lines[2]='寒ぃ日だ。';lines[37]='よいでしょぅか。'
    source='\n'.join(lines);target='別の資料を読みます。'
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf-8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text=s) for s in (source,target)])),encoding='utf-8')
    root=tk.Tk();root.withdraw();a=None;errors=[];calls=[];phase=['startup'];report=[];hold=[None]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    # Keep Tk's real class bindings and undo grouping. Only clipboard storage
    # is interpreter-local, so this test cannot touch the user's clipboard.
    root.tk.eval('''
        rename clipboard test_original_clipboard
        proc clipboard {operation args} {
            switch -- $operation {
                clear {set ::test_clipboard {}}
                append {append ::test_clipboard [lindex $args end]}
                get {return $::test_clipboard}
                default {error "Unexpected clipboard operation"}
            }
        }
        rename ::tk::GetSelection ::tk::test_original_GetSelection
        proc ::tk::GetSelection {w selection} {
            if {$selection eq "CLIPBOARD"} {return $::test_clipboard}
            return [::tk::test_original_GetSelection $w $selection]
        }
    ''')
    submit0=analysis_worker.Worker.submit;poll0=analysis_worker.Worker.poll
    def submit(worker,task,state=None):
        st=getattr(a,'_bg',None)
        calls.append(dict(phase=phase[0],kind=task['kind'],line=task.get('line'),
            owner=st['owner'] if st else work.owner(a) if a else None,background=bool(st)))
        return submit0(worker,task,state)
    def poll(worker,identifier):
        request=getattr(a,'_async_request',None)
        if hold[0] and request and request[0][0]==hold[0]:return None
        return poll0(worker,identifier)
    def done():
        return (not a._foreground_analysis_pending() and a._analyze_text==a.editor_source_text()
            and a._analyze_work==work.token(a) and a._analyze_dependencies==analysis_worker.state_key(a))
    def until(predicate,seconds=100):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            root.update();assert not errors,errors
            if predicate():return
            time.sleep(.005)
        raise AssertionError((phase[0],a.status.cget('text'),getattr(a,'_async_request',None)))
    def complete(index):
        tab=a.session.tabs[index]
        return tab_analysis.display_ready(tab_analysis.completed(a,tab['text'],work.owner_for_tab(a,tab)))
    def line_calls(owner):
        return [c for c in calls if c['phase']==phase[0] and c['kind']=='line' and c['owner']==owner]
    def colored():
        position=a.editor.search('よいでしょぅ','1.0')
        assert position and a.editor.tag_nextrange('suspect',position,position+' lineend'),('Lost tail color',phase[0],position)
    def cut(start,end):
        a.editor.tag_remove('sel','1.0','end');a.editor.tag_add('sel',start,end)
        selected=a.editor.get('sel.first','sel.last')
        a.editor.event_generate('<<Cut>>');a._on_change()
        assert root.tk.getvar('test_clipboard')==selected
        return selected
    def paste(index='1.0'):
        a.editor.tag_remove('sel','1.0','end');a.editor.mark_set('insert',index)
        a.editor.event_generate('<<Paste>>')
    def emit(**values):
        value=dict(phase=phase[0],**values);report.append(value)
        print('CASE',json.dumps(value,ensure_ascii=False),flush=True)
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *args:None),patch.object(analysis_worker.Worker,'submit',submit),patch.object(analysis_worker.Worker,'poll',poll):
        try:
            a=app.CorrectNoteApp(root);until(done);until(lambda:complete(1));initial=a.store.revision()
            owners=[work.owner_for_tab(a,t) for t in a.session.tabs]
            phase[0]='cut_paste_immediate_return';a.bookmarks.update({3,38})
            selected=cut('15.0','20.0');expected='\n'.join(lines[:14]+lines[19:])
            assert a.bookmarks=={3,33},a.bookmarks
            a._switch_tab(1);paste();a._switch_tab(0)
            assert a.editor_source_text().rstrip('\n')==expected
            colored();until(done);colored()
            assert len(line_calls(owners[0]))<=4,line_calls(owners[0])
            assert a.bookmarks=={3,33}
            emit(source_reanalyzed=len(line_calls(owners[0])),tail_color=True,bookmarks=sorted(a.bookmarks))
            until(lambda:complete(1));before=len(calls);a._switch_tab(1);until(done)
            assert len(calls)==before,'Paste destination prefetch was lost'
            assert a.editor_source_text().rstrip('\n')==selected+target
            emit(paste_target_reanalyzed=len(line_calls(owners[1])),prefetched_switch_requests=0)
            a._switch_tab(0);until(done)

            # Local IME readings must move with unchanged rows, not be borrowed
            # from the paste destination or compared as global offsets.
            doc=a._input_document;offset=0
            for line in doc.text.split('\n'):
                if line.startswith('資料'):assert doc.remember(offset,offset+2,'資料','しりょう')
                offset+=len(line)+1
            a._analyze();until(done);count_readings=len(doc.occurrences)
            phase[0]='cut_with_ime_prefetched_source'
            selected=cut('12.0','16.0');current=a.editor_source_text().rstrip('\n')
            assert len(doc.occurrences)==count_readings-4
            a._switch_tab(1);paste('end-1c');until(done);until(lambda:complete(0))
            source_calls=line_calls(owners[0]);assert len(source_calls)<=4,source_calls
            before=len(calls);a._switch_tab(0);until(done);colored()
            assert len(calls)==before,'Prefetched dirty source restarted'
            assert a.editor_source_text().rstrip('\n')==current
            assert len(a._input_document.occurrences)==count_readings-4
            emit(source_reanalyzed=len(source_calls),retained_readings=len(doc.occurrences),prefetched_switch_requests=0)

            # Several edits and tab swaps can precede even context preparation.
            phase[0]='repeated_edits_before_prepare';before_text=a.editor_source_text().rstrip('\n')
            for unused in range(3):
                a.editor.insert('8.end','。');a._on_change()
                a._switch_tab(1);a._switch_tab(0);colored()
            until(done);colored()
            edited=line_calls(owners[0]);assert 1<=len(edited)<=5,edited
            assert a.editor.get('8.0','8.end')==before_text.split('\n')[7]+'。。。'
            emit(source_reanalyzed=len(edited),tail_color=True)

            # Switch once preparation has started, but before its response.
            phase[0]='leave_during_prepare';hold[0]='prepare'
            a.editor.insert('9.end','追記');a._on_change()
            until(lambda:getattr(a,'_async_context_scope',None) is not None)
            a._switch_tab(1);a._switch_tab(0);colored();hold[0]=None
            until(done);colored();edited=line_calls(owners[0]);assert 1<=len(edited)<=5,edited
            emit(source_reanalyzed=len(edited),tail_color=True)
            assert a.store.revision()==initial
            print('CUT_TABS_OK',json.dumps(report,ensure_ascii=False),flush=True)
        finally:
            if a:a._on_close()
            else:root.destroy()


class CutTabGuiTests(unittest.TestCase):
    def test_cut_paste_and_dirty_tab_resumption(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-cut-tabs-') as folder:
            dest=Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            run=subprocess.run([sys.executable,'-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=300)
            print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('CUT_TABS_OK',run.stdout)


if __name__=='__main__':
    child() if '--child' in sys.argv else unittest.main()
