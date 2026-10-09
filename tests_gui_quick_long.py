# -*- coding: utf-8 -*-
"""Quick long rows on synthetic, nonactivated owned Windows desktops only."""
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path


def real_quick_child():
    import tkinter as tk
    import tkinter.font as tkfont
    from unittest.mock import Mock,patch
    from contextlib import ExitStack
    import app,quick_analysis
    from session import new_tab
    from text_links import TextLinks
    assert Path('.quick-long-owned').exists()
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False,unified_autofix=False,quick_autofix=False)),encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='')])),encoding='utf8')
    root=tk.Tk();root.withdraw();a=None;errors=[];clipboard=[]
    root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
    def forbid(*a,**k):clipboard.append(True);raise AssertionError('No clipboard access')
    root.clipboard_clear=root.clipboard_append=root.clipboard_get=forbid
    root.tk.eval('rename clipboard {}; proc clipboard {args} {error "No clipboard access"}')
    disabled=('_start_warmup','_analyze','_analyze_if_changed','_schedule_analysis_chunk','_learn_now','_schedule_learning','_first_run_setup')
    with ExitStack() as stack:
        stack.enter_context(patch.object(app,'GlobalHotkeys',return_value=Mock()))
        stack.enter_context(patch.object(tk.Toplevel,'winfo_pointerxy',return_value=(5,5)))
        stack.enter_context(patch.object(app,'monitor_work_area',return_value=(0,0,460,800)))
        stack.enter_context(patch.object(quick_analysis,'schedule_prepare'))
        scheduled=stack.enter_context(patch.object(quick_analysis,'schedule_change'))
        for method in disabled:stack.enter_context(patch.object(app.CorrectNoteApp,method,lambda *a,**k:None))
        try:
            a=app.CorrectNoteApp(root);root.geometry('700x400+0+0');root.deiconify();root.update()
            a._show_quick_capture(incoming_mode=0,selection=None);text=a._quick_text;root.update()
            display=text._correctnote_line_display
            assert not display._links_enabled and display._pending is None
            assert TextLinks.TAG not in text.tag_names()
            assert text._correctnote_observers['changed'].count(display.changed)==1
            assert display.view_changed not in text._correctnote_observers.get('viewed',())
            before=a.editor.get('1.0','end-1c');font=tkfont.Font(font=text.cget('font'));measured=[]
            proxy=Mock(wraps=font)
            proxy.measure.side_effect=lambda value:(measured.append(len(value)),font.measure(value))[1]
            with patch.object(a,'_quick_font',return_value=proxy),patch.object(a,'_start_pick_mode') as picked:
                for source in ('data:image/png;base64,'+'A'*36000+'==','長'*36000+'=='):
                    text.delete('1.0','end');text.insert('1.0',source);text.mark_set('insert','end-1c')
                    assert TextLinks.UNWRAPPED_TAG in text.tag_names('1.0')
                    started=time.perf_counter();a._on_quick_change();root.update();elapsed=time.perf_counter()-started
                    assert elapsed<2.0,elapsed
                    assert text.get('1.0','end-1c')==source
                    assert int(text.tk.call(text._w,'count','-displaylines','1.0','end'))==1
                    assert int(text.cget('height'))==a.QUICK_MIN_LINES
                    assert a._quick_win.winfo_width()<=420,a._quick_win.geometry()
                    picked.assert_not_called();assert max(measured)<=4000
                text.delete('1.0','end');text.insert('1.0','短い文章です。');a._on_quick_change();root.update()
                assert not text.tag_ranges(TextLinks.UNWRAPPED_TAG)
                assert text.get('1.0','end-1c')=='短い文章です。' and scheduled.called
            assert a.editor.get('1.0','end-1c')==before
            old_callbacks=text._correctnote_observers
            text.delete('1.0','end');a._close_quick_capture()
            assert display.changed not in old_callbacks.get('changed',())
            a._show_quick_capture(incoming_mode=0,selection=None);root.update();text=a._quick_text
            assert text._correctnote_observers['changed'].count(text._correctnote_line_display.changed)==1
            text.delete('1.0','end');a._close_quick_capture()
            print('QUICK_LONG_REAL_OK data/Japanese 36K, bounded measure, narrow window, no pick, short recovery, close/reopen',flush=True)
        finally:
            if a:
                if getattr(a,'_quick_text',None) is not None:a._quick_text.delete('1.0','end');a._close_quick_capture()
                a._on_close()
            else:root.destroy()
    assert not errors and not clipboard,(errors,clipboard)


class QuickLongRowsGuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        import tkinter.font as tkfont
        from unittest.mock import Mock,patch
        import app
        from text_links import TextLinks
        self.tk=tk;self.root=tk.Tk();self.root.withdraw();self.win=tk.Toplevel(self.root);self.win.geometry('420x200+0+0');self.errors=[]
        self.root.report_callback_exception=lambda *e:self.errors.append(e)
        self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);self.a.root=self.root;self.a._quick_win=self.win
        self.text=tk.Text(self.win,undo=True,wrap='char',font=('Consolas',12),padx=10,pady=8);self.text.pack(fill='both',expand=True)
        self.a._quick_text=self.text;self.a._pick_mode=None;self.a._start_pick_mode=Mock()
        self.font=tkfont.Font(font=self.text.cget('font'));self.font_proxy=Mock(wraps=self.font);self.a._quick_font=lambda:self.font_proxy
        self.display=TextLinks(self.text,links=False)
        self.area=patch.object(app,'monitor_work_area',return_value=(0,0,460,800));self.area.start();self.root.update()

    def tearDown(self):
        self.area.stop();self.root.destroy();self.assertEqual(self.errors,[])

    def tagged(self,row=1):
        from text_links import TextLinks
        return TextLinks.UNWRAPPED_TAG in self.text.tag_names(str(row)+'.0')

    def test_narrow_mixed_rows_measure_only_short_text_and_restore_wrapping(self):
        from literal_lines import literal_only
        data='data:image/png;base64,'+'A'*36000+'=='
        short='普通の文。'*100
        self.text.insert('1.0',data+'\n'+short)
        self.a._adjust_quick_size(self.text);self.root.update()
        self.assertTrue(self.tagged());self.assertFalse(self.tagged(2))
        self.assertEqual(self.text.cget('wrap'),'char')
        self.assertEqual(int(self.text.tk.call(self.text._w,'count','-displaylines','1.0','2.0')),1)
        self.assertGreater(int(self.text.tk.call(self.text._w,'count','-displaylines','2.0','end')),1)
        self.assertTrue(all(len(x.args[0])<=4000 for x in self.font_proxy.measure.call_args_list))
        self.text.replace('1.0','1.end','短文です。');self.a._adjust_quick_size(self.text);self.root.update()
        self.assertFalse(self.tagged());self.assertFalse(literal_only('短文です。'))
        self.assertEqual(self.text.get('2.0','2.end'),short)

    def test_data_equals_does_not_enter_pick_but_ordinary_equals_still_does(self):
        for value in ('data:,abc==','data:image/png;base64,'+'A'*900+'==','長'*4001+'='):
            self.text.delete('1.0','end');self.text.insert('1.0',value);self.text.mark_set('insert','end-1c')
            self.a._maybe_start_quick_pick_from_equals();self.a._start_pick_mode.assert_not_called()
            self.assertEqual(self.text.get('1.0','end-1c'),value)
        self.text.delete('1.0','end');self.text.insert('1.0','引用=');self.text.mark_set('insert','end-1c')
        self.a._maybe_start_quick_pick_from_equals();self.a._start_pick_mode.assert_called_once_with(via_equals=True,target='quick')

    def test_display_only_keeps_undo_selection_and_adds_no_link_bindings(self):
        from unittest.mock import patch
        import text_links,text_edit
        self.text.insert('1.0','x'*4001);self.text.edit_reset();self.text.edit_modified(False)
        self.text.tag_add('sel','1.2','1.8');before=self.text.get('sel.first','sel.last')
        self.display.changed();self.assertEqual(self.text.get('sel.first','sel.last'),before);self.assertFalse(self.text.edit_modified())
        with self.assertRaises(self.tk.TclError):self.text.edit_undo()
        self.text.insert('1.2000','\n');self.text.edit_separator();self.assertFalse(self.tagged());self.assertFalse(self.tagged(2))
        original=text_edit.UnicodeUndoCommand._invoke;sees=[]
        def invoke(command,args):
            if args and args[0]=='see' and command.widget is self.text:
                sees.append(args);self.assertEqual(self.tagged(),len(self.text.get('1.0','1.end'))>4000)
            return original(command,args)
        with patch.object(text_edit.UnicodeUndoCommand,'_invoke',invoke):
            self.text.edit_undo();self.assertTrue(self.tagged());self.text.edit_redo();self.assertFalse(self.tagged())
        self.assertTrue(sees)
        with patch.object(text_links,'find_links',side_effect=AssertionError('No link detection in Quick display')):
            self.text.delete('1.0','end');self.text.insert('1.0','https://example.test/');self.root.update()
        self.assertNotIn(text_links.TextLinks.TAG,self.text.tag_names())
        self.assertEqual(set(self.display._bindings),{'<Configure>','<Destroy>'});self.assertIsNone(self.display._pending)


class QuickLongRealAppGuiTests(unittest.TestCase):
    def test_actual_quick_creation_and_lifecycle_initial_state(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-quick-long-') as folder:
            dest=Path(folder)
            for path in source.iterdir():
                if path.is_file() and (path.suffix=='.py' or path.name in NAMES):shutil.copyfile(path,dest/path.name)
            (dest/'.quick-long-owned').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=90)
            print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout);self.assertIn('QUICK_LONG_REAL_OK',run.stdout)


if __name__=='__main__':real_quick_child() if '--child' in sys.argv else unittest.main()
