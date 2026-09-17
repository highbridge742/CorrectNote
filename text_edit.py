# -*- coding: utf-8 -*-
"""Group a user operation without erasing the Text widget's existing undo history."""
from contextlib import contextmanager

@contextmanager
def undo_group(widget):
    depth=getattr(widget,'_correctnote_undo_depth',0)
    if depth:
        widget._correctnote_undo_depth=depth+1
        try:yield
        finally:widget._correctnote_undo_depth=depth
        return
    automatic=widget.cget('autoseparators')
    widget.edit_separator()
    widget.configure(autoseparators=False)
    widget._correctnote_undo_depth=1
    try:
        yield
    finally:
        widget._correctnote_undo_depth=0
        widget.edit_separator()
        widget.configure(autoseparators=automatic)


class UnicodeUndoCommand:
    """Translate legacy Tk undo's UTF-16 columns only while replaying history.

    Tk 8.6.9 prints surrogate-unit columns into undo scripts but parses them
    as character columns. A small interpreter-local probe selects this path;
    ordinary edits and unaffected Tk builds retain the native command.
    """
    def __init__(self,widget,original):
        self.widget=widget;self.original=original;self.depth=0
        root=widget._root()
        enabled=getattr(root,'_correctnote_legacy_unicode_undo',None)
        if enabled is None:
            probe=root._w.rstrip('.')+'.correctnote_unicode_probe'
            suffix=0
            while widget.tk.call('winfo','exists',probe):
                suffix+=1;probe=root._w.rstrip('.')+'.correctnote_unicode_probe'+str(suffix)
            widget.tk.call('text',probe,'-undo',1)
            try:
                widget.tk.call(probe,'insert','1.0','az')
                widget.tk.call(probe,'edit','reset')
                widget.tk.call(probe,'insert','1.1','😀')
                widget.tk.call(probe,'edit','undo')
                enabled=widget.tk.call(probe,'get','1.0','end-1c')!='az'
            finally:widget.tk.call('destroy',probe)
            root._correctnote_legacy_unicode_undo=enabled
        self.enabled=enabled

    def _index(self,value):
        import re
        match=re.fullmatch(r'(\d+)\.(\d+)',str(value))
        if not match:return value
        row,column=map(int,match.groups())
        line=str(self.widget.tk.call(self.original,'get',str(row)+'.0',str(row)+'.end'))
        units=0
        for offset,char in enumerate(line):
            if units==column:return str(row)+'.'+str(offset)
            units+=2 if ord(char)>0xffff else 1
            if units>column:return value
        return str(row)+'.'+str(len(line)) if column>=units else value

    def __call__(self,*args):
        if not self.enabled:return self.widget.tk.call(self.original,*args)
        if self.depth and args:
            values=list(args)
            if args[0]=='insert':indices=(1,)
            elif args[0]=='delete':indices=range(1,len(args))
            elif args[0]=='replace':indices=(1,2)
            elif args[:2]==('mark','set'):indices=(3,)
            else:indices=()
            for index in indices:
                if index<len(values):values[index]=self._index(values[index])
            args=tuple(values)
        replay=args[:2] in (('edit','undo'),('edit','redo'))
        self.depth+=bool(replay)
        try:return self.widget.tk.call(self.original,*args)
        finally:self.depth-=bool(replay)
