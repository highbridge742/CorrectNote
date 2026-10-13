"""Brief pending row states stay invisible; analysis itself is unchanged."""
import math
import time


class PendingRowDisplay:
    def __init__(self, root, redraw, current_scope, delay=.3, clock=time.monotonic):
        self.root=root
        self.redraw=redraw
        self.current_scope=current_scope
        self.delay=delay
        self.clock=clock
        self.scope=None
        self.deadlines={}
        self.notified=set()
        self.job=None
        self.job_deadline=None
        self.ticket=None
        self.catch_up=None
        self.closed=False

    def _cancel(self):
        if self.job is not None:
            self.root.after_cancel(self.job)
        self.job=self.job_deadline=self.ticket=None

    def _clear(self):
        self._cancel()
        self.deadlines.clear()
        self.notified.clear()

    def close(self):
        self.closed=True
        if self.catch_up is not None:
            try:self.root.after_cancel(self.catch_up)
            except Exception:pass
            self.catch_up=None
        self._clear()
        self.scope=None

    def state(self, scope, row, state):
        if self.closed:return None
        if scope!=self.scope:
            self._clear()
            self.scope=scope
        if state!='pending':
            if row in self.deadlines:
                del self.deadlines[row]
                self.notified.discard(row)
                self._schedule()
            return state
        now=self.clock()
        if row not in self.deadlines:
            self.deadlines[row]=now+self.delay
            self._schedule()
        deadline=self.deadlines[row]
        if row in self.notified:
            return 'pending'
        if now>=deadline:
            self.notified.add(row)
            self._schedule()
            # The row became due in the middle of a paint: a pane painted a
            # moment earlier showed it without the mark. Paint all panes again
            # (CI 2026-10-14: the memo gutter missed the mark for good).
            self._repaint_soon()
            return 'pending'
        return None

    def _repaint_soon(self):
        if self.catch_up is not None:return
        try:self.catch_up=self.root.after_idle(self._catch_up)
        except Exception:self.catch_up=None

    def _catch_up(self):
        self.catch_up=None
        if not self.closed:self.redraw()

    def _schedule(self):
        now=self.clock()
        # A deadline may pass while the previous frame is being painted. Keep
        # that wakeup until a repaint has actually been requested for it.
        waiting=[value for row,value in self.deadlines.items() if row not in self.notified]
        deadline=min(waiting) if waiting else None
        if deadline==self.job_deadline:return
        self._cancel()
        if deadline is None:return
        ticket=object()
        scope=self.scope
        self.ticket=ticket
        self.job_deadline=deadline
        self.job=self.root.after(max(1,math.ceil((deadline-now)*1000)),
                                 lambda:self._ready(ticket,scope))

    def _ready(self,ticket,scope):
        if self.closed or ticket is not self.ticket:return
        # Windows timers may fire a few milliseconds before the deadline; the
        # timer firing is the deadline. Otherwise the first pane painted below
        # still sees the row as not yet due and the next one as due.
        fired=self.job_deadline
        self.job=self.job_deadline=self.ticket=None
        if scope!=self.current_scope():
            self.deadlines.clear()
            self.notified.clear()
            self.scope=None
            return
        now=max(self.clock(),fired or 0)
        # Expired offscreen rows are notified too, so they cannot create an
        # idle timer loop. Scrolling them back will evaluate their actual state.
        self.notified.update(row for row,value in self.deadlines.items() if value<=now)
        self.redraw()
        self._schedule()
