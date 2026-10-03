# -*- coding: utf-8 -*-
"""Keep the last displayed rows while new analysis is pending. No persisted history."""


def _document(app):
    return getattr(app, '_input_document', None)


def results(app):
    current = app.line_results
    source = getattr(_document(app), 'text', None)
    if isinstance(source,str) and '\n'.join(r['original'] for r in current)!=source:
        # A theme/scroll refresh can precede the new analysis plan. Position
        # old completed rows against the current input, never stale row numbers.
        current=[dict(original=line,corrected=line,pending=True) for line in source.split('\n')]
    state = getattr(app, '_display_state', None)
    if not state or state['document'] is not _document(app):
        return current
    previous = state['results']
    head = 0
    while head < min(len(current), len(previous)) and current[head]['original'] == previous[head]['original']:
        head += 1
    tail = 0
    while tail < min(len(current), len(previous)) - head and current[-1-tail]['original'] == previous[-1-tail]['original']:
        tail += 1
    matches = {i: i for i in range(head)}
    matches.update((len(current)-tail+i, len(previous)-tail+i) for i in range(tail))
    visible = list(current)
    for i, old in matches.items():
        if current[i].get('pending'):
            value = previous[old]
            if not value.get('pending') or value.get('_display_only'):
                visible[i] = dict(value, pending=True, _display_only=True)
    return visible


def _rebase_result_cursor(app,before,after,edit):
    """Carry one live result cursor through actual source line edits.

    No text history is stored. Before the next render, native Text indices
    still address old displayed rows, so retain an unclamped current row.
    A later explicit cursor move wins over this pending projection.
    """
    widget=getattr(app,'result_view',None)
    if widget is None:return
    lo,old_end=edit;new_end=old_end+len(after)-len(before)
    if before.count('\n',lo,old_end)==after.count('\n',lo,new_end):return
    native=str(widget.index('insert'));pending=getattr(app,'_result_cursor_pending',None)
    if pending and pending['document'] is _document(app):
        if pending['native']!=native:pending['overridden']=True
        if pending.get('overridden'):return
        row,column=pending['row'],pending['column']
    else:
        row,column=map(int,native.split('.'))
    position=0
    for unused in range(row-1):
        end=before.find('\n',position)
        if end<0:return
        position=end+1
    if position>=old_end:position+=new_end-old_end
    elif position>=lo:position=new_end
    row=after.count('\n',0,position)+1
    app._result_cursor_pending=dict(document=_document(app),native=native,row=row,column=column)


def result_cursor_pending(app):
    value=getattr(app,'_result_cursor_pending',None)
    return bool(value and value['document'] is _document(app) and not value.get('overridden'))


def consume_result_cursor(app,native):
    value=getattr(app,'_result_cursor_pending',None)
    app._result_cursor_pending=None
    if (value and value['document'] is _document(app) and not value.get('overridden')
            and value['native']==native):
        return '%s.%s' % (value['row'],value['column'])
    return native


def rebase(app, before, after, edit):
    """Move displayed rows through one observed edit, without keeping history.

    Text equality alone cannot identify repeated rows after several edits.
    Only rows outside the actual edit and still bounded by newlines survive.
    These values remain display-only; analysis invalidation is unchanged.
    """
    state = getattr(app, '_display_state', None)
    if not state or state['document'] is not _document(app) or edit is None:
        return
    previous = state['results']
    if '\n'.join(r['original'] for r in previous) != before:
        return
    lo, old_end = edit
    new_end = old_end + len(after) - len(before)
    if (not 0 <= lo <= old_end <= len(before) or not lo <= new_end <= len(after)
            or before[:lo] != after[:lo] or before[old_end:] != after[new_end:]):
        return
    _rebase_result_cursor(app,before,after,edit)
    first = before.count('\n', 0, lo)
    last = before.count('\n', 0, old_end)
    first_start = before.rfind('\n', 0, lo) + 1
    middle_end = after.find('\n', new_end)
    if middle_end < 0:
        middle_end = len(after)
    lines = after[first_start:middle_end].split('\n')
    middle = [dict(original=line, corrected=line, pending=True) for line in lines]
    offsets = {}
    at = first_start
    for row, line in enumerate(lines):
        offsets[at] = row
        at += len(line) + 1
    # Only the two edge rows can survive within the affected band. Reuse
    # prefix/tail rows directly, avoiding allocations for the whole document.
    for old_row in sorted({first, last}):
        result = previous[old_row]
        original = result['original']
        at = first_start if old_row == first else before.rfind('\n', 0, old_end) + 1
        end = at + len(original)
        moved = at if end <= lo else (at + new_end - old_end if at >= old_end else None)
        row = offsets.get(moved)
        if row is not None and lines[row] == original:
            middle[row] = result
    state['results'] = previous[:first] + middle + previous[last+1:]


def cached_units(app, result, source=None):
    state = getattr(app, '_display_state', None)
    if not result.get('_display_only') or not state or state['document'] is not _document(app):
        return None
    key = (result['original'], result['corrected'])
    return state['units'].get(key) if source is None else state['suspect'].get(key+(source,))


