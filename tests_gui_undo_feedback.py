"""Undo feedback on actual app/quick widgets and tab/theme lifecycles."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

def child():
 import tkinter as tk
 from unittest.mock import Mock,patch
 import app,analysis_work_app as work,quick_analysis,quick_ime
 from session import new_tab
 from text_edit import undo_group
 assert Path('.undo-feedback-isolated').exists()
 Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False,unified_autofix=False)),encoding='utf8')
 Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='元の本文。'),new_tab(text='別の本文。')])),encoding='utf8')
 root=tk.Tk();root.withdraw();a=None;errors=[]
 root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
 root.clipboard_clear=lambda **kw:None;root.clipboard_append=lambda *args,**kw:None
 def until(fn,seconds=80):
  end=time.monotonic()+seconds
  while True:
   root.update();assert not errors,errors
   if fn():return
   assert time.monotonic()<end,'timeout'
   time.sleep(.003)
 def marked(w):
  root.update_idletasks();text=w.get('1.0','end-1c');tag=w._correctnote_undo_feedback.TAG
  return ''.join(ch for i,ch in enumerate(text) if tag in w.tag_names(f'1.0+{i}c'))
 def exercise(w):
  w.edit_reset();original=w.get('1.0','end-1c')
  for text in ('甲😀','乙'):
   with undo_group(w):w.insert('1.end',text)
  w.event_generate('<<Undo>>');assert marked(w)=='甲😀',marked(w)
  assert w.tag_cget('undo_feedback','background')=='' and w.tag_cget('undo_feedback','underline')=='1'
  assert w.tag_cget('undo_feedback','underlinefg')==app.HISTORY_HINT_LINE
  w.event_generate('<<Redo>>');assert marked(w)=='乙',marked(w)
  w.event_generate('<<Undo>>');w.event_generate('<<Undo>>')
  assert w.get('1.0','end-1c')==original and marked(w)==''
  return original
 try:
  with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *v:None),patch.object(app.CorrectNoteApp,'_first_run_setup',lambda *v:None):
   a=app.CorrectNoteApp(root);root.geometry('900x480+0+0');root.deiconify()
   until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
   for layout in ('split','unified'):
    a.settings.set('layout',layout);a._apply_layout();root.update_idletasks()
    exercise(a.editor)
   for text in ('甲','乙'):
    with undo_group(a.editor):a.editor.insert('1.end',text)
   a.editor.edit_undo();assert marked(a.editor)=='甲'
   for dark in (True,False):
    a._apply_theme(dark);assert marked(a.editor)=='甲'
    assert a.editor.tag_cget('undo_feedback','background')==''
    assert a.editor.tag_cget('undo_feedback','underline')=='1'
    assert a.editor.tag_cget('undo_feedback','underlinefg')==app.HISTORY_HINT_LINE
   a._switch_tab(1)
   until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
   assert not a.editor._correctnote_undo_feedback.undo
   assert marked(a.editor)=='' and a.editor_source_text().rstrip('\n')=='別の本文。'
   with patch.object(quick_ime,'foreground_fullwidth_mode',return_value=None),patch.object(quick_analysis,'schedule_prepare'):
    a._open_quick_capture();root.update_idletasks();exercise(a._quick_text)
    quick_feedback=a._quick_text._correctnote_undo_feedback
    a._quick_text.delete('1.0','end');a._close_quick_capture()
    assert quick_feedback.closed and quick_feedback.job is None
   main_feedback=a.editor._correctnote_undo_feedback
   a._on_close();a=None
   assert main_feedback.closed and main_feedback.job is None
   print('UNDO_FEEDBACK_APP_OK: native Undo/Redo, both layouts, theme, tabs, quick window, close',flush=True)
 finally:
  if a:
   if getattr(a,'_quick_text',None) is not None:
    try:a._quick_text.delete('1.0','end');a._close_quick_capture()
    except tk.TclError:pass
   a._on_close()
  else:
   try:root.destroy()
   except tk.TclError:pass
 assert not errors,errors

class UndoFeedbackGuiTests(unittest.TestCase):
 def test_native_undo_feedback_survives_theme_and_stays_with_its_widget(self):
  from bundle_manifest import NAMES
  source=Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory(prefix='correctnote-undo-feedback-') as folder:
   dest=Path(folder)
   for p in source.iterdir():
    if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copyfile(p,dest/p.name)
   (dest/'.undo-feedback-isolated').touch()
   run=subprocess.run([sys.executable,'-B','-u','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=180)
   print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
   self.assertIn('UNDO_FEEDBACK_APP_OK',run.stdout)

if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
