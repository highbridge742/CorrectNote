# -*- coding: utf-8 -*-
"""Transient IME commit ranges proven by actual edits, never cursor guesses."""
from collections import deque
from dataclasses import dataclass,field

@dataclass(eq=False)
class _Composition:
    owner:object
    span:object=None
    results:list=field(default_factory=list)
    valid:bool=True

class CommitRanges:
    def __init__(self):
        self.owner=None;self.current=None;self.pending=deque(maxlen=64)

    def set_owner(self,owner):
        if owner!=self.owner:
            self.clear();self.owner=owner

    def clear(self):
        self.current=None;self.pending.clear()

    def begin(self):
        if self.owner is None:return
        self.current=_Composition(self.owner);self.pending.append(self.current)

    def finish(self):
        self.current=None

    def result(self,surface,reading):
        # Missing START is still a valid saved pair, but supplies no range.
        if self.current is not None and surface and reading:
            if len(self.current.results)>=64:self.current.valid=False
            else:self.current.results.append((surface,reading))

    def edited(self,owner,edit,inserted,discard=False):
        if owner!=self.owner:return
        if discard or edit is None or inserted is None:
            for group in self.pending:group.valid=False
            return
        lo,old=edit;start,new=inserted
        if lo!=start or old<lo or new<lo:
            for group in self.pending:group.valid=False
            return
        for group in self.pending:
            if not group.valid:continue
            span=group.span
            if group is self.current:
                if span is None:
                    if new>lo:group.span=(lo,new)
                elif span[0]<=lo<=old<=span[1]:
                    group.span=(span[0],span[1]+new-old)
                else:group.valid=False
            elif span is not None:
                if span[1]<=lo:continue
                if span[0]>=old:group.span=(span[0]+new-old,span[1]+new-old)
                else:group.valid=False

    def take(self,owner,text):
        """Match all partial results to the observed range as one sequence."""
        out=[];retained=deque(maxlen=64)
        for group in self.pending:
            if group.valid and group.owner==owner and group.span and group.results:
                lo,hi=group.span
                joined=''.join(face for face,reading in group.results)
                if 0<=lo<hi<=len(text) and text[lo:hi]==joined:
                    at=lo
                    for surface,reading in group.results:
                        out.append((at,at+len(surface),surface,reading));at+=len(surface)
                    group.span=None;group.results.clear()
            if group is self.current:retained.append(group)
        self.pending=retained
        return tuple(out)
