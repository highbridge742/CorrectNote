"""Volatile edit ranges for Undo/Redo color; never stores or replays document text."""
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
        return (start,removed,added)

    def _clear_color(self):
        self.epoch+=1
        if self.job is not None:
            self.widget.after_cancel(self.job);self.job=None
        self._call('tag','remove',self.TAG,'1.0','end')

    def _invalidate(self):
        self.undo.clear();self.redo.clear();self.last_kind=None;self.boundary=False
        self._clear_color()

    def _record(self,kind,operation,automatic):
        if not any(operation[1:]):return
        self.redo.clear()
        if self.boundary or (automatic and self.last_kind not in (None,kind)):
            self.undo.append([])
        if self.undo:self.undo[-1].append(operation)
        self.boundary=False;self.last_kind=kind
        limit=int(self._call('cget','-maxundo'))
        if limit>0:self.undo[:max(0,len(self.undo)-limit)]=[]

    def invoke(self,args,native):
        if self.closed or not args:return native()
        kind=args[0]
        is_replay=args[:2] in (('edit','undo'),('edit','redo'))
        if is_replay:
            return self._replay(args[1],native)
        if kind in ('insert','delete','replace'):
            if self._call('cget','-state')!='normal':return native()
            operation=None
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
            self.boundary=True;self.last_kind=None
        else:self._invalidate()
        if kind=='redo' and state['valid']:
            self._queue_color(inserted_ranges(state['operations']),redo=True)
        elif kind=='undo' and valid and self.undo:
            self._queue_color(inserted_ranges(self.undo[-1]))
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
