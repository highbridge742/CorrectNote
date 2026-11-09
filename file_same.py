# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Whether a file already holds this text: nothing to write then (2026-11-05: closing without any change wrote the
session, the vocabulary, the word book and the analysis file again)."""
import os


def same(path, text):
    """True when the file at `path` holds exactly `text` (written as UTF-8 with newline translation)."""
    try:
        encoded = text.replace('\n', os.linesep).encode('utf-8')
        if os.path.getsize(path) != len(encoded):
            return False
        with open(path, 'rb') as f:
            return f.read() == encoded
    except (OSError, ValueError):
        return False
