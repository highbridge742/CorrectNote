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
        self._install_click_gap()

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

    # ------------------------------------------------------------------
    # An emoji outside the BMP is two UTF-16 halves in Tk. One step of the
    # cursor (left/right, Shift+left/right) can stop between them: the pane
    # then draws half an emoji and the next step only finishes the first
    # (2026-10-14 うにさん「絵文字の右にカーソルを置き、左キーを1回押すと
    # 表示が変になり、絵文字の左側へカーソルが移動しません」). Positions are
    # moved off the middle with marks and relative steps only: Tk 8.6.9
    # returns `row.col` with the emoji as two columns but reads it as one,
    # so returned indexes must not be fed back.
    #
    # 2026-10-15 うにさん「❤この文字が2文字の幅を使っていて、カーソル移動で
    # うまく跨げません」: the same holds for every cluster of code points that
    # reads as one character (cluster_bounds): ❤ + U+FE0F (Tk 8.6.9 gives the
    # selector its own 18px), a skin tone, a ZWJ family, a flag, a keycap, a
    # combining mark. The cursor, the selection ends and a click stop only at
    # their edges; the colour overlay (emoji_color) covers the whole cluster,
    # and with no stop inside it the cursor is never hidden under it.
    _MID='correctnote_pair_mid'
    _KEY='correctnote_key_step'
    _GAP='correctnote_click_gap'
    # Tk's own Shift+Left/Right feed `index` back into `mark set` (text.tcl
    # <<SelectPrevChar>>/<<SelectNextChar>>); a mark keeps the place instead.
    _KEY_STEPS={'insert - 1displayindices':'back','insert + 1displayindices':'forward'}

    def _raw(self,*args):
        return self.widget.tk.call(self.original,*args)

    def _between_halves(self,mark):
        return between_halves(lambda *a:self._raw(*a),mark)

    def _whole(self,mark,forward):
        cluster_edge(self._raw,mark,'forward' if forward else 'back')

    def _pair_safe(self,args):
        """Run args with no cursor or selection end left inside a cluster."""
        if args[:3]==('mark','set','insert') and len(args)==4:
            self._raw('mark','set',self._MID,'insert')
            result=self._invoke(args)
            try:
                if _maybe_inside(self._raw,'insert'):
                    # Left steps back out, Right forward; a jump (a click,
                    # the same place again) to the closer edge.
                    if '@' in str(args[3]):mode='near'
                    elif self._raw('compare','insert','>',self._MID):mode='forward'
                    elif self._raw('compare','insert','<',self._MID):mode='back'
                    else:mode='near'
                    self._raw('mark','set',self._MID,'insert')
                    if cluster_edge(self._raw,self._MID,mode):
                        self._raw('mark','set','insert',self._MID)
            finally:self._raw('mark','unset',self._MID)
            return result
        if args[:3] in (('tag','add','sel'),('tag','remove','sel')) and len(args)==5:
            a,b=self._MID+'_a',self._MID+'_b'
            self._raw('mark','set',a,args[3]);self._raw('mark','set',b,args[4])
            self._whole(a,False);self._whole(b,True)
            try:return self._invoke(args[:3]+(a,b))
            finally:self._raw('mark','unset',a,b)
        return self._invoke(args)

    def _key_step(self,index):
        """The mark Tk's Shift+Left/Right moves to: one step, off any cluster."""
        self._raw('mark','set',self._KEY,index)
        cluster_edge(self._raw,self._KEY,self._KEY_STEPS[index])
        return self._KEY

    def _install_click_gap(self):
        """Clicks and drags stop at cluster edges (tk::TextClosestGap per pane).

        Tk's own procedure reads back the `row.col` it got from `index @x,y`,
        which Tk 8.6.9 misreads after an emoji; this one works with marks and
        keeps Tk's rule (the left half of a character stops before it). Panes
        without this command keep Tk's procedure."""
        w=self.widget;tk=w.tk
        try:
            if not tk.call('info','procs','::tk::TextClosestGap'):
                tk.call('auto_load','::tk::TextClosestGap')
            if not tk.call('info','procs','::tk::CorrectNoteNativeClosestGap'):
                tk.call('rename','::tk::TextClosestGap','::tk::CorrectNoteNativeClosestGap')
                tk.eval('proc ::tk::TextClosestGap {w x y} {\n'
                        '    if {[info exists ::correctnote_text_gap($w)]} {\n'
                        '        set gap [$::correctnote_text_gap($w) $x $y]\n'
                        '        if {$gap ne ""} {return $gap}\n'
                        '    }\n'
                        '    return [::tk::CorrectNoteNativeClosestGap $w $x $y]\n'
                        '}')
            name='::correctnote_text_gap('+w._w+')'
            tk.setvar(name,w.register(self._closest_gap))
        except Exception:
            return
        def destroyed(event):
            if event.widget is w:
                try:tk.call('unset','-nocomplain',name)
                except Exception:pass
        w.bind('<Destroy>',destroyed,add=True)

    def _closest_gap(self,x,y):
        try:
            call=self._raw;start,end=self._GAP,self._GAP+'_end'
            call('mark','set',start,'@%s,%s'%(x,y))
            cluster_edge(call,start,'back')
            split=lambda box:[int(float(v)) for v in self.widget.tk.splitlist(box)]
            box=call('bbox',start)
            if not box:return start
            bx,by,bw,_bh=split(box)
            call('mark','set',end,start+' +1c')
            cluster_edge(call,end,'forward')
            right=bx+bw
            after=call('bbox',end)
            if after:
                ex,ey=split(after)[:2]
                if ey==by and ex>bx:right=ex
            return start if int(float(x))-bx<(right-bx)//2 else end
        except Exception:
            return ''

    def __call__(self,*args):
        if (len(args)==2 and args[0]=='index' and args[1] in self._KEY_STEPS
                and not self.depth):
            return self._key_step(args[1])
        if args and args[0] in ('mark','tag') and not self.depth:
            return self._pair_safe(args)
        if not self.enabled:return self._invoke(args)
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
        try:return self._invoke(args)
        finally:self.depth-=bool(replay)

    def _invoke(self,args):
        feedback=getattr(self.widget,'_correctnote_undo_feedback',None)
        if feedback is None:return self.widget.tk.call(self.original,*args)
        return feedback.invoke(args,lambda:self.widget.tk.call(self.original,*args))


