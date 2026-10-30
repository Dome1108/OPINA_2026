"""Instantánea completa local, publicada en una sola transacción SQLite."""
from io import StringIO
import json
from pathlib import Path
import sqlite3
from datetime import datetime
from contextlib import closing

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "opina.sqlite3"


def save_snapshot(frames, updated, path=DATABASE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps([frame.to_json(orient="table", date_format="iso") for frame in frames])
    with closing(sqlite3.connect(path, timeout=30)) as connection:
        with connection:
            connection.execute("CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY CHECK(id=1), updated TEXT NOT NULL, payload TEXT NOT NULL)")
            connection.execute("INSERT OR REPLACE INTO snapshot VALUES (1, ?, ?)", (updated.isoformat(), payload))


def read_snapshot(path=DATABASE):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError("La primera sincronización todavía no ha terminado.")
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=30)) as connection:
        row = connection.execute("SELECT updated, payload FROM snapshot WHERE id=1").fetchone()
    if row is None:
        raise FileNotFoundError("La primera sincronización todavía no ha terminado.")
    frames = [pd.read_json(StringIO(value), orient="table") for value in json.loads(row[1])]
    return (*frames, datetime.fromisoformat(row[0]))
