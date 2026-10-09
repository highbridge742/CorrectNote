# -*- coding: utf-8 -*-
from pathlib import Path
import json,os,time,traceback
from unittest.mock import Mock,patch


def main():
    import tkinter as tk
    import app,quick_selection as Q,quick_ime,quick_analysis,analysis_work_app as work
    from selection_windows import Source
    from session import new_tab
    assert Path('.quick-selection-isolated').exists()
    Path('settings.json').write_text(json.dumps(dict(input_method_auto=False,layout='split',hotkey_insert_enabled=False,hotkey_minus_enabled=False)),encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='甲😀乙\n次\t行')]),ensure_ascii=False),encoding='utf8')
    root=tk.Tk();root.withdraw();a=None;errors=[]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    root.tk.eval('rename clipboard forbidden_original_clipboard; proc clipboard {args} {error "Clipboard forbidden in selection integration"}')
    source=[Source(1,2,os.getpid(),3)]
    def until(condition,seconds=60):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update();assert not errors,errors
            if condition():return
            time.sleep(.003)
        raise AssertionError('Owned quick selection timeout')
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *args:None),patch.object(app.messagebox,'askyesnocancel',return_value=False),patch.object(Q,'source_now',side_effect=lambda:source[0]),patch.object(Q,'read_selection',side_effect=AssertionError('Unmocked external read forbidden')),patch.object(quick_ime,'foreground_fullwidth_mode',return_value=8),patch.object(quick_ime,'apply_fullwidth_mode',return_value=True),patch.object(quick_analysis,'schedule_prepare'):
      try:
        a=app.CorrectNoteApp(root);root.geometry('1000x560');root.deiconify();root.update()
        until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
        a.editor.focus_force();a.editor.tag_add('sel','1.1','2.2');root.update()
        expected=a.editor.get('sel.first','sel.last');original=a.editor_source_text()
        a._open_quick_capture();root.update()
        assert a._quick_text.get('1.0','end-1c')==expected
        assert a.editor_source_text()==original
        a._open_quick_capture('minus');root.update();assert a._quick_win.state()=='iconic'
        a.editor.focus_force();a.editor.tag_remove('sel','1.0','end');a.editor.tag_add('sel','2.0','2.1');root.update()
        addition=a.editor.get('sel.first','sel.last');a._quick_text.mark_set('insert','end-1c')
        a._open_quick_capture('minus');root.update()
        assert a._quick_text.get('1.0','end-1c')==expected+addition
        a._quick_text.edit_undo();root.update();assert a._quick_text.get('1.0','end-1c')==expected
        a._quick_text.delete('1.0','end');a._close_quick_capture();root.update()
        source[0]=Source(10,20,os.getpid()+1000,30)
        a._selection_opening.reader=lambda *args:'項目\t金額\n合成\t￥1,200'
        a._open_quick_capture('insert')
        until(lambda:getattr(a,'_quick_text',None) is not None and a._quick_text.winfo_exists(),3)
        assert a._quick_text.get('1.0','end-1c')=='項目\t金額\n合成\t￥1,200'
        assert not errors
        print('QUICK_SELECTION_APP_OK: local active selection, original unchanged, restore appends, single Undo, external grid transfer, clipboard0',flush=True)
      finally:
        if a:
            text=getattr(a,'_quick_text',None)
            if text is not None and text.winfo_exists():text.delete('1.0','end');a._close_quick_capture()
            a._on_close()
        else:root.destroy()


import unittest,sys,tempfile,shutil,subprocess

class QuickSelectionGuiTests(unittest.TestCase):
    def test_selection_import_preserves_source_draft_undo_and_tab_separators(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-selection-') as folder:
            dest=Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copyfile(p,dest/p.name)
            (dest/'.quick-selection-isolated').touch()
            run=subprocess.run([sys.executable,'-B','-u','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=180)
            print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('QUICK_SELECTION_APP_OK',run.stdout)

if __name__=='__main__':main() if '--child' in sys.argv else unittest.main()

