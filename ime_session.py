# -*- coding: utf-8 -*-
"""Lazily retain read-only IME resources for one correction on one thread."""
from contextlib import contextmanager
from contextvars import ContextVar
from threading import get_ident
from time import monotonic

_CURRENT=ContextVar('correctnote_ime_resources',default=None)

# Answers of the read-only native interfaces kept while one line is typed
# (2026-10-17, speed). Each correction still owns its scope and its own
# per-correction caches; this store only lets the next correction of the same
# line (the text grown or edited in place) reuse what the native interface
# answered for text that is still there. Outside the analysis worker nothing
# is kept: a scope that was never enabled observes the native interface again.
#
# The native IME learns from the user's commits, so a stored forward answer
# (first conversion, forward words, candidate list) of a reading can go stale
# only after the user commits that reading again with another candidate. That
# commit writes new text into the line, and the fresh inverse reading of that
# new text names the reading: forget_readings drops those forward answers so
# they are asked again. Learning in another application while this line stays
# open is bounded by LINE_IDLE.
LINE_ANSWERS_MAX=2048   # entries per line before the line's store starts over
LINE_STORES_MAX=4       # recently typed lines kept apart (background rows interleave)
LINE_IDLE=120.0         # seconds without a correction before a line's answers expire
_LINE_STORES=None       # None: disabled


class LineAnswers:
    def __init__(self,line):
        self.line=line;self.answers={};self.used=monotonic()

    def get(self,key,default=None):
        return self.answers.get(key,default)

    def put(self,key,value):
        if len(self.answers)>=LINE_ANSWERS_MAX:self.answers.clear()
        self.answers[key]=value

    def forget(self,keys):
        for key in keys:self.answers.pop(key,None)


def _same_typing(old,new):
    """The new line is the old one typed further or edited in place."""
    if old==new:return True
    shorter=min(len(old),len(new))
    prefix=0
    while prefix<shorter and old[prefix]==new[prefix]:prefix+=1
    suffix=0
    while suffix<shorter-prefix and old[-1-suffix]==new[-1-suffix]:suffix+=1
    return prefix+suffix>=max(1,shorter//2)


def _current_line():
    try:
        from analysis_work import _INPUT
    except ImportError:return None
    active=_INPUT.get()
    return active[0] if active else None


def line_answers():
    """The store of the line now being corrected, or None when nothing is kept."""
    stores=_LINE_STORES
    if stores is None:return None
    line=_current_line()
    if not line:return None
    now=monotonic()
    stores[:]=[store for store in stores if now-store.used<=LINE_IDLE]
    for index,store in enumerate(stores):
        if _same_typing(store.line,line):
            store.line=line;store.used=now
            stores.append(stores.pop(index))
            return store
    store=LineAnswers(line);stores.append(store)
    del stores[:-LINE_STORES_MAX]
    return store


def forget_readings(readings):
    """Newly written text was read back: its readings' forward answers are asked again."""
    stores=_LINE_STORES
    if not stores:return
    keys=[]
    for reading in set(readings):
        if reading:keys.extend((('text',8,reading),('morph',0x00010000,reading),('candidates',reading)))
    for store in stores:store.forget(keys)


@contextmanager
def line_answers_scope():
    """Keep native answers per typed line while this scope lasts (the worker's life)."""
    global _LINE_STORES
    previous=_LINE_STORES;_LINE_STORES=[]
    try:yield
    finally:_LINE_STORES=previous


def retain(resource):
    scope=_CURRENT.get()
    if scope is None or scope[0]!=get_ident():return resource,False
    resources=scope[1]
    return resources.setdefault(type(resource),resource),True


def cleanup(actions):
    """Try every owned cleanup even if one optional native interface fails."""
    error=None
    for action in actions:
        try:action()
        except Exception as exc:
            if error is None:error=repr(exc)
    return error


@contextmanager
def resource_scope():
    scope=_CURRENT.get()
    if scope is not None and scope[0]==get_ident():
        yield
        return
    resources={};token=_CURRENT.set((get_ident(),resources))
    try:yield
    finally:
        _CURRENT.reset(token)
        try:cleanup([resource.close for resource in reversed(tuple(resources.values()))])
        finally:resources.clear()
