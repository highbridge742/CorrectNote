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


def session_calculations(app,text):
    """Save current explicit formula ranges alongside their tab, not shared caches."""
    doc=getattr(app,'_input_document',None)
    if doc is None or doc.owner!=owner(app):return []
    return [dict(start=x.start,end=x.end,surface=x.surface) for x in doc.calculations
            if 0<=x.start<x.end<=len(text) and text[x.start:x.end]==x.surface]


def restore_session_calculations(app):
    """Restore every tab before prefetch can analyze its plain source text."""
    from quote_calculator import clean_calculations,calculate
    registry={}
    for tab in app.session.tabs:
        text=tab.get('text','')
        records=clean_calculations(text,tab.get('calculations'))
        if not records:continue
        doc=Document(owner_for_tab(app,tab),text)
        for record in records:
            doc.remember_calculation(record['start'],record['end'],record['surface'],
                                     calculate(record['surface']))
        registry[doc.owner]=doc
    app._input_documents=registry


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
    events=getattr(app,'_ime_result_events',None)
    if events is not None:
        events.ranges.clear();events.ranges.set_owner(active)


def _observe_ime_edit(app, edit, inserted, discard):
    """Keep only the live insertion span for the current IME composition.

    Tk may deliver a committed string one character at a time. Contiguous
    edits within this span can extend it; unrelated edits or undo invalidate
    it until the next composition. No previous text or edit log is kept.
    """
    origin=getattr(app,'_ime_origin_work',None)
    previous,span=getattr(app,'_ime_inserted_range',(None,None))
    if not origin or origin[0]!=owner(app):
        app._ime_inserted_range=(None,None)
        return
    if discard or edit is None or inserted is None:
        span=None
    elif previous!=origin:
        span=inserted
    elif span is not None and span[0]<=edit[0]<=edit[1]<=span[1]:
        span=(span[0],span[1]+inserted[1]-edit[1])
    else:
        span=None
    app._ime_inserted_range=(origin,span)


def install(app):
    def edited(text,discard,edit):
        if getattr(app,'_navigation_padding_active',False):app._clear_navigation_padding()
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
        cancel_ime=discard or bool(getattr(app.editor,'_correctnote_replay_depth',0))
        _observe_ime_edit(app,edit,inserted,cancel_ime)
        # Only the current edit's row and generation; no text/history is kept.
        # A tab switch or a later edit invalidates this priority automatically.
        app._priority_input_row=(token(app),source.count('\n',0,edit[0])) if edit else None
        if doc is None or doc.owner!=owner(app):
            app._input_document=Document(owner(app),source)
        else:
            if not discard:
                import ui_projection
                ui_projection.rebase(app,doc.text,source,edit)
            doc.update(source,discard_readings=discard,edited=True,edit=edit)
        registry=getattr(app,'_input_documents',{})
        registry[owner(app)]=app._input_document
        app._input_documents=registry
        events=getattr(app,'_ime_result_events',None)
        if events is not None:events.ranges.edited(owner(app),edit,inserted,cancel_ime)
    prepare=getattr(app,'_prepare_pick_calculation_edit',None)
    from bookmark_tracking import during_edit
    observe_text(app.editor,edited,on_before_edit=(
        lambda args:prepare(app.editor,args)) if prepare is not None else None,
        track_change=lambda:during_edit(app))


def edited_first(app,todo):
    priority=getattr(app,'_priority_input_row',None)
    if priority is None or priority[0]!=token(app) or priority[1] not in todo:
        return todo,False
    row=priority[1]
    return [row]+[i for i in todo if i!=row],True


def has_readings(app):
    doc=getattr(app,'_input_document',None)
    return bool(doc and doc.owner==owner(app) and doc.occurrences)


def has_local_evidence(app):
    doc=getattr(app,'_input_document',None)
    return bool(doc and doc.owner==owner(app) and (doc.occurrences or doc.calculations))


def line_calculations(app,index,lines):
    doc=getattr(app,'_input_document',None)
    if doc is None or doc.owner!=owner(app):return ()
    return doc.row_calculations(index,lines[index])


def quick_document(app,text):
    doc=getattr(app,'_quick_calculation_document',None)
    widget=getattr(app,'_quick_text',None)
    if doc is None or doc.owner is not widget:
        doc=Document(widget,text);app._quick_calculation_document=doc
    else:
        if doc.text!=text:
            from quick_row_reuse import invalidate
            invalidate(app,doc.text,text)
        doc.update(text)
    return doc


