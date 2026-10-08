"""Requested editing operations, using an isolated real application and stores."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest


class SelectionTransformTests(unittest.TestCase):
    def test_reading_width_and_physical_keys_preserve_other_characters(self):
        from editor_transforms import transform_selection as convert
        self.assertEqual(convert('漢字 ガパ\nＡ１😀', 'hiragana'), 'かんじ がぱ\nＡ１😀')
        self.assertEqual(convert('漢字 がぱ\nＡ１😀', 'katakana'), 'カンジ ガパ\nＡ１😀')
        self.assertEqual(convert('漢字 がぱ\nＡ１😀', 'halfwidth'), 'ｶﾝｼﾞ ｶﾞﾊﾟ\nA1😀')
        self.assertEqual(convert('たんご。ぱっ\nＡ１😀', 'keys'), 'qyb@>f[Z\nA1😀')
        self.assertEqual(convert('ｶﾞﾊﾟ、²', 'katakana'), 'ガパ、²')
        for kind in ('halfwidth','keys'):
            self.assertEqual(convert('é한²😀',kind),'é한²😀')

    def test_signed_line_commands_are_distinct_from_arithmetic(self):
        from quote_calculator import quote_enter_kind as kind, calculate
        for value, result in (('-1', -1), ('＋２', 2), (' −３ ', -3), ('+0', 0)):
            self.assertEqual(kind(value), ('relative', result))
        self.assertEqual(kind('１２'), ('line', 12))
        for value, answer in (('-1+2', '1'), ('+1*2','2'), ('－１÷２','-0.5')):
            self.assertEqual(kind(value), ('calculation', None))
            self.assertEqual(calculate(value), answer)
        self.assertEqual(kind('-1\n'), (None,None))


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    import analysis_work_app as work
    import analysis_worker
    from session import new_tab
    from tests_tk_keys import deliver_key
    here = Path.cwd()
    assert (here/'.ui-operations-isolated').exists()
    (here/'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana',
        input_method_auto=False, unified_autofix=False)), encoding='utf8')
    (here/'session.json').write_text(json.dumps(dict(version=1,active=0,
        tabs=[new_tab(text=''),new_tab(text='別タブの資料')]),ensure_ascii=False),encoding='utf8')
    root=tk.Tk(); root.withdraw(); a=None; errors=[]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    def until(predicate, seconds=65):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            root.update()
            assert not errors, errors
            if predicate():return
            time.sleep(.005)
        raise AssertionError((a.status.cget('text'),getattr(a,'_analyze_last_error',None)))
    def done():
        return (not a._foreground_analysis_pending() and a._analyze_text==a.editor_source_text()
            and a._analyze_work==work.token(a) and a._analyze_dependencies==analysis_worker.state_key(a))
    def text(w=None):return (w or a.editor).get('1.0','end-1c').rstrip('\n')
    def set_text(value):
        if a._pick_mode:a._end_pick_mode()
        a._forget_bracket_cycle()
        a._clear_quick_sent()
        a._replace_editor_text(value);until(done)
        a.editor.edit_reset()
    def select(w, start, end):
        w.tag_remove('sel','1.0','end');w.tag_add('sel',start,end);w.mark_set('insert',end)
    def key(w,name,code):
        sequence='<KeyPress>' if name in ('Return','Escape') else '<'+name+'>'
        deliver_key(w,sequence,name,code,char='\r' if name=='Return' else '')
    with patch.object(app.CorrectNoteApp,'_learn_now',new=lambda *args:None), \
         patch.object(app,'GlobalHotkeys',return_value=Mock()):
        try:
            a=app.CorrectNoteApp(root);until(done);w=a.editor
            baseline=a.store.revision()
            # Both inclusive and interior selections replace existing brackets.
            for source,first,last,expected in (
                    ('前（文字）後','1.2','1.4','前「文字」後'),
                    ('前（文字）後','1.1','1.5','前「文字」後'),
                    ('前「文字」後','1.2','1.4','前（文字）後'),
                    ('前😀（文字）後','1.0+3c','1.0+5c','前😀「文字」後')):
                set_text(source);select(w,first,last);key(w,'F5',116)
                assert text()==expected,(source,text())
                assert a._cancel_bracket_cycle();assert text()==source
            set_text('前（文字）後');select(w,'1.2','1.4')
            a._wrap_with_brackets('【','】');assert text()=='前【文字】後'
            a._wrap_with_brackets('【','】');assert text()=='前【文字】後'
            w.edit_undo();assert text()=='前【文字】後'
            w.edit_undo();assert text()=='前（文字）後'
            # Single atomic edit, Unicode offsets, and both editor surfaces.
            with patch.object(a,'_set_window_icons_win32',side_effect=lambda win:win.withdraw()), \
                 patch.object(a,'_place_quick_window'),patch.object(a,'_focus_quick_window'):
                a._open_quick_capture()
            q=a._quick_text;a.settings.set('quick_autofix',False)
            for pane in (w,q):
                for name,code,expected in (('F6',117,'かんじ が'),('F7',118,'カンジ ガ'),
                                            ('F8',119,'ｶﾝｼﾞ ｶﾞ'),('F9',120,'tyd@ t@')):
                    if pane is w:set_text('前😀漢字 が後')
                    else:pane.replace('1.0','end-1c','前😀漢字 が後')
                    pane.edit_reset();select(pane,'1.0+2c','1.0+6c');key(pane,name,code)
                    assert text(pane)=='前😀'+expected+'後',(name,text(pane))
                    assert pane.get('sel.first','sel.last')==expected
                    pane.edit_undo();assert text(pane)=='前😀漢字 が後'
            # Explicit transforms survive the normal delayed automatic path.
            a.settings.set('unified_autofix',True);a._choose_layout('unified');until(done)
            for pane in (w,q):
                a.settings.set('quick_autofix',True)
                if pane is w:set_text('漢字')
                else:pane.replace('1.0','end-1c','漢字')
                select(pane,'1.0','1.2');key(pane,'F6',117)
                if pane is w:until(done)
                else:until(lambda:getattr(a,'_quick_after_id',None) is None)
                assert text(pane)=='かんじ',('automatic F6',text(pane))
            a.settings.set('quick_autofix',False)
            # Relative references, absolute references, blank and out-of-range.
            for layout in ('split','unified'):
                a.settings.set('unified_autofix',False);a._choose_layout(layout);until(done)
                for command,expected in (('-1','前の行'),('+1','後の行'),('1','前の行'),('－１','前の行')):
                    set_text('前の行\n差込\n後の行');w.mark_set('insert','2.end')
                    a.toggle_pick_mode();w.insert('insert',command);key(w,'Return',13)
                    assert text()=='前の行\n差込'+expected+'\n後の行',(command,text())
                    assert a._pick_mode is None
                set_text('前\n\n後');w.mark_set('insert','3.end')
                a.toggle_pick_mode();w.insert('insert','-1');key(w,'Return',13)
                assert text()=='前\n\n後' and a._pick_mode is None
                set_text('前\n後');w.mark_set('insert','1.end')
                a.toggle_pick_mode();w.insert('insert','-9');key(w,'Return',13)
                assert text()=='前-9\n後' and a._pick_mode
                a._end_pick_mode()
            # A signed integer is a row command even immediately after a calculation.
            set_text('前の行\n基点\n後の行');w.mark_set('insert','2.end')
            a.toggle_pick_mode();w.insert('insert','1+1');key(w,'Return',13);until(done)
            a.toggle_pick_mode();w.insert('insert','+1');key(w,'Return',13)
            assert a._pick_mode is None and '後の行' in w.get('2.0','2.end'),text()
            set_text('前の行\n基点\n後の行');w.mark_set('insert','2.end')
            q.replace('1.0','end-1c','');q.mark_set('insert','1.0')
            a._start_pick_mode(False,target='quick');q.insert('insert','+1');key(q,'Return',13)
            assert text(q)=='後の行' and a._pick_mode is None
            # List picks continue; only the first pick creates a blank separator.
            set_text('頭😀末\n既存行');w.mark_set('insert','1.0+1c');a.toggle_list_mode()
            assert a._pick_mode=='list'
            a._pick_insert('一つ');a._pick_insert('二つ')
            assert text()=='頭😀末\n\n一つ\n二つ\n既存行',text()
            assert a._pick_mode=='list'
            w.edit_undo();assert text()=='頭😀末\n\n一つ\n既存行'
            key(w,'Escape',27);assert a._pick_mode is None
            set_text('元');a.toggle_list_mode()
            deliver_key(w,'<KeyPress>','x',88,char='x')
            assert a._pick_mode is None
            set_text('元');a.toggle_list_mode()
            # IME 'u' can arrive with the F6 keysym: insert it once and leave list mode.
            deliver_key(w,'<F6>','F6',117,char='u')
            assert a._pick_mode is None and text().count('u')==1
            # The normal drag/release quotation path is also the list path.
            set_text('置き先\n拾う文字');w.mark_set('insert','1.0');a.toggle_list_mode()
            select(w,'2.0','2.4')
            from types import SimpleNamespace
            event=SimpleNamespace(widget=w,x=0,y=0,state=0)
            with patch.object(a,'_drag_release',return_value=False), patch.object(a,'_trim_mouse_selection'), patch.object(a,'_editor_unit_under_pointer',return_value=None):
                assert a._on_editor_release(event)=='break'
            assert text()=='置き先\n\n拾う文字\n拾う文字' and a._pick_mode=='list'
            # Crossing tabs preserves the insertion owner and continues there.
            a._switch_tab(1);until(done);a._pick_insert('別資料');until(done)
            assert a.session.active==0 and '拾う文字\n別資料\n' in text(),text()
            a._end_pick_mode()
            # Move marked chunks, retaining sentence fragments; one Undo restores all text.
            set_text('前甲中乙後\n既存行');w.mark_set('insert','1.2')
            a.toggle_list_mode()  # Newly sent highlights take priority over turning the mode off.
            w.mark_set('insert','1.2')
            a._mark_quick_sent('1.1',1);a._mark_quick_sent('1.3',1)
            a.toggle_list_mode()
            assert text()=='前中後\n\n甲\n乙\n既存行',text()
            assert a._pick_mode is None and not w.tag_ranges('quick_sent_a') and not w.tag_ranges('quick_sent_b')
            w.edit_undo();assert text()=='前甲中乙後\n既存行'
            # At line start, keep the first A and split only the contiguous A/B/A run.
            set_text('甲乙丙\n前丁後\n次');w.mark_set('insert','2.1')
            for index in ('1.0','1.1','1.2','2.1'):a._mark_quick_sent(index,1)
            a.toggle_list_mode();assert text()=='甲\n乙\n丙\n前丁後\n次',text()
            assert a.store.revision()==baseline,'Initial vocabulary changed'
            assert not errors,errors
            print('EDITOR_OPERATIONS_PASSED',flush=True)
        finally:
            if a is not None:a._on_close()
            else:root.destroy()


class EditorOperationsApplicationTests(unittest.TestCase):
    def test_requested_operations_in_real_initial_application(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-editor-operations-') as directory:
            dest=Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.ui-operations-isolated').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child'],
                cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=300)
            self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('EDITOR_OPERATIONS_PASSED',run.stdout)


if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:unittest.main()
