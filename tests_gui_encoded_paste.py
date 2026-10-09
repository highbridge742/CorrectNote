"""Synthetic oversized/data rows retain full text under a bounded display."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,unittest

def child():
 import base64,time,traceback,tkinter as tk
 import faulthandler
 faulthandler.dump_traceback_later(45,exit=True)
 from unittest.mock import Mock,patch
 import app,analysis_work_app as work
 from session import new_tab
 assert Path('.encoded-paste-isolated').exists()
 Path('settings.json').write_text(json.dumps(dict(layout='unified',input_method='kana',input_method_auto=False,unified_autofix=False)),encoding='utf8')
 Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='')])),encoding='utf8')
 payloads=('data:image/png;base64,'+base64.b64encode(bytes(range(256))*106).decode('ascii'),
           '長い文章でも全体を保持できます。ABC 😀 '*1600, 'abcdef0123456789'*3000, '\t '*10000)
 payload=payloads[0]
 root=tk.Tk();root.withdraw();a=None;errors=[];gaps=[];last=[time.monotonic()];timer=[None]
 root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
 def tick():
  now=time.monotonic();gaps.append(now-last[0]);last[0]=now;timer[0]=root.after(25,tick)
 def wait(predicate,seconds=30):
  end=time.monotonic()+seconds
  while True:
   root.update();assert not errors,errors
   if predicate():return
   assert time.monotonic()<end,'analysis did not finish';time.sleep(.003)
 def complete():return not a._foreground_analysis_pending() and a._analyze_work==work.token(a)
 try:
  # Override the Tcl selection reader in this owned interpreter only. This
  # drives the real paste binding without reading/changing the OS clipboard.
  with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *v:None),patch.object(app.CorrectNoteApp,'_first_run_setup',lambda *v:None):
   print('APP_START',flush=True)
   a=app.CorrectNoteApp(root);root.geometry('900x460+0+0');root.deiconify();wait(complete)
   body=root.tk.call('info','body','::tk_textPaste');assert '::tk::GetSelection' in body,body
   root.tk.call('rename','::tk::GetSelection','::tk::SavedGetSelection')
   callback=root.register(lambda widget,selection:payload if selection=='CLIPBOARD' else root.nametowidget(widget).get('sel.first','sel.last'))
   copied=[]
   def fake_clipboard(command,*args):
    if command=='clear':copied.clear()
    elif command=='append':copied.append(args[-1])
    else:raise AssertionError(command)
   root.tk.call('rename','clipboard','::SavedClipboard')
   root.tk.createcommand('clipboard',fake_clipboard)
   root.tk.call('proc','::tk::GetSelection','args','return ['+callback+' {*}$args]')
   print('APP_READY',flush=True)
   tick()
   for layout,payload in ((layout,value) for layout in ('unified','split') for value in payloads):
    print('LAYOUT',layout,flush=True)
    a.settings.set('layout',layout);a._apply_layout();wait(complete)
    root.geometry('420x300+0+0');root.update()
    a.editor.delete('1.0','end');a.editor.edit_reset();gaps.clear();last[0]=time.monotonic()
    print('PASTE_START',flush=True)
    start=time.monotonic();a.editor.event_generate('<<Paste>>');a._on_change()
    wait(complete,10);elapsed=time.monotonic()-start
    assert not getattr(a,'_pick_mode',None),'encoded padding must not start quote mode'
    assert a.editor_source_text().rstrip('\n')==payload
    assert not a.line_results[0].get('odd_spans') and not a.line_results[0].get('unsure_spans')
    assert a.line_results[0].get('analysis_status')=='complete'
    paste_gap=max(gaps,default=0)
    print('PASTE_RESPONSE',layout,'completed_seconds',round(elapsed,3),'max_event_gap',round(paste_gap,3),flush=True)
    assert paste_gap<2,'paste blocked UI callback for two seconds'
    if layout=='unified' and payload==payloads[0]:
     display=a.editor._correctnote_literal_display
     before=len(a.editor.get('1.0',a.editor.tag_ranges(display.ELIDED_TAG)[0]))
     family,size=a._editor_font();a._choose_editor_font(size=32);root.update()
     after=len(a.editor.get('1.0',a.editor.tag_ranges(display.ELIDED_TAG)[0]))
     assert after<before,(before,after)
     a._choose_editor_font(family=family,size=size);root.update()
    a.editor.tag_add('sel','1.0','end-1c');a.editor.event_generate('<<Copy>>')
    assert ''.join(copied)==payload,'copy must include the hidden part'
    a.editor.tag_remove('sel','1.0','end')
    a._save_session()
    saved=json.loads(Path('session.json').read_text(encoding='utf8'))
    assert saved['tabs'][saved['active']]['text'].rstrip('\n')==payload
    a.editor.focus_force();root.update();a.editor.mark_set('insert','1.0');a.editor.event_generate('<Right>');root.update()
    # Tk moves over elided characters as one display boundary. An oversized
    # leading tab may itself be clipped in a narrow pane. The arrow must still
    # move forward without editing or blocking, even when the whole row hides.
    assert a.editor.compare('insert','>','1.0'),(layout,len(payload),a.editor.index('insert'))
    if not payload.isspace():assert a.editor.index('insert')=='1.1'
    a.editor.edit_undo();root.update();assert a.editor.get('1.0','end-1c').strip()==''
    a.editor.edit_redo();root.update();assert a.editor_source_text().rstrip('\n')==payload
    print('ENCODED_PASTE',layout,'length',len(payload),'completed_seconds',round(elapsed,3),'max_event_gap',round(max(gaps,default=0),3),flush=True)
    assert max(gaps,default=0)<2,'long-row editing blocked UI callbacks'
    assert a.editor.get('1.0','end-1c').rstrip('\n')==payload
    a.editor.delete('1.0','end');a._on_change();wait(complete)
   a.editor.insert('1.0','見積=');a._on_change();root.update()
   assert a._pick_mode,'ordinary quote command is retained'
   a._end_pick_mode(keep_equals=True)
   print('ENCODED_PASTE_OK',flush=True)
 finally:
  faulthandler.cancel_dump_traceback_later()
  if timer[0]:root.after_cancel(timer[0])
  if a:a._on_close()
  else:root.destroy()
 assert not errors,errors

class EncodedPasteGuiTests(unittest.TestCase):
 def test_long_rows_keep_full_copy_save_and_native_editing_in_both_layouts(self):
  from bundle_manifest import NAMES
  source=Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory(prefix='correctnote-encoded-paste-') as folder:
   dest=Path(folder)
   for p in source.iterdir():
    if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copyfile(p,dest/p.name)
   (dest/'.encoded-paste-isolated').touch()
   output=source/'encoded_paste_child.log'
   with output.open('w',encoding='utf8') as log:
    run=subprocess.run([sys.executable,'-B','-u','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=log,stderr=subprocess.STDOUT,encoding='utf8',timeout=90)
   result=output.read_text(encoding='utf8');print(result,flush=True)
   self.assertEqual(run.returncode,0,result)
   self.assertIn('ENCODED_PASTE_OK',result)

if __name__=='__main__':child() if '--child' in sys.argv else unittest.main()
