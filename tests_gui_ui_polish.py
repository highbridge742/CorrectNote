# -*- coding: utf-8 -*-
"""Synthetic real app checks for the user's post-restart UI requests."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

def child():
 import tkinter as tk
 from unittest.mock import Mock,patch
 import app,analysis_work_app as work
 from session import new_tab
 from text_edit import undo_group
 assert Path('.ui-polish-isolated').exists()
 text='https://example.test/path\nC:\\Synthetic\\file.txt\n\n \t　\n本文です。'
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
 def event(w,sequence,index,**kwargs):
  box=w.bbox(index);assert box,(index,w)
  w.event_generate(sequence,x=box[0]+1,y=box[1]+box[3]//2,**kwargs);root.update()
 try:
  with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *v:None),patch.object(app.CorrectNoteApp,'_first_run_setup',lambda *v:None):
   a=app.CorrectNoteApp(root);root.geometry('1100x520+0+0');root.deiconify();complete()
   source=a.editor_source_text();a.editor.edit_reset()
   p=a._toolbar_preferences;p.open();root.update()
   first=p._listed.index('first');b=p.listbox.bbox(first)
   p.listbox.event_generate('<ButtonPress-1>',x=5,y=b[1]+b[3]//2);p.listbox.event_generate('<ButtonRelease-1>',x=5,y=b[1]+b[3]//2);root.update()
   assert 'first' in p.hidden and not a.first_line_btn.winfo_ismapped()
   p.check.invoke();root.update();assert 'first' not in p.hidden
   assert p._listed.count('layout_split')==1 and 'layout_unified' not in p._listed
   p.refresh_list(select='layout_split');p.check.invoke();root.update()
   assert not a.layout_split_btn.winfo_ismapped() and not a.layout_unified_btn.winfo_ismapped()
   p.check.invoke();root.update();assert a.layout_split_btn.winfo_ismapped() and a.layout_unified_btn.winfo_ismapped()
   # A one-position move must preserve every other button and editor selection.
   a.editor.tag_add('sel','5.0','5.2');before=tuple(map(str,a.editor.tag_ranges('sel')))
   p.refresh_list(select='last');p.move_selected(-1);root.update()
   assert p.order[0]=='last' and p.selected()=='last'
   assert tuple(map(str,a.editor.tag_ranges('sel')))==before
   p.close();saved=json.loads(Path('settings.json').read_text(encoding='utf8'));assert saved['toolbar_order'][0]=='last'
   p.reset();p.close();a.editor.tag_remove('sel','1.0','end')
   assert a.ruler_btn.cget('text')=='' and a.ruler_btn.cget('image')
   for dark in (True,False):
    a._apply_theme(dark);root.update()
    assert a._ruler_icon.transparency_get(4,5) and not a._ruler_icon.transparency_get(4,12)
   a.ruler_btn.invoke();root.update();assert a._editor_guides.enabled
   a.ruler_btn.invoke();root.update();assert not a._editor_guides.enabled
   for layout in ('split','unified'):
    a.settings.set('layout',layout);a._apply_layout();complete()
    panes=[(a.editor,a._text_links)]
    if layout=='split':panes.append((a.result_view,a._result_text_links))
    for w,links in panes:
     opener=links.opener=Mock()
     for index,target in (('1.5','https://example.test/path'),('2.5',r'C:\Synthetic\file.txt')):
      event(w,'<ButtonPress-1>',index);opener.assert_not_called()
      event(w,'<ButtonRelease-1>',index);opener.assert_called_once()
      assert opener.call_args[0][0].target==target
      opener.reset_mock()
     event(w,'<ButtonPress-1>','1.5');event(w,'<B1-Motion>','1.15',state=0x100);event(w,'<ButtonRelease-1>','1.15')
     opener.assert_not_called();assert w.tag_ranges('sel');w.tag_remove('sel','1.0','end')
    # Keep a new generation unplanned to prove blank suppression is immediate.
    with patch.object(a,'_analyze_if_changed'),patch.object(a,'_analyze'):
     a.editor.insert('3.0','\n');a._redraw_gutter_now()
     for row in (3,4,5):
      assert not a.editor.get(f'{row}.0',f'{row}.end').strip()
      assert a._line_analysis_display_state(row)=='done'
     assert a._line_analysis_state(6)=='pending'
     assert a._line_analysis_display_state(6) is None
     a.editor.delete('3.0','4.0')
    a._analyze_if_changed();complete()
   a.editor.edit_reset()
   for s in ('甲','乙'):
    with undo_group(a.editor):a.editor.insert('5.end',s)
   a.editor.edit_undo();root.update_idletasks()
   assert a.editor.tag_cget('undo_feedback','background')==''
   assert a.editor.tag_cget('undo_feedback','underline')=='1'
   assert a.editor.tag_cget('undo_feedback','underlinefg')==app.HISTORY_HINT_LINE
   a.editor.edit_redo();root.update_idletasks()
   assert a.editor.tag_cget('undo_feedback','background')==''
   assert a.editor.tag_cget('undo_feedback','underline')=='1'
   assert a.editor.tag_cget('undo_feedback','underlinefg')==app.HISTORY_HINT_LINE
   for dark in (True,False):
    a._apply_theme(dark);assert a.editor.tag_cget('undo_feedback','underlinefg')==app.HISTORY_HINT_LINE
   a.editor.edit_undo();a.editor.edit_undo();assert a.editor_source_text()==source
   root.geometry('500x300');root.update()
   print('UI_POLISH_SIZE',root.geometry(),root.minsize(),root.state(),flush=True)
   until(lambda:500<=root.winfo_width()<=502 and root.winfo_height()==300,2)
   assert root.minsize()==(420,260)
   assert a.editor.winfo_width()>100 and a.editor.winfo_height()>40
   # Removing the native caption can add a 2px frame adjustment on Windows.
   root.geometry('420x260');until(lambda:420<=root.winfo_width()<=422 and root.winfo_height()==260,2)
   assert a.editor.winfo_width()>100 and a.editor.winfo_height()>40
   p.set_visible('ruler',False);a._on_close();a=None
   assert p._save_job is None and 'ruler' in json.loads(Path('settings.json').read_text(encoding='utf8'))['toolbar_hidden']
   print('UI_POLISH_OK: checkbox, shared layout group, order, save, line icon, both-pane links/drag, empty rows, redo underline, smaller window, shutdown',flush=True)
 finally:
  if a:a._on_close()
  else:
   try:root.destroy()
   except tk.TclError:pass
 assert not errors,errors

class UiPolishGuiTests(unittest.TestCase):
 def test_requested_controls_links_and_display_preserve_document(self):
  from bundle_manifest import NAMES
  src=Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory(prefix='correctnote-ui-polish-') as folder:
   dest=Path(folder)
   for p in src.iterdir():
    if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copyfile(p,dest/p.name)
   (dest/'.ui-polish-isolated').touch()
   run=subprocess.run([sys.executable,'-B','-u','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=210)
   print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
   self.assertIn('UI_POLISH_OK',run.stdout)

if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
