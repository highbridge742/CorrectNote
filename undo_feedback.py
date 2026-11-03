"""Volatile edit ranges for Undo/Redo color, and the steps a file tab keeps while it is away (tab_undo).

Memory only: what the steps hold is never written anywhere, and goes with the step."""
import tkinter as tk


def inserted_ranges(operations):
    ranges=[]
    for start,removed,added in operations:
        end=start+removed;delta=added-removed;rebased=[]
        for left,right in ranges:
            if left<start:rebased.append((left,min(right,start)))
            if right>end:rebased.append((max(left,end)+delta,right+delta))
        if added:rebased.append((start,start+added))
        ranges=[]
        for left,right in sorted(rebased):
            if left>=right:continue
            if ranges and left<=ranges[-1][1]:ranges[-1]=(ranges[-1][0],max(ranges[-1][1],right))
            else:ranges.append((left,right))
    return ranges


_SEQ=[0]


def next_seq():
    """The order of the steps over all the tabs."""
    _SEQ[0]+=1
    return _SEQ[0]


LOG_CHARS=1000000   # what one tab's steps hold (tab_undo.TAB_CHARS); the oldest step goes first


def expanded(operations,undo=False):
    out=[]
    for start,removed,added in (reversed(operations) if undo else operations):
        if undo:removed,added=added,removed
        if removed:out.append((start,removed,0))
        if added:out.append((start,0,added))
    return out


