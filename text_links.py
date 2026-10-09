# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Visible explicit links; opening requires an uninterrupted user click."""
from bisect import bisect_right
from dataclasses import dataclass
import re
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Link:
    start: int
    end: int
    target: str
    kind: str


_START = re.compile(r'(?<![A-Za-z0-9_])(?:https?://|[A-Za-z]:[\\/]|\\\\)', re.I)
_END = re.compile(r'''[\s<>"'。、，．！？「」『』【】〈〉《》]''')
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
_URL_SPACE = re.compile(r'\s')
_QUOTES = {'"':'"', "'":"'", '「':'」', '『':'』'}
_CLOSERS = {')':'(', ']':'[', '}':'{', '）':'（'}


def find_links(text):
    """Find lexical ranges only: never inspect files or contact a server.

    A path containing spaces needs matching quotes. Relative paths and bare
    hostnames have no reliable boundary in prose and are deliberately left alone.
    """
    if not any(marker in text for marker in ('://',':\\',':/','\\\\')):return ()
    links=[]; consumed=0
    for match in _START.finditer(text):
        start=match.start()
        if start<consumed:continue
        is_url=match.group().lower().startswith(('http://','https://'))
        end=start
        quote=_QUOTES.get(text[start-1]) if start else None
        quoted=False
        if quote is not None:
            close=text.find(quote,match.end())
            newline=text.find('\n',match.end())
            if close>=0 and (newline<0 or close<newline):
                end=close;quoted=True
        if not quoted:
            boundary=_END.search(text,match.end())
            end=boundary.start() if boundary else len(text)
        target=text[start:end]
        if not quoted:
            target=target.rstrip('.,;:!')
            while target and target[-1] in _CLOSERS:
                close=target[-1];opening=_CLOSERS[close]
                if target.count(close)<=target.count(opening):break
                target=target[:-1].rstrip('.,;:!')
            end=start+len(target)
        # Never activate a nested drive/URL fragment inside a rejected token
        # (for example a Win32 device path such as \\?\C:\...).
        consumed=end
        if not target or _CONTROL.search(target):continue
        if is_url:
            # Parsing is syntactic only. Do not turn an incomplete scheme into
            # an active link while it is still being typed.
            try:
                parsed=urlsplit(target)
                valid=bool(parsed.hostname) and not _URL_SPACE.search(target)
            except ValueError:valid=False
            if not valid:continue
            kind='url'
        else:
            if any(c in target for c in '<>"|?*\r\n\t'):continue
            if target.startswith('\\\\'):
                parts=target[2:].split('\\')
                if len(parts)<2 or not parts[0] or not parts[1]:continue
                if parts[0] in ('.','?') or ':' in parts[0]:continue
            elif not re.match(r'^[A-Za-z]:[\\/]',target):continue
            kind='path'
        links.append(Link(start,end,target,kind));consumed=end
    return tuple(links)


def open_link(link):
    """This is called only by a completed left-click, never by detection."""
    if link.kind=='url':
        import webbrowser
        if not webbrowser.open(link.target):raise OSError('ブラウザーを開けませんでした')
    else:
        import os
        os.startfile(link.target)


