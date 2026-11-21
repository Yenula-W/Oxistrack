import os
import shutil
import tempfile

_tmp = tempfile.mkdtemp(prefix="oxistrack-test-")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "storage")
os.environ["ENVIRONMENT"] = "test"
os.environ["AI_PROVIDER"] = "heuristic"
os.environ["LLM_API_KEY"] = ""
os.environ["REVIEWER_API_KEY"] = ""
os.environ["REVIEWER_MODEL"] = ""
os.environ["AUTO_CREATE_TABLES"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth(client):
    r = client.post("/auth/register", json={"email": "ada@example.com", "name": "Ada", "password": "correct-horse"})
    assert r.status_code == 201, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return client


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_tmp, ignore_errors=True)