def between_halves(call,mark):
    """Whether `mark` sits between the two UTF-16 halves of an emoji."""
    value=str(call('get',mark))
    if value:return '\udc00'<=value[0]<='\udfff'
    # Newer Tk reads the second half as an empty character.
    return bool(call('compare',mark,'<','end-1c'))


def pair_safe_delete(widget,original,args):
    """`delete` arguments that never cut an emoji in half.

    Returns (args, marks to unset afterwards). BackSpace after an emoji asks
    for one character at `insert -1c`, which in Tk is only the second UTF-16
    half; Delete before it asks for only the first half. Both are widened to
    the whole emoji with marks and relative steps (see UnicodeUndoCommand).

    BackSpace and Delete themselves (Tk's `delete insert-1c` and `delete
    insert`) remove the whole cluster (cluster_bounds: ❤️, 👍🏽, 👨‍👩‍👧, 🇯🇵 ...).
    Other deletes keep their exact range apart from the halves: a program
    may mean to take one selector or mark away."""
    if not args or args[0]!='delete' or len(args) not in (2,3):return args,()
    call=lambda *a:widget.tk.call(original,*a)
    a,b='correctnote_pair_del_a','correctnote_pair_del_b'
    call('mark','set',a,args[1])
    def off_middle(mark,forward):
        # Tk counts forward over a whole emoji but may step back into its
        # middle; check after each step instead of assuming either way.
        for _ in range(2):
            if not between_halves(call,mark):return
            call('mark','set',mark,mark+(' +1c' if forward else ' -1c'))
    if len(args)==3:
        call('mark','set',b,args[2])
    else:
        call('mark','set',b,a+' +1c')
    if args[1:] in (('insert-1c',),('insert',)):
        moved=cluster_edge(call,a,'back')
        if cluster_edge(call,b,'forward') or moved:
            return ('delete',a,b),(a,b)
    if not (between_halves(call,a) or between_halves(call,b)):
        call('mark','unset',a,b);return args,()
    off_middle(a,False);off_middle(b,True)
    return ('delete',a,b),(a,b)


