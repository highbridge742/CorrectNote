"""Align visible logical rows without changing either document's text."""

_PREFIX = 'paired_row_pad_'


def align_rows(left, right, enabled=True, partners=None):
    panes=(left,right)
    signature=tuple(tuple(str(w.cget(k)) for k in
        ('font','wrap','spacing1','spacing2','spacing3'))+(w.winfo_width(),)
        for w in panes)+(bool(enabled),)
    changed=False
    for w in panes:
        if getattr(w,'_paired_row_signature',None)!=signature:
            for tag in w.tag_names():
                if tag.startswith(_PREFIX):w.tag_remove(tag,'1.0','end')
            w._paired_row_signature=signature
            changed=True
    if not enabled or any(w.winfo_width()<=1 for w in panes):
        return changed
    left_rows=_visible_rows(left);right_rows=_visible_rows(right)
    if partners is None:
        first=min(left_rows[0],right_rows[0]);last=max(left_rows[1],right_rows[1])
        pairs=[(row,row) for row in range(first,last+1)]
        lonely=[]
    else:
        # The correction pane can lag behind an edit: pair rows by the
        # source text they show, and pad neither side of a row whose partner
        # is not there yet. Pairing by number padded the memo's new rows to
        # the height of unrelated corrected rows until the next result.
        pairs=[];paired_right=set()
        for row in range(left_rows[0],left_rows[1]+1):
            partner=partners(row)
            if partner is not None and 0<partner:
                pairs.append((row,partner));paired_right.add(partner)
            else:pairs.append((row,None))
        lonely=[row for row in range(right_rows[0],right_rows[1]+1)
                if row not in paired_right]
    ends=[int(w.index('end-1c').split('.')[0]) for w in panes]
    for row,partner in pairs:
        if row>ends[0]-1 or (partner is not None and partner>ends[1]-1):
            continue
        if partner is None:
            changed=_set_padding(left,row,0) or changed
            continue
        heights=[_natural_height(left,row),_natural_height(right,partner)]
        height=max(heights)
        changed=_set_padding(left,row,height-heights[0]) or changed
        changed=_set_padding(right,partner,height-heights[1]) or changed
    for row in lonely:
        if row<=ends[1]-1:changed=_set_padding(right,row,0) or changed
    return changed


def _visible_rows(w):
    first=int(w.index('@0,0').split('.')[0])
    last=int(w.index(f'@0,{w.winfo_height()-1}').split('.')[0])+1
    return first,last


def _padding_tags(w,row):
    return [tag for tag in w.tag_names(f'{row}.0') if tag.startswith(_PREFIX)]


def _natural_height(w,row):
    tags=_padding_tags(w,row)
    padding=int(tags[-1][len(_PREFIX):]) if tags else 0
    total=w.count(f'{row}.0',f'{row+1}.0','update','ypixels')
    pixels=total[0] if isinstance(total,tuple) else (total or 0)
    return pixels-padding


def _set_padding(w,row,padding):
    start,end=f'{row}.0',f'{row+1}.0'
    tags=_padding_tags(w,row)
    previous=int(tags[-1][len(_PREFIX):]) if tags else 0
    if padding==previous and len(tags)<=1:return False
    for tag in tags:w.tag_remove(tag,start,end)
    if padding:
        name=_PREFIX+str(padding)
        w.tag_configure(name,spacing3=int(w.cget('spacing3'))+padding)
        w.tag_add(name,start,end)
    return True


def strip_inserted_rows(widget,start,text):
    """Rows an Enter creates start without the split row's padding.

    Tk gives inserted characters the tags on both sides, so a newline typed
    inside a padded row padded both halves until the next alignment: the
    rows below dropped by the padding and then rose again."""
    newlines=text.count('\n')
    if not newlines:return
    row,column=(int(part) for part in str(start).split('.'))
    first=row+1 if column else row
    for tag in widget.tag_names():
        if tag.startswith(_PREFIX):
            widget.tag_remove(tag,f'{first}.0',f'{first+newlines}.0')
