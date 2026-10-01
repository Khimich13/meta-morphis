import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

import meta_morphis.utils.http as http
from meta_morphis.db.init_db import init_db


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    # A fresh in-memory database with the real schema, built through
    # init_db so it can't drift from what production creates.
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    # A file-backed database with the real schema. Unlike `conn`, a second
    # connection to this file sees only committed data - which is what it
    # takes to prove a write actually reached the database.
    path = tmp_path / "cards.db"
    conn = sqlite3.connect(path)
    init_db(conn)
    conn.close()
    return path


@pytest.fixture(autouse=True)
def _reset_http_pacing_state() -> None:
    # request_with_retries persists the last-request timestamp at module
    # scope so it can pace between separate calls, not just within one
    # call's own retries. Reset it before every test so one
    # test's real timing can't leak into the next one's and cause an
    # unexpected real time.sleep().
    http._last_request_time = 0.0