def quick_edited(app,text,discard,edit):
    doc=getattr(app,'_quick_calculation_document',None)
    widget=getattr(app,'_quick_text',None)
    if doc is not None and doc.owner is widget:
        from quick_row_reuse import invalidate
        invalidate(app,doc.text,text,discard,edit)
        inserted=(edit[0],edit[1]+len(text)-len(doc.text)) if edit and not discard else None
        cancel=discard or bool(getattr(widget,'_correctnote_replay_depth',0))
        events=getattr(app,'_quick_ime_result_events',None)
        if events is not None:events.ranges.edited(widget,edit,inserted,cancel)
        doc.update(text,discard_readings=discard,edited=True,edit=edit)


def start_quick_readings(app):
    """Native callbacks own only this quick widget's volatile commit ranges."""
    close_quick_readings(app)
    widget=app._quick_text
    doc=quick_document(app,widget.get('1.0','end-1c'))
    from ime_events import ResultEvents
    events=ResultEvents(widget.winfo_id())
    events.ranges.set_owner(doc.owner)
    app._quick_ime_result_events=events


def drain_quick_readings(app):
    events=getattr(app,'_quick_ime_result_events',None)
    if events is None:return False
    events.take()  # Unpositioned pairs never become global reading evidence.
    doc=getattr(app,'_quick_calculation_document',None)
    widget=getattr(app,'_quick_text',None)
    if widget is None or doc is None or doc.owner is not widget:return False
    changed=False
    for start,end,surface,reading in events.ranges.take(widget,doc.text):
        changed=doc.remember(start,end,surface,reading) or changed
    return changed


def close_quick_readings(app):
    events=getattr(app,'_quick_ime_result_events',None)
    if events is not None:events.close()
    app._quick_ime_result_events=None
    app._quick_calculation_document=None


def _calculation_document(app,quick=False):
    if quick:
        doc=quick_document(app,app._quick_text.get('1.0','end-1c'))
    else:
        source=app.editor_source_text()
        doc=getattr(app,'_input_document',None)
        if doc is None or doc.owner!=owner(app):
            select_document(app,source);doc=app._input_document
        else:doc.update(source)
    return doc


def calculation_expression(app,start,end,quick=False):
    doc=_calculation_document(app,quick)
    from quote_calculator import continued_expression
    return continued_expression(doc.text,doc.calculations,start,end)


def remember_calculation(app,start,end,surface,result,quick=False):
    doc=_calculation_document(app,quick)
    if not doc.remember_calculation(start,end,surface,result):return False
    if not quick:app._work_epoch=getattr(app,'_work_epoch',0)+1
    return True


def remember(app,surface,reading,since=None):
    """Bind only a just-observed IME result that actually ends at the cursor."""
    doc=getattr(app,'_input_document',None)
    if doc is None or doc.owner!=owner(app):return False
    shown=app.editor.get('1.0','insert')
    end=len(shown)
    if hasattr(app,'editor_source_text'):
        source=app.editor_source_text().split('\n')
        row=shown.count('\n');col=len(shown.rsplit('\n',1)[-1])
        from text_positions import map_column
        current=app.editor.get(f'{row+1}.0',f'{row+1}.end')
        if row<len(source):end=sum(len(line)+1 for line in source[:row])+map_column(current,source[row],col)
    if since is not None:
        origin,span=getattr(app,'_ime_inserted_range',(None,None))
        if origin!=since or getattr(app,'_ime_origin_work',None)!=since or span is None:
            return False
        # Every character must belong to this composition's actual mutations,
        # never an older identical spelling next to the insertion point.
        if not span[0]<=end-len(surface)<end<=span[1]:return False
    if not doc.remember(end-len(surface),end,surface,reading):return False
    app._work_epoch=getattr(app,'_work_epoch',0)+1
    return True


def line_readings(app,index,lines):
    doc=getattr(app,'_input_document',None)
    if doc is None or doc.owner!=owner(app):return ()
    return doc.row_readings(index,lines[index])


def background_valid(app,state):
    from tab_analysis import background_compatible
    # The active editor's generation is unrelated to another document.
    # Hand an opened background document to foreground work instead.
    return state.get('owner')!=owner(app) and background_compatible(app,state)
