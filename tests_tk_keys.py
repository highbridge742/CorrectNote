# -*- coding: utf-8 -*-
"""Deliver installed key scripts to withdrawn Tk test windows without OS focus.

The scripts and bindtag order are unchanged. Only delivery uses a test-only
virtual event because Tk does not focus a withdrawn window for physical keys.
"""
def deliver_key(widget,sequence,keysym,keycode,state=0,event_type=2,char=''):
    from tkinter import _stringify
    virtual='<<CorrectNoteTestKey>>'
    tk=widget.tk;saved=[]
    try:
        for tag in widget.bindtags():
            previous=tk.call('bind',tag,virtual);saved.append((tag,previous))
            script=tk.call('bind',tag,sequence)
            if script:
                for field,value in (('%K',keysym),('%k',str(keycode)),('%A',_stringify(char)),
                                    ('%s',str(state)),('%T',str(event_type))):
                    script=script.replace(field,value)
            tk.call('bind',tag,virtual,script)
        widget.event_generate(virtual)
    finally:
        for tag,script in saved:tk.call('bind',tag,virtual,script)


def release_tk_fixture(owner, *attributes):
    """Drop destroyed test widgets and cycles while still on their UI thread."""
    import gc
    import threading
    import weakref
    if threading.current_thread() is not threading.main_thread():
        raise AssertionError('Tk fixture release must run on its creating thread')
    root_ref=weakref.ref(owner.root) if getattr(owner,'root',None) is not None else None
    for name in attributes:
        setattr(owner,name,None)
    gc.collect()
    if root_ref is not None and root_ref() is not None:
        raise AssertionError('Destroyed Tk root is still retained by the fixture')
