# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""Visible Ctrl-navigation boundaries, without modifying text or undo."""
import time
import tkinter as tk
import tkinter.font as tkfont
from editor_guides import FLASH_COLOR
from pos_font import (POS_CATEGORIES, POS_FONT_TAGS, POS_COLOR_TAGS,
                      has_adjustments,
                      font_size, normalize_multipliers, current_colors)



def plans(texts, tokenize):
    """Compatibility entry; compute stays in the pure text-navigation module."""
    from text_navigation import plans as navigation_plans
    return navigation_plans(texts,tokenize)


# Rows are bounded so a long document fits (128 rows was evicted by
# background analysis before the correction pane painted). Memory stays
# bounded by characters, the same ceiling as before (about 70 bytes a
# character, so at most about 18MB).
PLAN_CACHE_ROWS = 4096
PLAN_CACHE_CHARS = 262144


def remember(app, values):
    """Bounded volatile presentation values, never a persistent text history."""
    if not values:return
    cache=getattr(app,'_ctrl_boundary_plans',None)
    if not isinstance(cache,dict):cache=app._ctrl_boundary_plans={}
    # Running character total, so a full cache costs no scan per result.
    owner,total=getattr(app,'_ctrl_boundary_chars',(None,0))
    if owner is not cache:total=sum(map(len,cache))
    for text,value in values.items():
        if cache.pop(text,None) is None:total+=len(text)
        cache[text]=value
    while len(cache)>PLAN_CACHE_ROWS or total>PLAN_CACHE_CHARS:
        oldest=next(iter(cache));total-=len(oldest);cache.pop(oldest)
    app._ctrl_boundary_chars=(cache,total)
    for w in (getattr(app,'editor',None),getattr(app,'result_view',None),getattr(app,'_quick_text',None),
              *_doc_window_copies(app)):
        colors=getattr(w,'_correctnote_boundary_colors',None)
        if isinstance(colors,BoundaryColors):colors.data_ready(values)
    for window in getattr(app,'_doc_windows',()):
        try:window.paint_peer()
        except Exception:pass
    queue=getattr(app,'_queue_analysis_gutters',None)
    if queue is not None:queue(values)


def ready_for(app,*texts):
    cache=getattr(app,'_ctrl_boundary_plans',{})
    return isinstance(cache,dict) and all(text in cache for text in texts)


def plan_for(app,widget,row,text):
    cache=getattr(app,'_ctrl_boundary_plans',{})
    value=cache.get(text) if isinstance(cache,dict) else None
    if value is not None:
        # Rows on screen stay the most recently used.
        cache.pop(text);cache[text]=value
    colors=getattr(widget,'_correctnote_boundary_colors',None)
    if value is None and isinstance(colors,BoundaryColors):
        for saved in (colors._painted.get(row),colors._last_plans.get(row)):
            if saved is not None and saved[0]==text and saved[1] is not None:
                value=saved[1];break
    if value is None and widget is getattr(app,'result_view',None):
        # 補正欄の解析待ちの行は、補正の無い同じ字なら、入力欄の同じ行の品詞の大きさ・色をそのまま使う
        # （同じ字の区切りと品詞は同じ。2026-11-01 うにさん「19行目以外が小さかった」——解析が済むまで
        # 元の大きさで出て、解析の済んだ行とそろわなかった）
        editor=getattr(app,'editor',None)
        source=getattr(editor,'_correctnote_boundary_colors',None)
        if isinstance(source,BoundaryColors):
            for saved in (source._painted.get(row),source._last_plans.get(row)):
                if saved is not None and saved[0]==text and saved[1] is not None:
                    value=saved[1];break
    return value


def boundary_marker_spans(text, boundaries):
    """One character immediately before each navigation stop.

    The row's end is not marked: Ctrl+right always stops there and a tick
    after the last character read as a stray mark."""
    return tuple((stop - 1, stop) for stop in boundaries
                 if 0 < stop < len(text))

