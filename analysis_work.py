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
    # The keys typed for this commit (stroke_keys・shift_slip・keystroke_doubt・2026-10-24): [(key, pressed ms), ...]
    # and the Shift presses [(down ms, up ms), ...], in memory only, moved and dropped with the reading. Empty when
    # they are not known.
    strokes:tuple=()
    shifts:tuple=()


@dataclass(frozen=True)
class Calculation:
    start:int
    end:int
    surface:str
    result:str


@dataclass(frozen=True)
class Work:
    owner:object
    generation:int
    source:str
    dependencies:tuple
    readings:tuple
    calculations:tuple=()


class Document:
    """Only the current text and its live ranges; no edit log, times or counts."""
    def __init__(self,owner,text=''):
        self.owner=owner
        self.text=text
        self.generation=0
        self.occurrences=()
        self.calculations=()

    def update(self,text,discard_readings=False,edited=False,edit=None):
        before=self.text
        if text==before and not edited and not discard_readings:return False
        self.generation+=1
        self._reading_rows=None
        if discard_readings:
            self.occurrences=()
            self.calculations=()
        elif text!=before:
            if not (self.occurrences or self.calculations):
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
                    self.calculations=()
            for attribute in ('occurrences','calculations'):
                live=[]
                for item in getattr(self,attribute):
                    if item.end<=lo:
                        live.append(item)
                    elif item.start>=old:
                        moved=replace(item,start=item.start+new-old,end=item.end+new-old)
                        if text[moved.start:moved.end]==item.surface:live.append(moved)
                setattr(self,attribute,tuple(live))
        elif edited:
            # Undo/replace can return to identical text without preserving identity.
            self.occurrences=()
            self.calculations=()
        self.text=text
        return True

    def remember(self,start,end,surface,reading,strokes=(),shifts=()):
        from ime_readings import reading_to_hiragana,is_kana_reading,literal_reading_core
        reading=reading_to_hiragana(reading)
        if not 0<=start<end<=len(self.text) or self.text[start:end]!=surface:
            return False
        if not is_kana_reading(reading):
            core=literal_reading_core(surface,reading)
            if core is None:return False
            lo,hi,reading=core
            surface=surface[lo:hi];start,end=start+lo,start+hi
            strokes=shifts=()   # the keys were for the whole commit, not for this part of it
        entry=Occurrence(start,end,surface,reading,tuple(strokes),tuple(shifts) if strokes else ())
        live=tuple(x for x in self.occurrences if x.end<=start or end<=x.start)+(entry,)
        live=tuple(sorted(live,key=lambda x:(x.start,x.end,x.reading)))
        if live==self.occurrences:return False
        self.occurrences=live
        self._reading_rows=None
        self.generation+=1
        return True

    def remember_calculation(self,start,end,surface,result):
        if not 0<=start<end<=len(self.text) or self.text[start:end]!=surface:
            return False
        from quote_calculator import calculate
        if calculate(surface)!=result:return False
        entry=Calculation(start,end,surface,result)
        live=tuple(x for x in self.calculations if x.end<=start or end<=x.start)+(entry,)
        live=tuple(sorted(live,key=lambda x:(x.start,x.end)))
        if live==self.calculations:return False
        self.calculations=live;self.generation+=1
        return True

    def row_calculations(self,index,text):
        return self._row_occurrences(index,text,'calculations','_calculation_rows')

    def work(self,dependencies=()):
        return Work(self.owner,self.generation,self.text,tuple(dependencies),self.occurrences,self.calculations)

    def accepts(self,work,dependencies=()):
        return work==self.work(dependencies)

    def row_readings(self,index,text):
        """Index the current immutable occurrences once, instead of scanning per row."""
        return self._row_occurrences(index,text,'occurrences','_reading_rows')

    def _row_occurrences(self,index,text,attribute,cache_attribute):
        entries=getattr(self,attribute)
        if not entries:return ()
        cached=getattr(self,cache_attribute,None)
        if cached is None or cached[0] is not self.text or cached[1] is not entries:
            lines=self.text.split('\n');offsets=[];at=0
            for line in lines:offsets.append(at);at+=len(line)+1
            rows={}
            for item in entries:
                row=bisect_right(offsets,item.start)-1
                if row<0:continue
                start=offsets[row]
                if start<=item.start<item.end<=start+len(lines[row]):
                    rows.setdefault(row,[]).append(replace(item,start=item.start-start,end=item.end-start))
            cached=(self.text,entries,lines,{row:tuple(items) for row,items in rows.items()})
            setattr(self,cache_attribute,cached)
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
    exact=tuple(x.reading for x in active[1]
                if x.start==start and x.end==end and source[start:end]==x.surface)
    if exact:return exact
    # Adjacent actual result clauses/partial commits retain their whole
    # reading too. Every piece must match this same live source exactly;
    # gaps, overlaps and a changed occurrence provide no concatenation.
    pieces=sorted((x for x in active[1] if start<=x.start<x.end<=end),
                  key=lambda x:(x.start,x.end))
    edge=start;joined=[]
    for piece in pieces:
        if piece.start!=edge or source[piece.start:piece.end]!=piece.surface:break
        joined.append(piece.reading);edge=piece.end
    else:
        if edge==end and len(joined)>1:return (''.join(joined),)
    # An actual whole commit can attest a smaller native word boundary.
    # Strip only unchanged, independently read surrounding tokens. Never
    # split a native token or guess a kanji-to-reading character alignment.
    found=[]
    for occurrence in active[1]:
        if not (occurrence.start<=start<end<=occurrence.end
                and source[occurrence.start:occurrence.end]==occurrence.surface):continue
        from morphology import tokenize
        parts=tokenize(occurrence.surface)
        a,z=start-occurrence.start,end-occurrence.start
        if not (any(t.start==a for t in parts) and any(t.end==z for t in parts)
                and ''.join(t.surface for t in parts)==occurrence.surface):continue
        left=[t for t in parts if t.end<=a];right=[t for t in parts if z<=t.start]
        if not all(t.has_reading and t.reading for t in left+right):continue
        prefix=''.join(t.reading for t in left);suffix=''.join(t.reading for t in right)
        if not (occurrence.reading.startswith(prefix) and occurrence.reading.endswith(suffix)
                and len(prefix)+len(suffix)<len(occurrence.reading)):continue
        reading=occurrence.reading[len(prefix):len(occurrence.reading)-len(suffix) if suffix else None]
        if all('ぁ'<=c<='ゖ' or c=='ー' for c in reading):found.append(reading)
    return tuple(dict.fromkeys(found))


