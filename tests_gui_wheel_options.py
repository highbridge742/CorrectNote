# -*- coding: utf-8 -*-
"""Actual wheel bindings honor default inertia and its independent switch."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

def child():
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app,analysis_worker
    from session import new_tab
    assert Path('.ui-test-isolated').is_file()
    source='\n'.join('確認用の資料です。' for i in range(100))
    tabs=[new_tab(text=source),new_tab(text=source)]
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=tabs),ensure_ascii=False),encoding='utf8')
    # Neither inertia setting is supplied: this checks the real defaults.
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf8')
    root=tk.Tk();root.withdraw();a=None;errors=[];cases=[]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    def forbid(*args,**kwargs):raise AssertionError('No clipboard access')
    root.clipboard_clear=root.clipboard_append=root.clipboard_get=forbid
    root.tk.eval('rename clipboard {}; proc clipboard {args} {error "No clipboard access"}')
    def pump(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:root.update();assert not errors,errors;time.sleep(.003)
    def until(predicate,seconds=120):
        end=time.monotonic()+seconds
        while True:
            root.update();assert not errors,errors
            if predicate():return
            assert time.monotonic()<end,'GUI did not settle'
            time.sleep(.005)
    def done():return not a._foreground_analysis_pending() and a._analyze_work==analysis_work_app.token(a)
    def wheel(widget,delta=-120,state=0):
        widget.event_generate('<MouseWheel>',delta=delta,state=state,x=4,y=4,
            rootx=widget.winfo_rootx()+4,rooty=widget.winfo_rooty()+4)
    def position():
        a._scroll_inertia.cancel();a.editor.yview_moveto(.3);a.result_view.yview_moveto(.3);root.update()
        return a.editor.yview()[0]
    try:
        with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *args:None):
            a=app.CorrectNoteApp(root);root.geometry('900x480+0+0');root.deiconify();until(done)
            assert a.settings.get('wheel_inertia') and a.settings.get('right_drag_inertia')
            initial=a.editor_source_text();revision=a.store.revision();a.editor.edit_reset()
            for layout in ('split','unified'):
                if layout=='unified':a._set_layout_unified();until(done)
                start=position();tab=a.session.active;wheel(a.editor,delta=-360)
                assert a.session.active==tab and a._scroll_inertia.job is not None
                assert a.editor.yview()[0]==start
                pump(.035);middle=a.editor.yview()[0]
                until(lambda:a._scroll_inertia.job is None,seconds=1.2);end=a.editor.yview()[0]
                assert start<middle<end,(layout,start,middle,end)
                assert a._scroll_inertia.job is None
                if layout=='split':assert abs(a.result_view.yview()[0]-end)<.0001
                assert a.editor_source_text()==initial
                cases.append(layout+'_body_default_glides')
                a.settings.set('wheel_inertia',False);start=position();wheel(a.editor)
                assert a.editor.yview()[0]>start and a._scroll_inertia.job is None
                assert a.settings.get('right_drag_inertia') and a.session.active==tab
                cases.append(layout+'_body_option_off_immediate')
                a.settings.set('wheel_inertia',True);position();wheel(a.editor,delta=-600)
                assert a._scroll_inertia.job is not None
                a.editor.focus_force();root.update();a.editor.event_generate('<Right>');root.update()
                at=a.editor.yview();pump(.15)
                assert a.editor.yview()==at and a._scroll_inertia.job is None
                cases.append(layout+'_key_cancels_tail')
            # Inertia is on, but a tab-strip wheel must still switch at once.
            label=a._tab_widgets[a.session.active]['label'];tab=a.session.active
            wheel(label);root.update()
            assert a.session.active!=tab and a._scroll_inertia.job is None
            cases.append('default_on_tab_wheel_immediate');until(done)
            # Right+wheel over the editor is tab navigation, never body inertia.
            pump(.35);tab=a.session.active
            a.editor.event_generate('<ButtonPress-3>',x=4,y=4)
            wheel(a.editor,state=0x0400);root.update()
            a.editor.event_generate('<ButtonRelease-3>',state=0x0400,x=4,y=4);root.update()
            assert a.session.active!=tab and a._scroll_inertia.job is None
            cases.append('default_on_right_wheel_switches_tab');until(done)
            assert a.editor_source_text()==initial and a.store.revision()==revision
            # Scrolling and layout changes must not write into the active text.
            assert all(t['text']==source for t in a.session.tabs)
            print('WHEEL_OPTIONS_GUI_OK '+json.dumps(cases),flush=True)
    finally:
        if a:a._on_close()
        else:root.destroy()
    assert not errors,errors

class WheelOptionsGuiTests(unittest.TestCase):
    def test_actual_bindings_default_glide_option_off_and_tab_navigation(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-wheel-options-') as folder:
            dest=Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copyfile(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',errors='replace',timeout=240)
            self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('WHEEL_OPTIONS_GUI_OK',run.stdout)
            print(run.stdout,flush=True)
if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