class BoundaryColors:
    SETTLE_MS = 180
    # Rows that scroll into view get their marks once the view has settled.
    SCROLL_SETTLE_MS = 120
    # The stop is shown as a thin underline under the character before it,
    # a tag inside the Text. The earlier ┻ marks were child windows over the
    # Text; on Windows any mapped child made moving between rows about 20
    # times and scrolling about 10 times slower (tools_local/v114_mark_speed,
    # 2026-10-12), so typing and conversion lagged with the marks on.
    TICK_TAG = 'ctrl_boundary_tick'

    def __init__(self, app, widget):
        from analysis_work import observe_text
        self.app=app;self.widget=widget;self._job=None;self._rows=[]
        self._draw_job=None;self.lines={};self._marker_indices={}
        self._painted={};self._last_plans={};self._closed=False
        self._font_signature=None;self._color_signature=None
        self._painted_styles=self._sized_majors()
        self._painted_colors=self._colored_majors()
        self._view_job=None;self._scroll_job=None;self._drawn_view=None
        self._plans_job=None;self._plans_failed=set();self._plans_scope=None;self._plans_texts=();self._plans_until=0.0
        self._new_rows_band=None;self._new_rows_until=0.0
        observe_text(widget)
        widget._correctnote_observers.setdefault('changed',[]).append(self.changed)
        widget._correctnote_observers.setdefault('viewed',[]).append(self.viewed)
        widget._correctnote_observers.setdefault('moved',[]).append(self.cursor_moved)
        widget._correctnote_observers.setdefault('scrolled',[]).append(self.scrolled)
        self._sweep_job=None;self._sweep_row=1
        widget.bind('<FocusIn>',self.cursor_moved,add=True)
        self._cursor_rows=None
        widget.bind('<Configure>',self.viewed,add=True)
        widget.bind('<Map>',self.viewed,add=True)
        # Tk reports finished line-height recalculation (wrapping and fonts).
        widget.bind('<<WidgetViewSync>>',self.view_moved,add=True)
        if not str(widget.cget('yscrollcommand')):
            widget.configure(yscrollcommand=lambda *args:self.view_moved())
        widget.bind('<KeyPress>',self.typing,add=True)
        # The marks show only while Ctrl is held (うに 2026-10-12).
        for side in ('L','R'):
            widget.bind(f'<KeyPress-Control_{side}>',self.ctrl_down,add=True)
            widget.bind(f'<KeyRelease-Control_{side}>',self.ctrl_up,add=True)
        widget.bind('<FocusOut>',self.ctrl_up,add=True)
        widget.bind('<Destroy>',self.destroy,add=True)
        # Marker positions stay in presentation state, outside the text and undo stack.
        self._configure_pos_fonts()
        self.queue()

    def enabled(self):
        settings=getattr(self.app,'settings',None)
        return (settings is None or bool(settings.get('show_ctrl_boundaries'))
                or has_adjustments(settings.get('pos_font_multipliers'))
                or any(current_colors(settings).values()))

    def _all_rows(self):
        settings=getattr(self.app,'settings',None)
        return settings is not None and not settings.get('ctrl_boundaries_cursor_row_only')

    def _scope_rows(self):
        """Rows that show stops: the cursor's row, or every row."""
        if self._all_rows():return None
        w=self.widget
        editor=getattr(self.app,'editor',None)
        source=w
        try:
            # The correction pane follows the memo's cursor unless it has focus.
            if (w is getattr(self.app,'result_view',None) and editor is not None
                    and w.focus_get() is not w):
                source=editor
            return {int(source.index('insert').split('.')[0])}
        except (tk.TclError,KeyError,AttributeError):
            return set()

    def cursor_moved(self,event=None):
        if self._closed:return
        rows=self._scope_rows()
        if rows==self._cursor_rows:return
        self._cursor_rows=rows;self.queue_draw()
        if self.widget is getattr(self.app,'editor',None):
            partner=getattr(getattr(self.app,'result_view',None),
                            '_correctnote_boundary_colors',None)
            if isinstance(partner,BoundaryColors):partner.cursor_moved()

    # How far the mark moves from the text colour toward the background:
    # darker on a light pane and lighter on a dark one. The ┻ used .55 (.7 was
    # too faint to find); a 1px underline needs more: at .55 it was hard to
    # see (2026-10-12), so it sits nearer the text.
    MARKER_FADE = .3

    def _marker_color(self):
        """The pane's text colour faded close to its background."""
        try:
            bg=self.widget.winfo_rgb(self.widget.cget('background'))
            fg=self.widget.winfo_rgb(self.widget.cget('foreground'))
            fade=self.MARKER_FADE
            return '#'+''.join('%02x'%round((f+(b-f)*fade)/257) for f,b in zip(fg,bg))
        except tk.TclError:
            return FLASH_COLOR

    def _pos_multipliers(self):
        settings=getattr(self.app,'settings',None)
        value=(settings.get('pos_font_multipliers')
               if settings is not None else None)
        return normalize_multipliers(value)

    def _pos_colors(self):
        settings=getattr(self.app,'settings',None)
        return current_colors(settings)

    def _styled(self):
        """(sized, coloured) POS buckets: size or colour differs from the pane."""
        settings=getattr(self.app,'settings',None)
        key=(None if settings is None else
             repr((settings.get('pos_font_multipliers'),
                   settings.get('dark_mode'),
                   settings.get('pos_font_colors'),
                   settings.get('pos_font_colors_light'))))
        cached=getattr(self,'_styled_cache',None)
        if cached is not None and cached[0]==key:return cached[1]
        multipliers=self._pos_multipliers();colors=self._pos_colors()
        sized=tuple(k for k in POS_CATEGORIES if multipliers[k]!=1.0)
        colored=tuple(k for k in POS_CATEGORIES if colors[k])
        tags=tuple([(POS_FONT_TAGS[k],k) for k in sized]+
                   [(POS_COLOR_TAGS[k],k) for k in colored])
        self._styled_cache=(key,(sized,colored,tags))
        return self._styled_cache[1]

    def _sized_majors(self):return self._styled()[0]

    def _colored_majors(self):return self._styled()[1]

    def _row_tags(self):
        """(tag, major) pairs that can be on the text now."""
        return self._styled()[2]

    def _configure_pos_fonts(self):
        """Set per-POS tag fonts and colours from the pane font and options.

        Sizes and colours are on separate tags and checked separately: a new
        colour only touches the font-less colour tags, so Tk keeps the line
        layout and the rows do not move (colour palette hover)."""
        try:
            base_spec=str(self.widget.cget('font'))
            multipliers=self._pos_multipliers();colors=self._pos_colors()
            # Light and dark keep their own colours (pos_font.current_colors).
            color_signature=tuple((key,colors[key]) for key in POS_CATEGORIES)
            if color_signature!=self._color_signature:
                for major in POS_CATEGORIES:
                    tag=POS_COLOR_TAGS[major]
                    if (self._color_signature is None or
                            dict(self._color_signature).get(major)!=colors[major]):
                        self.widget.tag_configure(tag,foreground=colors[major])
                    self.widget.tag_lower(tag)
                self._color_signature=color_signature
            signature=(base_spec,tuple((key,multipliers[key])
                                       for key in POS_CATEGORIES))
            if signature==self._font_signature:return
            base=tkfont.Font(root=self.widget,font=base_spec)
            actual=base.actual()
            family=actual.get('family') or 'Yu Mincho'
            size=abs(int(actual.get('size') or 11))
            style=[]
            if str(actual.get('weight','normal')).lower()=='bold':
                style.append('bold')
            if str(actual.get('slant','roman')).lower()=='italic':
                style.append('italic')
            if bool(actual.get('underline',False)):style.append('underline')
            if bool(actual.get('overstrike',False)):style.append('overstrike')
            del base
            for major in POS_CATEGORIES:
                tag=POS_FONT_TAGS[major]
                spec=(family,font_size(size,multipliers[major]),*style)
                self.widget.tag_configure(tag,font=spec)
                self.widget.tag_lower(tag)
            self._font_signature=signature
        except (tk.TclError,TypeError,ValueError):
            self._font_signature=None;self._color_signature=None

    def _clear_pos_tags(self, start, end, all_tags=False):
        tags=(tuple(POS_FONT_TAGS.values())+tuple(POS_COLOR_TAGS.values())
              if all_tags else tuple(tag for tag,_major in self._row_tags()))
        for tag in tags:
            self.widget.tag_remove(tag,start,end)

    def _bare_rows(self,span=64):
        """bare(row) for ascending rows: True when no POS tag is on the row.

        After a tab's text is loaded no row has tags, so a pass over the
        document skips two Tk calls per POS and row (most of the cost of a tab
        switch). Each POS is first looked for once up to the end of the text;
        one that is not there is not asked again. The others are asked once
        per window of rows, bounded to the window (2026-11-01, speed: asking
        every POS for the first tagged row up to the end after each tagged row
        took 6 of 15 s while scrolling a 3,600-row tab). POS tags lie inside
        one row (they are added per token), so a range starts on its row."""
        w=self.widget;alive=None;window=[0,set()]
        def bare(row):
            nonlocal alive
            if alive is None:
                alive=[tag for tag,_major in self._row_tags() if w.tag_nextrange(tag,f'{row}.0','end')]
            if not alive:return True
            if row>window[0]:
                last=row+span-1;end=f'{last+1}.0';rows=set()
                for tag in alive:
                    index=f'{row}.0'
                    while True:
                        found=w.tag_nextrange(tag,index,end)
                        if not found:break
                        tagged=int(str(found[0]).split('.')[0]);rows.add(tagged)
                        index=f'{tagged+1}.0'
                window[0]=last;window[1]=rows
            return row not in window[1]
        return bare

    def _paint_rows(self,rows):
        """paint_row for ascending rows, skipping clears on untagged rows."""
        rows=list(rows)
        if not rows:return
        bare=self._bare_rows()
        for row in rows:
            self.paint_row(row,bare=bare)

    def _has_pos_tags(self,row):
        w=self.widget
        return any(w.tag_nextrange(tag,f'{row}.0',f'{row}.end')
                   for tag,_major in self._row_tags())

    def cancel(self):
        if self._job is not None:
            try:self.widget.after_cancel(self._job)
            except tk.TclError:pass
        self._job=None;self._rows=[]

    def _clear_lines(self):
        self.lines={};self._marker_indices={}
        try:self.widget.tag_remove(self.TICK_TAG,'1.0','end')
        except tk.TclError:pass

    def queue_draw(self,event=None):
        if self._closed or self._draw_job is not None:return
        try:self._draw_job=self.widget.after_idle(self.draw_markers)
        except tk.TclError:self._draw_job=None

    def _current_view(self):
        w=self.widget
        try:
            top=w.index('@0,0');display=w.dlineinfo(top)
            return (top,display[1] if display else None,
                    tuple(w.xview()),w.winfo_width(),w.winfo_height())
        except tk.TclError:
            return None

    def view_moved(self,event=None):
        """Any scroll, `see`, wrap or resize; checked after Tk lays out the view."""
        if self._closed or self._view_job is not None:return
        try:self._view_job=self.widget.after_idle(self._check_view)
        except tk.TclError:self._view_job=None

    def _check_view(self):
        self._view_job=None
        if self._closed:return
        if self._scroll_job is None and self._current_view()==self._drawn_view:
            if self._sweep_job is not None:
                # Sizing rows out of view while the sweep runs: the view did not
                # move, so one draw when the sweep ends is enough (with a redraw
                # between slices, each slice drew the marks again: 2026-10-18).
                self._sweep_wants_draw=True;return
            self.queue_draw();return
        self._hide_until_settled()
        # Rows that just came into view still need their markers and fonts.
        self._paint_new_rows()
        self.queue()

    def _hide_until_settled(self):
        # The marks are tags and move with the text; only rows coming into
        # view wait for the view to settle.
        if self._scroll_job is not None:
            try:self.widget.after_cancel(self._scroll_job)
            except tk.TclError:pass
        try:self._scroll_job=self.widget.after(self.SCROLL_SETTLE_MS,self._view_settled)
        except tk.TclError:self._scroll_job=None

    def scrolled(self):
        """A scroll command, before Tk redraws the moved view.

        Rows coming into view get their POS sizes from the cache in the same
        step, so the text does not appear first and then grow. The ticks are
        tags and scroll with the text."""
        if self._closed:return
        try:
            if self._current_view()==self._drawn_view:return
        except tk.TclError:return
        self._paint_new_rows()

    def _view_settled(self):
        self._scroll_job=None
        if not self._closed:self.draw_markers()

    def _configure_tick(self):
        w=self.widget;color=self._marker_color()
        if getattr(self,'_tick_color',None)==color:return
        w.tag_configure(self.TICK_TAG,underline=1)
        try:w.tag_configure(self.TICK_TAG,underlinefg=color)
        except tk.TclError:pass      # Tk before 8.6.6: the text colour
        # Below every other tag: a POS or format tag never loses its look.
        w.tag_lower(self.TICK_TAG)
        self._tick_color=color

    def _user_underline(self,index):
        """The character carries the U format (its own underline wins)."""
        from text_format import STYLE_TAGS
        try:return STYLE_TAGS['underline'] in self.widget.tag_names(index)
        except tk.TclError:return False

    def _tick_ranges(self):
        """(row, offset) of every character that carries the tick now."""
        w=self.widget;found={};start='1.0';symbolic={}
        while True:
            got=w.tag_nextrange(self.TICK_TAG,start)
            if not got:return found
            a,b=str(got[0]),str(got[1])
            row,col=map(int,a.split('.'))
            text=w.get(f'{row}.0',f'{row}.end')
            if any(ord(c)>0xFFFF for c in text):
                # Windows Tk 8.6.9 counts a character outside the BMP twice in
                # numeric columns: map back through the same `+Nc` indices
                # the ticks were added with.
                where=symbolic.get(row)
                if where is None:
                    where=symbolic[row]={str(w.index(f'{row}.0+{k}c')):k
                                         for k in range(len(text)+1)}
                first=where.get(a)
                if first is None:first=len(w.get(f'{row}.0',a))
            else:first=len(w.get(f'{row}.0',a))
            for i in range(len(w.get(a,b))):found[row,first+i]=f'{a}+{i}c'
            start=b

    def draw_markers(self):
        self._draw_job=None
        if self._closed or self._scroll_job is not None:return
        w=self.widget
        try:
            self._drawn_view=self._current_view()
            rows=self._scope_rows();self._cursor_rows=rows
            self._configure_tick()
            lo,hi=self._visible_range()
            want=set()
            for row,offsets in (self._marker_indices.items() if ctrl_held(self.app) else ()):
                if rows is not None and row not in rows:continue
                if not lo<=row<=hi:continue
                for offset in offsets:want.add((row,offset))
            have=self._tick_ranges()
            # Only the difference is changed: a retagged row is laid out
            # again, so rows whose ticks stay are left alone.
            for index,where in have.items():
                if index not in want:
                    w.tag_remove(self.TICK_TAG,where,f'{where}+1c')
            lines={}
            for row,offset in sorted(want):
                # Symbolic: Windows Tk returns UTF-16 columns, which shift
                # after an emoji when fed back as a numeric index.
                where=f'{row}.0+{offset}c'
                if (row,offset) not in have:
                    if self._user_underline(where):continue
                    w.tag_add(self.TICK_TAG,where,f'{where}+1c')
                lines[row,offset]=where
            self.lines=lines
        except tk.TclError:pass

    def queue(self):
        self.cancel()
        if not self._closed and self.enabled():
            self._job=self.widget.after(self.SETTLE_MS,self.start)

    def ctrl_down(self,event=None):
        if ctrl_held(self.app):return
        self.app._ctrl_boundaries_held=True
        for colors in _panes(self.app):colors.draw_markers()

    def ctrl_up(self,event=None):
        if not ctrl_held(self.app):return
        self.app._ctrl_boundaries_held=False
        for colors in _panes(self.app):colors._hide_ticks()

    def _hide_ticks(self):
        self.lines={}
        try:self.widget.tag_remove(self.TICK_TAG,'1.0','end')
        except tk.TclError:pass

    def typing(self,event):
        # A key without Ctrl: Ctrl was let go where this pane did not see it.
        if (ctrl_held(self.app) and not (int(getattr(event,'state',0))&4)
                and not str(getattr(event,'keysym','')).startswith('Control')):
            self.ctrl_up()
        # Navigation itself does not create new POS work. Actual typing waits
        # until the next quiet interval rather than parsing per keystroke.
        if getattr(event,'char','') and not (int(getattr(event,'state',0))&4):
            self.queue()

    def changed(self,args=None):
        if self._closed:return
        edit=getattr(self.widget,'_correctnote_last_edit',None)
        if edit is None:
            self._clear_lines()
            self._painted={};self._last_plans={};self._marker_indices={}
        else:
            # Only the edited rows change; rows elsewhere keep their ticks
            # and sizes and move with the text.
            self._follow_edit(*edit)
        self._paint_visible_now()
        self.queue_draw();self.queue()
        # Typing inside a row changes nothing elsewhere; new or removed rows
        # (Enter, paste, a tab's text) need the rest of the document sized.
        if edit is None or edit[1]:self._schedule_sweep()

    def _follow_edit(self,row,delta,last_row=None):
        # Rows from the first to the last the edit took text from (and the removed ones) are laid anew; their
        # tags went with the old text even when the row's text came back the same (a multi-row replace)
        first,last=row,max(row+max(0,-delta),last_row if last_row is not None else row)
        if not delta and first==last:
            # A key within one row: no other row moved, only this one is laid anew (every row was gone over for each key)
            for name in ('_painted','_last_plans','_marker_indices'):
                getattr(self,name).pop(row,None)
            for key in [key for key in self.lines if key[0]==row]:
                del self.lines[key]
            return
        def moved(r):
            if r<first:return r
            if r<=last:return None
            return r+delta
        for name in ('_painted','_last_plans','_marker_indices'):
            old=getattr(self,name);new={}
            for r,value in old.items():
                target=moved(r)
                if target is not None:new[target]=value
            setattr(self,name,new)
        lines,self.lines=self.lines,{}
        for (r,offset),where in lines.items():
            target=moved(r)
            if target is not None:
                self.lines[target,offset]=f'{target}.0+{offset}c'

    def viewed(self,event=None):
        if not self._closed:
            self.view_moved()
            self.queue()

    def refresh_option(self):
        self.cancel();self._last_plans.update(self._painted);self._painted={}
        if self._closed:return
        self._painted_styles=self._sized_majors()
        self._painted_colors=self._colored_majors()
        self._clear_lines()
        self._clear_pos_tags('1.0','end',all_tags=True)
        formatter=getattr(self.widget,'_correctnote_text_format',None)
        if formatter is not None:formatter.paint('1.0','end')
        self._font_signature=None;self._color_signature=None
        self.queue_draw();self.queue()

    def refresh_pos_style(self):
        """Apply new POS sizes/colours; True when the rows had to be repainted.

        While the same parts of speech stay styled, their tags are already on
        the text, so only the tag fonts and colours change: fast enough to
        follow the mouse over the colour palette."""
        if self._closed:return False
        sized=self._sized_majors()
        if sized!=getattr(self,'_painted_styles',None):
            self.refresh_option();return True
        sizes_before=self._font_signature
        self._recolor_rows(self._colored_majors())
        self._configure_pos_fonts()
        # A colour alone moves nothing; the marks are redrawn only for sizes.
        if self._font_signature!=sizes_before:self.queue_draw()
        return False

    def _recolor_rows(self,colored):
        """Give painted rows the colour tags of newly coloured parts of speech
        and drop the ones no longer coloured, without touching the sizes.

        Clearing and repainting every row (refresh_option) let the sized
        words shrink and grow back while the mouse crossed the palette."""
        before=getattr(self,'_painted_colors',None)
        if colored==before:return
        w=self.widget;before=set(before or ())
        for major in before-set(colored):
            w.tag_remove(POS_COLOR_TAGS[major],'1.0','end')
        added=[major for major in colored if major not in before]
        self._painted_colors=colored
        if not added:return
        for row,signature in list(self._painted.items()):
            value=signature[1] if signature else None
            if value is None or len(value)<=2:continue
            try:
                if w.get(f'{row}.0',f'{row}.end')!=signature[0]:continue
            except tk.TclError:continue
            grouped={major:[] for major in added}
            for major,a,z in value[2]:
                if major in grouped:
                    grouped[major].extend((f'{row}.0+{a}c',f'{row}.0+{z}c'))
            for major,ranges in grouped.items():
                if ranges:w.tag_add(POS_COLOR_TAGS[major],*ranges)

    def data_ready(self,values):
        if self._closed or not self.enabled():return
        # New plans are painted at once (visible rows first), not after the
        # typing pause: rows that were still waiting grew late before.
        if self._job is None:self._job=self.widget.after_idle(self.start)
        self._schedule_sweep()

    def start(self):
        self._job=None
        if self._closed or not self.enabled() or not self.widget.winfo_ismapped():return
        try:
            self._configure_pos_fonts()
            lo=int(self.widget.index('@0,0').split('.')[0])
            hi=int(self.widget.index('@0,'+str(max(0,self.widget.winfo_height()-1))).split('.')[0])
            last=int(self.widget.index('end-1c').split('.')[0])
            last=max(1,last)
            self._painted={r:v for r,v in self._painted.items() if r<=last}
            self._marker_indices={r:v for r,v in self._marker_indices.items() if r<=last}
            self._last_plans={r:v for r,v in self._last_plans.items() if lo<=r<=hi}
            self._rows=list(range(lo,min(last,hi)+1))
            self.queue_draw();self.paint_one()
            self._schedule_sweep()
        except tk.TclError:pass

    def _visible_range(self):
        w=self.widget
        lo=int(w.index('@0,0').split('.')[0])
        hi=int(w.index('@0,'+str(max(0,w.winfo_height()-1))).split('.')[0])
        return lo,hi

    def _composing(self):
        import ime_watch
        # Only while CorrectNote is in front: a conversion left behind must not hold the
        # rows' marks (2026-10-19, ime_watch.composition_live)
        try:return ime_watch.composition_live(self.widget.winfo_id())
        except tk.TclError:return True

    NEW_ROWS_S = 0.25

    def _paint_new_rows(self):
        """For a scroll: the same rows in view a moment ago were just painted. Reading every visible row again
        on each pixel step of the wheel was hundreds of Tk calls a frame (2026-11-03)."""
        try:
            band=self._visible_range()
        except tk.TclError:
            return
        now=time.monotonic()
        if band==self._new_rows_band and now<self._new_rows_until:return
        self._new_rows_band=band;self._new_rows_until=now+self.NEW_ROWS_S
        self._paint_visible_now()

    def _paint_visible_now(self):
        """Paint visible rows whose plan is already known, synchronously."""
        if self._closed or not self.enabled():return
        try:
            if not self.widget.winfo_ismapped() or self._composing():return
            self._configure_pos_fonts()
            lo,hi=self._visible_range()
            last=int(self.widget.index('end-1c').split('.')[0])
            self._paint_rows(range(lo,min(last,hi+self.MARGIN_ROWS)+1))
        except tk.TclError:pass

    MARGIN_ROWS = 8
    SWEEP_ROWS = 60
    # The rows out of view wait until tab switching pauses (2026-10-18, うにさん
    # 「タブを移動後につかえる」): a 3000-row tab kept the UI busy for about 2s
    # after each switch, and the next switch came in the middle of it.
    # The visible rows are still painted at once (_paint_visible_now / start).
    TAB_SETTLE_S = 0.35

    def _schedule_sweep(self):
        """Give every row with a known plan its sizes, a slice per tick.

        Rows outside the view were sized only when scrolled into it, so text
        appeared first and then grew (scrolling and switching tabs shook)."""
        self._sweep_row=1
        if self._closed or self._sweep_job is not None or not self.enabled():return
        try:self._sweep_job=self.widget.after(1,self._sweep)
        except tk.TclError:self._sweep_job=None

    def _sweep(self):
        self._sweep_job=None
        if self._closed or not self.enabled():return
        w=self.widget
        try:
            if self._composing():
                self._sweep_job=w.after(self.SETTLE_MS,self._sweep);return
            switched=getattr(self.app,'_tab_switched_at',None)
            rest=self.TAB_SETTLE_S-(time.monotonic()-switched) if switched is not None else 0
            if rest>0:
                self._sweep_job=w.after(int(rest*1000)+1,self._sweep);return
            self._configure_pos_fonts()
            # One read of the text; rows already sized for their text are
            # skipped without asking Tk, so a pass over a long document is
            # cheap. Rows that need work are re-read in paint_row.
            # One split per version of the text: a slice over a very long file split it all again (36 ms at 172,000 rows)
            whole=getattr(w,'_correctnote_whole_text',None)
            changes=whole.get('changes') if isinstance(whole,dict) and not whole.get('busy') else None
            kept=getattr(self,'_sweep_lines',None)
            if changes is not None and kept is not None and kept[0]==changes:lines=kept[1]
            else:
                lines=w.get('1.0','end-1c').split(chr(10));self._sweep_lines=(changes,lines)
            cache=getattr(self.app,'_ctrl_boundary_plans',None)
            if not isinstance(cache,dict):cache={}
            row=self._sweep_row;painted=0;bare_row=self._bare_rows()
            # Rows out of view move no visible mark. Redrawing the marks after
            # every slice measured every visible row again (bbox/dlineinfo)
            # while the sizes kept changing, the largest cost of a tab switch
            # on Windows after the painting itself.
            lo,hi=self._visible_range();hi+=self.MARGIN_ROWS
            while row<=len(lines) and painted<self.SWEEP_ROWS:
                text=lines[row-1];signature=self._painted.get(row)
                # A cached None is "no plan for this row"; repainting it on
                # every pass painted the correction pane's whole text again
                # each time its view moved (Windows, with the marks on).
                if text and (signature is None or signature[0]!=text
                             or (signature[1] is None and cache.get(text) is not None)):
                    self.paint_row(row,bare=bare_row,draw=lo<=row<=hi);painted+=1
                row+=1
            self._sweep_row=row
            if row<=len(lines):self._next_sweep_slice()
            elif getattr(self,'_sweep_wants_draw',False):
                self._sweep_wants_draw=False;self.queue_draw()
        except tk.TclError:pass

    def _next_sweep_slice(self):
        """The next slice once Tk has been idle (its redraw runs there).

        Back-to-back 1ms slices kept a timer always due, so Tk never went idle
        and drew nothing until the whole document was swept: about 2.7s after
        switching to a 3000-row tab, the window looked stuck (2026-10-18,
        うにさん「タブを移動後につかえる」). Same slices, same order."""
        w=self.widget

        def slice_after_paint():
            if self._closed:return
            try:self._sweep_job=w.after(1,self._sweep)
            except tk.TclError:self._sweep_job=None
        try:self._sweep_job=w.after_idle(slice_after_paint)
        except tk.TclError:self._sweep_job=None

    def paint_one(self):
        self._job=None
        if self._closed or not self.enabled() or not self._rows:return
        w=self.widget
        try:
            # IME preedit text is owned by the native editor. Revisit it after
            # the same quiet interval; never decorate or tokenize mid-composition.
            if self._composing():
                self.queue();return
            rows,self._rows=self._rows,[]
            self._paint_rows(sorted(set(rows)))
        except tk.TclError:pass

    PLANS_WAIT_S = 3.0
    PLANS_POLL_MS = 15
    PLANS_RETRY_MS = 300
    TYPING_S = 1.0

    def _finished_row(self,w,row,text):
        """The memo's row whose analysis is over: nothing more will bring its plan once the cache has let it go, and
        it stayed marked as unanalysed with nothing scheduled (2026-11-03)."""
        if w is not getattr(self.app,'editor',None):return False
        results=getattr(self.app,'line_results',None) or ()
        result=results[row-1] if 0<row<=len(results) else None
        return bool(result) and result.get('original')==text and not result.get('pending')

    def _plan_missing(self,row,text):
        """A visible row with no plan yet. With a child, it makes them: reading the tables here for this cost
        about 90MB of the window's memory, kept to the end, and a stop of each jump (2026-11-03)."""
        import analysis_async
        if analysis_async.child_alive(self.app) and text not in self._plans_failed:
            self._ask_plans_soon(text)
            return None
        # No child, or it did not answer in time: a row whose analysis is over gets nothing more from it, and
        # stayed marked as unanalysed with nothing scheduled (2026-11-03)
        results=getattr(self.app,'line_results',None) or ()
        if 0<row<=len(results) and (results[row-1] or {}).get('pending'):
            return None     # its analysis is coming and brings the plan
        return self._plan_now(text)

    def _ask_plans_soon(self,text):
        if text in self._plans_failed or self._closed or self._plans_scope is not None:return
        if self._plans_job is not None:
            try:self.widget.after_cancel(self._plans_job)
            except tk.TclError:pass
        # After the view stops: a row in the child gives way to the question, and is begun again
        try:self._plans_job=self.widget.after(self.SCROLL_SETTLE_MS,self._ask_plans)
        except tk.TclError:self._plans_job=None

    def _ask_plans(self):
        self._plans_job=None
        if self._closed or not self.enabled():return
        import analysis_async
        from literal_lines import literal_only
        app=self.app;w=self.widget
        try:
            if self._composing():return
            # The row being typed gets its plan with its answer: the question would begin that row again
            if time.monotonic()-getattr(app,'_last_edit_at',0.0)<self.TYPING_S:
                self._plans_job=w.after(self.PLANS_RETRY_MS,self._ask_plans);return
            lo,hi=self._visible_range()
            last=int(w.index('end-1c').split('.')[0])
            texts=[]
            for row in range(lo,min(last,hi+self.MARGIN_ROWS)+1):
                text=w.get(f'{row}.0',f'{row}.end')
                if (text and text not in self._plans_failed and not literal_only(text)
                        and plan_for(app,w,row,text) is None):
                    texts.append(text)
            if not texts:return
            pending=getattr(app,'_async_request',None)
            typed=getattr(app,'_typed_row_pending',None)
            # Nor a row just typed: the question would begin it again
            if (pending is not None and pending[0][0]=='prepare') or (typed is not None and typed()):
                self._plans_job=w.after(self.PLANS_RETRY_MS,self._ask_plans);return
        except tk.TclError:return
        scope=analysis_async.plans_ask(app,texts)
        if scope is None:
            self._plans_given_up(texts);return
        self._plans_scope=scope;self._plans_texts=texts
        self._plans_until=time.monotonic()+self.PLANS_WAIT_S
        self._plans_job=w.after(self.PLANS_POLL_MS,self._poll_plans)

    def _poll_plans(self):
        """The answer arrives while the window goes on: waiting for it stopped each jump by up to 0.4 s."""
        self._plans_job=None
        import analysis_async
        scope,texts=self._plans_scope,self._plans_texts
        if self._closed:
            analysis_async.plans_cancel(self.app,scope);self._plans_scope=None;return
        present,values=analysis_async.plans_poll(self.app,scope)
        if present and values is None:
            if time.monotonic()<self._plans_until:
                try:self._plans_job=self.widget.after(self.PLANS_POLL_MS,self._poll_plans)
                except tk.TclError:analysis_async.plans_cancel(self.app,scope);self._plans_scope=None
                return
            analysis_async.plans_cancel(self.app,scope)
            present=False
        self._plans_scope=None
        if present:
            if values:remember(self.app,values)
            # A row these rows did not cover (the view moved meanwhile) asks by itself when it is painted again
            self._repaint_for_plans()
        else:
            self._plans_given_up(texts)

    def _repaint_for_plans(self):
        try:self._paint_visible_now()
        except tk.TclError:pass

    def _plans_given_up(self,texts):
        # Not asked again: the row's analysis brings it, or _plan_missing makes it when that is over
        if len(self._plans_failed)>4096:self._plans_failed.clear()
        self._plans_failed.update(texts)

    def _plan_now(self,text):
        """補正欄の見えている行で、品詞の大きさ・色の区切り（plan）がまだ無いものを、その場で作る。

        2026-11-01 うにさん「19行目以外が小さかった」: 補正した行の字（本文と違う字）の区切りは解析の子が
        作って届けるが、控え（PLAN_CACHE_ROWS／CHARS）から押し出されていると、届くまで元の大きさで出て、
        届いた行（カーソルの行など）とそろわなかった。同じ字なら同じ区切りなので、本体の形態素解析で作る
        （見えている行だけ・1行数ミリ秒）。作ったものは控えに入れて使い回す。"""
        try:
            store=getattr(self.app,'store',None)
            tokenize=getattr(store,'_tokenize_fn',None)
            if tokenize is None:
                import corrector
                tokenize=store._tokenize_fn=corrector.make_tokenizer(store)
            values=plans([text],tokenize)
        except Exception:
            return None
        value=values.get(text)
        if value is not None:
            # remember と同じ上限で控える（ほかの欄へは知らせない: この行だけの描き直し）
            app=self.app
            cache=getattr(app,'_ctrl_boundary_plans',None)
            if not isinstance(cache,dict):cache=app._ctrl_boundary_plans={}
            owner,total=getattr(app,'_ctrl_boundary_chars',(None,0))
            if owner is not cache:total=sum(map(len,cache))
            if cache.pop(text,None) is None:total+=len(text)
            cache[text]=value
            while len(cache)>PLAN_CACHE_ROWS or total>PLAN_CACHE_CHARS:
                oldest=next(iter(cache));total-=len(oldest);cache.pop(oldest)
            app._ctrl_boundary_chars=(cache,total)
        return value

    def paint_row(self,row,bare=False,draw=True):
        """Sizes, colours and stops for one row from its known plan.

        ``bare`` says the caller knows the row has no POS tags yet (or is
        _bare_rows' test, asked only when the row is painted); ``draw`` False
        leaves the marks alone (the row is out of view)."""
        w=self.widget
        text=w.get(f'{row}.0',f'{row}.end')
        if not text:
            self._painted.pop(row,None);self._marker_indices.pop(row,None)
            return
        signature=self._painted.get(row)
        if signature is not None and signature[0]==text and signature[1] is not None:
            return
        if callable(bare):bare=bare(row)
        value=plan_for(self.app,w,row,text)
        if value is None and draw and (w is getattr(self.app,'result_view',None) or self._finished_row(w,row,text)):
            value=self._plan_missing(row,text)
        signature=(text,value)
        if value is None and not bare and self._has_pos_tags(row):
            # Typing: keep this row's sizes until the new plan arrives.
            # Clearing them first made every following row jump twice.
            if self._marker_indices.pop(row,None) is not None and draw:self.queue_draw()
            return
        if self._painted.get(row)==signature:return
        if not bare:self._clear_pos_tags(f'{row}.0',f'{row}.end')
        self._marker_indices.pop(row,None)
        if value is not None:
            settings=getattr(self.app,'settings',None)
            show_boundaries=(settings is None or
                             bool(settings.get('show_ctrl_boundaries')))
            if show_boundaries and value[0]:
                offsets=tuple(a for a,z in boundary_marker_spans(text,value[0]))
                if offsets:self._marker_indices[row]=offsets
            tags=self._row_tags()
            if tags and len(value)>2:
                grouped={major:[] for _tag,major in tags}
                for major,a,z in value[2]:
                    if major in grouped:
                        grouped[major].extend((f'{row}.0+{a}c',
                                               f'{row}.0+{z}c'))
                for tag,major in tags:
                    if grouped[major]:w.tag_add(tag,*grouped[major])
                if w is getattr(self.app,'_quick_text',None):
                    # Sized characters can be wider than the window was made for.
                    resize=getattr(self.app,'_queue_quick_resize',None)
                    if callable(resize):resize()
        formatter=getattr(w,'_correctnote_text_format',None)
        if formatter is not None:formatter.paint(f'{row}.0',f'{row}.end')
        if '\t' in text and draw and getattr(self.app,'_ws_paint_sig',None) is not None:
            # The row's tab stops are measured with its sized fonts; lay
            # them again now that the sizes changed (once the app paints
            # whitespace at all).
            schedule=getattr(self.app,'_schedule_whitespace_paint',None)
            if callable(schedule):schedule(delay=1)
        self._painted[row]=signature
        if draw:self.queue_draw()

    def destroy(self,event):
        if event.widget is not self.widget or self._closed:return
        self._closed=True;self.cancel();self._painted={};self._last_plans={}
        for name in ('_draw_job','_view_job','_scroll_job','_sweep_job'):
            job=getattr(self,name)
            if job is not None:
                try:self.widget.after_cancel(job)
                except tk.TclError:pass
                setattr(self,name,None)
        self._clear_lines()
        for key,callback in (('changed',self.changed),('viewed',self.viewed),
                             ('moved',self.cursor_moved),('scrolled',self.scrolled)):
            callbacks=self.widget._correctnote_observers.get(key,[])
            if callback in callbacks:callbacks.remove(callback)
        if getattr(self.widget,'_correctnote_boundary_colors',None) is self:
            del self.widget._correctnote_boundary_colors


