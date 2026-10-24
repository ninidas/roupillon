import os
import tempfile
from datetime import datetime

_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["NIGHTLY_BACKUP"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import service  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "un-mot-de-passe-long"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 24, 7, 0)

    def set(self, s: str):
        self.now = datetime.strptime(s, "%Y-%m-%d %H:%M")


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(service, "now_local", lambda: c.now)
    return c


@pytest.fixture
def client(clock):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    limiter.reset()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client):
    r = client.post("/api/setup", json={
        "child_name": "Bébé", "birth_date": "2026-07-01",
        "accounts": [{"display_name": "Parent A", "username": "pa", "password": PASSWORD},
                     {"display_name": "Parent B", "username": "pb", "password": PASSWORD}]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
