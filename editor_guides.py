"""Per-tab logical-row rulers and transient cursor navigation guides."""
import os
import tkinter as tk


NAVIGATION_KEYS=frozenset(('Left','Right','Up','Down','Home','End','Prior','Next',
    'KP_Left','KP_Right','KP_Up','KP_Down','KP_Home','KP_End','KP_Prior','KP_Next'))
FLASH_COLOR='#ee963e'
FLASH_MS=180
# 地の明るい配色での強調（2026-11-23 うにさん「ライトモードでのオレンジのカーソル強調が見えにくいので、白に合わせた調整を
# 入れる」）。#ee963e は白地とのコントラスト比が約2.3で見えにくかった。濃いめのオレンジ（白地で約6.0・ライトの配色の欄の地で
# 4.5 以上）にし、強調の間だけ入力カーソルを太くする。ダーク系は今のまま。地の色の明るさで決める（配色の名前に頼らない）。
# CN_CARET_FLASH_LIGHT=0 で前の形
FLASH_COLOR_LIGHT='#b13a0a'
FLASH_WIDTH_LIGHT=3


def _luminance(widget,color):
    r,g,b=(c/65535.0 for c in widget.winfo_rgb(color))
    def lin(c):return c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
    return 0.2126*lin(r)+0.7152*lin(g)+0.0722*lin(b)


def contrast(widget,a,b):
    la,lb=sorted((_luminance(widget,a),_luminance(widget,b)),reverse=True)
    return (la+0.05)/(lb+0.05)


def flash_style(pane):
    """(強調の色, 強調の間の入力カーソルの幅 or None)。地が明るい欄は濃いめのオレンジと太いカーソル。"""
    import os
    if os.environ.get('CN_CARET_FLASH_LIGHT')=='0':return FLASH_COLOR,None
    try:light=_luminance(pane,pane.cget('background'))>=0.5
    except (tk.TclError,ValueError):light=False
    if not light:return FLASH_COLOR,None
    try:width=max(int(pane.cget('insertwidth')),FLASH_WIDTH_LIGHT)
    except (tk.TclError,ValueError):width=FLASH_WIDTH_LIGHT
    return FLASH_COLOR_LIGHT,width
# ルーラーの線の太さ（px）。2026-11-20 うにさん「ルーラーが見えにくい。目次と本文の境目の線は見えやすい…今の太さと
# 境目の線の太さの中間にする」: 色は境目の線と同じ RULE で、違いは太さだけ（ルーラー 1px・境目の線 約3px）。中間の 2px。
# デバッグのパラメータ（debug_menu の ruler_width）。CN_RULER_THIN=1 で前の 1px
RULER_WIDTH=2
RULER_WIDTH_MAX=6


def ruler_width():
    import os
    if os.environ.get('CN_RULER_THIN')=='1':return 1
    return max(1,int(RULER_WIDTH))


