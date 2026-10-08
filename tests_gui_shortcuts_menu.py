"""Key and menu behavior on an isolated synthetic Tk document."""
import ctypes,json,shutil,subprocess,sys,tempfile,time,traceback,unittest
from pathlib import Path


def child():
    import tkinter as tk
    from types import SimpleNamespace
    from unittest.mock import Mock,patch
    import app,analysis_work_app as work
    from session import new_tab
    assert (Path.cwd()/'.ui-test-isolated').exists()
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf-8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='資料を読みます。')]),ensure_ascii=False),encoding='utf-8')
    root=tk.Tk();root.withdraw();a=None;errors=[];copied=['']
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    root.tk.eval('''
        rename clipboard test_original_clipboard
        proc clipboard {operation args} {
            switch -- $operation {
                clear {set ::test_clipboard {}}
                append {append ::test_clipboard [lindex $args end]}
                get {return $::test_clipboard}
                default {error "Unexpected clipboard operation"}
            }
        }
        rename ::tk::GetSelection ::tk::test_original_GetSelection
        proc ::tk::GetSelection {w selection} {
            if {$selection eq "CLIPBOARD"} {return $::test_clipboard}
            return [::tk::test_original_GetSelection $w $selection]
        }
    ''')
    def until(predicate,seconds=45):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            root.update();assert not errors,errors
            if predicate():return
            time.sleep(.005)
        raise AssertionError(a.status.cget('text'))
    def done():
        return (a._analyze_text==a.editor_source_text() and
                a._analyze_work==work.token(a) and not a._foreground_analysis_pending())
    def key(sequence):
        a.editor.event_generate(sequence);root.update();assert not errors,errors
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.PostMessageW.argtypes=(ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t)
    user32.PostMessageW.restype=ctypes.c_int
    def native_key(vk,widget=None):
        target=widget if widget is not None else a.editor
        # Tk routes native key messages to its focused widget, even when the
        # posted HWND belongs to another widget. focus_get is mocked below,
        # so verify the real Tcl focus before sending a Windows key message.
        target.focus_force()
        until(lambda:str(root.tk.call('focus'))==str(target),seconds=2)
        assert target.winfo_viewable(),str(target)
        hwnd=target.winfo_id()
        assert user32.PostMessageW(hwnd,0x100,vk,1)
        assert user32.PostMessageW(hwnd,0x101,vk,0xC0000001)
        for _ in range(4):root.update();time.sleep(.005)
        assert not errors,errors
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *args:None):
        try:
            a=app.CorrectNoteApp(root);until(done)
            original_focus=root.focus_get;root.focus_get=lambda:a.editor
            menu=a._edit_menu
            labels={menu.entrycget(i,'label'):i for i in range(menu.index('end')+1) if menu.type(i)!='separator'}
            for label,accelerator in [('検索…','Ctrl+F'),
                ('コピー','選択してF1 / Ctrl+C'),('ペースト','F4 / Ctrl+V / Win+V'),
                ('改行','F3 / Enter'),('後ろ1文字を削除','CapsLock / BackSpace'),
                ('括弧を挿入','F5入力ごとに括弧を切替'),
                ('語を拾って差し込む','無選択でF1 / = / Insert'),
                ('簡易入力ウィンドウを開く','Ctrl+Insert')]:
                assert menu.entrycget(labels[label],'accelerator')==accelerator,label
            assert '次を検索' not in labels
            assert a.settings.get('capslock_backspace_enabled') is True
            assert a.settings.get('insert_quote_enabled') is True
            assert not a._plain_shortcut(SimpleNamespace(keysym='F5',char='',state=0x20000))
            a.editor.tag_add('sel','1.0','1.2')
            menu.invoke(labels['コピー'])
            assert root.tk.getvar('test_clipboard')=='資料'
            key('<F1>')
            assert root.tk.getvar('test_clipboard')=='資料'
            assert not getattr(a,'_pick_mode',None)
            a.editor.tag_remove('sel','1.0','end')
            a.result_view.tag_add('sel','1.0','1.2')
            a._on_pick_key(SimpleNamespace(widget=a.editor,keysym='F1',char='',state=0))
            assert getattr(a,'_pick_mode',None)
            a.result_view.tag_remove('sel','1.0','end')
            key('<F1>');assert not getattr(a,'_pick_mode',None)
            # The same F1 split works in the read-only correction pane.
            a.result_view.tag_add('sel','1.0','1.2')
            a.result_view.event_generate('<F1>');root.update()
            assert root.tk.getvar('test_clipboard')=='資料'
            a.result_view.tag_remove('sel','1.0','end')
            a.editor.mark_set('insert','1.end');key('<F4>')
            assert a.editor.get('1.0','1.end').endswith('資料')
            menu.invoke(labels['ペースト'])
            assert a.editor.get('1.0','1.end').endswith('資料資料')
            with patch.object(a.editor,'event_generate',wraps=a.editor.event_generate) as generate:
                assert a.editor.bind('<F3>')
                assert a._on_f3_return(SimpleNamespace(widget=a.editor,keysym='F3',char='',state=0,keycode=114))=='break'
                generate.assert_any_call('<Return>')
            menu.invoke(labels['改行']);assert a.editor.index('insert').startswith('2.')
            a.editor.insert('2.0','あ');a.editor.mark_set('insert','2.1')
            with patch.object(a.editor,'event_generate',wraps=a.editor.event_generate) as generate:
                assert a.editor.bind('<Caps_Lock>')
                assert a._on_caps_backspace(SimpleNamespace(widget=a.editor,keysym='Caps_Lock',char='',state=0))=='break'
                generate.assert_any_call('<BackSpace>')
            menu.invoke(labels['後ろ1文字を削除']);assert a.editor.get('2.0','2.end')==''
            a.editor.insert('2.0','い');a.editor.mark_set('insert','2.1')
            a.capslock_backspace_var.set(False)
            a._on_toggle_edit_shortcut('capslock_backspace_enabled',a.capslock_backspace_var)
            assert menu.entrycget(labels['後ろ1文字を削除'],'accelerator')=='BackSpace'
            assert a._on_caps_backspace(SimpleNamespace(widget=a.editor,keysym='Caps_Lock',char='',state=0)) is None
            assert a.editor.get('2.0','2.end')=='い'
            menu.invoke(labels['後ろ1文字を削除']);assert a.editor.get('2.0','2.end')==''
            a.editor.mark_set('insert','1.0');assert a.editor.bind('<Insert>')
            assert a._on_insert_quote(SimpleNamespace(widget=a.editor,keysym='Insert',char='',state=0))=='break'
            assert getattr(a,'_pick_mode',None)
            a._on_insert_quote(SimpleNamespace(widget=a.editor,keysym='Insert',char='',state=0));assert not getattr(a,'_pick_mode',None)
            a.insert_quote_var.set(False)
            a._on_toggle_edit_shortcut('insert_quote_enabled',a.insert_quote_var)
            assert menu.entrycget(labels['簡易入力ウィンドウを開く'],'accelerator')=='Ctrl+Insert'
            a._on_insert_quote(SimpleNamespace(widget=a.editor,keysym='Insert',char='',state=0));assert not getattr(a,'_pick_mode',None)
            a.editor.mark_set('insert','1.0')
            assert a.editor.bind('<Break>') or a.editor.bind('<Pause>')
            assert a.editor.bind('<Cancel>')
            a._on_break_bookmark(SimpleNamespace(widget=a.editor,keysym='Break',char='',state=0))
            assert 1 in a.bookmarks,a.bookmarks
            # The menu invokes the same bookmark toggle and native edit path.
            menu.invoke(labels['ブックマーク切替']);assert 1 not in a.bookmarks
            root.geometry('1x1+10000+10000');root.deiconify();root.update()
            # A newly mapped CI window may focus the toplevel instead of the
            # editor. Deliberately start there to exercise native_key's setup.
            root.focus_force();root.update()
            assert str(root.tk.call('focus'))==str(root)
            native_key(0x13)  # WM_KEYDOWN(VK_PAUSE), including Tk's state bit 8
            assert 1 in a.bookmarks,a.bookmarks
            native_key(0x03)  # VK_CANCEL is another Windows Break form
            assert 1 not in a.bookmarks,a.bookmarks
            # Native routing also reaches the correction pane, not only editor.
            a.result_view.tag_remove('sel','1.0','end')
            a.result_view.mark_set('insert','1.0')
            native_key(0x13,a.result_view)
            assert 1 in a.bookmarks,a.bookmarks
            native_key(0x03,a.result_view)
            assert 1 not in a.bookmarks,a.bookmarks
            assert a.editor.bind('<F5>')
            assert len(a._bracket_buttons)==5
            assert all(label not in labels for label in
                       ('（）を挿入','「」を挿入','『』を挿入','【】を挿入','“”を挿入'))
            a.editor.delete('1.0','end');a.editor.insert('1.0','語')
            a.editor.mark_set('insert','1.end');a.editor.focus_force();root.update()
            for expected in ('語（）','語「」','語『』','語【】','語“”','語（）'):
                key('<F5>')
                assert a.editor.get('1.0','1.end')==expected,expected
            key('<Escape>')
            assert a.editor.get('1.0','1.end')=='語'
            assert a.editor.index('insert')=='1.1'
            menu.invoke(labels['括弧を挿入'])
            assert a.editor.get('1.0','1.end')=='語（）'
            key('<F5>')
            assert a.editor.get('1.0','1.end')=='語「」'
            key('<Escape>')
            assert a.editor.get('1.0','1.end')=='語'
            # Each bracket button assigns its own style; Escape cancels the gesture.
            a.editor.delete('1.0','end');a.editor.insert('1.0','語')
            a.editor.tag_add('sel','1.0','1.1')
            a.editor.mark_set('insert','1.1')
            buttons=a._bracket_buttons
            a._on_bracket_click(SimpleNamespace(widget=buttons[0],num=1))
            buttons[0].invoke()
            assert a.editor.get('1.0','1.end')=='（語）'
            a._on_bracket_click(SimpleNamespace(widget=buttons[1],num=1))
            buttons[1].invoke()
            assert a.editor.get('1.0','1.end')=='「語」'
            buttons[1].invoke()
            assert a.editor.get('1.0','1.end')=='「語」'
            key('<Escape>')
            assert a.editor.get('1.0','1.end')=='語'
            assert tuple(map(str,a.editor.tag_ranges('sel')))==('1.0','1.1')
            # ASCII selection keeps halfwidth parentheses across a replacement.
            a.editor.delete('1.0','end');a.editor.insert('1.0','abc')
            a.editor.tag_add('sel','1.0','1.3')
            buttons[0].invoke();assert a.editor.get('1.0','1.end')=='(abc)'
            buttons[2].invoke();assert a.editor.get('1.0','1.end')=='『abc』'
            buttons[0].invoke();assert a.editor.get('1.0','1.end')=='(abc)'
            key('<Escape>');assert a.editor.get('1.0','1.end')=='abc'
            # Clicking elsewhere or moving vertically commits the visible pair.
            a.editor.tag_remove('sel','1.0','end')
            a.editor.mark_set('insert','1.end')
            key('<F5>');assert a.editor.get('1.0','1.end')=='abc（）'
            a.editor.event_generate('<ButtonPress-1>',x=5,y=5);root.update()
            assert a._bracket_cycle is None
            key('<Escape>');assert a.editor.get('1.0','1.end')=='abc（）'
            a.editor.mark_set('insert','1.end')
            key('<F5>');assert a.editor.get('1.0','1.end')=='abc（）（）'
            key('<Up>');assert a._bracket_cycle is None
            key('<Escape>')
            assert a.editor.get('1.0','1.end')=='abc（）（）'
            a.editor.mark_set('insert','1.end')
            key('<F5>')
            key('<Down>');assert a._bracket_cycle is None
            key('<Escape>')
            assert a.editor.get('1.0','1.end')=='abc（）（）（）'
            a.editor.delete('1.0','end');a.editor.insert('1.0','語')
            a.editor.mark_set('insert','1.end')
            key('<F5>')
            a.layout_split_btn.event_generate('<ButtonPress-1>',x=2,y=2)
            root.update();assert a._bracket_cycle is None
            key('<Escape>');assert a.editor.get('1.0','1.end')=='語（）'
            a.editor.edit_undo();root.update()
            assert a.editor.get('1.0','1.end')=='語'
            # F2's chosen word stays the target through replacement and Escape.
            a.editor.delete('1.0','end');a.editor.insert('1.0','語')
            a.editor.mark_set('insert','1.end')
            a._f2_focus_target=dict(widget=a.editor,row=1,start=0,end=1,text='語')
            buttons[2].invoke();assert a.editor.get('1.0','1.end')=='『語』'
            buttons[3].invoke();assert a.editor.get('1.0','1.end')=='【語】'
            key('<Escape>');assert a.editor.get('1.0','1.end')=='語'
            # Switching tabs commits the pair even after returning.
            a.editor.mark_set('insert','1.end')
            key('<F5>');assert a.editor.get('1.0','1.end')=='語（）'
            a.session.tabs.append(new_tab(text='別のタブ'))
            a._switch_tab(1);until(done)
            a._switch_tab(0);until(done)
            key('<Escape>');assert a.editor.get('1.0','1.end')=='語（）'
            # The same gesture works when corrected text shares the input pane.
            a._set_layout_unified();until(done)
            a.editor.delete('1.0','end');a.editor.insert('1.0','語')
            a.editor.mark_set('insert','1.end')
            key('<F5>');key('<F5>')
            assert a.editor.get('1.0','1.end')=='語「」'
            key('<Escape>');assert a.editor.get('1.0','1.end')=='語'
            a._set_layout_split();until(done)
            # Whole-line selections keep the trailing newline outside the pair.
            a.editor.delete('1.0','end');a.editor.insert('1.0','一行\n二行\n')
            a.editor.tag_add('sel','1.0','3.0')
            buttons[0].invoke()
            assert a.editor.get('1.0','3.0')=='（一行\n二行）\n'
            key('<F5>')
            assert a.editor.get('1.0','3.0')=='「一行\n二行」\n'
            key('<Escape>')
            assert a.editor.get('1.0','3.0')=='一行\n二行\n'
            # A real Win32 F5 message can carry Tk state bit 8 without Alt.
            a.editor.delete('1.0','end');a.editor.insert('1.0','語')
            a.editor.mark_set('insert','1.end')
            native_key(0x74)
            assert a.editor.get('1.0','1.end')=='語（）'
            # An IME-confirmed Latin character masquerading as F5 stays text.
            a.editor.delete('1.0','end');a.editor.insert('1.0','語')
            a.editor.mark_set('insert','1.end')
            a._on_f5_brackets(SimpleNamespace(widget=a.editor,keysym='F5',char='t',state=0,keycode=116));root.update()
            assert a.editor.get('1.0','1.end')=='語t'
            # Check menu hover dispatch against Tk's actual Menubutton paths
            # without posting an OS-native menu in this headless child.
            b0,b1=a._menu_buttons[:2]
            root.tk.globalsetvar('tk::Priv(postedMb)',str(b0))
            root.tk.eval('rename tk::MbPost test_original_MbPost; proc tk::MbPost {w args} {set ::tk::Priv(postedMb) $w}')
            try:
                with patch.object(a._menu_bar_frame,'winfo_rootx',return_value=0),\
                     patch.object(a._menu_bar_frame,'winfo_rooty',return_value=0),\
                     patch.object(a._menu_bar_frame,'winfo_width',return_value=200),\
                     patch.object(a._menu_bar_frame,'winfo_height',return_value=25),\
                     patch.object(b0,'winfo_rootx',return_value=0),\
                     patch.object(b0,'winfo_rooty',return_value=0),\
                     patch.object(b0,'winfo_width',return_value=50),\
                     patch.object(b0,'winfo_height',return_value=25),\
                     patch.object(b1,'winfo_rootx',return_value=50),\
                     patch.object(b1,'winfo_rooty',return_value=0),\
                     patch.object(b1,'winfo_width',return_value=50),\
                     patch.object(b1,'winfo_height',return_value=25):
                    a._on_menu_bar_motion(SimpleNamespace(x_root=60,y_root=10))
                    assert root.tk.globalgetvar('tk::Priv(postedMb)')==str(b1)
                    root.tk.globalsetvar('tk::Priv(postedMb)',str(b0))
                    with patch.object(root,'winfo_pointerxy',return_value=(60,10)):
                        a._start_menu_hover_watch()
                        until(lambda:root.tk.globalgetvar('tk::Priv(postedMb)')==str(b1),seconds=2)
                    # The first poll may precede Tk's native menu posting.
                    root.tk.globalsetvar('tk::Priv(postedMb)','')
                    with patch.object(root,'winfo_pointerxy',return_value=(60,10)):
                        a._start_menu_hover_watch()
                        root.after(90,lambda:root.tk.globalsetvar('tk::Priv(postedMb)',str(b0)))
                        until(lambda:root.tk.globalgetvar('tk::Priv(postedMb)')==str(b1),seconds=2)
            finally:
                root.tk.eval('rename tk::MbPost {}; rename test_original_MbPost tk::MbPost')
                root.tk.globalsetvar('tk::Priv(postedMb)','')
                if a._menu_hover_after_id is not None:
                    root.after_cancel(a._menu_hover_after_id)
                    a._menu_hover_after_id=None
            tab=a._tab_widgets[0]['label'];a._tab_hover_hint(SimpleNamespace(widget=tab),True)
            assert '右クリック' in a.editor_header.cget('text')
            a._tab_hover_hint(SimpleNamespace(widget=tab),False)
            assert '右クリック' not in a.editor_header.cget('text')
            assert a.settings.get('capslock_backspace_enabled') is False
            assert a.settings.get('insert_quote_enabled') is False
            assert menu.entrycget(labels['語を拾って差し込む'],'accelerator')=='無選択でF1 / ='
            print('SHORTCUTS_MENU_OK',flush=True)
        finally:
            root.focus_get=original_focus
            if a:a._on_close()
            else:root.destroy()


class ShortcutsMenuGuiTests(unittest.TestCase):
    def test_keys_menus_and_tab_hint(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-shortcuts-') as folder:
            dest=Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            run=subprocess.run([sys.executable,'-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=180)
            print(run.stdout,flush=True)
            self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('SHORTCUTS_MENU_OK',run.stdout)


if __name__=='__main__':
    child() if '--child' in sys.argv else unittest.main()
