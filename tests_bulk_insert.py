# -*- coding: utf-8 -*-
"""Selected-row boundaries, grouped undo, window lifetime and current-value persistence."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path
from bulk_insert import insertion_offsets


class OffsetTests(unittest.TestCase):
    def test_each_selected_fragment_has_its_own_start_and_end(self):
        self.assertEqual(insertion_offsets('cde\nfghij\nkl',1),([1,5,11],0))
        self.assertEqual(insertion_offsets('cde\nfghij\nkl',1,True),([2,8,11],0))
    def test_edges_blank_lines_and_exclusive_next_line(self):
        self.assertEqual(insertion_offsets('abc\n\nz\n',0),([0,4,5],0))
        self.assertEqual(insertion_offsets('abc\n\nz\n',0,True),([3,4,6],0))
        self.assertEqual(insertion_offsets('\n',0),([0],0))
        self.assertEqual(insertion_offsets('',0),([],0))
    def test_outside_position_uses_the_opposite_edge_of_each_fragment(self):
        self.assertEqual(insertion_offsets('abc\nfghij\nkl',5),([3,9,12],2))
        self.assertEqual(insertion_offsets('abc\nfghij\nkl',5,True),([0,4,10],2))
        self.assertEqual(insertion_offsets('😀a\n\nz\n',99),([2,3,5],3))
        self.assertEqual(insertion_offsets('😀a\n\nz\n',99,True),([0,3,4],3))
    def test_unicode_codepoints_are_not_utf16_units(self):
        self.assertEqual(insertion_offsets('😀ab\n終😀',1),([1,5],0))
        self.assertEqual(insertion_offsets('😀ab\n終😀',1,True),([2,5],0))
    def test_invalid_distances_do_not_produce_an_edit(self):
        for value in (-1,1.5,True,None):
            with self.subTest(value=value),self.assertRaises(ValueError):insertion_offsets('abc',value)


def child(phase):
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,analysis_work_app as work
    from session import new_tab
    from tests_tk_keys import deliver_key
    assert Path('.bulk-insert-isolated').exists()
    if phase=='edit':
        Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False,unified_autofix=False)),encoding='utf8')
        Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='')])),encoding='utf8')
    root=tk.Tk();root.withdraw();a=None;errors=[]
    root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
    root.clipboard_clear=lambda **kw:None;root.clipboard_append=lambda *v,**kw:None
    def settle():
        root.update();assert not errors,errors
    def until(test):
        limit=time.monotonic()+90
        while True:
            settle()
            if test():return
            assert time.monotonic()<limit,('timeout',a.status.cget('text'))
            time.sleep(.005)
    def body():return a.editor.get('1.0','end-1c').rstrip('\n')
    try:
        with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *v:None):
            a=app.CorrectNoteApp(root);root.geometry('900x480+0+0');root.deiconify()
            until(lambda:not a._foreground_analysis_pending() and a._analyze_work==work.token(a))
            a.bulk_insert_btn.invoke();settle();d=a._bulk_insert
            if phase=='restart':
                assert d.text.get('1.0','end-1c')=='次回😀\n保持'
                assert (d.direction.get(),d.distance.get())==('end','2')
                print('BULK_RESTART_OK',flush=True);return
            for dark in (True,False):
                a._apply_theme(dark);settle()
                assert d.text.cget('bg')==app.PANEL and d.text.cget('fg')==app.INK
                assert d.position.cget('bg')==app.PANEL and d.position.cget('fg')==app.INK
            ordered=a._toolbar.pack_slaves()
            assert ordered.index(a.bulk_insert_btn)==ordered.index(a.word_book_btn)+1
            assert a.bulk_insert_btn.winfo_ismapped()
            assert a.bulk_insert_btn.winfo_width()==a.bulk_insert_btn.winfo_reqwidth()
            def prepare(text,first,last,distance=0,direction='start',insertion='■'):
                a.editor.delete('1.0','end');a.editor.insert('1.0',text)
                a.editor.edit_reset();a.editor.tag_add('sel',first,last)
                d.direction.set(direction);d.distance.set(str(distance))
                d.text.delete('1.0','end');d.text.insert('1.0',insertion)
            for layout in ('split','unified'):
                a.settings.set('layout',layout);a._apply_layout();settle()
                prepare('ABCDE\nFGHIJ\nKLMNO','1.0+2c','3.0+2c',1)
                d.execute.invoke();settle()
                assert body()=='ABC■DE\nF■GHIJ\nK■LMNO',(layout,body())
                a.editor.edit_undo();assert body()=='ABCDE\nFGHIJ\nKLMNO',body()
                a.editor.edit_redo();assert body()=='ABC■DE\nF■GHIJ\nK■LMNO',body()
                prepare('ABCDE\nFGHIJ\nKLMNO','1.0+2c','3.0+2c',1,'end')
                d.execute.invoke();assert body()=='ABCD■E\nFGHI■J\nK■LMNO',body()
                prepare('😀abc\n終😀xyz','1.0+1c','2.0+2c',1,'end','☆😀')
                d.execute.invoke();assert body()=='😀ab☆😀c\n終☆😀😀xyz',body()
                a.editor.edit_undo();assert body()=='😀abc\n終😀xyz',body()
                prepare('前\n\n後\n次','1.0','4.0',0,'end','!')
                d.execute.invoke();assert body()=='前!\n!\n後!\n次',body()
                prepare('abc\nx\nend','1.0','3.end',2,'start','\n+')
                d.execute.invoke();assert body()=='ab\n+c\nx\n+\nen\n+d',body()
                assert '1行' in d.message.cget('text')
            # Preview markers are overlays: they never enter text, selection or Undo.
            prepare('ABCDE\nFGHIJ\nKLMNO','1.0+2c','3.0+2c',1)
            d.text.focus_force();settle()
            def preview_offsets():
                return [len(a.editor.get('1.0',point[0])) for point in d._preview_points]
            assert preview_offsets()==[3,7,13],preview_offsets()
            initial=body();selection_before=tuple(map(str,a.editor.tag_ranges('sel')))
            d.distance.set('2');settle();assert preview_offsets()==[4,8,14],preview_offsets()
            d.direction.set('end');settle();assert preview_offsets()==[3,9,12],preview_offsets()
            d.distance.set('99');settle();assert preview_offsets()==[2,6,12],preview_offsets()
            assert body()==initial and tuple(map(str,a.editor.tag_ranges('sel')))==selection_before
            assert a.editor.dump('1.0','end',window=True)==[],a.editor.dump('1.0','end',window=True)
            d.distance.set('bad');settle();assert not d._preview_points
            d.distance.set('0');settle();assert len(d._preview_points)==3
            a.editor.focus_force();settle();assert not d._preview_points
            d.text.focus_force();settle();assert len(d._preview_points)==3
            prepare('😀abc\n\n終😀xyz','1.0+1c','3.0+2c',1,'end')
            settle();assert preview_offsets()==[3,5,7],preview_offsets()
            # Scrolled-off rows create no overlay; a change in view queues a redraw.
            many='\n'.join('資料です。'*15 for i in range(80))
            prepare(many,'1.0','end-1c',3);settle()
            a.editor.yview_moveto(.7);settle()
            assert d._preview_points and len(d._preview_points)<20,len(d._preview_points)
            for index,x,y,height in d._preview_points:
                assert a.editor.bbox(index) is not None
                assert 0<=x<a.editor.winfo_width()
            a.editor.yview_moveto(0);settle()
            prepare('ABCDE','1.0','1.end',2);settle()
            assert preview_offsets()==[2]
            # A click on the visual caret is delivered back to the editor.
            marker=d._preview_markers[0]
            marker.event_generate('<ButtonPress-1>',x=0,y=3,
                rootx=marker.winfo_rootx(),rooty=marker.winfo_rooty()+3)
            settle();assert root.focus_get() is a.editor and not d._preview_points
            d.text.focus_force();settle()
            # Compact spacings are measured from actual mapped widgets.
            assert a._tab_viewport.winfo_rooty()-(a._menu_bar_frame.winfo_rooty()+a._menu_bar_frame.winfo_height())==2
            assert a._toolbar.winfo_rooty()-(a._tab_viewport.winfo_rooty()+a._tab_viewport.winfo_height())==2
            assert d.execute.winfo_rootx()<d.undo_button.winfo_rootx()<d.close_button.winfo_rootx()
            # Direct entry remains available; arrows add/subtract one with a zero floor.
            assert d.position.winfo_class()=='Spinbox'
            d.distance.set('12');d.position.invoke('buttonup');assert d.distance.get()=='13'
            d.position.invoke('buttondown');assert d.distance.get()=='12'
            d.distance.set('0');d.position.invoke('buttondown');assert d.distance.get()=='0'
            d.distance.set('12');d._update_position_menu()
            assert [int(d.position_menu.entrycget(i,'label')) for i in range(21)]==list(range(2,23))
            d.position_menu.invoke(11);assert d.distance.get()=='13'
            d.distance.set('12345');d._update_position_menu()
            d.position_menu.invoke(9);assert d.distance.get()=='12344'
            prepare('ABCDE\nFGHIJ\nKLMNO','1.0+2c','3.0+2c',99)
            selection=tuple(map(str,a.editor.tag_ranges('sel')))
            old_inactive=d._selection_style[0]
            for dark in (True,False):
                a._apply_theme(dark);d.text.focus_force();settle()
                assert root.focus_get() is d.text
                assert tuple(map(str,a.editor.tag_ranges('sel')))==selection
                assert a.editor.cget('inactiveselectbackground')==app.EDITOR_SEL_BG
                assert not a.editor.tk.getboolean(a.editor.cget('exportselection'))
            d.execute.invoke();assert body()=='ABCDE■\nFGHIJ■\nKL■MNO',body()
            d.execute.invoke();assert body()=='ABCDE■■\nFGHIJ■■\nKL■■MNO',body()
            d.undo_button.invoke();assert body()=='ABCDE■\nFGHIJ■\nKL■MNO',body()
            d.undo_button.invoke();assert body()=='ABCDE\nFGHIJ\nKLMNO',body()
            assert tuple(map(str,a.editor.tag_ranges('sel')))==selection
            d.undo_button.invoke();assert body()=='ABCDE\nFGHIJ\nKLMNO'
            prepare('ABCDE\nFGHIJ\nKLMNO','1.0+2c','3.0+2c',99,'end')
            d.execute.invoke();assert body()=='AB■CDE\n■FGHIJ\n■KLMNO',body()
            import ime_watch
            with patch.object(ime_watch,'composition_active',return_value=True):
                unchanged=body();d.undo_button.invoke();assert body()==unchanged
                d.execute.invoke();assert body()==unchanged
            d.undo_button.invoke();assert body()=='ABCDE\nFGHIJ\nKLMNO'
            # A preceding edit is never undone; later typing invalidates the button.
            prepare('abc','1.0','1.end',1)
            a.editor.insert('end-1c','tail');a.editor.edit_separator()
            d.execute.invoke();d.undo_button.invoke();assert body()=='abctail',body()
            a.editor.tag_add('sel','1.0','1.end');d.execute.invoke()
            a.editor.insert('end-1c','later');unchanged=body()
            d.undo_button.invoke();assert body()==unchanged and '本文の編集' in d.message.cget('text')
            prepare('abc','1.0','1.end',1)
            d.execute.invoke();a.editor.edit_undo();unchanged=body()
            d.undo_button.invoke();assert body()==unchanged
            # A real tab switch resets Tk history and must not undo another tab.
            prepare('abc','1.0','1.end',1);d.execute.invoke()
            a.new_file();settle();other=body();d.undo_button.invoke();assert body()==other
            prepare('abc\nx\nend','1.0','3.end',1)
            before=body();a.editor.tag_remove('sel','1.0','end')
            d.execute.invoke();assert body()==before and '選択' in d.message.cget('text')
            a.editor.tag_add('sel','1.0','end-1c');d.distance.set('-1')
            d.execute.invoke();assert body()==before and '整数' in d.message.cget('text')
            d.distance.set('999');d.execute.invoke();assert body()!=before and '端に挿入' in d.message.cget('text')
            d.undo_button.invoke();assert body()==before
            d.text.delete('1.0','end');d.text.insert('1.0','閉じても保持😀')
            deliver_key(a.editor,'<Escape>','Escape',27);settle()
            assert d.window is None
            assert not d._preview_markers and not d._preview_bindings and d._preview_job is None
            assert a.editor.cget('inactiveselectbackground')==old_inactive
            a.bulk_insert_btn.invoke();settle();assert d.text.get('1.0','end-1c')=='閉じても保持😀'
            deliver_key(d.text,'<Escape>','Escape',27);settle();assert d.window is None
            a.bulk_insert_btn.invoke();settle()
            d.text.delete('1.0','end');d.text.insert('1.0','次回😀\n保持')
            d.direction.set('end');d.distance.set('2')
            print('BULK_EDIT_UNDO_ESCAPE_OK',flush=True)
    finally:
        if a:a._on_close()
        else:root.destroy()
    assert not errors,errors


@unittest.skipUnless(sys.platform=='win32','Owned Windows GUI checks')
class BulkInsertGuiTests(unittest.TestCase):
    def test_selection_undo_escape_and_restart(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-bulk-insert-') as directory:
            dest=Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.bulk-insert-isolated').touch()
            for phase in ('edit','restart'):
                run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child',phase],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=200)
                print(run.stdout,flush=True)
                self.assertEqual(run.returncode,0,run.stdout)
                self.assertIn('BULK_'+('EDIT_UNDO_ESCAPE' if phase=='edit' else 'RESTART')+'_OK',run.stdout)


if __name__=='__main__':child(sys.argv[-1]) if '--child' in sys.argv else unittest.main()
