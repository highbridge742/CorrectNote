# -*- coding: utf-8 -*-
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

def child():
 import tkinter as tk
 from unittest.mock import Mock,patch
 import app,analysis_work_app as work
 from session import new_tab,SessionStore
 from text_edit import undo_group
 assert Path('.ruler-rows-isolated').exists()
 text='第一行です。\n'+'長い行です。'*24+'\n第三行です。\n第四行です。'
 Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False,unified_autofix=False)),encoding='utf8')
 Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text=text)])),encoding='utf8')
 root=tk.Tk();root.withdraw();a=None;errors=[]
 root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
 def until(fn,seconds=90):
  end=time.monotonic()+seconds
  while True:
   root.update();assert not errors,errors
   if fn():return
   assert time.monotonic()<end,'timeout';time.sleep(.004)
 def complete():until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
 def choose(row):
  a.editor.mark_set('insert',str(row)+'.0');a.editor.see('insert');a._sync_cursor_line(a.editor,force=True);root.update()
 def marked(rows):
  root.update();assert a._editor_guides.ruler_rows()==set(rows),(a._editor_guides.ruler_rows(),rows)
 try:
  with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *v:None),patch.object(app.CorrectNoteApp,'_first_run_setup',lambda *v:None):
   a=app.CorrectNoteApp(root);root.geometry('1120x660+0+0');root.deiconify();complete()
   original=a.editor_source_text();a.editor.edit_reset();a.editor.tag_add('sel','1.0','1.2')
   selection=tuple(map(str,a.editor.tag_ranges('sel')))
   choose(2);a.ruler_btn.invoke();marked({2})
   before=a._editor_guides.lines[a.editor,2].winfo_y()
   choose(3);marked({2});assert a._editor_guides.lines[a.editor,2].winfo_y()==before
   assert a.ruler_btn.cget('relief')=='flat'
   a.ruler_btn.invoke();marked({2,3});assert a.ruler_btn.cget('relief')=='sunken'
   assert a.editor_source_text()==original
   assert tuple(map(str,a.editor.tag_ranges('sel')))==selection
   try:a.editor.edit_undo();raise AssertionError('ruler toggle dirtied undo')
   except tk.TclError:pass
   a._capture_session();first=a.session.current();assert first['ruler_rows']==[2,3]
   a.session.add_tab(new_tab(text='別タブです。\n次の行です。',ruler_rows=[1]))
   a._load_active_tab();complete();marked({1})
   a.session.active=0;a._load_active_tab();complete();marked({2,3})
   for layout in ('unified','split'):
    a.settings.set('layout',layout);a._apply_layout();complete();marked({2,3})
   choose(2);a.ruler_btn.invoke();marked({3});choose(2);a.ruler_btn.invoke();marked({2,3})
   a.editor.tag_remove('sel','1.0','end');a.editor.edit_reset()
   with undo_group(a.editor):a.editor.insert('1.0','追加行です。\n')
   marked({3,4});a.editor.edit_undo();marked({2,3});a.editor.edit_redo();marked({3,4})
   a._capture_session();a.session.save();loaded=SessionStore();assert loaded.load('session.json')
   assert loaded.current()['ruler_rows']==[3,4]
   a.session.add_tab(new_tab());a._load_active_tab();complete();choose(1)
   a.ruler_btn.invoke();marked({1})
   a._place_in_new_tab(None,'読み込んだ文です。');marked(set())
   assert a._editor_guides.ruler_rows()==set()
   print('RULER_ROWS_APP_OK: multiple logical rows, fixed cursor, button state, selection/undo preserved, tabs, layouts, edit undo redo, session capture/load, reused file tab reset',flush=True)
   a._on_close();a=None
 finally:
  if a:a._on_close()
  else:
   try:root.destroy()
   except tk.TclError:pass
 assert not errors,errors

class RulerRowsAppTests(unittest.TestCase):
 def test_real_app_ruler_rows_are_owned_by_their_tab(self):
  from bundle_manifest import NAMES
  src=Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory(prefix='correctnote-ruler-rows-') as folder:
   dest=Path(folder)
   for p in src.iterdir():
    if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copyfile(p,dest/p.name)
   (dest/'.ruler-rows-isolated').touch()
   run=subprocess.run([sys.executable,'-B','-u','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=210)
   print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
   self.assertIn('RULER_ROWS_APP_OK',run.stdout)

if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
