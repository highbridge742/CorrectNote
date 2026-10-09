"""Per-tab logical-row rulers and transient cursor navigation guides."""
import tkinter as tk


NAVIGATION_KEYS=frozenset(('Left','Right','Up','Down','Home','End','Prior','Next',
    'KP_Left','KP_Right','KP_Up','KP_Down','KP_Home','KP_End','KP_Prior','KP_Next'))
FLASH_COLOR='#ee963e'
FLASH_MS=180


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
            self._flash=(pane,pane.cget('insertbackground'),pane.cget('insertofftime'))
        pane.configure(insertbackground=FLASH_COLOR,insertofftime=0)
        self._restore_job=self.root.after(FLASH_MS,self.restore)

    def restore(self):
        self._cancel('_restore_job')
        saved,self._flash=self._flash,None
        if saved is None:return
        pane,color,off=saved
        try:
            # A theme change may already have installed its new color.
            if str(pane.cget('insertbackground'))==FLASH_COLOR:pane.configure(insertbackground=color)
            if int(pane.cget('insertofftime'))==0:pane.configure(insertofftime=off)
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
        row=int(self.active.index('insert').split('.')[0]);rows=set(self._rows)
        if row in rows:rows.remove(row)
        else:rows.add(row)
        self.set_ruler_rows(rows)
        return row in rows

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
                    y=info[1]+info[3]-1
                    if not 0<=y<pane.winfo_height():continue
                    key=(pane,row);line=self.lines.get(key)
                    if line is None:
                        line=self.lines[key]=tk.Frame(pane,height=1,bd=0,takefocus=False)
                        for seq in ('<ButtonPress-1>','<B1-Motion>','<ButtonRelease-1>',
                                    '<ButtonPress-3>','<B3-Motion>','<ButtonRelease-3>','<MouseWheel>'):
                            line.bind(seq,lambda e,s=seq,w=pane:self._forward(e,s,w))
                    line.configure(bg=self.color())
                    line.place(x=2,y=y,width=max(1,pane.winfo_width()-4),height=1,bordermode='outside')
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
