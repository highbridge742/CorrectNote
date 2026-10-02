# -*- coding: utf-8 -*-
"""Bookmarks stay current when saving or changing tabs during analysis preparation."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_worker,analysis_work_app as work
    from session import new_tab
    assert (Path.cwd()/'.ui-test-isolated').exists()
    text='先頭の文です。\n'+'\n'.join('同じ内容の行です。' for _ in range(18))+'\n末尾の文です。'
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf-8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text=text,bookmarks=[3,8,15]),new_tab(text='別のタブです。',bookmarks=[1])]),ensure_ascii=False),encoding='utf-8')
    root=tk.Tk();root.withdraw();a=None;errors=[];hold=[False]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    original=analysis_worker.Worker.poll
    def poll(worker,identifier):
        pending=getattr(a,'_async_request',None)
        if hold[0] and pending and pending[0][0]=='prepare':return None
        return original(worker,identifier)
    def until(predicate,seconds=100):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update();assert not errors,errors
            if predicate():return
            time.sleep(.005)
        raise AssertionError((a.status.cget('text'),getattr(a,'_async_request',None)))
    def done():
        return (not a._foreground_analysis_pending() and a._analyze_text==a.editor_source_text()
            and a._analyze_work==work.token(a) and a._analyze_dependencies==analysis_worker.state_key(a))
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *args:None),patch.object(analysis_worker.Worker,'poll',poll):
        try:
            a=app.CorrectNoteApp(root);until(done)
            root.attributes('-alpha',0);root.geometry('1400x720+10000+10000');root.deiconify();root.update()
            original_text=a.editor_source_text()
            toolbar=a.first_line_btn.master
            labels=[w.cget('text') for w in toolbar.pack_slaves() if w.winfo_class()=='Button']
            assert labels[:4]==['1行目','最終行','▲ 前のブックマーク','▼ 次のブックマーク'],labels
            def glyph_center(w,row):
                info=w.dlineinfo(f'{row}.0');assert info,(row,w.yview())
                ascent=int(w.tk.call('font','metrics',w.cget('font'),'-ascent'))
                height=int(w.tk.call('font','metrics',w.cget('font'),'-linespace'))
                return w.winfo_rooty()+info[1]+info[4]-ascent+height/2
            for window_height in (720,1400):
                root.geometry(f'1400x{window_height}+10000+10000');root.update()
                for target in (1,3,15,20):
                    a._goto_line(target);root.update()
                    middle=root.winfo_rooty()+root.winfo_height()/2
                    for w in (a.editor,a.result_view):
                        assert abs(glyph_center(w,target)-middle)<=2,(window_height,target,glyph_center(w,target),middle)
                    assert a.editor.index('insert')==f'{target}.0'
                    assert a.editor_source_text()==original_text
                a.last_line_btn.invoke();root.update()
                assert a.editor.index('insert')=='21.0'
                assert abs(glyph_center(a.editor,21)-(root.winfo_rooty()+root.winfo_height()/2))<=2
                a.first_line_btn.invoke();root.update()
                assert a.editor.index('insert')=='1.0'
                assert not a.editor.tag_ranges('navigation_head')
                assert not a.editor.tag_ranges('navigation_tail')
                assert a.editor_source_text()==original_text
            root.geometry('1400x720+10000+10000');root.update()
            # Toolbar and right-pane shortcuts share the central destination.
            a.bookmark_next_btn.invoke();root.update()
            assert a.editor.index('insert')=='3.0'
            assert abs(glyph_center(a.editor,3)-(root.winfo_rooty()+root.winfo_height()/2))<=2
            a.result_view.mark_set('insert','3.0')
            a._goto_bookmark(True,widget=a.result_view);root.update()
            assert a.result_view.index('insert')=='8.0'
            assert abs(glyph_center(a.result_view,8)-(root.winfo_rooty()+root.winfo_height()/2))<=2
            a._set_layout_unified();until(done);root.update()
            a.last_line_btn.invoke();root.update()
            assert a.editor.index('insert')=='21.0'
            assert abs(glyph_center(a.editor,21)-(root.winfo_rooty()+root.winfo_height()/2))<=2
            a._set_layout_split();until(done);root.update()
            a.first_line_btn.invoke();root.update()
            a.result_view.mark_set('insert','1.0')
            print('CENTERED_NAVIGATION_OK',flush=True)
            # Right-pane navigation follows the same surviving row while
            # analysis preparation is held. An old visual cursor must not
            # make Previous revisit the bookmark we are already on.
            a._goto_bookmark(True,widget=a.result_view)
            assert a.result_view.index('insert')=='3.0'
            hold[0]=True;a.editor.delete('1.0','2.0');a._on_change()
            a._goto_bookmark(False,widget=a.result_view)
            assert a.bookmarks=={2,7,14},a.bookmarks
            assert a.editor.index('insert')=='14.0',a.editor.index('insert')
            assert a.result_view.index('insert')=='14.0',a.result_view.index('insert')
            # Restore the synthetic first row before the existing lifecycle.
            a.editor.insert('1.0','先頭の文です。\n');a._on_change();a._render_corrected()
            assert a.bookmarks=={3,8,15},a.bookmarks
            assert a.result_view.index('insert')=='15.0',a.result_view.index('insert')
            hold[0]=True;a.editor.insert('1.0','追記した行です。\n');a._on_change()
            assert a.bookmarks=={4,9,16},a.bookmarks
            until(lambda:getattr(a,'_async_context_scope',None) is not None)
            a.editor.delete('2.0','3.0');a.editor.insert('11.0','さらに一行です。\n');a._on_change()
            assert a.bookmarks=={3,8,16},a.bookmarks
            a._capture_session();assert a.session.current()['bookmarks']==[3,8,16]
            a._switch_tab(1);assert a.bookmarks=={1},a.bookmarks
            hold[0]=False;until(done)
            a._switch_tab(0);until(done)
            assert a.bookmarks=={3,8,16},a.bookmarks
            assert a.editor_gutter.bookmarks is a.bookmarks
            assert a.result_gutter.bookmarks is a.bookmarks
            a._capture_session();assert a.session.current()['bookmarks']==[3,8,16]
            print('BOOKMARK_LIFECYCLE_OK',flush=True)
        finally:
            if a is not None:a._on_close()
            else:root.destroy()

class BookmarkLifecycleGuiTests(unittest.TestCase):
    def test_save_and_switch_while_prepare_is_pending(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-bookmarks-') as folder:
            dest=Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            run=subprocess.run([sys.executable,'-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=240)
            print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)

if __name__=='__main__':
    child() if '--child' in sys.argv else unittest.main()