class TextLinks:
    TAG='explicit_link'
    UNWRAPPED_TAG='literal_no_wrap'
    ELIDED_TAG='literal_hidden_tail'

    def __init__(self,widget,*,blocked=lambda:False,scope=lambda:None,
                 opener=open_link,on_error=lambda error:None,dark=False,links=True):
        from analysis_work import observe_text
        self.widget=widget;self.blocked=blocked;self.scope=scope
        self.opener=opener;self.on_error=on_error;self._links_enabled=links
        # Windows Tk Mod1 is NumLock, not Alt (tkWinPointer.c).
        # Keep lock keys transparent; preserve X11 Alt/AltGr selection gestures.
        windows=widget.tk.call('tk','windowingsystem')=='win32'
        self._modifier_mask=0x1|0x4|0x600|(0x20000 if windows else (0x8|0x80|0x20000))
        self._rows={};self._pressed=None;self._pending=None;self._generation=0
        self._dirty_rows=None;self._line_count=None
        self._pending_lines=None;self._row_text={}
        self._unwrapped_rows={};self._clip_signature=None
        self._destroyed=False
        widget._correctnote_literal_display=self
        # Reuse the existing widget observer; leave document/cursor callbacks
        # intact. Display-only projection changes must invalidate links too.
        observe_text(widget)
        widget._correctnote_observers.setdefault('changed',[]).append(self.changed)
        if links:widget._correctnote_observers.setdefault('viewed',[]).append(self.view_changed)
        self._bindtag='CorrectNoteLinks_'+str(id(self))
        widget.bindtags((self._bindtag,)+widget.bindtags())
        self._bindings={}
        # Class bindings are owned by root in current Tkinter. Use the same
        # owner for registration and deletion on older versions as well.
        self._binding_owner=widget._root()
        for event,handler in (
                ('<ButtonPress-1>',self.press),('<ButtonRelease-1>',self.release),
                ('<B1-Motion>',self.motion),('<Double-Button-1>',self.cancel),
                ('<ButtonPress-2>',self.cancel),('<ButtonPress-3>',self.cancel),
                ('<KeyPress>',self.cancel),('<FocusOut>',self.cancel),
                ('<MouseWheel>',self.cancel),('<Button-4>',self.cancel),
                ('<Button-5>',self.cancel),('<Configure>',self._display_configured),
                ('<Destroy>',self.destroy)):
            if not links and event not in ('<Configure>','<Destroy>'):continue
            self._bindings[event]=self._binding_owner.bind_class(self._bindtag,event,handler)
        widget.tag_configure(self.UNWRAPPED_TAG,wrap='none')
        widget.tag_configure(self.ELIDED_TAG,elide=True)
        self.set_dark(dark);self.changed()

    def set_dark(self,dark):
        if self._links_enabled:
            self.widget.tag_configure(self.TAG,foreground='#78b9ff' if dark else '#065dcc')
        self.widget.tag_raise('sel')

    def cancel(self,event=None):
        self._pressed=None

    def view_changed(self):
        if self._pressed and (self._pressed[3]!=self.widget.yview() or self._pressed[4]!=self.widget.xview()):
            self.cancel()

    def changed(self,args=None):
        if self._destroyed:return
        self._generation+=1;self.cancel()
        widget=self.widget;row=None
        count=int(widget.index('end-1c').split('.')[0])
        # With an unchanged line count, insert or a single delete cannot cross
        # a newline. A replace is equally local only when its new text has no
        # newline. Multi-range deletes, Undo and display rebuilds use full scan.
        if args and count==self._line_count and (
                args[0]=='insert' or (args[0]=='delete' and len(args)<=3)
                or (args[0]=='replace' and not any('\n' in value for value in args[3::2]))):
            from tkinter import TclError
            try:row=min(count,int(widget.index(args[1]).split('.')[0]))
            except TclError:
                # sel.first/last may cease to exist after a successful delete.
                # Do not turn that completed edit into an observer error.
                row=None
        self._line_count=count
        if row is None:
            self._dirty_rows=None;self._rows={};self._row_text={}
            self._pending_lines=widget.get('1.0','end-1c').split('\n')
            if self._links_enabled:widget.tag_remove(self.TAG,'1.0','end')
            self._sync_unwrapped(enumerate(self._pending_lines,1))
        else:
            self._rows.pop(row,None)
            text=widget.get(f'{row}.0',f'{row}.end')
            if self._pending_lines is not None:self._pending_lines[row-1]=text
            else:self._row_text[row]=text
            if self._links_enabled:widget.tag_remove(self.TAG,f'{row}.0',f'{row}.end')
            self._sync_unwrapped(((row,text),),row)
            if self._dirty_rows is not None:self._dirty_rows.add(row)
        if not self._links_enabled:
            self._pending_lines=None;self._row_text={};self._dirty_rows=set()
            return
        if self._pending is None:self._pending=self.widget.after_idle(self.refresh)

    def _sync_unwrapped(self,lines,row=None):
        # Tk undo/redo can issue see before idle callbacks. Apply presentation
        # tags in the completed edit notification, including nested replay.
        # Keep the shared predicate local to avoid literal_lines/find_links'
        # import cycle. No payload decoding or extra widget listener is needed.
        from literal_lines import unwrapped_only
        widget=self.widget
        start,end=('1.0','end') if row is None else (f'{row}.0',f'{row}.end')
        widget.tag_remove(self.UNWRAPPED_TAG,start,end)
        if row is None:self._unwrapped_rows={}
        else:self._unwrapped_rows.pop(row,None)
        ranges=[]
        for line,text in lines:
            if unwrapped_only(text):
                self._unwrapped_rows[line]=text
                ranges.extend((f'{line}.0',f'{line}.end'))
        if ranges:widget.tag_add(self.UNWRAPPED_TAG,*ranges)
        self._refresh_clipping(row)

    def _display_metrics(self):
        widget=self.widget;font=widget.cget('font')
        measure=lambda value:int(widget.tk.call('font','measure',font,'-displayof',widget._w,value))
        unit=max(1,measure('0'))
        inset=2*sum(widget.winfo_pixels(str(widget.cget(option)))
                    for option in ('padx','borderwidth','highlightthickness'))
        # Cap native drawing even at unusually wide windows.
        budget=min(8192,max(1,widget.winfo_width()-inset)+min(128,2*unit))
        tabs=tuple(map(str,widget.tk.splitlist(widget.cget('tabs'))))
        signature=(budget,str(font),tuple(widget.tk.call('font','actual',font)),tabs,
                   str(widget.cget('tabstyle')))
        return signature,measure,unit

    def _visible_prefix(self,text,budget,measure,unit,tabs):
        # This secondary work cap never replaces the measured pixel limit.
        limit=min(len(text),4096);cursor=0;x=0.;positions=[];left_tabs=True
        for item in tabs:
            if item in ('left','right','center','numeric'):
                left_tabs=left_tabs and item=='left'
            else:
                try:positions.append(float(self.widget.winfo_fpixels(item)))
                except (ValueError,TypeError):left_tabs=False
        step=positions[-1]-(positions[-2] if len(positions)>1 else 0) if positions else 8*unit
        step=max(1.,step);chunk=max(1,min(32,int(budget//unit)))
        while cursor<limit:
            if text[cursor]=='\t':
                # Non-left alignment depends on a distant cell end: stop here.
                if not left_tabs:break
                target=next((stop for stop in positions if stop>x),None)
                if target is None:
                    last=positions[-1] if positions else 0.
                    target=last+(int((x-last)//step)+1)*step
                if target>budget:break
                x=target;cursor+=1;continue
            base=cursor;end=text.find('\t',cursor,limit)
            if end<0:end=limit
            while cursor<end:
                stop=min(end,cursor+chunk)
                if x+measure(text[base:stop])>budget:
                    low,high=cursor,stop-1
                    while low<high:
                        middle=(low+high+1)//2
                        if x+measure(text[base:middle])<=budget:low=middle
                        else:high=middle-1
                    return low
                cursor=stop
            x+=measure(text[base:cursor])
        return cursor

    def _refresh_clipping(self,row=None):
        widget=self.widget
        start,end=('1.0','end') if row is None else (f'{row}.0',f'{row}.end')
        widget.tag_remove(self.ELIDED_TAG,start,end)
        if not self._unwrapped_rows:return
        signature,measure,unit=self._display_metrics()
        if signature!=self._clip_signature:
            row=None;widget.tag_remove(self.ELIDED_TAG,'1.0','end')
        self._clip_signature=signature
        rows=self._unwrapped_rows.items() if row is None else ((row,self._unwrapped_rows[row]),) if row in self._unwrapped_rows else ()
        ranges=[]
        for line,text in rows:
            end=self._visible_prefix(text,signature[0],measure,unit,signature[3])
            if end<len(text):ranges.extend((f'{line}.0+{end}c',f'{line}.end'))
        if ranges:widget.tag_add(self.ELIDED_TAG,*ranges)
        widget.tag_raise(self.ELIDED_TAG)

    def refresh_display(self):
        # Public hook for same-size font/tab changes, with document untouched.
        if not self._destroyed:self._refresh_clipping()

    def _display_configured(self,event):
        if event.widget!=self.widget or self._destroyed or not self._unwrapped_rows:return
        signature,_,_=self._display_metrics()
        if signature!=self._clip_signature:self.refresh_display()

    def refresh(self):
        self._pending=None
        if self._destroyed:return
        widget=self.widget;dirty=self._dirty_rows;self._dirty_rows=set()
        pending=self._pending_lines;row_text=self._row_text
        self._pending_lines=None;self._row_text={}
        if dirty is not None:
            ranges=[]
            for row in sorted(dirty):
                if row in self._unwrapped_rows:continue
                links=find_links(row_text[row])
                if links:self._rows[row]=[(link.start,link.end,link) for link in links]
                for link in links:
                    ranges.extend((f'{row}.0+{link.start}c',f'{row}.0+{link.end}c'))
            if ranges:widget.tag_add(self.TAG,*ranges)
            return
        # Empty excluded rows preserve following links' logical coordinates.
        text='\n'.join('' if row in self._unwrapped_rows else line
                       for row,line in enumerate(pending,1))
        links=find_links(text)
        starts=[0]+[match.end() for match in re.finditer('\n',text)] if links else []
        rows={};ranges=[]
        for link in links:
            line=bisect_right(starts,link.start)
            a=link.start-starts[line-1];z=link.end-starts[line-1]
            rows.setdefault(line,[]).append((a,z,Link(a,z,link.target,link.kind)))
            ranges.extend((f'{line}.0+{a}c',f'{line}.0+{z}c'))
        if ranges:widget.tag_add(self.TAG,*ranges)
        self._rows=rows

    def _hit(self,event):
        widget=self.widget
        line,column=map(int,widget.index(f'@{event.x},{event.y}').split('.'))
        # Tk 8.6 reports UTF-16 columns; +Nc indices use Unicode characters.
        if int(widget.tk.call('string','length','\U0001f600'))!=1 and column:
            text=widget.get(f'{line}.0',f'{line}.end')
            prefix=text[:column].encode('utf-16-le','surrogatepass')[:column*2]
            column=len(prefix.decode('utf-16-le','surrogatepass'))
        box=widget.bbox(f'{line}.0+{column}c')
        if not box or not (box[0]<=event.x<box[0]+box[2] and box[1]<=event.y<box[1]+box[3]):
            return None
        return next((link for a,z,link in self._rows.get(line,()) if a<=column<z),None)

    def _modified(self,event):
        # Shift/Ctrl/Alt and another held mouse button belong to selection or
        # scrolling. CapsLock/NumLock do not change a normal click.
        return bool(getattr(event,'state',0)&self._modifier_mask)

    def press(self,event):
        self.cancel()
        if self.blocked() or self._modified(event):return
        link=self._hit(event)
        if link is not None:
            self._pressed=(link,self._generation,self.scope(),self.widget.yview(),
                           self.widget.xview(),event.x,event.y)

    def motion(self,event):
        # Do not consume motion: the ordinary Tk selection drag must run.
        if self._pressed and max(abs(event.x-self._pressed[-2]),abs(event.y-self._pressed[-1]))>3:self.cancel()

    def release(self,event):
        pressed=self._pressed;self.cancel()
        if pressed is None or self.blocked() or self._modified(event):return
        link,generation,scope,yview,xview,x,y=pressed
        if (generation!=self._generation or scope!=self.scope()
                or yview!=self.widget.yview() or xview!=self.widget.xview()
                or abs(x-event.x)>3 or abs(y-event.y)>3
                or link!=self._hit(event) or self.widget.tag_ranges('sel')):
            return
        self.widget.tk.call('tk::CancelRepeat')
        try:self.opener(link)
        except (OSError,ValueError) as error:self.on_error(error)
        return 'break'

    def destroy(self,event):
        if event.widget!=self.widget or self._destroyed:return
        self._destroyed=True;self.cancel();self._rows={}
        self._pending_lines=None;self._row_text={};self._unwrapped_rows={}
        if getattr(self.widget,'_correctnote_literal_display',None) is self:
            del self.widget._correctnote_literal_display
        if self._pending is not None:self.widget.after_cancel(self._pending)
        self._pending=None
        changed=self.widget._correctnote_observers.get('changed',[])
        if self.changed in changed:changed.remove(self.changed)
        viewed=self.widget._correctnote_observers.get('viewed',[])
        if self.view_changed in viewed:viewed.remove(self.view_changed)
        for event,command in self._bindings.items():
            self._binding_owner.unbind_class(self._bindtag,event)
            self._binding_owner.deletecommand(command)


def install(app):
    import analysis_work_app as work
    for widget,attribute in ((app.editor,'_text_links'),(app.result_view,'_result_text_links')):
        setattr(app,attribute,TextLinks(widget,
            blocked=lambda:bool(getattr(app,'_pick_mode',None)),
            scope=lambda:work.token(app),dark=app.settings.get('dark_mode'),
            on_error=lambda error:app.status.configure(text='リンクを開けませんでした: '+str(error))))
