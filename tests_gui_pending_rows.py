"""Synthetic real Tk rows keep quick completions invisible and long work visible."""
from pathlib import Path
import copy,json,shutil,subprocess,sys,tempfile,time,traceback,unittest


def child():
 import tkinter as tk
 from unittest.mock import Mock,patch
 import app,analysis_work_app as work
 from session import new_tab
 assert Path('.pending-rows-isolated').exists()
 Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False,unified_autofix=False)),encoding='utf8')
 Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='資料です。\n確認します。')])),encoding='utf8')
 root=tk.Tk();root.withdraw();a=None;errors=[]
 root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
 def until(fn,seconds=80):
  end=time.monotonic()+seconds
  while True:
   root.update();assert not errors,errors
   if fn():return
   assert time.monotonic()<end,'timeout'
   time.sleep(.003)
 def wait(seconds):
  end=time.monotonic()+seconds
  until(lambda:time.monotonic()>=end,seconds+2)
 try:
  with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *v:None),patch.object(app.CorrectNoteApp,'_first_run_setup',lambda *v:None):
   a=app.CorrectNoteApp(root);root.geometry('900x480+0+0');root.deiconify()
   until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
   a._redraw_gutter_now();original=copy.deepcopy(a.line_results)
   source=a.editor_source_text();projection=a.result_view.get('1.0','end-1c')
   for layout in ('split','unified'):
    a.settings.set('layout',layout);a._apply_layout();root.update()
    a._redraw_gutter_now()
    gutters=(a.editor_gutter,a.result_gutter) if layout=='split' else (a.editor_gutter,)
    assert not any(g.find_withtag('analysis_state') for g in gutters)
    numbers={g:tuple(g.itemcget(i,'text') for i in g.find_withtag('num')) for g in gutters}
    a.line_results=[dict(original[0],pending=True)]+original[1:]
    a._redraw_gutter_now()
    assert a._line_analysis_state(1)=='pending'
    assert not any(g.find_withtag('analysis_state') for g in gutters)
    wait(.07)
    a.line_results=copy.deepcopy(original);a._redraw_gutter_now()
    wait(.35)
    assert not any(g.find_withtag('analysis_state') for g in gutters)
    assert a._pending_row_display.job is None
    # A genuinely pending row appears without another edit or explicit repaint.
    a.line_results=[dict(original[0],pending=True)]+original[1:]
    a._redraw_gutter_now()
    held=root.after(120000,lambda:None);a._gutter_after_id=held
    until(lambda:all(g.find_withtag('analysis_pending') for g in gutters),2)
    assert a._gutter_after_id==held
    root.after_cancel(held);a._gutter_after_id=None
    for g in gutters:
     assert len(g.find_withtag('analysis_pending'))==1
     assert g.find_withtag('analysis_row_1')
     assert tuple(g.itemcget(i,'text') for i in g.find_withtag('num'))==numbers[g]
    assert a._pending_row_display.job is None
    a.line_results=copy.deepcopy(original);a._redraw_gutter_now()
    assert not any(g.find_withtag('analysis_state') for g in gutters)
   assert a.editor_source_text()==source
   assert a.line_results==original
   assert a.result_view.get('1.0','end-1c')==projection
   # Editing the document invalidates any old delayed color before its callback.
   a.line_results=[dict(original[0],pending=True)]+original[1:];a._redraw_gutter_now()
   display=a._pending_row_display;old_ticket=display.ticket;old_scope=display.scope
   a.editor.insert('1.end','\n')
   display._ready(old_ticket,old_scope)
   assert display.scope is None and not display.deadlines
   assert not a.editor_gutter.find_withtag('analysis_state')
   a._redraw_gutter_now();job=display.job
   assert job is not None
   a._on_close();a=None
   assert display.closed and display.job is None and not display.deadlines
   print('PENDING_ROWS_GUI_OK: fast completion hidden, long work visible, layouts, raw results, edit ownership, close',flush=True)
 finally:
  if a:a._on_close()
  else:
   try:root.destroy()
   except tk.TclError:pass
 assert not errors,errors


class PendingRowsGuiTests(unittest.TestCase):
 def test_brief_pending_does_not_flash_and_continuing_work_stays_visible(self):
  from bundle_manifest import NAMES
  source=Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory(prefix='correctnote-pending-rows-') as folder:
   dest=Path(folder)
   for p in source.iterdir():
    if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copyfile(p,dest/p.name)
   (dest/'.pending-rows-isolated').touch()
   run=subprocess.run([sys.executable,'-B','-u','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=150)
   print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
   self.assertIn('PENDING_ROWS_GUI_OK',run.stdout)


if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
