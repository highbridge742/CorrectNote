"""Isolated real Tk operations; never use the user's data or clipboard."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest


def child(phase):
    import tkinter as tk
    from types import SimpleNamespace as Event
    from unittest.mock import Mock, patch
    import app
    import analysis_work_app as work
    import analysis_worker
    from session import new_tab
    from tests_tk_keys import deliver_key
    here = Path.cwd()
    assert (here / '.toolbar-wordbook-isolated').exists()
    if phase in ('edit', 'layout', 'responsive', 'taskbar', 'sets_menu'):
        (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana',
            input_method_auto=False, unified_autofix=False)), encoding='utf8')
        (here / 'session.json').write_text(json.dumps(dict(version=1, active=0,
            tabs=[new_tab(text='')])), encoding='utf8')
    if phase == 'sets_menu':
        (here/'word_book.json').write_text(json.dumps(dict(words=['旧登録😀'],visible=False,width=110),ensure_ascii=False),encoding='utf8')
    root = tk.Tk(); root.withdraw(); a = None; errors = []; clipboard = []
    root.clipboard_clear = lambda **kw: clipboard.clear()
    root.clipboard_append = lambda text, **kw: clipboard.append(text)
    root.clipboard_get = lambda **kw: ''.join(clipboard)
    root.report_callback_exception = lambda *exc: errors.append(''.join(traceback.format_exception(*exc)))

    def until(predicate, seconds=90):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update()
            assert not errors, errors
            if predicate(): return
            time.sleep(.005)
        raise AssertionError((getattr(a, '_analyze_last_error', None), a.status.cget('text')))

    def done():
        return (not a._foreground_analysis_pending() and a._analyze_text == a.editor_source_text()
            and a._analyze_work == work.token(a) and a._analyze_dependencies == analysis_worker.state_key(a))

    def content(): return a.editor.get('1.0', 'end-1c').rstrip('\n')
    def set_text(value):
        if a._pick_mode: a._end_pick_mode()
        a._clear_quick_sent(); a._replace_editor_text(value); until(done)
        a.editor.edit_reset()
    def hover(button):
        button.event_generate('<Enter>'); root.update()
        return a.editor_header.cget('text')
    def leave(button):
        button.event_generate('<Leave>'); root.update()

    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
            patch.object(app.CorrectNoteApp, '_learn_now', lambda *args: None):
        try:
            a = app.CorrectNoteApp(root); root.deiconify(); until(done)
            book = a._word_book; w = a.editor
            if phase == 'sets_menu':
                from tkinter import messagebox
                from word_book import WordBook
                import ctypes as c
                from ctypes import wintypes as W
                book.open();root.update()
                assert book.words == ['旧登録😀'] and book.active_set == 0
                labels={a._edit_menu.entrycget(i,'label'):i for i in range(a._edit_menu.index('end')+1) if a._edit_menu.type(i)!='separator'}
                assert labels['現在の単語帳をリセットする']==labels['単語帳セットを切り替える']+1
                menu=a._word_book_set_menu
                assert [menu.entrycget(i,'label') for i in range(4)] == ['セット1','セット2','セット3','セット4']
                for index in range(4):
                    menu.invoke(index);book.add('セット%dの語😀' % (index+1))
                    assert book.active_set==index and book.buttons[-1].cget('text')=='セット%dの語😀' % (index+1)
                expected=[list(items) for items in book.sets]
                menu.invoke(1)
                with patch.object(messagebox,'askyesno',return_value=False) as ask:
                    a._edit_menu.invoke(labels['現在の単語帳をリセットする'])
                    assert 'セット2' in ask.call_args[0][1] and '選択外のセットは消えません' in ask.call_args[0][1]
                    assert book.sets==expected
                with patch.object(messagebox,'askyesno',return_value=True):
                    a._edit_menu.invoke(labels['現在の単語帳をリセットする'])
                expected[1]=[];assert book.sets==expected and not book.buttons
                menu.invoke(3);book.buttons[0].invoke();root.update()
                assert clipboard==['セット4の語😀']
                saved=json.loads((here/'word_book.json').read_text(encoding='utf8'))
                assert saved['sets']==expected and saved['active_set']==3
                restored=WordBook(a,here/'word_book.json',book.colors,book.initial_width,book.work_area)
                assert restored.sets==expected and restored.active_set==3 and restored.visible
                book.close()
                # Real native menus: no replacement of tk::MbPost. A native
                # timer supplies only test pointer positions; the production
                # MSGF_MENU hook uses the same handler during modal submenus.
                font=next(b for b in a._menu_buttons if b.cget('text')=='フォント')
                edit=next(b for b in a._menu_buttons if b.cget('text')=='編集')
                view=next(b for b in a._menu_buttons if b.cget('text')=='表示')
                points={str(b):(b.winfo_rootx()+3,b.winfo_rooty()+3) for b in (font,edit,view)}
                u=c.WinDLL('user32');tp=c.WINFUNCTYPE(None,W.HWND,W.UINT,c.c_size_t,W.DWORD)
                u.SetTimer.argtypes=[W.HWND,c.c_size_t,W.UINT,tp];u.SetTimer.restype=c.c_size_t
                u.KillTimer.argtypes=[W.HWND,c.c_size_t];u.EndMenu.argtypes=[]
                seen=[];ticks=[];cascades=[]
                enum_type=c.WINFUNCTYPE(W.BOOL,W.HWND,c.c_ssize_t)
                u.EnumThreadWindows.argtypes=[W.DWORD,enum_type,c.c_ssize_t]
                u.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,c.c_int]
                u.PostMessageW.argtypes=[W.HWND,W.UINT,c.c_size_t,c.c_ssize_t]
                kernel=c.WinDLL('kernel32');kernel.GetCurrentThreadId.restype=W.DWORD
                menu_thread=kernel.GetCurrentThreadId();font_ticks=[]
                def tick(hwnd,msg,ident,ms):
                    ticks.append(ms)
                    native=getattr(a,'_native_menu_hover',None)
                    if native is None:return
                    if not seen or seen[-1]!=native.current:seen.append(native.current)
                    if native.current==str(font) and not cascades:
                        windows=[]
                        def each(handle,lp):
                            name=c.create_unicode_buffer(100);u.GetClassNameW(handle,name,100)
                            if name.value=='#32768':windows.append(handle)
                            return True
                        u.EnumThreadWindows(menu_thread,enum_type(each),0)
                        font_ticks.append(len(windows))
                        if len(windows)>=2:cascades.append(True)
                        elif windows and len(font_ticks)<=3:
                            key=0x28 if len(font_ticks)<=2 else 0x27
                            u.PostMessageW(windows[0],0x0100,key,1)
                            u.PostMessageW(windows[0],0x0101,key,0xc0000001)
                            return
                        elif len(font_ticks)<10:return
                        else:u.EndMenu();return
                    target=str(edit) if native.current==str(font) else str(view) if native.current==str(edit) else None
                    if target is None:u.EndMenu()
                    else:
                        message=W.MSG();message.message=0x0200;message.pt.x,message.pt.y=points[target]
                        native.callback(2,0,c.addressof(message))
                callback=tp(tick);timer=u.SetTimer(None,0,200,callback)
                try:a._post_menu_bar(Event(widget=font))
                finally:u.KillTimer(None,timer)
                assert seen==[str(font),str(edit),str(view)] and cascades,(seen,ticks,cascades)
                assert not a._native_menu_active and a._native_menu_hover is None
                assert all(b.cget('state')=='normal' for b in a._menu_buttons)
                assert str(root.tk.globalgetvar('tk::Priv(postedMb)')) == '', repr(root.tk.globalgetvar('tk::Priv(postedMb)'))
                print('WORD_BOOK_FOUR_SETS_AND_NATIVE_MENU_SWITCH_PASSED',flush=True)
                return

            if phase == 'taskbar':
                import ctypes as c
                from ctypes import wintypes as W
                u = c.WinDLL('user32', use_last_error=True)
                u.GetForegroundWindow.restype = W.HWND
                u.GetAncestor.argtypes = [W.HWND, W.UINT]; u.GetAncestor.restype = W.HWND
                u.GetWindow.argtypes = [W.HWND, W.UINT]; u.GetWindow.restype = W.HWND
                u.GetWindowLongW.argtypes = [W.HWND, c.c_int]; u.GetWindowLongW.restype = W.LONG
                u.PostMessageW.argtypes = [W.HWND, W.UINT, c.c_size_t, c.c_ssize_t]
                u.SetForegroundWindow.argtypes = [W.HWND]
                u.ShowWindow.argtypes = [W.HWND, c.c_int]
                root.focus_force(); root.update()
                main_hwnd = u.GetAncestor(root.winfo_id(), 2)
                book.open(); root.update(); win = book.window; native = book._native
                # Keep testing the real window/restore path when the desktop
                # has no Explorer taskbar. Never report that as shell success.
                assert (native.taskbar is not None) != bool(native.taskbar_error)
                if native.taskbar_error:
                    print('TASKBAR_REGISTRATION_UNAVAILABLE: '+native.taskbar_error,flush=True)
                hwnd = native.hwnd; style = u.GetWindowLongW(hwnd, -20)
                assert style & 0x80, hex(style)  # compact caption, explicit shell button
                assert not u.GetWindow(hwnd, 4), 'word book must be unowned'
                assert win.winfo_width() == a._word_book_initial_width(), win.geometry()
                book.add('コピー検査😀')
                book.minimize_button.invoke(); until(lambda: win.state() == 'iconic')
                assert root.state() == 'normal'
                # The native system-menu restore is also the taskbar restore path.
                u.PostMessageW(hwnd, 0x0112, 0xf120, 0)
                until(lambda: win.state() == 'normal')
                root.iconify(); until(lambda: root.state() == 'iconic')
                assert win.state() == 'normal'
                root.deiconify(); until(lambda: root.state() == 'normal'); root.update()
                main_hwnd = u.GetAncestor(root.winfo_id(), 2)
                u.SendMessageW.argtypes = [W.HWND, W.UINT, c.c_size_t, c.c_ssize_t]
                u.SendMessageW.restype = c.c_ssize_t
                # The execution desktop refuses SetForegroundWindow even for
                # this test's root (raw failure retained). Deliver the native
                # activation message to the real wrapper, then observe the
                # requested OS transfer without touching the user's foreground.
                u.SendMessageW(hwnd, 0x0006, 1, main_hwnd)
                assert native.previous[0] == main_hwnd, native.previous
                with patch.object(native.user,'GetForegroundWindow',return_value=hwnd), patch.object(native.user,'SetForegroundWindow',return_value=1) as transfer:
                    book.buttons[0].invoke(); until(lambda: book._focus_job is None)
                    transfer.assert_called_once_with(main_hwnd)
                assert clipboard == ['コピー検査😀'] and win.state() == 'normal'
                peer_source = '''import ctypes as c,json,sys,tkinter as tk
from pathlib import Path
from ctypes import wintypes as W
r=tk.Tk();r.title('CorrectNote isolated focus recipient');r.geometry('240x100+500+400')
u=c.WinDLL('user32');u.GetAncestor.argtypes=[W.HWND,W.UINT];u.GetAncestor.restype=W.HWND
r.update();Path('focus_peer.json').write_text(json.dumps(dict(hwnd=u.GetAncestor(r.winfo_id(),2))),encoding='utf8')
def tick():
 if Path('focus_peer_stop').exists():r.destroy()
 else:r.after(30,tick)
r.after(30,tick);r.mainloop()
'''
                (here/'focus_peer.py').write_text(peer_source,encoding='utf8')
                peer = subprocess.Popen([sys.executable,'-B','-X','utf8',str(here/'focus_peer.py')],cwd=here)
                try:
                    until(lambda: (here/'focus_peer.json').exists())
                    peer_hwnd = json.loads((here/'focus_peer.json').read_text(encoding='utf8'))['hwnd']
                    u.SendMessageW(hwnd,0x0006,2,peer_hwnd)
                    assert native.previous[0] == peer_hwnd and native.previous[1] == peer.pid, native.previous
                    with patch.object(native.user,'GetForegroundWindow',return_value=hwnd), patch.object(native.user,'SetForegroundWindow',return_value=1) as transfer:
                        book.buttons[0].invoke(); until(lambda: book._focus_job is None)
                        transfer.assert_called_once_with(peer_hwnd)
                    assert clipboard == ['コピー検査😀']
                    with patch.object(native.user,'GetForegroundWindow',return_value=main_hwnd), patch.object(native.user,'SetForegroundWindow',return_value=1) as transfer:
                        book.buttons[0].invoke(); until(lambda: book._focus_job is None)
                        transfer.assert_not_called()
                    (here/'focus_peer_stop').touch(); peer.wait(timeout=15); root.update()
                    with patch.object(native.user,'GetForegroundWindow',return_value=hwnd), patch.object(native.user,'SetForegroundWindow',return_value=1) as transfer:
                        book.buttons[0].invoke(); until(lambda: book._focus_job is None)
                        transfer.assert_not_called()
                    assert clipboard == ['コピー検査😀']
                finally:
                    (here/'focus_peer_stop').touch()
                    peer.wait(timeout=15)
                book.close(); assert native.hwnd is None and book._focus_job is None
                book.open(); root.update()
                assert (book._native.taskbar is not None) != bool(book._native.taskbar_error)
                assert book._native.hwnd and book.window.winfo_width() == a._word_book_initial_width()
                print('WORD_BOOK_TASKBAR_AND_PREVIOUS_WINDOW_PASSED',flush=True)
                return

            if phase == 'responsive':
                from word_book import word_book_position
                from tkinter import font as tkfont
                expected_hint='【簡易入力】別ウインドウを開き、エスケープキーで閉じると入力していた文字列をコピーしてカーソル位置に移します'
                assert hover(a.quick_input_btn)==expected_hint
                leave(a.quick_input_btn)
                assert word_book_position((130,50,1030,600),(150,200),(0,0,1920,1040),number_left=175)==(0,80)
                assert word_book_position((100,50,1000,600),(150,200),(0,0,1920,1040),number_left=140)==(850,80)
                assert word_book_position((-1790,50,-890,600),(150,200),(-1920,0,0,1040),number_left=-1745)==(-1920,80)
                area=app.monitor_work_area(root.winfo_rootx(),root.winfo_rooty()) or (0,0,root.winfo_screenwidth(),root.winfo_screenheight())
                root.geometry('1200x520+%d+%d' % (area[0]+350,area[1]+80));root.update()
                book.open();root.update();win=book.window
                frame_width=win.winfo_width()+2*max(0,win.winfo_rootx()-win.winfo_x())
                a.editor_gutter.redraw();box=a.editor_gutter.bbox('num')
                offset=a.editor_gutter.winfo_rootx()+box[0]-root.winfo_x()
                book.close()
                # Outside space is insufficient; the unused app margin makes the left fit.
                left=area[0]+frame_width-offset+5
                root.geometry('+%d+%d' % (left,area[1]+80));root.update()
                book.open();root.update();win=book.window
                number_left=a.editor_gutter.winfo_rootx()+a.editor_gutter.bbox('num')[0]
                book_right=win.winfo_x()+win.winfo_width()+2*max(0,win.winfo_rootx()-win.winfo_x())
                assert win.winfo_x()==area[0] and book_right<=number_left,(win.geometry(),root.geometry(),number_left,book_right)
                assert book_right>root.winfo_x(),(book_right,root.winfo_x())
                overlap_geometry=win.geometry()
                # Independent window state: neither minimizing nor restoring the app owns it.
                assert not win.transient()
                root.iconify();until(lambda:root.state()=='iconic')
                assert win.state()=='normal' and win.winfo_ismapped(),(root.state(),win.state())
                root.deiconify();until(lambda:root.state()=='normal')
                book.minimize_button.invoke();until(lambda:win.state()=='iconic')
                assert root.state()=='normal' and book.visible
                root.iconify();until(lambda:root.state()=='iconic')
                root.deiconify();until(lambda:root.state()=='normal')
                assert win.state()=='iconic'
                a.word_book_btn.invoke();until(lambda:win.state()=='normal')
                assert book.window is win and book.visible
                # Reclicking an already visible word book still closes it.
                a.word_book_btn.invoke();assert book.window is None
                root.geometry('+%d+%d' % (area[0],area[1]+80));root.update()
                book.open();root.update();win=book.window
                assert win.winfo_x()>a.editor.winfo_rootx(),win.geometry()
                book.close()
                # Measure actual native widgets at each transition, not fixed pixel guesses.
                root.minsize(100,480)
                # The validation desktop can be narrower than the full toolbar.
                # Permit this synthetic window to allocate the requested width;
                # do not mistake a window-manager cap for a label-fit failure.
                native_max=root.maxsize()
                root.maxsize(max(native_max[0],2000),max(native_max[1],600))
                root.geometry('1800x520');root.update()
                until(lambda:a._toolbar_fit_job is None)
                variants=[(a.bookmark_prev_btn,'▲ 前のブックマーク','▲',1),
                    (a.bookmark_next_btn,'▼ 次のブックマーク','▼',1),
                    (a.layout_split_btn,'左右に並べる','分割',2),
                    (a.layout_unified_btn,'1つにまとめる','統合',2),
                    (a.pick_mode_btn,'クリックして引用','引用',3)]
                widgets=a._toolbar.pack_slaves();full=0;savings=[0,0,0,0]
                for widget in widgets:
                    raw_pad=widget.pack_info()['padx']
                    pad=(raw_pad,) if isinstance(raw_pad,int) else raw_pad if isinstance(raw_pad,(tuple,list)) else root.tk.splitlist(raw_pad)
                    full+=widget.winfo_reqwidth()+sum(widget.winfo_pixels(v) for v in pad)*(2 if len(pad)==1 else 1)
                for button,long,short,stage in variants:
                    font=tkfont.Font(root=root,font=button.cget('font'))
                    full+=font.measure(long)-font.measure(button.cget('text'))
                    savings[stage]+=font.measure(long)-font.measure(short)
                needs=[full]
                for stage in (1,2,3):needs.append(needs[-1]-savings[stage])
                before=content();widths=[]
                for stage in (0,1,2,3,2,1,0):
                    available=needs[stage]+4 if stage==0 else (needs[stage-1]+needs[stage])//2
                    root.geometry('%dx520' % (available+32));root.update()
                    # Native border rounding can differ from the requested
                    # geometry by pixels. Require the measured width to enter
                    # this exact stage's interval, not an assumed client width.
                    until(lambda:a._toolbar_fit_job is None and
                          a._toolbar.winfo_width()>=needs[stage] and
                          (stage==0 or a._toolbar.winfo_width()<needs[stage-1]))
                    assert a._toolbar_label_stage==stage,(stage,a._toolbar_label_stage,available,needs)
                    for button,long,short,threshold in variants:
                        assert button.cget('text')==(short if stage>=threshold else long)
                    for button in widgets:
                        assert button.winfo_ismapped() and button.winfo_width()==button.winfo_reqwidth(),(stage,button.cget('text'),button.winfo_width(),button.winfo_reqwidth())
                        assert 0<=button.winfo_x() and button.winfo_x()+button.winfo_width()<=a._toolbar.winfo_width()
                    widths.append((stage,root.winfo_width()))
                assert content()==before
                # Commands remain connected after label changes.
                root.geometry('%dx520' % (needs[3]+36));root.update();until(lambda:a._toolbar_fit_job is None)
                a.layout_unified_btn.invoke();root.update();assert a._layout_is_unified()
                a.layout_split_btn.invoke();root.update();assert not a._layout_is_unified()
                a.pick_mode_btn.invoke();assert a._pick_mode=='f1';a._end_pick_mode()
                root.minsize(900,480);root.geometry('900x520');root.update();until(lambda:a._toolbar_fit_job is None)
                assert all(button.winfo_ismapped() and button.winfo_width()==button.winfo_reqwidth() for button in widgets)
                print(json.dumps(dict(overlap=overlap_geometry,stage_widths=widths,independent_minimize=True),ensure_ascii=False),flush=True)
                print('WORD_BOOK_RESPONSIVE_PASSED',flush=True)
                return
            if phase == 'layout':
                from word_book import word_book_position
                from tkinter import font as tkfont
                assert hover(a.word_book_btn) == '【単語帳】追加ボタンから登録した単語をクリックするとコピー状態になり、ペーストすることができます'
                leave(a.word_book_btn)
                # Pure geometry includes a monitor to the left of the primary.
                assert word_book_position((400, 50, 1200, 650), (150, 200), (0, 0, 1920, 1040)) == (244, 80)
                assert word_book_position((0, 50, 800, 650), (150, 200), (0, 0, 1920, 1040)) == (650, 80)
                assert word_book_position((-1500, 50, -600, 650), (150, 200), (-1920, 0, 0, 1040)) == (-1656, 80)
                assert word_book_position((-1920, 1000, -1000, 1500), (150, 200), (-1920, 0, 0, 1040)) == (-1150, 840)
                area = app.monitor_work_area(root.winfo_rootx(), root.winfo_rooty()) or (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
                root.geometry('900x520+%d+%d' % (area[0] + 350, area[1] + 70)); root.update()
                a.word_book_btn.invoke(); root.update()
                book.add('単語一'); book.add('単語二'); book.add('とても長い単語' * 15); root.update()
                win = book.window
                border = max(0, win.winfo_rootx() - win.winfo_x())
                assert win.winfo_x() + win.winfo_width() + 2 * border <= root.winfo_x(), (win.geometry(), root.geometry())
                assert win.winfo_x() >= area[0]
                assert win.winfo_width() == a._word_book_initial_width()
                assert book.buttons[2].winfo_reqwidth() > book.buttons[2].winfo_width()
                font = tkfont.Font(root=root, font=a._editor_font())
                old = tk.Button(root, text='単語', relief='flat', font=a._editor_font(), padx=8, pady=3)
                root.update_idletasks()
                old_gap = old.winfo_reqheight() - font.metrics('linespace')
                new_gap = book.buttons[1].winfo_rooty() - book.buttons[0].winfo_rooty() - font.metrics('linespace')
                old.destroy()
                assert 0 < new_gap <= old_gap * .35 + 1, (old_gap, new_gap)
                assert new_gap >= old_gap * .15, (old_gap, new_gap)
                left_geometry = win.geometry()
                book.close(); root.geometry('+%d+%d' % (area[0], area[1] + 70)); root.update()
                book.open(); root.update()
                win = book.window
                book_right = win.winfo_x() + win.winfo_width() + 2 * max(0, win.winfo_rootx() - win.winfo_x())
                app_right = root.winfo_x() + root.winfo_width() + 2 * max(0, root.winfo_rootx() - root.winfo_x())
                assert abs(book_right - min(app_right, area[2])) <= 2, (book_right, app_right, win.geometry())
                assert win.winfo_x() > a.editor.winfo_rootx(), (win.geometry(), a.editor.winfo_rootx())
                right_geometry = win.geometry(); book.close()

                # Actual press/release in blank cells and in a line's right margin.
                def click(widget, x, y):
                    widget.event_generate('<ButtonPress-1>', x=x, y=y)
                    root.update()
                    widget.event_generate('<ButtonRelease-1>', x=x, y=y)
                    root.update()
                for kind in ('space', 'empty_line', 'right_margin'):
                    set_text('資料   表示\n\n末尾')
                    w.mark_set('insert', '3.end'); a.list_mode_btn.invoke()
                    if kind == 'space':
                        box = w.bbox('1.2'); x, y = box[0] + 1, box[1] + box[3] // 2
                    elif kind == 'empty_line':
                        box = w.bbox('2.0'); x, y = box[0] + 25, box[1] + box[3] // 2
                    else:
                        box = w.bbox('1.end'); x, y = min(w.winfo_width() - 8, box[0] + 40), box[1] + box[3] // 2
                    before = content(); click(w, x, y)
                    assert a._pick_mode is None and content() == before, (kind, a._pick_mode, content())

                set_text('資料\n転記先'); w.mark_set('insert', '2.end'); a.list_mode_btn.invoke()
                box = w.bbox('1.0'); click(w, box[0] + 2, box[1] + box[3] // 2)
                assert a._pick_mode == 'list' and content() == '資料\n転記先\n\n資料', content()
                until(done)
                box = w.bbox('1.end'); before = content()
                click(w, min(w.winfo_width() - 8, box[0] + 40), box[1] + box[3] // 2)
                assert a._pick_mode is None and content() == before

                # Nonblank dragging released in a margin still copies the selection.
                set_text('資料 表示\n転記先'); w.mark_set('insert', '2.end'); a.list_mode_btn.invoke()
                w.tag_add('sel', '1.0', '1.2'); box = w.bbox('1.end')
                event = Event(widget=w, x=box[0] + 30, y=box[1] + box[3] // 2, state=0)
                with patch.object(a, '_drag_release', return_value=False), patch.object(a, '_trim_mouse_selection'):
                    assert a._on_editor_release(event) == 'break'
                assert a._pick_mode == 'list' and content().endswith('\n\n資料')
                a._end_pick_mode()
                # Result and quick-input fields use the same blank-click exit rule.
                set_text('資料\n転記先'); w.mark_set('insert', '2.end'); a.list_mode_btn.invoke()
                rv = a.result_view; box = rv.bbox('1.end'); before = content()
                click(rv, min(rv.winfo_width() - 8, box[0] + 40), box[1] + box[3] // 2)
                assert a._pick_mode is None and content() == before
                a.quick_input_btn.invoke(); root.update(); q = a._quick_text
                q.delete('1.0', 'end'); q.insert('1.0', '語'); root.update()
                w.mark_set('insert', '2.end'); a.list_mode_btn.invoke()
                box = q.bbox('1.end'); before = content()
                click(q, min(q.winfo_width() - 8, box[0] + 35), box[1] + box[3] // 2)
                assert a._pick_mode is None and content() == before
                a._close_quick_capture()
                # Other picking modes retain their behavior on whitespace.
                a.toggle_pick_mode(); box = w.bbox('1.end')
                click(w, min(w.winfo_width() - 8, box[0] + 40), box[1] + box[3] // 2)
                assert a._pick_mode == 'f1'; a._end_pick_mode()
                # Button and queued OS-hotkey dispatch share the minimize toggle.
                set_text('本体は保持'); before = content()
                a.settings.set('quick_autofix', False)
                a.quick_input_btn.invoke(); root.update(); q = a._quick_text; quick = a._quick_win
                q.delete('1.0', 'end'); q.insert('1.0', '保持する文字'); q.mark_set('insert', '1.2')
                q.tag_add('sel', '1.0', '1.2'); root.update()
                a.quick_input_btn.invoke(); until(lambda: quick.state() == 'iconic')
                limit = time.monotonic() + .2
                while time.monotonic() < limit: root.update(); time.sleep(.005)
                assert quick.state() == 'iconic', quick.state()
                assert q.get('1.0', 'end-1c') == '保持する文字' and content() == before
                a.quick_input_btn.invoke(); until(lambda: quick.state() == 'normal')
                assert q.index('insert') == '1.2' and q.get('sel.first', 'sel.last') == '保持'
                a._hotkey_queue.put('minus'); until(lambda: quick.state() == 'iconic')
                a._hotkey_queue.put('insert'); until(lambda: quick.state() == 'normal')
                assert a._quick_win is quick and q.get('1.0', 'end-1c') == '保持する文字'
                assert content() == before
                q.delete('1.0', 'end'); a._close_quick_capture()

                # A lone line-start chunk and a separated colour do not light the button.
                for value, marks in [('甲\n次', [('1.0', 1)]),
                        ('甲 間乙\n次', [('1.0', 1), ('1.3', 1)]),
                        ('甲\n乙', [('1.0', 1), ('2.0', 1)])]:
                    set_text(value)
                    for first, length in marks: a._mark_quick_sent(first, length)
                    assert not a._has_quick_sent() and a.list_mode_btn.cget('bg') == app.PANEL, value
                    assert hover(a.list_mode_btn) == a._LIST_PICK_HINT; leave(a.list_mode_btn)
                    w.mark_set('insert', '1.0'); a.list_mode_btn.invoke()
                    assert a._pick_mode == 'list' and content() == value
                    a._end_pick_mode()
                # The first coloured phrase stays at the same original line start.
                for value, marks, expected in [
                        ('甲乙丙後\n次', ['1.0', '1.1', '1.2'], '甲\n乙\n丙後\n次'),
                        ('前の行\n甲乙\n次', ['2.0', '2.1'], '前の行\n甲\n乙\n次'),
                        ('甲乙丙\n前丁後\n次', ['1.0', '1.1', '1.2', '2.1'], '甲\n乙\n丙\n前丁後\n次')]:
                    set_text(value); w.mark_set('insert', 'end-1c')
                    for first in marks: a._mark_quick_sent(first, 1)
                    assert a._has_quick_sent() and a.list_mode_btn.cget('bg') == app.QUICK_SENT_BG_A
                    a.list_mode_btn.invoke()
                    assert content() == expected and a._pick_mode is None, content()
                    assert a.list_mode_btn.cget('bg') == app.PANEL
                    w.edit_undo(); assert content() == value
                # The existing sentence-middle extraction remains active.
                set_text('前甲後'); w.mark_set('insert', '1.0'); a._mark_quick_sent('1.1', 1)
                assert a._has_quick_sent()
                a.list_mode_btn.invoke(); assert content() == '前後\n\n甲', content()
                w.edit_undo(); assert content() == '前甲後'
                print(json.dumps(dict(old_gap=old_gap, new_gap=new_gap, left=left_geometry, right=right_geometry)), flush=True)
                print('WORD_BOOK_LAYOUT_PASSED', flush=True)
                return
            if phase == 'restore':
                until(lambda: book.window is not None and book.window.winfo_ismapped())
                assert book.words == ['資料😀', '長い語' * 50], book.words
                assert book.width == 240, book.width
                assert book.window.winfo_width() == 240, book.window.geometry()
                a.word_book_btn.invoke(); assert book.window is None
                assert json.loads((here / 'word_book.json').read_text(encoding='utf8'))['visible'] is False
                print('WORD_BOOK_RESTART_PASSED', flush=True)
                return
            if phase == 'closed':
                assert book.window is None and len(book.words) == 2
                print('WORD_BOOK_CLOSED_RESTART_PASSED', flush=True)
                return

            # First insertion uses blank rows without accumulating separators.
            for value, row, expected in [('', 1, '甲\n乙'), ('\n\n次', 2, '\n甲\n乙\n次'),
                    ('前\n\n次', 2, '前\n\n甲\n乙\n次'), ('前\n次', 1, '前\n\n甲\n乙\n次')]:
                set_text(value); w.mark_set('insert', f'{row}.0'); a.list_mode_btn.invoke()
                assert a._pick_hint == a._LIST_PICK_HINT
                a._pick_insert('甲'); a._pick_insert('乙')
                assert content() == expected, (value, content())
                assert a._pick_mode == 'list'
                a._end_pick_mode()
            assert hover(a.list_mode_btn) == a._LIST_PICK_HINT; leave(a.list_mode_btn)
            assert hover(a.pick_mode_btn) == a._QUOTE_START_HINT; leave(a.pick_mode_btn)
            a.pick_mode_btn.invoke(); assert a._pick_hint == a._QUOTE_PICK_HINT
            assert hover(a.pick_mode_btn) == a._QUOTE_PICK_HINT; leave(a.pick_mode_btn); a._end_pick_mode()
            for count, button in enumerate(a._bracket_buttons, 1):
                assert hover(button) == ('選択中の文字や、変換中の文字を括弧で包みます。ショートカットキー：F5'
                    + (f'を{count}回' if count > 1 else ''))
                leave(button)
            # Pending sent text highlights the button without entering a mode.
            set_text('\n甲乙'); w.mark_set('insert', '1.0')
            a._mark_quick_sent('2.0', 1); a._mark_quick_sent('2.1', 1)
            assert a._pick_mode is None and a.list_mode_btn.cget('bg') == app.QUICK_SENT_BG_A
            for dark in (True, False):
                a._apply_theme(dark); root.update()
                assert a.list_mode_btn.cget('bg') == app.QUICK_SENT_BG_A
            assert hover(a.list_mode_btn) == a._LIST_MOVE_HINT
            a.list_mode_btn.invoke(); assert content() == '\n甲\n乙', content()
            assert a.editor_header.cget('text') == a._LIST_MOVE_HINT
            assert a.list_mode_btn.cget('bg') == app.PANEL and a._pick_mode is None
            leave(a.list_mode_btn); w.edit_undo(); assert content() == '\n甲乙', content()
            # The menu order and quick-input action are actual widgets/commands.
            toolbar = a.list_mode_btn.master
            buttons = toolbar.pack_slaves()
            offset = buttons.index(a.list_mode_btn)
            assert buttons[offset + 1:offset + 3] == [a.quick_input_btn, a.word_book_btn]
            assert all(b.winfo_ismapped() for b in buttons), [(b.cget('text'), b.winfo_ismapped()) for b in buttons]
            assert hover(a.quick_input_btn) == '【簡易入力】別ウインドウを開き、エスケープキーで閉じると入力していた文字列をコピーしてカーソル位置に移します'; leave(a.quick_input_btn)
            a.quick_input_btn.invoke(); root.update(); assert a._quick_win is not None
            a._close_quick_capture()

            set_text('資料😀\n別の資料')
            a.word_book_btn.invoke(); until(lambda: book.window.winfo_ismapped())
            first_width = book.window.winfo_width()
            assert first_width == a._word_book_initial_width(), (first_width, a._word_book_initial_width())
            first_height = book.window.winfo_height()
            before = content(); book.add_button.invoke()
            assert a._pick_mode == 'wordbook'
            w.tag_add('sel', '1.0', '1.end')
            event = Event(widget=w, x=0, y=0, state=0)
            with patch.object(a, '_drag_release', return_value=False), patch.object(a, '_trim_mouse_selection'), \
                    patch.object(a, '_editor_unit_under_pointer', return_value=None):
                assert a._on_editor_release(event) == 'break'
            assert book.words == ['資料😀'] and a._pick_mode is None
            assert content() == before
            root.update(); assert book.window.winfo_height() > first_height
            assert book.rows.pack_slaves()[-1] is book.add_button
            book.buttons[0].invoke(); assert clipboard == ['資料😀'], clipboard
            # A single-word click uses the existing quoting route too.
            book.add_button.invoke()
            with patch.object(a, '_drag_release', return_value=False), patch.object(a, '_trim_mouse_selection'), \
                    patch.object(a, '_editor_unit_under_pointer', return_value=(1, dict(text='別資料'))):
                a._on_editor_release(event)
            assert book.words == ['資料😀', '別資料']
            with patch.object(tk.Menu, 'tk_popup'), patch.object(tk.Menu, 'grab_release'):
                book.buttons[1].event_generate('<Button-3>', x=1, y=1); root.update()
                assert book._menu.entrycget(0, 'label') == '消す'
                book._menu.invoke(0)
            assert book.words == ['資料😀']
            book.add_button.invoke(); a._pick_insert('長い語' * 50); root.update()
            assert book.window.winfo_width() == first_width, book.window.geometry()
            assert book.buttons[1].winfo_width() <= first_width
            assert book.buttons[1].winfo_reqwidth() > book.buttons[1].winfo_width()
            book.window.geometry('240x%d' % book.window.winfo_height()); root.update()
            until(lambda: book.width == 240)
            # Esc and normal typing cancel addition without adding a phrase.
            book.add_button.invoke(); deliver_key(w, '<KeyPress>', 'Escape', 27)
            assert a._pick_mode is None and len(book.words) == 2
            book.add_button.invoke(); deliver_key(w, '<KeyPress>', 'x', 88, char='x')
            assert a._pick_mode is None and len(book.words) == 2
            assert book.visible and book.window is not None
            print('TOOLBAR_WORD_BOOK_OPERATIONS_PASSED', flush=True)
        finally:
            if a is not None: a._on_close()
            else: root.destroy()
            assert not errors, errors


class ToolbarWordBookTests(unittest.TestCase):
    def test_four_sets_and_native_menu_switch(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-toolbar-taskbar-') as directory:
            dest=Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.toolbar-wordbook-isolated').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child','sets_menu'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=300)
            self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('WORD_BOOK_FOUR_SETS_AND_NATIVE_MENU_SWITCH_PASSED',run.stdout)
            print(run.stdout,flush=True)

    def test_taskbar_and_return_to_previous_window(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-toolbar-taskbar-') as directory:
            dest=Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.toolbar-wordbook-isolated').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child','taskbar'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=300)
            self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('WORD_BOOK_TASKBAR_AND_PREVIOUS_WINDOW_PASSED',run.stdout)
            print(run.stdout,flush=True)

    def test_responsive_toolbar_and_independent_wordbook(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-toolbar-responsive-') as directory:
            dest=Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.toolbar-wordbook-isolated').touch()
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(dest/Path(__file__).name),'--child','responsive'],cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=300)
            self.assertEqual(run.returncode,0,run.stdout)
            self.assertIn('WORD_BOOK_RESPONSIVE_PASSED',run.stdout)
            print(run.stdout,flush=True)

    def test_compact_placement_and_blank_click_exit(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-toolbar-layout-') as directory:
            dest = Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copy2(p, dest / p.name)
            (dest / '.toolbar-wordbook-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child', 'layout'],
                cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8', timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn('WORD_BOOK_LAYOUT_PASSED', run.stdout)
            print(run.stdout, flush=True)

    def test_real_operations_and_two_restart_states(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-toolbar-book-') as directory:
            dest = Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copy2(p, dest / p.name)
            (dest / '.toolbar-wordbook-isolated').touch()
            for phase, marker in [('edit', 'TOOLBAR_WORD_BOOK_OPERATIONS_PASSED'),
                    ('restore', 'WORD_BOOK_RESTART_PASSED'), ('closed', 'WORD_BOOK_CLOSED_RESTART_PASSED')]:
                run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child', phase],
                    cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8', timeout=300)
                self.assertEqual(run.returncode, 0, run.stdout)
                self.assertIn(marker, run.stdout)


if __name__ == '__main__':
    if '--child' in sys.argv: child(sys.argv[-1])
    else: unittest.main()
