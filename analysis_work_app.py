# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Tk integration for volatile work identity. Persistent caches stay value caches."""
from analysis_work import Document,observe_text
from contextlib import contextmanager


def owner_for_tab(app,tab):
    registry=getattr(app,'_work_tab_owners',{})
    present={id(item) for item in app.session.tabs}
    registry={key:value for key,value in registry.items() if key in present}
    key=id(tab)
    if key not in registry:
        number=getattr(app,'_work_next_tab',0)+1
        app._work_next_tab=number
        # The reference prevents Python object-id reuse until closed tabs are
        # removed; the opaque lifecycle number never reuses an old work owner.
        registry[key]=(tab,number)
    app._work_tab_owners=registry
    return ('tab',registry[key][1])


def owner(app):
    try:return owner_for_tab(app,app.session.tabs[app.session.active])
    except (AttributeError,IndexError):return id(app)


def token(app):
    return (owner(app),getattr(app,'_work_epoch',0))


@contextmanager
def display_update(app):
    """Change the projection without creating a new input generation."""
    widget=app.editor
    depth=getattr(widget,'_correctnote_display_depth',0)
    widget._correctnote_display_depth=depth+1
    try:yield
    finally:widget._correctnote_display_depth=depth


def select_document(app,text):
    app._work_epoch=getattr(app,'_work_epoch',0)+1
    registry=getattr(app,'_input_documents',{})
    active=owner(app)
    present={owner_for_tab(app,tab) for tab in app.session.tabs}
    registry={key:value for key,value in registry.items() if key in present}
    doc=registry.get(active)
    if doc is None:doc=Document(active,text)
    else:doc.update(text)
    registry[active]=doc
    app._input_documents=registry;app._input_document=doc


def install(app):
    def edited(text,discard,edit):
        app._work_epoch=getattr(app,'_work_epoch',0)+1
        doc=getattr(app,'_input_document',None)
        source=app.editor_source_text() if hasattr(app,'editor_source_text') else text
        # Derived rows can have different lengths. Their widget offsets must
        # not be treated as offsets in the canonical input document.
        if source!=text:edit=None
        if edit is None and not discard and doc is not None:
            lo=0
            while lo<min(len(doc.text),len(source)) and doc.text[lo]==source[lo]:lo+=1
            old,new=len(doc.text),len(source)
            while old>lo and new>lo and doc.text[old-1]==source[new-1]:old-=1;new-=1
            edit=(lo,old)
        inserted=(edit[0],edit[1]+len(source)-len(doc.text)) if (
            edit and not discard and doc is not None and doc.owner==owner(app)) else None
        app._input_last_edit=(token(app),inserted)
        if doc is None or doc.owner!=owner(app):
            app._input_document=Document(owner(app),source)
        else:
            doc.update(source,discard_readings=discard,edited=True,edit=edit)
        registry=getattr(app,'_input_documents',{})
        registry[owner(app)]=app._input_document
        app._input_documents=registry
    observe_text(app.editor,edited)


def has_readings(app):
    doc=getattr(app,'_input_document',None)
    return bool(doc and doc.owner==owner(app) and doc.occurrences)


def remember(app,surface,reading,since=None):
    """Bind only a just-observed IME result that actually ends at the cursor."""
    doc=getattr(app,'_input_document',None)
    if doc is None or doc.owner!=owner(app):return False
    shown=app.editor.get('1.0','insert')
    end=len(shown)
    if hasattr(app,'editor_source_text'):
        source=app.editor_source_text().split('\n')
        row=shown.count('\n');col=len(shown.rsplit('\n',1)[-1])
        from app import map_column
        current=app.editor.get(f'{row+1}.0',f'{row+1}.end')
        if row<len(source):end=sum(len(line)+1 for line in source[:row])+map_column(current,source[row],col)
    if since is not None:
        work,edit=getattr(app,'_input_last_edit',(None,None))
        if not work or work[0]!=since[0] or work[1]<=since[1] or not edit:return False
        # The actual input mutation must contain this result, not just an older
        # identical spelling beside the cursor. Partial/unmatched events remain
        # ordinary saved pairs and are never upgraded to occurrence evidence.
        if not edit[0]<=end-len(surface)<end<=edit[1]:return False
    if not doc.remember(end-len(surface),end,surface,reading):return False
    app._work_epoch=getattr(app,'_work_epoch',0)+1
    return True


def line_readings(app,index,lines):
    doc=getattr(app,'_input_document',None)
    if doc is None or doc.owner!=owner(app):return ()
    return doc.row_readings(index,lines[index])


def background_valid(app,state):
    from tab_analysis import background_compatible
    return (state.get('work_epoch')==getattr(app,'_work_epoch',0)
            and background_compatible(app,state))
