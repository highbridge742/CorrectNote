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
        if now>=deadline:
            self.notified.add(row)
            self._schedule()
            return 'pending'
        return None

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
        self.job=self.job_deadline=self.ticket=None
        if scope!=self.current_scope():
            self.deadlines.clear()
            self.notified.clear()
            self.scope=None
            return
        now=self.clock()
        # Expired offscreen rows are notified too, so they cannot create an
        # idle timer loop. Scrolling them back will evaluate their actual state.
        self.notified.update(row for row,value in self.deadlines.items() if value<=now)
        self.redraw()
        self._schedule()
