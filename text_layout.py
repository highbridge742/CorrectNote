"""Align visible logical rows without changing either document's text."""

_PREFIX = 'paired_row_pad_'


def align_rows(left, right, enabled=True):
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
    first=min(int(w.index('@0,0').split('.')[0]) for w in panes)
    last=min(min(int(w.index('end-1c').split('.')[0]) for w in panes)-1,
        max(int(w.index(f'@0,{w.winfo_height()-1}').split('.')[0]) for w in panes)+1)
    for row in range(first,last+1):
        start,end=f'{row}.0',f'{row+1}.0'
        heights=[];old=[]
        for w in panes:
            tags=[tag for tag in w.tag_names(start) if tag.startswith(_PREFIX)]
            padding=int(tags[-1][len(_PREFIX):]) if tags else 0
            total=w.count(start,end,'update','ypixels')
            pixels=total[0] if isinstance(total,tuple) else (total or 0)
            heights.append(pixels-padding)
            old.append((padding,tags))
        height=max(heights)
        for w,natural,(previous,tags) in zip(panes,heights,old):
            padding=height-natural
            if padding==previous:continue
            for tag in tags:w.tag_remove(tag,start,end)
            if padding:
                name=_PREFIX+str(padding)
                w.tag_configure(name,spacing3=int(w.cget('spacing3'))+padding)
                w.tag_add(name,start,end)
            changed=True
    return changed