# ----------------------------------------------------------------------
# Characters made of several code points (the parts of UAX #29 extended
# grapheme clusters met in memos). Halfwidth ﾞ ﾟ stay letters of their own:
# Tk draws them as such and CorrectNote repairs halfwidth kana by them.
def _pictographic(o):
    return (0x1f000<=o<=0x1faff or 0x2600<=o<=0x27bf or 0x2300<=o<=0x23ff
            or 0x2b00<=o<=0x2bff or 0x2194<=o<=0x21aa or 0x25aa<=o<=0x25fe
            or 0x2934<=o<=0x2935
            or o in (0xa9,0xae,0x203c,0x2049,0x2122,0x2139,0x3030,0x303d,0x3297,0x3299))


def _kind(ch):
    import unicodedata
    o=ord(ch)
    if o==0x200d:return 'zwj'
    if 0x1f1e6<=o<=0x1f1ff:return 'ri'
    if (0xfe00<=o<=0xfe0f or 0x1f3fb<=o<=0x1f3ff or 0xe0020<=o<=0xe007f
            or 0xe0100<=o<=0xe01ef):return 'extend'
    if 0xd800<=o<=0xdfff or o in (0xff9e,0xff9f):return 'other'
    if unicodedata.category(ch) in ('Mn','Me','Mc'):return 'extend'
    return 'pict' if _pictographic(o) else 'other'


def _units(text):
    return len(text.encode('utf-16-le','surrogatepass'))//2


def _joined(text):
    # Two halves cut apart by a mark come back together as one code point.
    return text.encode('utf-16-le','surrogatepass').decode('utf-16-le','surrogatepass')


def cluster_bounds(text):
    """UTF-16 offsets in `text` where the cursor may stop (0 and the end too).

    Joined to the character before them: combining marks, variation
    selectors (U+FE0F), skin tones, tag characters, a ZWJ and the pictograph
    after it (👨‍👩‍👧), and regional indicators in pairs (🇯🇵)."""
    out=[0];units=0;prev=None;base=None;ri=0
    for ch in _joined(text):
        k=_kind(ch)
        if prev is None:join=True;base=k
        elif k in ('extend','zwj'):join=True
        elif k=='pict' and prev=='zwj' and base=='pict':join=True
        elif k=='ri' and prev=='ri' and ri%2:join=True
        else:join=False
        if not join:out.append(units);base=k
        ri=ri+1 if k=='ri' else 0
        units+=2 if ord(ch)>0xffff else 1
        prev=k
    if units:out.append(units)
    return out


_WINDOW=32   # code points read on each side; longer clusters are not met


def _maybe_inside(call,mark):
    """Cheap first look: could `mark` be inside a cluster?"""
    ahead=str(call('get',mark))
    if not ahead:return between_halves(call,mark)
    k=_kind(ahead[0])
    if k in ('extend','zwj') or '\udc00'<=ahead[0]<='\udfff':return True
    if k in ('pict','ri'):
        behind=_joined(str(call('get',mark+' -2c',mark)))
        if behind:
            p=_kind(behind[-1])
            return (k=='pict' and p=='zwj') or (k=='ri' and p=='ri')
    return False


def cluster_edge(call,mark,mode):
    """Move `mark` to an edge of the cluster it is inside. Returns whether it moved.

    mode is 'back', 'forward' or 'near' (the closer edge, the earlier on a
    tie). Only marks and relative steps are used: Tk 8.6.9 goes back one
    UTF-16 half per -1c but forward one code point per +1c, so each step is
    measured instead of assumed."""
    if not _maybe_inside(call,mark):return False
    anchor='correctnote_cluster_anchor'
    try:
        call('mark','set',anchor,mark+' -%dc'%(2*_WINDOW))
        before=str(call('get',anchor,mark))
        if '\n' in before:
            call('mark','set',anchor,mark+' linestart')
            before=str(call('get',anchor,mark))
        after=str(call('get',mark,mark+' +%dc'%_WINDOW)).split('\n',1)[0]
        pos=_units(before);bounds=cluster_bounds(before+after)
        if pos in bounds:
            if not between_halves(call,mark):return False
            # A Tk that reads the second half as nothing: one step out.
            call('mark','set',mark,mark+(' +1c' if mode=='forward' else ' -1c'))
            return True
        lo=max(b for b in bounds if b<pos);hi=min(b for b in bounds if b>pos)
        if mode=='forward' or (mode=='near' and hi-pos<pos-lo):target=hi
        else:target=lo
        for _ in range(2*abs(target-pos)+2):
            now=_units(str(call('get',anchor,mark)))
            if now==target:break
            call('mark','set',mark,mark+(' +1c' if now<target else ' -1c'))
        return True
    finally:
        call('mark','unset',anchor)
