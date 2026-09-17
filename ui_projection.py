# -*- coding: utf-8 -*-
"""Keep the last displayed rows while new analysis is pending. No persisted history."""


def _document(app):
    return getattr(app, '_input_document', None)


def results(app):
    current = app.line_results
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


def cached_units(app, result, source=None):
    state = getattr(app, '_display_state', None)
    if not result.get('_display_only') or not state or state['document'] is not _document(app):
        return None
    key = (result['original'], result['corrected'])
    return state['units'].get(key) if source is None else state['suspect'].get(key+(source,))


def remember(app, visible):
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
        app._display_state = None


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

