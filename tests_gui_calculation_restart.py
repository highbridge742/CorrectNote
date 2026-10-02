# -*- coding: utf-8 -*-
"""Explicit calculations survive real process restarts without spreading by text."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

class SavedCalculationTests(unittest.TestCase):
    def test_ranges_are_validated_and_old_sessions_remain_plain(self):
        from quote_calculator import clean_calculations
        from session import SessionStore,new_tab
        source='😀1-2+3｜1-2+3'
        valid=dict(start=1,end=6,surface='1-2+3')
        bad=[None,[],{},dict(start=True,end=6,surface='1-2+3'),dict(start=-1,end=6,surface='1-2+3'),dict(start=1,end=99,surface='1-2+3'),dict(start=1,end=6,surface='33+4'),dict(start=1,end=2,surface='1')]
        self.assertEqual(clean_calculations(source,[valid,valid]+bad[:-1]),[valid])
        self.assertEqual(clean_calculations('1/0',[dict(start=0,end=3,surface='1/0')]),[])
        for records in (None,False,42,'bad',{}):self.assertEqual(clean_calculations(source,records),[])
        with tempfile.TemporaryDirectory() as folder:
            store=SessionStore(str(Path(folder)/'session.json'))
            store.tabs=[new_tab(text=source,calculations=[valid]),new_tab(text=source)]
            self.assertTrue(store.save());loaded=SessionStore(store.path);self.assertTrue(loaded.load())
            self.assertEqual(loaded.tabs[0]['calculations'],[valid]);self.assertNotIn('calculations',loaded.tabs[1])


def child(phase,layout,automatic):
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app as work,analysis_worker,tab_analysis
    from session import new_tab
    from tests_tk_keys import deliver_key
    assert Path('.ui-test-isolated').exists()
    spelling='--spelling' in sys.argv
    prefix='のひっています\t😀' if spelling else '😀'
    shown_prefix='残っています\t😀' if spelling else '😀'
    source=prefix+'1-2+3｜1-2+3\n33+4'
    if phase=='write':
        Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(),new_tab(text=source),new_tab()]),ensure_ascii=False),encoding='utf-8')
        Path('settings.json').write_text(json.dumps(dict(layout=layout,unified_autofix=automatic,input_method='kana',input_method_auto=False)),encoding='utf-8')
    root=tk.Tk();root.withdraw();a=None;errors=[]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    def until(predicate,seconds=90):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            root.update();assert not errors,errors
            if predicate():return
            time.sleep(.005)
        raise AssertionError((phase,getattr(a,'_analyze_last_error',None),a.status.cget('text')))
    def done():
        return (not a._foreground_analysis_pending() and a._analyze_text==a.editor_source_text()
            and a._analyze_work==work.token(a) and a._analyze_dependencies==analysis_worker.state_key(a))
    def formula(value):
        w=a.editor;w.tag_remove('sel','1.0','end')
        deliver_key(w,'<Control-c>','c',67,state=4);w.insert('insert',value)
        deliver_key(w,'<KeyPress>','Return',13,char='\r')
        assert a._pick_mode is None,(phase,a.status.cget('text'))
        until(done)
    def tab(index):a._switch_tab(index);until(done)
    def result(row=0):return a.line_results[row]['corrected']
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None):
        try:
            a=app.CorrectNoteApp(root);until(done);revision=a.store.revision()
            if phase=='write':
                a._replace_editor_text(prefix+'｜1-2+3\n');until(done)
                shown=a.editor.get('1.0','1.end')
                a.editor.mark_set('insert',f"1.0+{shown.index('｜')}c");formula('1-2+3')
                a.editor.mark_set('insert','2.0');formula('33+4')
                assert result()==shown_prefix+'2｜1-2+3' and result(1)=='37',a.line_results
                tab(2);a.editor.mark_set('insert','1.0');formula('1/2');assert result()=='0.5'
                tab(1);assert result()==shown_prefix+'1-2+3｜1-2+3'
            elif phase=='restart':
                assert a.session.active==1 and not a._input_document.calculations
                assert result()==shown_prefix+'1-2+3｜1-2+3'
                assert len(tab_analysis._calculations(a,work.owner_for_tab(a,a.session.tabs[0])))==2
                tab(0);assert result()==shown_prefix+'2｜1-2+3' and result(1)=='37',a.line_results
                assert a.editor_source_text().rstrip('\n')==source
                shown=a.editor.get('1.0','1.end')
                a.editor.mark_set('insert',f"1.0+{shown.index('｜')}c");formula('*4')
                assert result()==shown_prefix+'11｜1-2+3',a.line_results
                tab(2);assert result()=='0.5'
                a.editor.insert('1.0','😀');a._analyze();until(done);assert result()=='😀0.5'
                tab(1)
            elif phase=='verify':
                tab(0);assert result()==shown_prefix+'11｜1-2+3' and result(1)=='37',a.line_results
                tab(2);assert result()=='😀0.5'
                a._replace_editor_text('9+1');until(done);assert not a._input_document.calculations
                tab(1)
            else:
                tab(2);assert result()=='9+1' and not a._input_document.calculations
                tab(1);assert result()==shown_prefix+'1-2+3｜1-2+3' and not a._input_document.calculations
            a._save_session();assert a.store.revision()==revision
            print('CALCULATION_RESTART_OK',phase,layout,automatic,flush=True)
        finally:
            if a is not None:a._on_close()
            else:root.destroy()

class CalculationRestartGuiTests(unittest.TestCase):
    def run_restart(self,layout,automatic,spelling=False):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-calculation-restart-') as folder:
            dest=Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            for phase in ('write','restart','verify','deleted'):
                print('CALCULATION_RESTART_BEGIN',phase,layout,automatic,spelling,flush=True)
                run=subprocess.run([sys.executable,'-B','-X','utf8','-X','faulthandler',str(dest/Path(__file__).name),'--child',phase,layout,str(int(automatic))]+(['--spelling'] if spelling else []),cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',timeout=150)
                print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
                self.assertIn('CALCULATION_RESTART_OK',run.stdout)
    def test_split_restart(self):self.run_restart('split',False)
    def test_unified_manual_restart(self):self.run_restart('unified',False)
    def test_unified_automatic_restart(self):self.run_restart('unified',True)
    def test_unified_spelling_and_restart(self):self.run_restart('unified',True,spelling=True)

if __name__=='__main__':
    if '--child' in sys.argv:child(sys.argv[2],sys.argv[3],bool(int(sys.argv[4])))
    else:unittest.main()
