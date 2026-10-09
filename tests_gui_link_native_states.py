# -*- coding: utf-8 -*-
"""Windows lock bits on actual app widgets; no real opener or personal data."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

def child():
 import tkinter as tk
 from unittest.mock import Mock,patch
 import app,analysis_work_app as work
 from session import new_tab
 assert Path('.native-links-isolated').is_file()
 text='https://example.test/path\nC:\\Synthetic\\file.txt'
 Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf8')
 Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text=text)])),encoding='utf8')
 root=tk.Tk();root.withdraw();a=None;errors=[];stamp=1000
 root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
 def until(fn,seconds=60):
  end=time.monotonic()+seconds
  while True:
   root.update();assert not errors,errors
   if fn():return
   assert time.monotonic()<end,'timeout';time.sleep(.004)
 def event(w,seq,index,state):
  nonlocal stamp
  stamp+=800
  box=w.bbox(index);assert box,(str(w),index)
  w.event_generate(seq,x=box[0]+1,y=box[1]+box[3]//2,state=state,time=stamp)
  root.update()
 try:
  with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *v:None),patch.object(app.CorrectNoteApp,'_first_run_setup',lambda *v:None):
   a=app.CorrectNoteApp(root);root.geometry('1100x500+0+0');root.deiconify()
   until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
   assert root.tk.call('tk','windowingsystem')=='win32'
   source=a.editor_source_text();a.editor.edit_reset()
   for row in (1,2):
    a.editor.mark_set('insert',f'{row}.0');a._editor_guides.cursor_changed(a.editor)
    assert a._toggle_ruler()
   root.update();assert a._editor_guides.ruler_rows()=={1,2}
   for layout in ('split','unified'):
    a.settings.set('layout',layout);a._apply_layout()
    until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
    panes=[(a.editor,a._text_links)]
    if layout=='split':panes.append((a.result_view,a._result_text_links))
    for w,links in panes:
     opened=links.opener=Mock()
     for locks in (0,0x8,0x2,0x20,0x2|0x8|0x20):
      for index,target in (('1.5','https://example.test/path'),('2.5',r'C:\Synthetic\file.txt')):
       event(w,'<ButtonPress-1>',index,locks);opened.assert_not_called()
       event(w,'<ButtonRelease-1>',index,locks|0x100)
       assert opened.call_count==1,(layout,str(w),locks,index,'opener calls',opened.call_count)
       assert opened.call_args[0][0].target==target;opened.reset_mock()
     for modifier in (1,4,0x20000,0x200,0x400):
      event(w,'<ButtonPress-1>','1.5',0x8|modifier)
      event(w,'<ButtonRelease-1>','1.5',0x108|modifier)
      opened.assert_not_called();w.tag_remove('sel','1.0','end')
     event(w,'<ButtonPress-1>','1.5',0x8)
     event(w,'<B1-Motion>','1.15',0x108)
     event(w,'<ButtonRelease-1>','1.15',0x108)
     opened.assert_not_called();assert w.tag_ranges('sel');w.tag_remove('sel','1.0','end')
   assert a.editor_source_text()==source
   assert a._editor_guides.ruler_rows()=={1,2}
   try:a.editor.edit_undo()
   except tk.TclError:pass
   else:raise AssertionError('link interaction added Undo')
   print('NATIVE_LINK_STATES_OK: Num/Caps/Scroll locks, URL/path, both panes/layouts, modifiers, drag, unchanged text/undo',flush=True)
 finally:
  if a:a._on_close()
  else:root.destroy()
 assert not errors,errors

class NativeLinkStatesGuiTests(unittest.TestCase):
 def test_lock_states_open_and_selection_modifiers_do_not(self):
  from bundle_manifest import NAMES
  src=Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory(prefix='correctnote-native-links-') as folder:
   dest=Path(folder)
   for p in src.iterdir():
    if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copyfile(p,dest/p.name)
   (dest/'.native-links-isolated').touch()
   run=subprocess.run([sys.executable,'-B','-u','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=180)
   print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
   self.assertIn('NATIVE_LINK_STATES_OK',run.stdout)
if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
