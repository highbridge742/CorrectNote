# -*- coding: utf-8 -*-
"""Real editor projection under a fast cached response and continuing input."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest,copy
from pathlib import Path


def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app as work,analysis_worker,analysis_input
    from session import new_tab
    assert Path('.input-pause-isolated').exists()
    source='寒ぃ日だ。';wanted='寒い日だ。'
    Path('settings.json').write_text(json.dumps(dict(layout='unified',input_method='kana',input_method_auto=False,unified_autofix=True)),encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text=source),new_tab(text='別タブ')])),encoding='utf8')
    root=tk.Tk();root.withdraw();a=None;errors=[]
    root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
    def until(fn,seconds=80):
        deadline=time.monotonic()+seconds
        while True:
            root.update();assert not errors,errors
            if fn():return
            assert time.monotonic()<deadline,('timeout',a.status.cget('text'))
            time.sleep(.002)
    def body():return a.editor.get('1.0','1.end')
    try:
        with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *v:None):
            a=app.CorrectNoteApp(root);root.geometry('900x480+0+0');root.deiconify()
            until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
            assert a.line_results[0]['corrected']==wanted,a.line_results[0]
            results=copy.deepcopy(a.line_results);cache=dict(a._units_cache)
            # Use a real previously computed value to model a response arriving
            # before 300ms. Computation is held, display and text remain real Tk.
            with patch.object(a,'_analyze_if_changed',new=lambda:setattr(a,'_after_id',None)),patch('ime_watch.composition_active',return_value=False):
                def fast_response():
                    a._cancel_analysis_job();a._autofix_reset()
                    a.editor.replace('1.0','1.end',source)
                    a._mark_typed(1,0,len(source));a._sync_typed_shadow()
                    a._on_change();a.line_results=copy.deepcopy(results);a._units_cache=dict(cache)
                    a._analyze_text=a.editor_source_text();a._prev_lines=a._analyze_text.split('\n')
                    a._analyze_work=work.token(a);a._analyze_dependencies=analysis_worker.state_key(a)
                    a._analyze_todo=[];a._analyze_pos=0
                    a._refresh_after_analysis(learn=False)
                    assert body()==source and a._input_display_job is not None
                    assert a._foreground_analysis_pending()
                fast_response();deadline=a._input_display_after
                while time.monotonic()<deadline-.025:
                    root.update();assert body()==source,body();time.sleep(.002)
                until(lambda:body()==wanted,2)
                assert not a._foreground_analysis_pending()
                assert not a.status.winfo_ismapped()
                # A later Backspace/replacement owns the text, even if an old
                # accepted response had already queued its display callback.
                fast_response();a.editor.replace('1.0','1.end','本人の入力');a._on_change()
                end=time.monotonic()+.4
                while time.monotonic()<end:root.update();time.sleep(.002)
                assert body()=='本人の入力',body()
                # An active IME composition remains protected after the quiet
                # period too; its end can reuse the completed value.
                fast_response()
                with patch('ime_watch.composition_active',return_value=True):
                    until(lambda:time.monotonic()>a._input_display_after+.05,2)
                    assert body()==source and a._unified_autofix_waiting_ime
                a._refresh_after_analysis(learn=False)
                until(lambda:body()==wanted,2)
                # Tab cancellation and shutdown cancel the pending projection.
                fast_response();job=a._input_display_job
                a.session.active=1;a._cancel_analysis_job()
                assert a._input_display_job is None
                assert str(job) not in root.tk.call('after','info')
            print('EARLY_COMPUTE_QUIET_DISPLAY_NEW_INPUT_IME_CANCEL_OK',flush=True)
    finally:
        if a:a._on_close()
        else:root.destroy()
    assert not errors,errors

@unittest.skipUnless(sys.platform=='win32','Owned Windows GUI check')
class InputPauseGuiTests(unittest.TestCase):
    def test_fast_response_waits_without_overwriting_new_input(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-input-pause-') as directory:
            dest=Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.input-pause-isolated').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=200)
            print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('EARLY_COMPUTE_QUIET_DISPLAY_NEW_INPUT_IME_CANCEL_OK',run.stdout)

if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
