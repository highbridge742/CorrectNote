# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""SR-C/G: volatile input evidence and work identity. Never serialized as history."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass,replace
from bisect import bisect_right


@dataclass(frozen=True)
class Occurrence:
    start:int
    end:int
    surface:str
    reading:str


@dataclass(frozen=True)
class Work:
    owner:object
    generation:int
    source:str
    dependencies:tuple
    readings:tuple


class Document:
    """Only the current text and its live ranges; no edit log, times or counts."""
    def __init__(self,owner,text=''):
        self.owner=owner
        self.text=text
        self.generation=0
        self.occurrences=()

    def update(self,text,discard_readings=False,edited=False,edit=None):
        before=self.text
        if text==before and not edited and not discard_readings:return False
        self.generation+=1
        self._reading_rows=None
        if discard_readings:
            self.occurrences=()
        elif text!=before:
            if not self.occurrences:
                self.text=text
                return True
            if edit is None:
                lo=0
                while lo<min(len(before),len(text)) and before[lo]==text[lo]:lo+=1
                old,new=len(before),len(text)
                while old>lo and new>lo and before[old-1]==text[new-1]:old-=1;new-=1
            else:
                lo,old=edit
                new=old+len(text)-len(before)
                if (not 0<=lo<=old<=len(before) or not lo<=new<=len(text)
                        or before[:lo]!=text[:lo] or before[old:]!=text[new:]):
                    self.occurrences=()
            live=[]
            for item in self.occurrences:
                if item.end<=lo:
                    live.append(item)
                elif item.start>=old:
                    moved=replace(item,start=item.start+new-old,end=item.end+new-old)
                    if text[moved.start:moved.end]==item.surface:live.append(moved)
            self.occurrences=tuple(live)
        elif edited:
            # Undo/replace can return to identical text without preserving identity.
            self.occurrences=()
        self.text=text
        return True

    def remember(self,start,end,surface,reading):
        from ime_readings import reading_to_hiragana,is_kana_reading
        reading=reading_to_hiragana(reading)
        if (not 0<=start<end<=len(self.text) or self.text[start:end]!=surface
                or not is_kana_reading(reading)):
            return False
        entry=Occurrence(start,end,surface,reading)
        live=tuple(x for x in self.occurrences if x.end<=start or end<=x.start)+(entry,)
        live=tuple(sorted(live,key=lambda x:(x.start,x.end,x.reading)))
        if live==self.occurrences:return False
        self.occurrences=live
        self._reading_rows=None
        self.generation+=1
        return True

    def work(self,dependencies=()):
        return Work(self.owner,self.generation,self.text,tuple(dependencies),self.occurrences)

    def accepts(self,work,dependencies=()):
        return work==self.work(dependencies)

    def row_readings(self,index,text):
        """Index the current immutable occurrences once, instead of scanning per row."""
        if not self.occurrences:return ()
        cached=getattr(self,'_reading_rows',None)
        if cached is None or cached[0] is not self.text or cached[1] is not self.occurrences:
            lines=self.text.split('\n');offsets=[];at=0
            for line in lines:offsets.append(at);at+=len(line)+1
            rows={}
            for item in self.occurrences:
                row=bisect_right(offsets,item.start)-1
                if row<0:continue
                start=offsets[row]
                if start<=item.start<item.end<=start+len(lines[row]):
                    rows.setdefault(row,[]).append(replace(item,start=item.start-start,end=item.end-start))
            cached=(self.text,self.occurrences,lines,{row:tuple(items) for row,items in rows.items()})
            self._reading_rows=cached
        if not 0<=index<len(cached[2]) or cached[2][index]!=text:return ()
        return cached[3].get(index,())

    def line_readings(self,start,text):
        if self.text[start:start+len(text)]!=text:return ()
        return tuple(replace(x,start=x.start-start,end=x.end-start)
                     for x in self.occurrences if start<=x.start<x.end<=start+len(text))


_INPUT=ContextVar('correctnote_current_input',default=None)


@contextmanager
def current_input(source,readings=()):
    token=_INPUT.set((source,tuple(readings)))
    try:yield
    finally:_INPUT.reset(token)


def occurrence_readings(source,start,end):
    active=_INPUT.get()
    if not active or active[0]!=source:return ()
    return tuple(x.reading for x in active[1]
                 if x.start==start and x.end==end and source[start:end]==x.surface)


def observe_text(widget,on_edit=None,on_cursor=None):
    """Share one Tcl observer for edits, Unicode undo and cursor notifications."""
    callbacks=getattr(widget,'_correctnote_observers',None)
    if callbacks is not None:
        if on_edit is not None:callbacks['edit']=on_edit
        if on_cursor is not None:callbacks['cursor']=on_cursor
        return
    callbacks={'edit':on_edit,'cursor':on_cursor}
    widget._correctnote_observers=callbacks
    original=widget._w+'_correctnote_work'
    widget.tk.call('rename',widget._w,original)
    from text_edit import UnicodeUndoCommand
    invoke=UnicodeUndoCommand(widget,original)
    def command(*args):
        on_edit=callbacks['edit']
        mutation=(on_edit is not None and not getattr(widget,'_correctnote_display_depth',0) and args and (args[0] in ('insert','delete','replace')
                            or args[:2] in (('edit','undo'),('edit','redo'))))
        before=widget.tk.call(original,'get','1.0','end-1c') if mutation else None
        edit=None
        discard=args[:2] in (('edit','undo'),('edit','redo'))
        if mutation and args[0] in ('insert','delete','replace'):
            lo=len(str(widget.tk.call(original,'get','1.0',args[1])))
            if args[0]=='insert':end=lo
            elif len(args)>2:end=len(str(widget.tk.call(original,'get','1.0',args[2])))
            else:end=lo+len(str(widget.tk.call(original,'get',args[1],str(args[1])+'+1c')))
            edit=(lo,end)
            if args[0]=='delete' and len(args)>3:discard=True
        result=invoke(*args)
        if mutation:
            after=widget.tk.call(original,'get','1.0','end-1c')
            if after!=before or args[:2] in (('edit','undo'),('edit','redo')):
                on_edit(str(after),discard,edit)
        if callbacks['cursor'] is not None and args and (
                args[:3]==('mark','set','insert')
                or args[0] in ('insert','delete','replace')
                or args[:2] in (('edit','undo'),('edit','redo'))):
            callbacks['cursor']()
        return result
    # 48-ACO: native Tcl errors must return to Tcl without becoming an
    # uncaught Python callback error. Otherwise even a caller's handled cget
    # error (dark-mode probing) remains pending and aborts the next mainloop.
    # Preserve the error and its Tcl options; do not silently accept bad edits.
    from tkinter import TclError
    def forward(*args):
        try:
            return (0,command(*args),())
        except TclError as error:
            options=widget.tk.call('dict','create','-code',1,'-level',0,
                '-errorcode',widget.tk.getvar('::errorCode'),
                '-errorinfo',widget.tk.getvar('::errorInfo'))
            return (1,str(error),options)
    callback=widget.register(forward)
    # register() supplies a generated Tcl command name, never document text.
    widget.tk.call('proc',widget._w,'args',
        'set outcome ['+callback+' {*}$args]\n'
        'if {[lindex $outcome 0]} {\n'
        '    return -options [lindex $outcome 2] [lindex $outcome 1]\n'
        '}\n'
        'return [lindex $outcome 1]')
    def destroyed(event):
        if event.widget==widget:
            try:widget.tk.call('rename',widget._w,'')
            except TclError:pass
    widget.bind('<Destroy>',destroyed,add=True)
