# -*- coding: utf-8 -*-
"""Volatile evidence of which document-context entries a completed row read."""
from collections.abc import Mapping


class Reads(Mapping):
    def __init__(self, values):
        self._values=values or {}
        self.keys_read=set()
        self.truth=None
        self.whole=False

    def __getitem__(self,key):
        self.keys_read.add(key)
        return self._values[key]

    def __iter__(self):
        self.whole=True
        return iter(self._values)

    def __len__(self):
        self.whole=True
        return len(self._values)

    def __bool__(self):
        self.truth=bool(self._values)
        return self.truth

    def evidence(self,unit_keys=()):
        return dict(version=1,keys=tuple(sorted(self.keys_read)),truth=self.truth,
                    whole=self.whole,unit_keys=tuple(sorted(unit_keys)))


def compatible(result,previous,current,attested):
    """Unknown evidence falls back to ordinary reanalysis, including disk caches."""
    evidence=(result or {}).get('_context_evidence')
    if not isinstance(evidence,dict) or evidence.get('version')!=1:
        return False
    previous=previous or {};current=current or {}
    if evidence.get('whole') and previous!=current:
        return False
    if evidence.get('truth') is not None and bool(current)!=evidence['truth']:
        return False
    missing=object()
    if any(previous.get(key,missing)!=current.get(key,missing)
           for key in evidence.get('keys',())):
        return False
    return all((key in attested)==present for key,present in evidence.get('unit_keys',()))


def completed(value):
    """Attach proof only after receiving a completed worker result."""
    result=value['result']
    evidence=value.get('context_evidence')
    if evidence is not None:
        result=dict(result,_context_evidence=evidence)
    if value.get('ime_evidence') is not None:
        result=dict(result,_ime_evidence=value['ime_evidence'])
    if value.get('input_signature') is not None:
        result=dict(result,_input_signature=value['input_signature'])
    return result


def signature(nearby=(),readings=(),calculations=()):
    return tuple(nearby),tuple(readings),tuple(calculations)


def reuse_rows(results,todo,previous,signatures,old_context,new_context,attested):
    """Reuse only completed values whose semantic inputs still match exactly."""
    from analysis_cache import reusable_result
    available={}
    for row in previous:
        key=(row or {}).get('_input_signature')
        if (key is not None and reusable_result(row)
                and compatible(row,old_context,new_context,attested)):
            available[(row['original'],key)]=row
    remaining=[]
    for index in todo:
        old=available.get((results[index]['original'],signatures[index]))
        if old is None:remaining.append(index)
        else:results[index]=dict(old)
    return remaining


from contextlib import contextmanager
from contextvars import ContextVar
from threading import get_ident

_REQUEST_CHECK=ContextVar('correctnote_request_check',default=None)


class SupersededAnalysis(BaseException):
    """Internal control flow; optional-evidence errors must not swallow it."""


def check_current_request():
    scope=_REQUEST_CHECK.get()
    if scope is not None and scope[0]==get_ident() and scope[1]():
        raise SupersededAnalysis()


@contextmanager
def request_scope(check):
    token=_REQUEST_CHECK.set((get_ident(),check))
    try:yield
    finally:_REQUEST_CHECK.reset(token)