class EditorGuides:
    def __init__(self,root,panes,owner=lambda:None,color=lambda:'#777777',can_flash=lambda event:True,
                 on_change=lambda:None,on_state=lambda:None):
        self.root=root;self.panes=tuple(panes);self.owner=owner;self.color=color;self.can_flash=can_flash
        self.on_change=on_change;self.on_state=on_state
        self.enabled=False;self.active=self.panes[0] if self.panes else None
        from session import clean_ruler_rows
        current=owner()
        self._rows=set(clean_ruler_rows(current.get('ruler_rows')) if isinstance(current,dict) else ())
        self.enabled=bool(self._rows)
        self._owner=owner();self._draw_job=None;self._key_job=None;self._restore_job=None
        self._flash=None;self._armed=None;self._closed=False;self.lines={}
        self.tag='CorrectNoteEditorGuides'+str(id(self));self._commands=[]
        for sequence,handler in (('<KeyPress>',self._key),('<FocusOut>',self._focus_out)):
            command=root.bind_class(self.tag,sequence,handler)
            self._commands.append(command)
            if root._tclCommands is None:root._tclCommands=[]
            if command not in root._tclCommands:root._tclCommands.append(command)
        for pane in self.panes:
            pane.bindtags((self.tag,)+pane.bindtags())
            pane.bind('<Configure>',self.queue_draw,add=True)
        root.bind('<Destroy>',self._destroy,add=True)
        # Ruler toggles take their turn in the editor's Ctrl+Z / Ctrl+Y history
        # (2026-10-25 うにさん「ルーラーの挿入を、Undoの対象にする」), as text_format's styles:
        # a step is due while the editor's text and tab are as they were when it was made.
        self.history=[];self.redo=[]
        observers=getattr(self.panes[0],'_correctnote_observers',None) if self.panes else None
        if observers is not None:
            observers.setdefault('undo_hooks',[]).append(self.undo_step)
            observers.setdefault('changed',[]).append(self._text_changed)
        # ルーラーは欄に置いた枠なので、字と一緒には動かない。字が変わった・行の高さが変わった（品詞の字・行の高さ揃え・
        # 補正欄の描き直し）時に、前の高さに残って字に重なっていた（2026-11-23 うにさん「ルーラーも帯が重なってました。
        # 27行目 何秒もずっと」）。字が変わったら、その行から下の線をその場で隠して描き直しを予約し、行の高さが変わった
        # 知らせ（<<WidgetViewSync>>）でも描き直す（描くたびに今の位置へ引き直す）。CN_GUIDES_VIEW_SYNC=0 で前の形
        if os.environ.get('CN_GUIDES_VIEW_SYNC')!='0':
            for pane in self.panes:
                obs=getattr(pane,'_correctnote_observers',None)
                if obs is not None:
                    obs.setdefault('changed',[]).append(lambda args=None,pane=pane:self._pane_changed(pane,args))
                pane.bind('<<WidgetViewSync>>',self.queue_draw,add=True)

    def _cancel(self,name):
        job=getattr(self,name);setattr(self,name,None)
        if job is not None:
            try:self.root.after_cancel(job)
            except tk.TclError:pass

    def _key(self,event):
        if (event.widget not in self.panes or event.keysym not in NAVIGATION_KEYS
                or getattr(event,'char','') or not self.can_flash(event)):return
        self._cancel('_key_job')
        self._armed=(event.widget,event.widget.index('insert'),self.owner())
        # Runs after the actual Text/shortcut handler, including handlers
        # which return break. Only an actual insertion-mark move flashes.
        self._key_job=self.root.after_idle(self._after_key)

    def _after_key(self):
        self._key_job=None;armed,self._armed=self._armed,None
        if self._closed or armed is None:return
        pane,before,owner=armed
        try:
            if (owner is not self.owner() or self.root.focus_get() is not pane
                    or pane.index('insert')==before):return
            self.cursor_changed(pane)
            self._begin_flash(pane)
        except tk.TclError:pass

    def _begin_flash(self,pane):
        if self._flash is not None and self._flash[0] is not pane:self.restore()
        self._cancel('_restore_job')
        if self._flash is None:
            color,width=flash_style(pane)
            self._flash=(pane,pane.cget('insertbackground'),pane.cget('insertofftime'),color,
                         (pane.cget('insertwidth'),width) if width else None)
            # Only as the flash begins: configure makes Tk lay out and draw the whole pane again, and each arrow key
            # paid 40ms for a colour it already had (2026-11-05 うにさん「左右キーでのカーソル移動が重い」)
            if width:pane.configure(insertbackground=color,insertofftime=0,insertwidth=width)
            else:pane.configure(insertbackground=color,insertofftime=0)
        self._restore_job=self.root.after(FLASH_MS,self.restore)

    def restore(self):
        self._cancel('_restore_job')
        saved,self._flash=self._flash,None
        if saved is None:return
        pane,color,off=saved[:3]
        shown=saved[3] if len(saved)>3 else FLASH_COLOR
        widths=saved[4] if len(saved)>4 else None
        try:
            # A theme change may already have installed its new color.
            if str(pane.cget('insertbackground'))==shown:pane.configure(insertbackground=color)
            if int(pane.cget('insertofftime'))==0:pane.configure(insertofftime=off)
            if widths and int(pane.cget('insertwidth'))==int(widths[1]):pane.configure(insertwidth=widths[0])
        except tk.TclError:pass

    def _focus_out(self,event):
        self._cancel('_key_job');self._armed=None;self.restore()

    def _sync_owner(self):
        owner=self.owner()
        if owner is not self._owner:
            self._cancel('_key_job');self._armed=None;self.restore();self._owner=owner
            from session import clean_ruler_rows
            self._rows=set(clean_ruler_rows(owner.get('ruler_rows')) if isinstance(owner,dict) else ())
            self.enabled=bool(self._rows)

    def ruler_rows(self):
        self._sync_owner()
        return set(self._rows)

    def set_ruler_rows(self,rows,notify=True):
        self._sync_owner()
        from session import clean_ruler_rows
        rows=set(clean_ruler_rows(rows))
        if rows==self._rows:return
        self._rows=rows;self.enabled=bool(rows)
        if isinstance(self._owner,dict):self._owner['ruler_rows']=sorted(rows)
        self.queue_draw();self.on_state()
        if notify:self.on_change()

    def current_row_marked(self):
        self._sync_owner()
        return bool(self.active is not None and int(self.active.index('insert').split('.')[0]) in self._rows)

    def cursor_changed(self,pane):
        if pane not in self.panes or self._closed:return
        self._sync_owner();self.active=pane;self.queue_draw();self.on_state()

    def toggle(self):
        self._sync_owner()
        if self.active is None:return False
        return self.toggle_row(int(self.active.index('insert').split('.')[0]))

    def toggle_row(self,row):
        """Put a ruler under this logical row, or take it away (the button: the cursor's row;
        the line-number menu: the clicked row, 2026-10-25). One Ctrl+Z step either way."""
        self._sync_owner()
        row=int(row);before=set(self._rows);rows=set(before)
        if row in rows:rows.remove(row)
        else:rows.add(row)
        self.set_ruler_rows(rows)
        if self._rows!=before:self._record(before,set(self._rows))
        return row in rows

    # --- undo / redo -------------------------------------------------
    HISTORY_LIMIT=200

    def _text(self):
        return self.panes[0].get('1.0','end-1c')

    def _record(self,before,after):
        try:
            from analysis_work import next_step_seq
            seq=next_step_seq(self.panes[0]);text=self._text()
        except (ImportError,tk.TclError,IndexError):return
        self.history.append((text,self._owner,frozenset(before),frozenset(after),seq))
        del self.history[:-self.HISTORY_LIMIT]
        self.redo.clear()

    def _due(self,kind):
        stack=self.history if kind=='undo' else self.redo
        if not stack or self._closed:return None
        self._sync_owner()
        entry=stack[-1]
        try:
            from analysis_work import same_step_text
            if entry[1] is not self._owner or not same_step_text(entry[0],self._text()):return None
        except tk.TclError:return None
        return entry

    def due_step_seq(self,kind):
        """The number of the step Ctrl+Z / Ctrl+Y would take now, or None (analysis_work._hooks_in_turn)."""
        entry=self._due(kind)
        return None if entry is None else entry[4]

    def step_top(self,kind):
        """The step next in this stack, of any tab: (number, its text, its tab) (tab_undo)."""
        stack=self.history if kind=='undo' else self.redo
        return (stack[-1][4],stack[-1][0],stack[-1][1]) if stack else None

    def step_drop(self,kind):
        (self.history if kind=='undo' else self.redo).pop()

    def undo_step(self,kind):
        """Take one Ctrl+Z / Ctrl+Y step if a ruler change is next in line (its text and tab are current)."""
        if self._due(kind) is None:return False
        stack,other=(self.history,self.redo) if kind=='undo' else (self.redo,self.history)
        entry=stack.pop()
        self.set_ruler_rows(entry[2] if kind=='undo' else entry[3])
        other.append(entry)
        changed=entry[2]^entry[3]
        self.last_place='%d.0'%min(changed) if changed else None     # for a Ctrl+Z from another tab (tab_undo)
        return True

    def _text_changed(self,args=None):
        if (self.redo and args and args[0] in ('insert','delete','replace')
                and not getattr(self.panes[0],'_correctnote_replay_depth',0)
                and not getattr(self.panes[0],'_correctnote_tab_swap',False)):
            # A new edit ends what can be redone, as for text.
            self.redo.clear()

    def _pane_changed(self,pane,args=None):
        """字が変わった欄の、変わった行から下のルーラーをその場で隠し、字を並べ直した後に引き直す。"""
        if self._closed or not self.lines:return
        try:
            first=int(str(pane.index(args[1])).split('.')[0]) if args and len(args)>1 else 1
        except Exception:
            first=1
        for (widget,row),line in tuple(self.lines.items()):
            if widget is pane and row>=first:
                try:line.place_forget()
                except tk.TclError:pass
        self.queue_draw()

    def queue_draw(self,event=None):
        if not self._closed and self._draw_job is None:
            self._draw_job=self.root.after_idle(self.draw)

    def _forward(self,event,sequence,pane):
        options=dict(x=event.x_root-pane.winfo_rootx(),y=event.y_root-pane.winfo_rooty(),state=event.state)
        if hasattr(event,'time'):options['time']=event.time
        if sequence=='<MouseWheel>':options['delta']=event.delta
        elif sequence.startswith('<ButtonPress-'):
            for (widget,row),line in self.lines.items():
                if widget is pane:line.place_forget()
            pane.focus_set()
        pane.event_generate(sequence,**options)
        return 'break'

    def draw(self):
        self._draw_job=None
        self._sync_owner()
        for key,line in tuple(self.lines.items()):
            line.place_forget()
            if key[1] not in self._rows:
                line.destroy();self.lines.pop(key)
        if not self.enabled or self._closed:return
        for pane in self.panes:
            try:
                if not pane.winfo_ismapped():continue
                last=int(pane.index('end-1c').split('.')[0])
                for row in sorted(self._rows):
                    if row>last:continue
                    # The last display segment owns the boundary of the
                    # logical row, independent of the insertion mark.
                    info=pane.dlineinfo(str(row)+'.end')
                    if info is None:continue
                    width=ruler_width()
                    y=info[1]+info[3]-width
                    if not 0<=y<pane.winfo_height():continue
                    key=(pane,row);line=self.lines.get(key)
                    if line is None:
                        line=self.lines[key]=tk.Frame(pane,height=1,bd=0,takefocus=False)
                        for seq in ('<ButtonPress-1>','<B1-Motion>','<ButtonRelease-1>',
                                    '<ButtonPress-3>','<B3-Motion>','<ButtonRelease-3>','<MouseWheel>'):
                            line.bind(seq,lambda e,s=seq,w=pane:self._forward(e,s,w))
                    line.configure(bg=self.color())
                    line.place(x=2,y=y,width=max(1,pane.winfo_width()-4),height=width,bordermode='outside')
                    line.lift()
            except tk.TclError:pass

    def theme_changed(self):
        self.restore();self.queue_draw()

    def close(self):
        if self._closed:return
        self._closed=True
        for name in ('_key_job','_draw_job'):self._cancel(name)
        self._armed=None;self.restore()
        for pane in self.panes:
            try:pane.bindtags(tuple(t for t in pane.bindtags() if t!=self.tag))
            except tk.TclError:pass
        for line in self.lines.values():
            try:line.destroy()
            except tk.TclError:pass
        self.lines.clear()
        for sequence in ('<KeyPress>','<FocusOut>'):
            try:self.root.unbind_class(self.tag,sequence)
            except tk.TclError:pass

    def _destroy(self,event):
        if event.widget is self.root:self.close()
