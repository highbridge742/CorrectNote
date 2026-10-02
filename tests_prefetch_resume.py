"""Invalidated preparation must requeue foreground work and then prefetch."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path


def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app as work,analysis_worker,tab_analysis
    from session import new_tab
    assert (Path.cwd()/'.ui-test-isolated').exists()
    texts=['最初の文です。','次の文を確認します。','別の資料を開きます。']
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,
        tabs=[new_tab(text=t) for t in texts]),ensure_ascii=False),encoding='utf-8')
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',
        input_method_auto=False)),encoding='utf-8')
    root=tk.Tk();root.withdraw();errors=[];a=None
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    def until(predicate,seconds=35):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update()
            if errors:raise AssertionError(errors)
            if predicate():return
            time.sleep(.005)
        raise AssertionError(dict(status=a.status.cget('text'),scope=getattr(a,'_async_context_scope',None),
            pending=a._foreground_analysis_pending(),pos=a._analyze_pos,todo=len(a._analyze_todo)))
    def done():
        return (a._warmup is None and getattr(a,'_async_context_scope',None) is None
            and a._analyze_text==a.editor_source_text() and a._analyze_pos>=len(a._analyze_todo)
            and a._analyze_work==work.token(a) and a._analyze_dependencies==analysis_worker.state_key(a))
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),\
         patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None):
        try:
            a=app.CorrectNoteApp(root);until(done)
            # New text starts preparation. Change only the dependency revision;
            # never grow the vocabulary or write a user decision.
            a.editor.insert('1.0','新しい確認です。\n');a._analyze()
            assert getattr(a,'_async_context_scope',None) is not None
            a._invalidate_analysis_cache()
            until(done)
            until(lambda:tab_analysis.completed(a,texts[1],work.owner_for_tab(a,a.session.tabs[1])) is not None)
            a._switch_tab(1);until(done)
            a.editor.mark_set('insert','1.0');root.update()
            assert a.editor_gutter._cursor_row==a.result_gutter._cursor_row=='1'
            print('PREFETCH_RESUMED',flush=True)
        finally:
            if a is not None:a._on_close()
            else:root.destroy()


class PrefetchResumeTests(unittest.TestCase):
    def test_dependency_change_during_prepare_resumes_without_typing(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-prefetch-') as folder:
            dest=Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            result=subprocess.run([sys.executable,'-X','utf8',str(dest/Path(__file__).name),'--child'],
                cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=110)
            self.assertEqual(result.returncode,0,result.stdout)
            self.assertIn('PREFETCH_RESUMED',result.stdout)

if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:unittest.main()
