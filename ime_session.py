# -*- coding: utf-8 -*-
"""Lazily retain read-only IME resources for one correction on one thread."""
from contextlib import contextmanager
from contextvars import ContextVar
from threading import get_ident

_CURRENT=ContextVar('correctnote_ime_resources',default=None)


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
