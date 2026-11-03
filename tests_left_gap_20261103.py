# -*- coding: utf-8 -*-
"""While the right pane waits for its small font, the left pane's rows must not be padded to the right's old height."""
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

import app as app_module
import text_layout


def rows_of(pane):
    return [t for t in pane.tag_names() if t.startswith('paired_row_pad_') and pane.tag_ranges(t)]


def main():
    root = tk.Tk()
    try:
        left = tk.Text(root, width=30, height=8, font=('Arial', 5), wrap='char')
        right = tk.Text(root, width=30, height=8, font=('Arial', 12), wrap='char')
        left.pack()
        right.pack()
        for pane in (left, right):
            pane.insert('1.0', '\n'.join('row %d' % i for i in range(1, 20)))
        root.update()

        # the mechanism: measured against the old font, the left rows get gaps
        text_layout.align_rows(left, right, enabled=True)
        root.update()
        assert rows_of(left), 'the fixture no longer pads the small pane'

        # the gaps leave with the old font
        text_layout.clear_padding(left)
        assert not rows_of(left), rows_of(left)
        assert left._paired_row_signature is None
        root.update()
        small = left.dlineinfo('2.0')[1] - left.dlineinfo('1.0')[1]
        assert small == tk.font.Font(root=root, font=left.cget('font')).metrics('linespace') + int(left.cget('spacing1')) + int(left.cget('spacing3')), small

        # no alignment while the right pane lags
        fake = SimpleNamespace(result_view=right, editor=left, _syncing=False, _ov_right_font=('Arial', 5))
        with patch.object(text_layout, 'align_rows', side_effect=AssertionError('aligned while the right pane lags')):
            app_module.CorrectNoteApp._align_pane_rows(fake)
        assert not rows_of(left)
    finally:
        root.destroy()
    print('OK')


if __name__ == '__main__':
    import tkinter.font  # noqa: F401
    main()
