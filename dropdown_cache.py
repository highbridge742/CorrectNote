# -*- coding: utf-8 -*-
"""The re-conversion list's candidates, kept for a little while (2026-10-26 うにさん「少し前に開いたものは覚えておいて
即表示する」).

Only what is worked out from the word and its line is kept: the candidates (同音の語・漢字にする・打ち間違いの可能性・
かな表記…) and the 品詞判定／根拠 lines. The rest of the list (元に戻す・自動の補正の取り消し・紫を下ろす…) is made
again on every open from the current state, as before. A kept entry is used only when its key is the same: the word
(its whole unit), the line's text and analysis result, the neighbouring words, the document and model state
(analysis_worker.state_key: vocabulary, choices, decisions via the analysis revision, dictionary, input method…) and
the settings the list reads. Memory only, the newest few dozen; nothing is written anywhere.
"""
from collections import OrderedDict

LIMIT = 48


def _copy(value):
    if isinstance(value, list):
        return [dict(item) if isinstance(item, dict) else item for item in value]
    return value


class DropdownCache:
    def __init__(self, limit=LIMIT):
        self.limit = limit
        self._entries = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key, compute):
        """The kept value for key, or compute() kept for next time. Callers get their own copy."""
        if key is not None and key in self._entries:
            self._entries.move_to_end(key)
            self.hits += 1
            return _copy(self._entries[key])
        value = compute()
        self.misses += 1
        if key is not None:
            self._entries[key] = _copy(value)
            while len(self._entries) > self.limit:
                self._entries.popitem(last=False)
        return value

    def clear(self):
        self._entries.clear()

    def __len__(self):
        return len(self._entries)