def remember(app, visible):
    source=getattr(_document(app),'text',None)
    if isinstance(source,str) and '\n'.join(r['original'] for r in visible)!=source:
        return
    old = getattr(app, '_display_state', None)
    same = old and old['document'] is _document(app)
    units = dict(old['units']) if same else {}
    suspect = dict(old['suspect']) if same else {}
    units.update(getattr(app, '_units_cache', {}))
    suspect.update(getattr(app, '_suspect_units_cache', {}))
    pairs = {(r['original'], r['corrected']) for r in visible}
    app._display_state = dict(document=_document(app), results=list(visible),
        units={k:v for k,v in units.items() if k in pairs},
        suspect={k:v for k,v in suspect.items() if k[:2] in pairs})


def restore_tab(app, text):
    from analysis_work_app import owner
    saved = getattr(app, '_completed_tabs', {}).get(owner(app))
    if saved and saved['text'] == text.rstrip('\n'):
        app._display_state = dict(document=_document(app), results=list(saved['results']),
                                  units=dict(saved['units']), suspect=dict(saved['suspect']))
    else:
        saved = getattr(app, '_fg_parked', {}).get(owner(app), {}).get('display')
        # The edit observer already moved these displayed rows through the
        # actual cut. Never borrow another document's projection or evidence.
        app._display_state = saved if saved and saved['document'] is _document(app) else None


def corrections(result, source=True):
    """Use the same ranges for color and menus, including older span-less results."""
    details = result.get('details') or []
    spans = result.get('original_spans' if source else 'spans') or []
    text = result.get('original' if source else 'corrected', '')
    cursor = 0
    for i, detail in enumerate(details):
        fragment = detail[0 if source else 1]
        if len(spans) == len(details):
            start, end = spans[i]
        else:
            start = text.find(fragment, cursor) if fragment else -1
            if start < 0:
                continue
            end = start + len(fragment)
        if 0 <= start <= end <= len(text):
            yield start, end, detail
            cursor = end


def original_range(result, start, end):
    """Map a whole displayed unit using the recorded edits, not equal letters."""
    original=result.get('original','');shown=result.get('corrected','')
    if not 0<=start<end<=len(shown):return None
    source_spans=result.get('original_spans') or ()
    shown_spans=result.get('spans') or ()
    details=result.get('details') or ()
    if not details or len(source_spans)!=len(details) or len(shown_spans)!=len(details):return None
    original_at=shown_at=0;segments=[]
    for (lo,hi),(first,last),detail in zip(source_spans,shown_spans,details):
        if not (original_at<=lo<hi<=len(original) and shown_at<=first<last<=len(shown)
                and original[original_at:lo]==shown[shown_at:first]
                and original[lo:hi]==detail[0] and shown[first:last]==detail[1]):return None
        segments.extend(((shown_at,first,original_at,lo,False),(first,last,lo,hi,True)))
        original_at,shown_at=hi,last
    if original[original_at:]!=shown[shown_at:]:return None
    segments.append((shown_at,len(shown),original_at,len(original),False))
    edges=[]
    for edge in (start,end):
        for first,last,lo,hi,changed in segments:
            if first<=edge<=last:
                if edge==first:edges.append(lo)
                elif edge==last:edges.append(hi)
                elif changed:return None
                else:edges.append(lo+edge-first)
                break
    return tuple(edges) if len(edges)==2 and edges[0]<edges[1] else None


def _key(index):
    return tuple(map(int, str(index).split('.')))


def update_tag(widget, tag, ranges, stable_index):
    """Modify only changed tag intervals, preserving unrelated rows and Unicode indices."""
    requested = tuple(ranges)
    native = tuple(map(str, widget.tag_ranges(tag)))
    cache = getattr(widget, '_projection_tag_ranges', None)
    text = widget.get('1.0', 'end-1c')
    if cache is None or getattr(widget, '_projection_tag_text', None) != text:
        cache = widget._projection_tag_ranges = {}
        widget._projection_tag_text = text
    if cache.get(tag) == (requested, native):
        return
    wanted = sorted((_key(widget.index(a)), _key(widget.index(b))) for a,b in requested)
    merged = []
    for start, end in wanted:
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    desired = set(merged)
    existing = {(_key(a), _key(b)) for a,b in zip(native[::2], native[1::2])}
    def position(pair):
        return stable_index(widget, '%s.%s' % pair)
    for a,b in sorted(existing-desired):
        widget.tag_remove(tag, position(a), position(b))
    added = sorted(desired-existing)
    for lo in range(0, len(added), 1000):
        values = [position(p) for pair in added[lo:lo+1000] for p in pair]
        if values:
            widget.tag_add(tag, *values)
    cache[tag] = (requested, tuple(map(str, widget.tag_ranges(tag))))


def replace_text(widget, old, new):
    """Keep unchanged text/tag ranges intact when one displayed row changes."""
    if old == new:
        return False
    start = 0
    while start < min(len(old),len(new)) and old[start] == new[start]:
        start += 1
    old_end, new_end = len(old), len(new)
    while old_end > start and new_end > start and old[old_end-1] == new[new_end-1]:
        old_end -= 1
        new_end -= 1
    def index(offset):
        prefix = old[:offset]
        return '%s.0+%sc' % (prefix.count('\n')+1, len(prefix.rsplit('\n',1)[-1]))
    widget.replace(index(start), index(old_end), new[start:new_end])
    return True

