# -*- coding: utf-8 -*-
"""Short, cancellable pixel scrolling; no document edits or recurring idle work."""
import math
import time


# Keep wheel travel unchanged, spreading it over a longer glide.
_WHEEL_DECAY_SECONDS = .12


class ScrollInertia:
    def __init__(self, root, scroll, owner, clock=time.monotonic):
        self.root, self.scroll, self.owner, self.clock = root, scroll, owner, clock
        self.job = None
        self.ticket = None
        self.scope = None
        self.remaining = 0.
        self.fraction = 0.
        self.last = None
        self.kind = None
        self.samples = []
        self.closed = False

    def cancel(self, event=None):
        if self.job is not None:
            self.root.after_cancel(self.job)
        self.job = self.ticket = None
        self.remaining = self.fraction = 0.
        self.last = self.scope = self.kind = None
        self.samples = []

    def close(self):
        self.cancel(); self.closed = True

    def wheel(self, pixels):
        if self.closed or not math.isfinite(pixels) or not pixels:
            return
        owner = self.owner()
        if self.kind != 'wheel' or owner is not self.scope or self.remaining * pixels < 0:
            self.cancel()
        self.kind = 'wheel'; self.scope = owner
        self.remaining += pixels
        self.last = self.clock() if self.last is None else self.last
        self._schedule()

    def sample_drag(self, pixels):
        now = self.clock()
        self.samples = [(at, delta) for at, delta in self.samples if now-at <= .10]
        if self.samples and pixels * self.samples[-1][1] < 0:
            self.samples = []
        self.samples.append((now, pixels))

    def release_drag(self):
        now = self.clock()
        samples = [(at, delta) for at, delta in self.samples if now-at <= .10]
        self.samples = []
        if self.closed or len(samples) < 2 or now-samples[-1][0] > .07:
            return
        elapsed = samples[-1][0]-samples[0][0]
        if elapsed <= .008:
            return
        # Ignore the first sample's distance: its preceding interval is unknown.
        velocity = sum(delta for _, delta in samples[1:])/elapsed
        velocity = max(-5000., min(5000., velocity))
        if abs(velocity) < 70:
            return
        self.cancel()
        self.kind = 'drag'; self.scope = self.owner(); self.last = now
        self.remaining = velocity * .12
        self._schedule()

    def _schedule(self):
        if self.job is None and not self.closed:
            ticket = self.ticket = object()
            self.job = self.root.after(12, lambda: self._tick(ticket))

    def _tick(self, ticket):
        if self.closed or ticket is not self.ticket:
            return
        self.job = self.ticket = None
        if self.scope is not self.owner():
            self.cancel(); return
        now = self.clock()
        elapsed = max(0., now-self.last); self.last = now
        decay = _WHEEL_DECAY_SECONDS if self.kind == 'wheel' else .12
        if abs(self.remaining) < .6 or elapsed > .2:
            step, self.remaining = self.remaining, 0.
        else:
            step = self.remaining * (1-math.exp(-elapsed/decay))
            self.remaining -= step
        self.fraction += step
        pixels = int(self.fraction)
        if not self.remaining:
            pixels = round(self.fraction)
        self.fraction -= pixels
        if pixels and self.scroll(pixels) is False:
            self.cancel(); return
        if self.remaining:
            self._schedule()
        else:
            self.cancel()


def install(app):
    """Cancel before keys/presses even when a widget binding returns break."""
    controller = ScrollInertia(app.root, app._scroll_pixels,
        lambda:app.session.current() if getattr(app,'session',None) is not None else None)
    app._scroll_inertia = controller
    tag = 'CorrectNoteScrollStop_'+str(id(controller))
    root = app.root
    commands = []
    for event in ('<KeyPress>', '<ButtonPress-1>', '<ButtonPress-2>', '<ButtonPress-3>', '<FocusOut>'):
        commands.append(root.bind_class(tag, event, controller.cancel))
    # Tkinter's class binding commands belong to root for teardown.
    if root._tclCommands is None:root._tclCommands=[]
    root._tclCommands.extend(command for command in commands if command not in root._tclCommands)
    for widget in (app.editor, app.result_view, app.editor_gutter, app.result_gutter):
        widget.bindtags((tag,)+widget.bindtags())
    root.bind('<ButtonPress-1>', controller.cancel, add=True)
    return controller
