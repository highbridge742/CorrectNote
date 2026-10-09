# -*- coding: utf-8 -*-
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

def child():
 import tkinter as tk
 from unittest.mock import patch,Mock
 from session import new_tab
 import app,analysis_worker,analysis_work_app as work
 assert Path('.literal-cancel-isolated').is_file()
 Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf8')
 Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='資料を確認します。')])),encoding='utf8')
 root=tk.Tk();root.withdraw();a=None;errors=[];calls=[]
 root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
 original=analysis_worker.Worker.submit
 def submit(worker,task,state=None):
  calls.append((worker,dict(task)));return original(worker,task,state)
 def until(fn,seconds=70):
  end=time.monotonic()+seconds
  while True:
   root.update();assert not errors,errors
   if fn():return
   assert time.monotonic()<end,'timeout';time.sleep(.005)
 def done():return a._warmup is None and not a._foreground_analysis_pending() and a._analyze_work==work.token(a)
 try:
  with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *v:None),patch.object(app.CorrectNoteApp,'_first_run_setup',lambda *v:None),patch.object(analysis_worker.Worker,'submit',submit):
   a=app.CorrectNoteApp(root);root.geometry("900x500");root.deiconify();a._analyze_if_changed();until(done)
   a.editor.delete('1.0','end');a.editor.insert('1.0',('処理がじゃのになっていないだろうか\n')*12)
   a._analyze_if_changed()
   until(lambda:getattr(a,'_async_request',None) is not None)
   worker=a._correction_worker;before=len(calls)
   literal=' \t\nhttps://example.test/sample\nC:/Synthetic/file.txt'
   a.editor.delete('1.0','end');a.editor.insert('1.0',literal);a._analyze_if_changed();until(done)
   sent=[task for owner,task in calls[before:] if owner is worker]
   assert sent==[{'kind':'cancel'}],sent
   assert worker.process.is_alive() and a._correction_worker is worker
   assert a.editor_source_text().rstrip('\n')==literal
   assert all(row.get('analysis_status')=='complete' for row in a.line_results)
   before=len(calls);a.editor.insert('3.end','\n次の資料を確認します。');a._analyze_if_changed();until(done)
   assert any(owner is worker and task['kind']=='line' for owner,task in calls[before:])
   assert a.editor_source_text().rstrip('\n')==literal+'\n次の資料を確認します。'
   assert all(row.get('analysis_status')=='complete' for row in a.line_results)
   assert not errors;print('LITERAL_CANCEL_GUI_OK: old request cancelled, same worker reused, next ordinary edit complete',flush=True)
 finally:
  if a:a._on_close()
  else:root.destroy()

class LiteralCancellationGuiTests(unittest.TestCase):
 def test_edit_to_literal_only_cancels_old_worker_and_next_input_completes(self):
  from bundle_manifest import NAMES
  source=Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory(prefix='correctnote-literal-cancel-') as folder:
   dest=Path(folder)
   for p in source.iterdir():
    if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copyfile(p,dest/p.name)
   (dest/'.literal-cancel-isolated').touch()
   run=subprocess.run([sys.executable,'-B','-u','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=180)
   print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
   self.assertIn('LITERAL_CANCEL_GUI_OK',run.stdout)
if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
