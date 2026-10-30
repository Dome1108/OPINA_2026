from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from storage import read_snapshot, save_snapshot


class SnapshotTests(unittest.TestCase):
    def test_roundtrip_preserves_ids_dates_and_booleans(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.sqlite3'
            frame = pd.DataFrame({'cedula': ['0123456789'], 'fecha': pd.to_datetime(['2026-10-30T12:00:00Z']), 'accepted': [True]})
            now = datetime.now(timezone.utc)
            save_snapshot([frame] * 4, now, path)
            snapshot = read_snapshot(path)
            pd.testing.assert_frame_equal(snapshot[0], frame)
            self.assertEqual(snapshot[-1], now)

    def test_replaces_entire_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.sqlite3'
            frame = pd.DataFrame({'id': ['1']})
            now = datetime.now(timezone.utc)
            save_snapshot([frame] * 4, now, path)
            replacement = pd.DataFrame({'id': ['2', '3']})
            save_snapshot([replacement] * 4, now, path)
            self.assertEqual(read_snapshot(path)[0].id.tolist(), ['2', '3'])
