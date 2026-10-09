# -*- coding: utf-8 -*-
"""Keep current bookmark rows attached to a real Text edit, not an analysis diff."""
from contextlib import contextmanager
from tkinter import TclError


@contextmanager
def during_edit(app):
    bookmarks=getattr(app,'bookmarks',None)
    guides=getattr(app,'_editor_guides',None)
    rulers=guides.ruler_rows() if guides is not None else set()
    if not (bookmarks or rulers) or getattr(app,'_bookmark_tracking_active',False):
        yield None
        return
    widget=app.editor;names=[]
    app._bookmark_tracking_active=True
    try:
        groups=[]
        for kind,source in (('bookmark',bookmarks or set()),('ruler',rulers)):
            anchors=[]
            for i,row in enumerate(sorted(source)):
                name='_correctnote_'+kind+'_'+str(i)
                widget.mark_set(name,str(row)+'.0')
                widget.mark_gravity(name,'right')
                names.append(name);anchors.append(name)
            groups.append((kind,source,anchors))
        def commit():
            last=int(widget.index('end-1c').split('.')[0])
            changed=False
            for kind,source,anchors in groups:
                rows={min(last,int(widget.index(name).split('.')[0])) for name in anchors}
                if rows==source:continue
                if kind=='bookmark':
                    bookmarks.clear();bookmarks.update(rows)
                    app.editor_gutter.redraw();app.result_gutter.redraw()
                else:guides.set_ruler_rows(rows,notify=False)
                changed=True
            if changed:app._schedule_session_save()
        yield commit
    finally:
        try:
            if names:widget.mark_unset(*names)
        except TclError:
            pass
        app._bookmark_tracking_active=False
