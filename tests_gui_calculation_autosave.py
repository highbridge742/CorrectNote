"""Formula confirmation after an idle save survives without a closing save."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

def child(phase,layout,automatic):
 import tkinter as tk
 from unittest.mock import Mock,patch
 import app,analysis_work_app as work,analysis_worker
 from session import new_tab
 from tests_tk_keys import deliver_key
 assert Path('.ui-test-isolated').exists()
 if phase=='write':
  Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab()])),encoding='utf-8')
  Path('settings.json').write_text(json.dumps(dict(layout=layout,unified_autofix=automatic,input_method='kana',input_method_auto=False)),encoding='utf-8')
 root=tk.Tk();root.withdraw();a=None;errors=[]
 root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
 def until(fn,seconds=100):
  deadline=time.monotonic()+seconds
  while time.monotonic()<deadline:
   root.update();assert not errors,errors
   if fn():return
   time.sleep(.005)
  raise AssertionError((phase,a.status.cget('text'),getattr(a,'_analyze_last_error',None)))
 def done():return (not a._foreground_analysis_pending() and a._analyze_text==a.editor_source_text() and a._analyze_work==work.token(a) and a._analyze_dependencies==analysis_worker.state_key(a))
 def pause(seconds):
  stop=time.monotonic()+seconds;until(lambda:time.monotonic()>stop,seconds+1)
 with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None):
  try:
   a=app.CorrectNoteApp(root);until(done);w=a.editor
   if phase=='write':
    for suffix,expected,full in (('1-2','-1','1-2'),('+3','2','1-2+3')):
     w.mark_set('insert','1.end');deliver_key(w,'<Control-c>','c',67,state=4)
     for ch in suffix:
      deliver_key(w,'<KeyPress>',ch,0,char=ch)
      deliver_key(w,'<KeyRelease>',ch,0,event_type=3,char=ch)
     # Finish the text-driven save before formula confirmation changes metadata.
     pause(2.1)
     deliver_key(w,'<KeyPress>','Return',13,char='\r');until(done);pause(2.1)
     assert a.line_results[0]['corrected']==expected,a.line_results
     saved=json.loads(Path('session.json').read_text(encoding='utf-8'))
     assert saved['tabs'][0]['text']==full,saved
     assert saved['tabs'][0].get('calculations')==[dict(start=0,end=len(full),surface=full)],saved
    # Closing cannot repair a missing autosave in this test.
    with patch.object(a,'_save_session'),patch.object(a,'_save_analysis_cache'):
     a._on_close();a=None
   else:
    assert a.editor_source_text().rstrip('\n')=='1-2+3'
    assert a.line_results[0]['corrected']=='2',a.line_results
    assert len(a._input_document.calculations)==1
   print('CALCULATION_AUTOSAVE_OK',phase,layout,automatic,flush=True)
  finally:
   if a is not None:a._on_close()

class CalculationAutosaveGuiTests(unittest.TestCase):
 def run_case(self,layout,automatic):
  from bundle_manifest import NAMES
  source=Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory(prefix='correctnote-calculation-autosave-') as folder:
   dest=Path(folder)
   for p in source.iterdir():
    if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
   (dest/'.ui-test-isolated').touch()
   for phase in ('write','restart'):
    run=subprocess.run([sys.executable,'-B','-X','utf8','-X','faulthandler',str(dest/Path(__file__).name),'--child',phase,layout,str(int(automatic))],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',timeout=150)
    print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
    self.assertIn('CALCULATION_AUTOSAVE_OK',run.stdout)
 def test_split_idle_confirmation(self):self.run_case('split',False)
 def test_unified_idle_confirmation(self):self.run_case('unified',False)
 def test_unified_automatic_idle_confirmation(self):self.run_case('unified',True)

if __name__=='__main__':
 if '--child' in sys.argv:child(sys.argv[2],sys.argv[3],bool(int(sys.argv[4])))
 else:unittest.main()
