# -*- coding: utf-8 -*-
"""Correct the row being composed in the IME before it is committed.

2026-10-17 (うにさん「文字入力中から補正を考えておいたり…入力に対するレスポンスをあげる」):
after an IME commit the typed row took about 300-500ms in the child. While a
composition is live, its string is what the commit will insert at the
cursor. The row with that string, and the reading the commit will record for
it, is sent ahead with its whole text (the child prepares first, then corrects
the row, as after the commit). When the commit matches, the answer is already
here.

The answer is used only for exactly the work the commit leads to: the same
text and row, the same row inputs (readings, calculations, recent words, input
method, keyboard), the same nearby words and context from the same prepare,
and a model state the existing rule accepts (analysis_worker.result_compatible:
only IME readings changed, and none this row asked about). Otherwise the row is
computed as before. Only the latest composition is kept; no text history.
"""
import keyboard_layout
import analysis_context
import analysis_work_app as input_work
from analysis_worker import state_key, same_model_state, result_compatible

_ROW_FIELDS = ('line', 'input_method', 'keyboard', 'recent', 'readings', 'calculations')


def _source_and_cursor(app):
    """The source text and the cursor's offset in it, or None when the editor
    shows derived rows or a selection would be replaced by the commit."""
    try:
        editor = app.editor
        if editor.tag_ranges('sel'):
            return None
        source = app.editor_source_text()
        if editor.get('1.0', 'end-1c') != source:
            return None
        return source, len(editor.get('1.0', 'insert'))
    except Exception:
        return None


def speculate(app, comp, reading):
    """Send the row as it will be once `comp` is committed (the IME watcher)."""
    if not comp or getattr(app, '_closing', False):
        return
    at = _source_and_cursor(app)
    if at is None:
        return
    source, pos = at
    text = source[:pos] + comp + source[pos:]
    spec = getattr(app, '_ime_speculation', None)
    if spec is not None and spec['text'] == text:
        return
    doc = getattr(app, '_input_document', None)
    if doc is None or doc.owner != input_work.owner(app) or doc.text != source:
        return
    from analysis_work import Document
    # The document after the commit: the insertion moves later readings, then
    # the watcher binds the committed string to the reading it was typed with.
    after = Document(doc.owner, doc.text)
    after.occurrences, after.calculations = doc.occurrences, doc.calculations
    after.update(text, edited=True, edit=(pos, pos))
    if reading:
        after.remember(pos, pos + len(comp), comp, reading)
    lines = text.split('\n')
    row = text.count('\n', 0, pos)
    task = dict(kind='line', line=lines[row], result=None, context=None,
                input_method=(app.settings.get('input_method') or 'kana'),
                keyboard=keyboard_layout.spec(app.settings), nearby=None, lines=lines, row=row,
                recent=app.recent_words.words() if getattr(app, 'recent_words', None) is not None else (),
                readings=after.row_readings(row, lines[row]), calculations=after.row_calculations(row, lines[row]),
                attested=())
    state = state_key(app)
    scope = ('speculate', text, row, state)
    import analysis_async
    try:
        analysis_async._request(app, task, scope)
    except Exception:
        return
    app._ime_speculation = dict(text=text, source=source, row=row, state=state, scope=scope, task=task,
                                value=None)


def waiting(app):
    """True while the child is computing a composed row (normal requests would
    supersede it); takes its answer when it is there.

    Once the editor holds neither the text before the composition nor the
    composed text (another string was committed, or the text was edited), the
    composed row can no longer be used: it is dropped at once so the normal
    request goes out without waiting for it (2026-10-18)."""
    spec = getattr(app, '_ime_speculation', None)
    if spec is None or spec['value'] is not None:
        return False
    try:
        now = app.editor_source_text()
    except Exception:
        now = None
    if now is not None and now != spec['text'] and now != spec.get('source'):
        app._ime_speculation = None
        return False
    import analysis_async
    try:
        present, value = analysis_async._poll(app, spec['scope'])
    except Exception:
        app._ime_speculation = None
        return False
    if not present:
        app._ime_speculation = None       # superseded or the child was replaced
        return False
    if value is None:
        return True
    spec['value'] = value
    return False


def context_for(app, text):
    """The prepare of the committed text, when the composed row's request made it."""
    spec = getattr(app, '_ime_speculation', None)
    if spec is None or spec['value'] is None or spec['text'] != text:
        return None
    prepared = spec['value'].get('prepared')
    current = state_key(app)
    if prepared is None or not (spec['state'] == current or same_model_state(spec['state'], current)):
        return None
    return prepared


def take(app, index, task):
    """The composed row's answer for the typed row's task, or None."""
    spec = getattr(app, '_ime_speculation', None)
    if spec is None or spec['value'] is None or task.get('kind') != 'line':
        return None
    value = spec['value']
    if (spec['row'] != index or spec['text'] != getattr(app, '_analyze_text', None)
            or any(task.get(name) != spec['task'].get(name) for name in _ROW_FIELDS)
            or value.get('input_signature') != analysis_context.signature(
                task.get('nearby', ()), task.get('readings', ()), task.get('calculations', ()))
            or (value.get('prepared') or {}).get('context') != task.get('context')
            or not result_compatible(app, analysis_context.completed(value), spec['state'])):
        return None
    app._ime_speculation = None
    return value


def forget(app):
    app._ime_speculation = None
