# -*- coding: utf-8 -*-
"""Keyboard scrolling after bookmarks and bulk insertion into corrected rows."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path

def child(phase):
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app as work,analysis_worker
    from session import new_tab
    from tests_tk_keys import deliver_key
    assert Path('.operation-followups-isolated').exists()
    Path('settings.json').write_text(json.dumps(dict(layout='unified',input_method='kana',input_method_auto=False,unified_autofix=True)),encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='')])),encoding='utf8')
    root=tk.Tk();root.withdraw();a=None;errors=[]
    root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
    def until(fn,seconds=100):
        deadline=time.monotonic()+seconds
        while True:
            root.update();assert not errors,errors
            if fn():return
            assert time.monotonic()<deadline,('timeout',a.status.cget('text'))
            time.sleep(.003)
    def done():return not a._foreground_analysis_pending() and a._analyze_work==work.token(a)
    def body():return a.editor.get('1.0','end-1c').rstrip('\n')
    def typed(value):
        a._autofix_reset();a.editor.replace('1.0','end-1c',value)
        for row,line in enumerate(value.split('\n'),1):a._mark_typed(row,0,len(line))
        a._sync_typed_shadow();a._on_change();until(done)
    try:
        with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *v:None):
            a=app.CorrectNoteApp(root);root.geometry('1000x700+0+0');root.deiconify();until(done)
            if phase=='bookmark':
                a.settings.set('unified_autofix',False)
                typed('\n'.join('資料です。' for _ in range(40)))
                original=a.editor_source_text()
                for unified in (True,False):
                    (a._set_layout_unified if unified else a._set_layout_split)();until(done)
                    a.first_line_btn.invoke();root.update();info=a.editor.dlineinfo('1.0');baseline=info[1]+info[4]
                    for pane in ((a.editor,) if unified else (a.editor,a.result_view)):
                        for sequence,keysym,keycode in (('<Prior>','Prior',33),('<Control-Home>','Home',36),('<Control-Shift-Home>','Home',36)):
                            a._goto_line(3);pane.mark_set('insert','3.0');root.update()
                            deliver_key(pane,sequence,keysym,keycode,state=5 if sequence=='<Control-Shift-Home>' else 4 if sequence=='<Control-Home>' else 0)
                            root.update()
                            info=a.editor.dlineinfo('1.0');assert info,(unified,sequence,a.editor.yview())
                            assert abs(info[1]+info[4]-baseline)<=1,(unified,sequence,info,baseline)
                            assert a.editor_source_text()==original
                for sequence,keysym,char in (('<Prior>','Prior','!'),('<Next>','Next','"'),('<Home>','Home','$')):
                    a.editor.tag_remove('sel','1.0','end');a.editor.mark_set('insert','1.end')
                    before=a.editor.get('1.0','1.end')
                    deliver_key(a.editor,sequence,keysym,ord(char),char=char)
                    assert a.editor.get('1.0','1.end')==before+char,(sequence,a.editor.get('1.0','1.end'))
                print('BOOKMARK_KEYBOARD_TOP_AND_IME_SYMBOLS_OK',flush=True)
            else:
                typed('寒ぃ日だ。\nよいでしょぅか。')
                expected='寒い日だ。\nよいでしょうか。';assert body()==expected,body()
                a.bulk_insert_btn.invoke();root.update();d=a._bulk_insert
                a.editor.tag_remove('sel','1.0','end');a.editor.tag_add('sel','1.1','2.3')
                d.direction.set('start');d.distance.set('0');d.text.insert('1.0','■')
                d.execute.invoke();inserted='寒■い日だ。\n■よいでしょうか。'
                assert body()==inserted,body();until(done);assert body()==inserted,body()
                a.editor.event_generate('<<Undo>>');assert body()==expected,body()
                a._on_change();until(done);assert body()==expected,body()
                a.editor.event_generate('<<Redo>>');assert body()==inserted,body()
                a._on_change();until(done);assert body()==inserted,body()
                a._capture_session();assert a.session.current()['text']==inserted,a.session.current()['text']
                print('BULK_CORRECTED_ROWS_UNDO_REDO_SAVE_OK',flush=True)
    finally:
        if a:a._on_close()
        else:root.destroy()
    assert not errors,errors

class OperationFollowupGuiTests(unittest.TestCase):
    def run_phase(self,phase):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-followup-') as directory:
            dest=Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.operation-followups-isolated').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child',phase],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=220)
            print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
    def test_bookmark_keyboard_returns_first_row_to_top(self):self.run_phase('bookmark')
    def test_bulk_insert_into_autofixed_rows_undo_redo_save(self):self.run_phase('bulk')

if __name__=='__main__':child(sys.argv[-1]) if '--child' in sys.argv else unittest.main()
