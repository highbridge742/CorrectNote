# -*- coding: utf-8 -*-
"""Real first-run preparation stays responsive and can close while collecting."""
import json,sys,time,traceback,unittest
from pathlib import Path

def child(mode):
 import tkinter as tk
 from unittest.mock import Mock,patch
 import app,analysis_worker,analysis_work_app as work
 from session import new_tab
 assert (Path.cwd()/'.ui-test-isolated').is_file()
 Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='最初の資料です。'),new_tab(text='別のメモです。')]),ensure_ascii=False),encoding='utf-8')
 Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf-8')
 initial_interval=sys.getswitchinterval()
 root=tk.Tk();root.withdraw();a=None;closed=False;errors=[];gaps=[];last=[time.monotonic()]
 root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
 def tick():
  now=time.monotonic();gaps.append(now-last[0]);last[0]=now;root.after(10,tick)
 def until(fn,seconds=90):
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   root.update();assert not errors,errors
   if fn():return
   time.sleep(.003)
  raise AssertionError(('timeout',getattr(a,'_initial_setup',None),getattr(a,'_async_request',None)))
 def done():
  return (getattr(a,'_initial_setup',None) is None and a._warmup is None and not getattr(a,'_async_context_scope',None)
   and a._analyze_text==a.editor_source_text() and a._analyze_pos>=len(a._analyze_todo)
   and a._analyze_work==work.token(a) and a._analyze_dependencies==analysis_worker.state_key(a))
 with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None):
  try:
   a=app.CorrectNoteApp(root);initial=[dict(e) for e in a.store.to_list()]
   root.after(10,tick);last[0]=time.monotonic()
   until(lambda:getattr(a,'_initial_setup',None) is not None and a._initial_setup['worker'] is not None)
   state=a._initial_setup;worker=state['worker'];start=time.monotonic()
   if mode=='close':
    a._on_close();closed=True;a=None
    assert worker.closed and not worker.process.is_alive()
    assert sys.getswitchinterval()==initial_interval
    assert not Path(app.SETUP_FILE).exists()
    print('INITIAL_SETUP_REPORT '+json.dumps(dict(mode=mode,close_ms=round((time.monotonic()-start)*1000,2))),flush=True)
    return
   a._switch_tab(1);a.editor.insert('1.0','追加しました。');a._on_change()
   interaction_ms=(time.monotonic()-start)*1000
   assert a.editor_source_text().startswith('追加しました。')
   assert interaction_ms<250,interaction_ms
   until(done)
   assert sys.getswitchinterval()==initial_interval
   assert a.editor_source_text().startswith('追加しました。')
   assert Path(app.SETUP_FILE).is_file()
   assert state['pos'] and not state['failed']
   # Same public entries, same store.add API, and no language-learning run.
   from vocabulary import VocabularyStore
   expected=VocabularyStore()
   for e in initial:expected._by_reading[e['reading']][e['surface']]=dict(e)
   for reading,surface,category,world in state['rows']:expected.add(reading,surface,category,world=world)
   ordered=lambda store:sorted(store.to_list(),key=lambda e:(e['reading'],e['surface']))
   assert ordered(expected)==ordered(a.store),'First-run result differs from the original import arguments'
   assert max(gaps,default=0)<1.0,('Tk blocked',max(gaps))
   print('INITIAL_SETUP_REPORT '+json.dumps(dict(mode=mode,interaction_ms=round(interaction_ms,2),max_tk_gap_ms=round(max(gaps)*1000,2),imported=state['pos'],entries=len(a.store.to_list())),ensure_ascii=False),flush=True)
  finally:
   if a is not None:a._on_close()
   elif not closed:root.destroy()

def run(mode):
 import shutil,tempfile,subprocess
 from bundle_manifest import NAMES
 source=Path(__file__).resolve().parent
 with tempfile.TemporaryDirectory(prefix='correctnote-first-run-') as folder:
  dest=Path(folder)
  for p in source.iterdir():
   if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
  (dest/'.ui-test-isolated').touch()
  result=subprocess.run([sys.executable,'-X','utf8',str(dest/Path(__file__).name),'--child',mode],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',timeout=150)
  print(result.stdout,flush=True)
  if result.returncode:raise AssertionError(result.stdout)
  return json.loads(next(line[len('INITIAL_SETUP_REPORT '):] for line in result.stdout.splitlines() if line.startswith('INITIAL_SETUP_REPORT ')))

class InitialSetupTkTests(unittest.TestCase):
 def test_edit_and_tab_switch_during_initial_dictionary_collection(self):run('complete')
 def test_close_during_initial_dictionary_collection(self):run('close')

if __name__=='__main__':
 if '--child' in sys.argv:child(sys.argv[-1])
 else:unittest.main()
