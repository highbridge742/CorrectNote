# -*- coding: utf-8 -*-
"""Keep current bookmark rows attached to a real Text edit, not an analysis diff."""
from contextlib import contextmanager
from tkinter import TclError


@contextmanager
def during_edit(app):
    bookmarks=getattr(app,'bookmarks',None)
    if not bookmarks or getattr(app,'_bookmark_tracking_active',False):
        yield None
        return
    widget=app.editor;names=[]
    app._bookmark_tracking_active=True
    try:
        for i,row in enumerate(sorted(bookmarks)):
            name='_correctnote_bookmark_'+str(i)
            widget.mark_set(name,str(row)+'.0')
            widget.mark_gravity(name,'right')
            names.append(name)
        def commit():
            last=int(widget.index('end-1c').split('.')[0])
            rows={min(last,int(widget.index(name).split('.')[0])) for name in names}
            if rows==bookmarks:return
            bookmarks.clear();bookmarks.update(rows)
            app.editor_gutter.redraw();app.result_gutter.redraw()
            app._schedule_session_save()
        yield commit
    finally:
        try:
            if names:widget.mark_unset(*names)
        except TclError:
            pass
        app._bookmark_tracking_active=False