def ctrl_held(app):
    return bool(getattr(app,'_ctrl_boundaries_held',False))


def _doc_window_copies(app):
    """The second windows' own text boxes (a tab the main window no longer shows・doc_window copy mode)."""
    return [w.text for w in getattr(app,'_doc_windows',()) if getattr(w,'mode',None)=='copy' and w.text is not None]


def _panes(app):
    for widget in [getattr(app,name,None) for name in ('editor','result_view','_quick_text')]+_doc_window_copies(app):
        colors=getattr(widget,'_correctnote_boundary_colors',None)
        if isinstance(colors,BoundaryColors) and not colors._closed:yield colors


def paint_view(app, widget, lo, hi):
    """Paint rows lo..hi (1-based) of `widget`'s text for another view of it.

    A second window showing the same tab is a peer of the memo and shares its tags, but the memo's painter
    paints only the rows in the memo's own view (2026-10-30 うにさん「別ウインドウで開いたウインドウの文字が、
    品詞ごとの書式が反映されていないことが多い」)."""
    colors=getattr(widget,'_correctnote_boundary_colors',None)
    if not isinstance(colors,BoundaryColors) or colors._closed or not colors.enabled():return
    try:
        if colors._composing():return
        colors._configure_pos_fonts()
        last=int(widget.index('end-1c').split('.')[0])
        colors._paint_rows(range(max(1,lo),min(last,hi)+1))
    except tk.TclError:pass


def install(app,widget):
    colors=getattr(widget,'_correctnote_boundary_colors',None)
    if colors is None:
        colors=widget._correctnote_boundary_colors=BoundaryColors(app,widget)
    return colors