WHOLE_TEXT=('get','1.0','end-1c')
# Text commands that never change the characters ('edit' is not here:
# undo/redo do, and the rest are rare).
READ_ONLY_COMMANDS=frozenset(('bbox','cget','compare','configure','count','debug','dlineinfo',
                              'dump','get','index','mark','scan','search','see','tag','xview','yview'))


def next_step_seq(widget):
    """A number for a non-text Undo step on this widget, rising with each step (2026-10-25)."""
    value=getattr(widget,'_correctnote_step_seq',0)+1
    widget._correctnote_step_seq=value
    return value


def _hooks_in_turn(hooks,kind):
    """Undo hooks whose owner tells its due step (due_step_seq(kind) -> number or None) go
    newest first for Undo and oldest first for Redo; the others keep their order after them."""
    ranked=[]
    for order,hook in enumerate(tuple(hooks)):
        due=getattr(getattr(hook,'__self__',None),'due_step_seq',None)
        try:seq=due(kind) if due is not None else None
        except Exception:seq=None
        key=(0,-seq if kind=='undo' else seq,order) if seq is not None else (1,0,order)
        ranked.append((key,hook))
    return [hook for _key,hook in sorted(ranked,key=lambda item:item[0])]


def observe_text(widget,on_edit=None,on_cursor=None,on_before_edit=None,track_change=None):
    """Share one Tcl observer for edits, Unicode undo and cursor notifications."""
    callbacks=getattr(widget,'_correctnote_observers',None)
    if callbacks is not None:
        if on_edit is not None:callbacks['edit']=on_edit
        if on_cursor is not None:callbacks['cursor']=on_cursor
        if on_before_edit is not None:callbacks['before']=on_before_edit
        if track_change is not None:callbacks['track']=track_change
        return
    callbacks={'edit':on_edit,'cursor':on_cursor,'before':on_before_edit,'track':track_change}
    widget._correctnote_observers=callbacks
    original=widget._w+'_correctnote_work'
    widget.tk.call('rename',widget._w,original)
    from text_edit import UnicodeUndoCommand
    invoke=UnicodeUndoCommand(widget,original)
    replays=[]
    # The whole text, kept between edits (2026-10-16). With the part-of-speech
    # colours a 3000-row pane holds ~70,000 tag ranges and one native read
    # of the whole text costs ~16 ms; one refresh read it ~10 times. Every
    # command that may change the text passes through command() below, so
    # any such command forgets the copy, and none is served or kept while
    # one is running (an undo replays its edits inside it).
    whole=dict(text=None,busy=0,changes=0,known=None,after=None)
    widget._correctnote_whole_text=whole
    @contextmanager
    def replay_scope(enabled):
        if not enabled:
            yield None
            return
        state=dict(handled=False,after=None);replays.append(state)
        depth=getattr(widget,'_correctnote_replay_depth',0)
        widget._correctnote_replay_depth=depth+1
        try:yield state
        finally:
            widget._correctnote_replay_depth=depth
            replays.pop()
    def command(*args):
        if args==WHOLE_TEXT:
            if not whole['busy'] and whole['text'] is not None:return whole['text']
            result=edit_command(*args)
            if not whole['busy']:whole['text']=str(result)
            return result
        if args and args[0] in READ_ONLY_COMMANDS:return edit_command(*args)
        whole['changes']+=1
        whole['known']=((whole['changes'],whole['text'])
                        if not whole['busy'] and whole['text'] is not None else None)
        whole['text']=None;whole['after']=None;whole['busy']+=1
        try:return edit_command(*args)
        finally:
            whole['busy']-=1;whole['known']=None
            after=whole['after'];whole['after']=None
            # Keep the text read after this edit only if nothing changed it since.
            if not whole['busy'] and after is not None and after[0]==whole['changes']:
                whole['text']=after[1]
    def edit_command(*args):
        if args[:2] in (('edit','undo'),('edit','redo')):
            # Steps that are not text edits (text_format: bold, underline...;
            # editor_guides: the ruler) take their turn in the same Ctrl+Z /
            # Ctrl+Y history. When several are due at the same text, Undo takes
            # the newest step and Redo the oldest (next_step_seq, 2026-10-25).
            for hook in _hooks_in_turn(callbacks.get('undo_hooks',()),args[1]):
                if hook(args[1]):
                    if callbacks['cursor'] is not None:callbacks['cursor']()
                    return ''
        on_edit=callbacks['edit']
        mutation=(on_edit is not None and not getattr(widget,'_correctnote_display_depth',0) and args and (args[0] in ('insert','delete','replace')
                            or args[:2] in (('edit','undo'),('edit','redo'))))
        if mutation and args[0] in ('insert','replace') and callbacks.get('before') is not None:
            prepared=callbacks['before'](args)
            if prepared is not None:args=prepared
        known=whole['known'];whole['known']=None
        if not mutation:before=None
        elif known is not None and known[0]==whole['changes']:before=known[1]
        else:before=widget.tk.call(original,'get','1.0','end-1c')
        edit=None
        discard=args[:2] in (('edit','undo'),('edit','redo'))
        if mutation and args[0] in ('insert','delete','replace'):
            lo=len(str(widget.tk.call(original,'get','1.0',args[1])))
            if args[0]=='insert':end=lo
            elif len(args)>2:end=len(str(widget.tk.call(original,'get','1.0',args[2])))
            else:end=lo+len(str(widget.tk.call(original,'get',args[1],str(args[1])+'+1c')))
            edit=(lo,end)
            if args[0]=='delete' and len(args)>3:discard=True
        from contextlib import nullcontext
        track=callbacks.get('track') if mutation else None
        inserted=None;span=None
        if (len(args)>1 and args[0] in ('insert','delete','replace') and callbacks.get('changed')
                and not (args[0]=='delete' and len(args)>3)):
            # Where the edit starts and how many rows it adds or removes, so
            # row-keyed presentation can follow the text instead of resetting.
            try:span=(int(str(widget.tk.call(original,'index',args[1])).split('.')[0]),
                      int(str(widget.tk.call(original,'index','end')).split('.')[0]))
            except Exception:span=None
        if len(args)>2 and args[0]=='insert' and callbacks.get('inserted'):
            inserted=(widget.tk.call(original,'index',args[1]),''.join(str(chunk) for chunk in args[2::2]))
        with replay_scope(discard) as replay, (track() if track is not None else nullcontext()) as commit:
            result=invoke(*args)
            if inserted is not None:
                for callback in tuple(callbacks.get('inserted',())):callback(*inserted)
            if mutation:
                after=widget.tk.call(original,'get','1.0','end-1c')
                whole['after']=(whole['changes'],str(after))
                if after!=before or args[:2] in (('edit','undo'),('edit','redo')):
                    if after!=before and commit is not None:commit()
                    # Tk may replay undo through ordinary insert/delete
                    # commands. Those actual edits already rebased the live
                    # document and discarded only touched evidence. Avoid a
                    # second global discard after their final text matches.
                    # Unobserved/native replay retains the conservative path.
                    if replay is None or not replay['handled'] or replay['after']!=after:
                        on_edit(str(after),discard,edit)
                        for state in replays:
                            state.update(handled=True,after=after)
        if callbacks['cursor'] is not None and args and (
                args[:3]==('mark','set','insert')
                or args[0] in ('insert','delete','replace')
                or args[:2] in (('edit','undo'),('edit','redo'))):
            callbacks['cursor']()
        if args and (args[:3]==('mark','set','insert')
                or args[0] in ('insert','delete','replace')
                or args[:2] in (('edit','undo'),('edit','redo'))):
            for moved in tuple(callbacks.get('moved',())):moved()
        if args and (args[0] in ('insert','delete','replace')
                or args[:2] in (('edit','undo'),('edit','redo'))):
            if span is not None:
                try:span=(span[0],int(str(widget.tk.call(original,'index','end')).split('.')[0])-span[1])
                except Exception:span=None
            widget._correctnote_last_edit=span
            for changed in tuple(callbacks.get('changed',())):changed(args)
        if len(args)>1 and args[0] in ('xview','yview'):
            for viewed in tuple(callbacks.get('viewed',())):viewed()
        if len(args)>1 and args[0]=='tag' and args[1] in ('add','remove','configure','raise','lower','delete'):
            # Fonts and spacing may move rows without an edit or a scroll
            # (emoji_color lays its labels again: 2026-10-15).
            for tagged in tuple(callbacks.get('tagged',())):tagged()
        if args and ((len(args)>1 and args[0] in ('xview','yview')) or args[0]=='see'):
            # Synchronous, before Tk redraws the moved view at idle time.
            for scrolled in tuple(callbacks.get('scrolled',())):scrolled()
        return result
    # 48-ACO: native Tcl errors must return to Tcl without becoming an
    # uncaught Python callback error. Otherwise even a caller's handled cget
    # error (dark-mode probing) remains pending and aborts the next mainloop.
    # Preserve the error and its Tcl options; do not silently accept bad edits.
    from tkinter import TclError
    def forward(*args):
        try:
            # BackSpace/Delete next to an emoji must not remove only half of
            # it (text_edit.pair_safe_delete); widened before the edit span
            # is measured, so analysis sees the real edit.
            from text_edit import pair_safe_delete
            args,marks=pair_safe_delete(widget,original,args)
            try:return (0,command(*args),())
            finally:
                if marks:widget.tk.call(original,'mark','unset',*marks)
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