class UndoFeedback:
    TAG='undo_feedback'

    def __init__(self,widget,color,underline_color=lambda:'#b65000'):
        self.widget=widget
        self.original=widget._w+'_correctnote_work'
        self.undo=[];self.redo=[]
        # The same steps, newest last, with their text: (seq, the entry of undo/redo, [(start, removed, added)]).
        # log/redo_log line up with undo/redo from the end. parked/parked_redo: steps from before this tab was
        # left (tab_undo), older than anything in the Text's own history
        self.log=[];self.redo_log=[];self.log_chars=0
        self.parked=[];self.parked_redo=[]
        self.on_empty=None      # a Ctrl+Z with nothing to undo here (tab_undo)
        self._pending_text=None
        self.boundary=not bool(self._call('edit','canundo'))
        self.last_kind=None
        self.replay=None
        self.job=None
        self.closed=False
        self.epoch=0
        self._color=color;self._underline_color=underline_color;self._redo_style=False
        self.refresh_theme()
        widget._correctnote_undo_feedback=self
        widget.bind('<Destroy>',self._destroy,add=True)

    def _call(self,*args):
        return self.widget.tk.call(self.original,*args)

    def _count(self,start,end):
        value=self._call('count','-chars',start,end)
        return int(value[0] if isinstance(value,tuple) else value or 0)

    def _operation(self,args):
        kind=args[0]
        start_index=self._call('index',args[1])
        if self._call('compare',start_index,'>','end-1c'):start_index='end-1c'
        start=self._count('1.0',start_index)
        if kind=='insert':finish=start_index;parts=args[2::2]
        elif kind=='replace':finish=args[2];parts=args[3::2]
        elif kind=='delete' and len(args)<=3:
            finish=args[2] if len(args)==3 else str(args[1])+'+1c';parts=()
        else:return None
        if self._call('compare',finish,'>','end-1c'):finish='end-1c'
        if self._call('compare',finish,'<',start_index):finish=start_index
        removed=self._count(start_index,finish) if kind!='insert' else 0
        added=sum(int(self.widget.tk.call('string','length',part)) for part in parts)
        self._pending_text=(start,str(self._call('get',start_index,finish)) if removed else '',
                            ''.join(str(part) for part in parts))
        return (start,removed,added)

    def _clear_color(self):
        self.epoch+=1
        if self.job is not None:
            self.widget.after_cancel(self.job);self.job=None
        self._call('tag','remove',self.TAG,'1.0','end')

    def _invalidate(self):
        self.undo.clear();self.redo.clear();self.last_kind=None;self.boundary=False
        self.log.clear();self.redo_log.clear();self.log_chars=0
        self.parked.clear();self.parked_redo.clear()
        self._clear_color()

    def _record(self,kind,operation,automatic):
        if not any(operation[1:]):return
        self.redo.clear();self.redo_log.clear();self.parked_redo.clear()
        if self.boundary or (automatic and self.last_kind not in (None,kind)):
            self.undo.append([])
            self.log.append((next_seq(),self.undo[-1],[]))
        if self.undo:
            self.undo[-1].append(operation)
            text=self._pending_text
            if self.log and self.log[-1][1] is self.undo[-1] and text is not None:
                self.log[-1][2].append(text)
                self.log_chars+=len(text[1])+len(text[2])
                self._trim_log()
        self.boundary=False;self.last_kind=kind
        limit=int(self._call('cget','-maxundo'))
        if limit>0:self.undo[:max(0,len(self.undo)-limit)]=[]

    def _trim_log(self):
        while self.log_chars>LOG_CHARS and (self.parked or len(self.log)>1):
            entry=(self.parked or self.log).pop(0)
            self.log_chars-=sum(len(a)+len(b) for _start,a,b in entry[2])
        # With some of its steps gone the rest still leads back from the text as it is; only the older ones go

    def take(self):
        """The steps of the tab being left."""
        snapshot=dict(undo=self.parked+self.log,redo=list(self.parked_redo or self.redo_log))
        # New lists: what comes next must not join a step that has left with the tab
        self.undo=[];self.redo=[];self.log=[];self.redo_log=[];self.parked=[];self.parked_redo=[]
        self.log_chars=0;self.boundary=True;self.last_kind=None
        return snapshot

    def give(self,snapshot):
        """The steps of the tab that came back, after its history was reset."""
        self.parked=list(snapshot['undo']);self.parked_redo=list(snapshot['redo'])
        self.log_chars=sum(len(a)+len(b) for entry in self.parked for _start,a,b in entry[2])

    def _unit_index(self,text,units):
        """Where `units` (the Text's count: an emoji can be 2) falls in the Python string."""
        if int(self.widget.tk.call('string','length','😀'))!=2 or text.isascii():return units
        at=0;seen=0
        while seen<units and at<len(text):
            seen+=2 if ord(text[at])>0xffff else 1
            at+=1
        return at

    def _where(self,text,at):
        row=text.count('\n',0,at)+1
        return f"{row}.0+{at-(text.rfind(chr(10),0,at)+1)}c"

    def _apply_raw(self,text,start,removed,added):
        at=self._unit_index(text,start)
        if text[at:at+len(removed)]!=removed:raise ValueError
        if removed:self._call('delete',self._where(text,at),self._where(text,at+len(removed)))
        if added:self._call('insert',self._where(text,at),added)
        return text[:at]+added+text[at+len(removed):]

    def _fits(self,text,ops,undo):
        """Does this step fit the text as it is? Checked before anything is touched."""
        for start,removed,added in (reversed(ops) if undo else ops):
            if undo:removed,added=added,removed
            at=self._unit_index(text,start)
            if text[at:at+len(removed)]!=removed:return False
            text=text[:at]+added+text[at+len(removed):]
        return True

    def _bring_back(self):
        """Puts the newest kept step into the Text's own history: its own Undo then does the rest as for any other."""
        entry=self.parked[-1]
        text=str(self._call('get','1.0','end-1c'))
        if not self._fits(text,entry[2],True):
            self.parked.clear();self.parked_redo.clear()
            return False
        automatic=self._call('cget','-autoseparators')
        self._call('configure','-undo',0)
        try:
            for start,removed,added in reversed(entry[2]):
                text=self._apply_raw(text,start,added,removed)
        finally:self._call('configure','-undo',1)
        self._call('configure','-autoseparators',0)
        try:
            self._call('edit','separator')
            for start,removed,added in entry[2]:
                text=self._apply_raw(text,start,removed,added)
            self._call('edit','separator')
        finally:self._call('configure','-autoseparators',automatic)
        self.parked.pop()
        self.undo[:]=[entry[1]];self.log[:]=[entry]
        self.redo.clear();self.redo_log.clear()
        return True

    def _redo_kept(self):
        """The next kept redo, done here: the Text's history gets it as an ordinary step."""
        entry=self.parked_redo[-1]
        text=str(self._call('get','1.0','end-1c'))
        if not self._fits(text,entry[2],False):
            self.parked_redo.clear()
            return
        automatic=self._call('cget','-autoseparators')
        self._call('configure','-autoseparators',0)
        try:
            self._call('edit','separator')
            for start,removed,added in entry[2]:
                text=self._apply_raw(text,start,removed,added)
            self._call('edit','separator')
        finally:self._call('configure','-autoseparators',automatic)
        self.parked_redo.pop()
        self.undo.append(entry[1]);self.log.append(entry)
        self.boundary=True;self.last_kind=None
        self._queue_color(inserted_ranges(entry[1]),redo=True)

    def invoke(self,args,native):
        if self.closed or not args:return native()
        kind=args[0]
        is_replay=args[:2] in (('edit','undo'),('edit','redo'))
        if is_replay:
            if self.replay is None:
                if args[1]=='undo' and not int(self._call('edit','canundo')):
                    if not (self.parked and self._bring_back()) and self.on_empty is not None:
                        self.on_empty()
                elif args[1]=='redo' and not int(self._call('edit','canredo')) and self.parked_redo:
                    self._redo_kept()
                    return ''
            return self._replay(args[1],native)
        if kind in ('insert','delete','replace'):
            if self._call('cget','-state')!='normal':return native()
            operation=None;self._pending_text=None
            try:
                operation=self._operation(args)
                enabled=bool(int(self._call('cget','-undo')))
                automatic=bool(int(self._call('cget','-autoseparators')))
                self._clear_color()
            except (tk.TclError,TypeError,ValueError,IndexError):
                enabled=False;automatic=False
            try:result=native()
            except Exception:
                self._invalidate()
                raise
            if operation is None or not enabled:
                self._invalidate()
                if self.replay is not None:self.replay['valid']=False
            elif self.replay is not None:
                self.replay['operations'].extend(expanded([operation]))
            else:self._record(kind,operation,automatic)
            return result
        result=native()
        if args[:2]==('edit','reset'):
            self._invalidate();self.boundary=True
        elif args[:2]==('edit','separator'):
            self.boundary=True
        elif kind=='configure' and len(args)>2:
            if any(str(key) in ('-undo','-maxundo') for key in args[1::2]):self._invalidate()
        elif kind in ('image','window','peer') or kind not in (
                'bbox','cget','compare','configure','count','debug','dlineinfo','dump',
                'edit','get','index','mark','scan','search','see','tag','xview','yview'):
            self._invalidate()
        return result

    def _replay(self,kind,native):
        self._clear_color()
        if self.replay is not None:
            self.replay['valid']=False
            return native()
        state={'operations':[],'valid':True}
        self.replay=state
        try:result=native()
        except Exception:
            self._invalidate()
            raise
        finally:self.replay=None
        stack=self.undo if kind=='undo' else self.redo
        group=stack[-1] if stack else None
        expected=expanded(group,undo=kind=='undo') if group else None
        valid=state['valid'] and expected==state['operations']
        if valid:
            stack.pop()
            (self.redo if kind=='undo' else self.undo).append(group)
            log=self.log if kind=='undo' else self.redo_log
            if log and log[-1][1] is group:
                (self.redo_log if kind=='undo' else self.log).append(log.pop())
            self.boundary=True;self.last_kind=None
        else:self._invalidate()
        if kind=='redo' and state['valid']:
            self._queue_color(inserted_ranges(state['operations']),redo=True)
        elif kind=='undo' and valid:
            # What came back (a cut, a replaced word: 2026-11-03 うにさん「下線がない」); when an undo only took
            # text away there is nothing to show of it, so the step that is next, as before
            back=inserted_ranges([(start,added,removed) for start,removed,added in reversed(group)]) if group else []
            if back:self._queue_color(back)
            elif self.undo:self._queue_color(inserted_ranges(self.undo[-1]))
        return result

    def _queue_color(self,ranges,redo=False):
        if not ranges:return
        epoch=self.epoch
        def paint():
            self.job=None
            if self.closed or epoch!=self.epoch:return
            # Read the current projection only while painting, never retain text.
            text=str(self._call('get','1.0','end-1c'))
            positions={};wanted={value for pair in ranges for value in pair}
            units=0;row=1;column=0
            wide=int(self.widget.tk.call('string','length','😀'))==2
            for char in text:
                if units in wanted:positions[units]=f'{row}.0+{column}c'
                if len(positions)==len(wanted):break
                units+=2 if wide and ord(char)>0xffff else 1
                if char=='\n':row+=1;column=0
                else:column+=1
            if units in wanted:positions[units]=f'{row}.0+{column}c'
            if len(positions)!=len(wanted):return
            self._redo_style=redo
            self.refresh_theme()
            for left,right in ranges:self._call('tag','add',self.TAG,positions[left],positions[right])
            self._call('tag','raise',self.TAG)
            self._call('tag','raise','sel')
        self.job=self.widget.after_idle(paint)

    def _destroy(self,event):
        if event.widget is not self.widget:return
        self.closed=True
        if self.job is not None:self.widget.after_cancel(self.job)
        self.job=None;self.undo.clear();self.redo.clear()
        self.widget._correctnote_undo_feedback=None

    def refresh_theme(self):
        if not self.closed:
            self._call('tag','configure',self.TAG,'-background','',
                       '-underline',1,'-underlinefg',self._underline_color())


def install(widget,color,underline_color=lambda:'#b65000'):
    existing=getattr(widget,'_correctnote_undo_feedback',None)
    if existing is not None:return existing
    from analysis_work import observe_text
    observe_text(widget)
    return UndoFeedback(widget,color,underline_color)
