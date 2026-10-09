# -*- coding: utf-8 -*-
"""Current-row indicators and quick-window placement on synthetic owned Tk windows."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path

def child():
 import tkinter as tk
 from unittest.mock import Mock,patch
 from types import SimpleNamespace
 import app,analysis_work_app as work,quick_ime,quick_analysis
 from session import new_tab
 assert Path('.row-quick-test-isolated').exists()
 Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False,unified_autofix=False)),encoding='utf8')
 Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='資料です。\n確認します。')])),encoding='utf8')
 root=tk.Tk();root.withdraw();a=None;errors=[]
 root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
 root.clipboard_clear=lambda **kw:None;root.clipboard_append=lambda *args,**kw:None
 def until(fn,seconds=70):
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
  with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *a:None):
   a=app.CorrectNoteApp(root);root.geometry('900x480+0+0');root.deiconify()
   until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
   a.status.config(text='');settle()
   assert not a.status.winfo_ismapped()
   expanded=a._body.winfo_height()
   original=list(a.line_results)
   numbers={g:[g.itemcget(i,'text') for i in g.find_withtag('num')] for g in (a.editor_gutter,a.result_gutter)}
   a.line_results=[dict(original[0],pending=True)]+original[1:]
   a._redraw_gutter_now()
   assert not any(g.find_withtag('analysis_state') for g in (a.editor_gutter,a.result_gutter))
   until(lambda:all(g.find_withtag('analysis_pending') for g in (a.editor_gutter,a.result_gutter)),2)
   for g in (a.editor_gutter,a.result_gutter):
    assert len(g.find_withtag('analysis_pending'))==1,(str(g),[g.gettags(i) for i in g.find_all()],a._analyze_work,work.token(a))
    assert not g.find_withtag('analysis_done')
    assert len(g.find_withtag('analysis_state'))==1
    assert all(g.type(item)=='rectangle' for item in g.find_withtag('analysis_state'))
    assert [g.itemcget(item,'text') for item in g.find_withtag('num')]==numbers[g]
   a.line_results[0]=dict(original[0],analysis_status='incomplete')
   assert a._line_analysis_state(1)=='incomplete'
   a.line_results[0]=dict(original[0],analysis_error='synthetic failure')
   assert a._line_analysis_state(1)=='incomplete'
   # A newer edit invalidates the old row markers before the debounce expires.
   a.editor.insert('2.end','追記');a._redraw_gutter_now()
   assert a._line_analysis_state(1)==a._line_analysis_state(2)=='pending'
   a.line_results=original
   a._on_change()
   until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
   a.status.config(text='');settle();expanded=a._body.winfo_height()
   with patch.object(a,'_foreground_analysis_pending',return_value=True):
    a.status.config(text='解析中… 1/2 行');settle()
    assert a.status.winfo_ismapped()
    assert a._body.winfo_height()<expanded
   a.status.config(text='');a._queue_status_visibility();settle()
   assert not a.status.winfo_ismapped() and a._body.winfo_height()==expanded
   root.state('zoomed');settle()
   assert a.status.winfo_ismapped()
   root.state('normal');settle()
   assert not a.status.winfo_ismapped()
   # Both layouts keep the small indicators and the original number text.
   a.settings.set('layout','unified');a._apply_layout();settle();a.editor_gutter.redraw()
   assert not a.editor_gutter.find_withtag('analysis_state')
   pointer=[(500,240)]
   # Simulate distinct monitor work areas without changing the user's desktop.
   def area(x,y):return (-1600,-900,0,900) if x<0 else (0,0,900,900) if x<900 else (900,0,2100,900)
   applied=[]
   with patch.object(tk.Toplevel,'winfo_pointerxy',side_effect=lambda:pointer[0]),patch.object(app,'monitor_work_area',side_effect=area),patch.object(quick_ime,'foreground_fullwidth_mode',return_value=0x19),patch.object(quick_ime,'apply_fullwidth_mode',side_effect=lambda hwnd,mode:applied.append((hwnd,mode)) or True),patch.object(quick_analysis,'schedule_prepare'):
    for book_open in (False,True):
     if book_open:a._word_book.open();settle()
     a._open_quick_capture();settle();win=a._quick_win;text=a._quick_text
     assert abs(win.winfo_x()-516)<=2 and abs(win.winfo_y()-256)<=2,(win.geometry(),book_open)
     assert applied and all(h==text.winfo_id() and mode==0x19 for h,mode in applied)
     # A move still queued by Tk must survive an immediate automatic resize.
     win.geometry('+650+330');text.insert('1.0','幅を広げる文字列'*5)
     a._adjust_quick_size(text);settle()
     assert abs(win.winfo_x()-650)<=2 and abs(win.winfo_y()-330)<=2,win.geometry()
     text.delete('1.0','end');a._adjust_quick_size(text);settle()
     a._open_quick_capture();settle();assert win.state()=='iconic'
     pointer[0]=(1300,400)
     a._open_quick_capture();settle()
     assert win.state()=='normal' and abs(win.winfo_x()-1316)<=2 and abs(win.winfo_y()-416)<=2,(win.state(),win.geometry(),book_open)
     # A monitor left/above the primary uses negative virtual coordinates.
     a._open_quick_capture();settle();assert win.state()=='iconic'
     pointer[0]=(-1000,-400)
     a._open_quick_capture();settle()
     assert abs(win.winfo_x()+984)<=2 and abs(win.winfo_y()+384)<=2,(win.geometry(),book_open)
     text.insert('1.0','左画面の入力'*8);a._adjust_quick_size(text);settle()
     assert abs(win.winfo_x()+984)<=2 and abs(win.winfo_y()+384)<=2,win.geometry()
     text.delete('1.0','end');a._close_quick_capture();settle()
     applied.clear();pointer[0]=(500,240)
     if book_open:a._word_book.close();settle()
   print('ROW_QUICK_UI_OK: row states, normal/maximized footer, move/resize/reopen with word book closed/open',flush=True)
 finally:
  if a:
   if getattr(a,'_quick_win',None) is not None:a._quick_text.delete('1.0','end');a._close_quick_capture()
   a._on_close()
  else:root.destroy()
 assert not errors,errors

class RowQuickGuiTests(unittest.TestCase):
 def test_current_rows_footer_and_quick_window(self):
  from bundle_manifest import NAMES
  source=Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory(prefix='correctnote-row-quick-') as folder:
   dest=Path(folder)
   for p in source.iterdir():
    if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
   (dest/'.row-quick-test-isolated').touch()
   run=subprocess.run([sys.executable,'-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=150)
   print(run.stdout,flush=True)
   self.assertEqual(run.returncode,0,run.stdout)
   self.assertIn('ROW_QUICK_UI_OK',run.stdout)

if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()