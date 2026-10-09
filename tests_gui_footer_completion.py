"""Completed normal windows stay expanded after deferred startup diagnostics."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path

def child():
 import tkinter as tk
 from unittest.mock import Mock,patch
 import app,analysis_work_app as work
 from session import new_tab
 assert Path('.footer-completion-isolated').exists()
 Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False,unified_autofix=False)),encoding='utf8')
 Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='資料です。')])),encoding='utf8')
 root=tk.Tk();root.withdraw();a=None;errors=[];deferred=[]
 root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
 root.clipboard_clear=lambda **kw:None;root.clipboard_append=lambda *args,**kw:None
 native_after=root.after
 def startup_after(delay,func=None,*args):
  if delay==8000 and func is not None:
   # Execute the actual deferred startup callback after analysis completes,
   # without making a slow machine race an arbitrary eight-second deadline.
   job=native_after(120000,func,*args);deferred.append((job,func,args));return job
  return native_after(delay,func,*args)
 def until(fn,seconds=60):
  end=time.monotonic()+seconds
  while True:
   root.update();assert not errors,errors
   if fn():return
   assert time.monotonic()<end,('timeout',a.status.cget('text'))
   time.sleep(.004)
 def settle():
  end=time.monotonic()+.1
  while time.monotonic()<end:root.update();time.sleep(.004)
  assert not errors,errors
 try:
  with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *a:None),patch.object(app.CorrectNoteApp,'_first_run_setup',lambda *a:None):
   with patch.object(root,'after',side_effect=startup_after):a=app.CorrectNoteApp(root)
   root.geometry('900x480+0+0');root.deiconify()
   until(lambda:not a._foreground_analysis_pending() and getattr(a,'_analyze_work',None)==work.token(a))
   settle();assert not a.status.winfo_ismapped(),a.status.cget('text')
   expanded=a._body.winfo_height()
   for job,callback,args in deferred:root.after_cancel(job);callback(*args)
   settle()
   assert not a.status.winfo_ismapped(),('completed footer reopened',a.status.cget('text'))
   assert a._body.winfo_height()==expanded
   # The completed footer can still show a real notification and maximized space.
   notice='保存できませんでした（合成検査）'
   a.status.config(text=notice);settle()
   assert a.status.winfo_ismapped() and a.status.cget('text')==notice
   a.status.config(text='');settle()
   assert not a.status.winfo_ismapped() and a._body.winfo_height()==expanded
   root.state('zoomed');settle();assert a.status.winfo_ismapped()
   root.state('normal');settle();assert not a.status.winfo_ismapped()
   print('FOOTER_COMPLETION_OK: completed space, deferred startup, notices, maximized window',flush=True)
 finally:
  for job,callback,args in deferred:
   try:root.after_cancel(job)
   except tk.TclError:pass
  if a:a._on_close()
  else:root.destroy()
 assert not errors,errors

class FooterCompletionGuiTests(unittest.TestCase):
 def test_completed_footer_stays_hidden_after_startup(self):
  from bundle_manifest import NAMES
  source=Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory(prefix='correctnote-footer-completion-') as folder:
   dest=Path(folder)
   for p in source.iterdir():
    if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
   (dest/'.footer-completion-isolated').touch()
   run=subprocess.run([sys.executable,'-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=100)
   print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
   self.assertIn('FOOTER_COMPLETION_OK',run.stdout)

if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
