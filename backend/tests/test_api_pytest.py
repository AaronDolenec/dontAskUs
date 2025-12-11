import os
import sys
import pytest

# Add backend folder to path so we can import main
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Use a local sqlite file for tests
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from fastapi.testclient import TestClient
from main import app


@pytest.fixture(scope="module")
def client():
    # TestClient doesn't trigger on_event("startup") by default
    # We need to manually trigger the startup seeder
    from database import engine, Base
    Base.metadata.create_all(bind=engine)
    
    # Import and call the seeder directly
    from main import seed_default_question_sets
    seed_default_question_sets()
    
    return TestClient(app)


def test_basic_flow(client):
    # Create group
    resp = client.post("/api/groups", json={"name": "Test Group"})
    assert resp.status_code == 200
    group = resp.json()

    # List public sets
    resp = client.get("/api/question-sets")
    assert resp.status_code == 200
    sets = resp.json()
    assert len(sets) > 0
    set_id = sets[0]["set_id"]

    # Join user
    resp = client.post("/api/users/join", json={"display_name": "alice", "group_invite_code": group["invite_code"]})
    assert resp.status_code == 200
    user = resp.json()

    # Assign set to group via admin header
    admin_token = group["admin_token"]
    payload = {"question_set_ids": [set_id], "replace": True}
    headers = {"X-Admin-Token": admin_token}
    resp = client.post(f"/api/groups/{group['group_id']}/question-sets", json=payload, headers=headers)
    assert resp.status_code == 200
    assigned = resp.json()

    # Get group's question sets
    resp = client.get(f"/api/groups/{group['group_id']}/question-sets")
    assert resp.status_code == 200
    gs = resp.json()
    assert gs["group_id"] == group["group_id"]
    assert len(gs["question_sets"]) >= 1
