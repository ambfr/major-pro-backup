"""
Integration tests for MindGram FastAPI endpoints.
Uses the async test client + in-memory SQLite from conftest.py.
All AI pipeline calls are mocked so tests run without GPU.
"""

import pytest
from unittest.mock import patch, MagicMock
from schemas.schemas import PipelineResult
from main import app
from routers.auth import get_current_user


# ── Shared mock pipeline result ──────────────────────────────

MOCK_PIPELINE = PipelineResult(
    sentiment="positive",
    sentiment_score=0.72,
    emotion="joy",
    emotion_score=0.81,
    sarcasm=False,
    sarcasm_score=0.04,
    risk_score=0.08,
    feed_score=0.87,
)

MOCK_AGENT_REPORT_ATTRS = {
    "risk_level": "low",
    "decision": "monitor",
    "intervention": "No immediate action.",
    "rag_suggestion": "Keep taking care of yourself.",
    "metadata": {"analysis": {}, "reflection": {}},
}


def make_mock_agent_report():
    from ai.agents.orchestrator import AgentReport
    return AgentReport(**MOCK_AGENT_REPORT_ATTRS)


# ── Users ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestUsersEndpoints:
    async def test_create_user_success(self, client):
        resp = await client.post("/api/users", json={
            "username": "testuser", "display_name": "Test User"
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "testuser"
        assert data["id"] is not None

    async def test_create_user_duplicate_fails(self, client):
        payload = {"username": "dupuser", "display_name": "Dup"}
        await client.post("/api/users", json=payload)
        resp = await client.post("/api/users", json=payload)
        assert resp.status_code == 409

    async def test_get_user_by_id(self, client, seeded_user):
        resp = await client.get(f"/api/users/{seeded_user.id}")
        assert resp.status_code == 200
        assert resp.json()["username"] == "test_user"

    async def test_get_nonexistent_user_404(self, client):
        resp = await client.get("/api/users/99999")
        assert resp.status_code == 404

    async def test_list_users(self, client, seeded_user):
        resp = await client.get("/api/users")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1


# ── Posts ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPostsEndpoints:
    @patch("routers.posts.analyze_text", return_value=MOCK_PIPELINE)
    @patch("routers.posts.run_agents", return_value=make_mock_agent_report())
    async def test_create_post_success(self, mock_agents, mock_pipeline, client, seeded_user):
        resp = await client.post("/api/posts", json={
            "user_id": seeded_user.id,
            "content": "Feeling great today!",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "Feeling great today!"
        assert data["sentiment"] == "positive"
        assert data["emotion"] == "joy"
        assert data["risk_score"] == pytest.approx(0.08)

    @patch("routers.posts.analyze_text", return_value=MOCK_PIPELINE)
    @patch("routers.posts.run_agents", return_value=make_mock_agent_report())
    async def test_create_post_unknown_user_404(self, mock_agents, mock_pipeline, client):
        resp = await client.post("/api/posts", json={
            "user_id": 99999,
            "content": "Hello world",
        })
        assert resp.status_code == 404

    @patch("routers.posts.analyze_text", return_value=MOCK_PIPELINE)
    @patch("routers.posts.run_agents", return_value=make_mock_agent_report())
    async def test_get_post_by_id(self, mock_agents, mock_pipeline, client, seeded_user):
        create_resp = await client.post("/api/posts", json={
            "user_id": seeded_user.id,
            "content": "Test post",
        })
        post_id = create_resp.json()["id"]
        resp = await client.get(f"/api/posts/{post_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == post_id

    async def test_get_nonexistent_post_404(self, client):
        resp = await client.get("/api/posts/99999")
        assert resp.status_code == 404

    @patch("routers.posts.analyze_text", return_value=MOCK_PIPELINE)
    @patch("routers.posts.run_agents", return_value=make_mock_agent_report())
    async def test_get_user_posts(self, mock_agents, mock_pipeline, client, seeded_user):
        for i in range(3):
            await client.post("/api/posts", json={
                "user_id": seeded_user.id,
                "content": f"Post number {i}",
            })
        resp = await client.get(f"/api/posts/user/{seeded_user.id}")
        assert resp.status_code == 200
        assert len(resp.json()) == 3


# ── Feed ─────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestFeedEndpoints:
    async def test_feed_returns_list(self, client, seeded_user):
        resp = await client.get(f"/api/feed/{seeded_user.id}")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_feed_respects_limit(self, client, seeded_user):
        resp = await client.get(f"/api/feed/{seeded_user.id}?limit=5")
        assert resp.status_code == 200
        assert len(resp.json()) <= 5


# ── Messages ─────────────────────────────────────────────────

@pytest.mark.asyncio
class TestMessagesEndpoints:
    @patch("routers.messages.analyze_text", return_value=MOCK_PIPELINE)
    async def test_send_message_success(self, mock_pipeline, client, db_session, seeded_user):
        from models.models import User
        other = User(id=2, username="other", display_name="Other", avatar_url="", bio="")
        db_session.add(other)
        await db_session.commit()

        resp = await client.post("/api/messages", json={
            "sender_id": seeded_user.id,
            "receiver_id": 2,
            "content": "Hello there!",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "Hello there!"
        assert data["sentiment"] == "positive"

    @patch("routers.messages.analyze_text", return_value=MOCK_PIPELINE)
    async def test_send_message_unknown_sender_404(self, mock_pipeline, client, seeded_user):
        resp = await client.post("/api/messages", json={
            "sender_id": 9999,
            "receiver_id": seeded_user.id,
            "content": "Hello",
        })
        assert resp.status_code == 404

    @patch("routers.messages.analyze_text", return_value=MOCK_PIPELINE)
    async def test_get_thread(self, mock_pipeline, client, db_session, seeded_user):
        from models.models import User
        other = User(id=2, username="other2", display_name="Other2", avatar_url="", bio="")
        db_session.add(other)
        await db_session.commit()

        await client.post("/api/messages", json={
            "sender_id": seeded_user.id, "receiver_id": 2, "content": "Hi"
        })
        await client.post("/api/messages", json={
            "sender_id": 2, "receiver_id": seeded_user.id, "content": "Hey back"
        })

        resp = await client.get(f"/api/messages/thread/{seeded_user.id}/2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ── Interactions ─────────────────────────────────────────────

@pytest.mark.asyncio
class TestInteractionsEndpoints:
    @patch("routers.posts.analyze_text", return_value=MOCK_PIPELINE)
    @patch("routers.posts.run_agents", return_value=make_mock_agent_report())
    async def test_like_post(self, mock_agents, mock_pipeline, client, seeded_user):
        create = await client.post("/api/posts", json={
            "user_id": seeded_user.id, "content": "Like me!"
        })
        post_id = create.json()["id"]

        resp = await client.post("/api/interactions", json={
            "user_id": seeded_user.id, "post_id": post_id, "action": "like"
        })
        assert resp.status_code == 200
        assert resp.json()["action"] == "like"

    @patch("routers.interactions.analyze_text", return_value=MOCK_PIPELINE)
    @patch("routers.posts.analyze_text", return_value=MOCK_PIPELINE)
    @patch("routers.posts.run_agents", return_value=make_mock_agent_report())
    async def test_add_comment(self, mock_agents, mock_pipeline, mock_comment_pipeline, client, seeded_user):
        create = await client.post("/api/posts", json={
            "user_id": seeded_user.id, "content": "Comment on me!"
        })
        post_id = create.json()["id"]

        resp = await client.post("/api/interactions/comment", json={
            "post_id": post_id, "user_id": seeded_user.id, "content": "Great post!"
        })
        assert resp.status_code == 201
        assert resp.json()["content"] == "Great post!"


# ── Analytics ────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAnalyticsEndpoints:
    async def test_analytics_empty_user(self, client, seeded_user):
        resp = await client.get(f"/api/analytics/{seeded_user.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == seeded_user.id
        assert data["emotion_timeline"] == []
        assert data["current_risk"] == 0.0

    async def test_risk_endpoint(self, client, seeded_user):
        resp = await client.get(f"/api/analytics/{seeded_user.id}/risk")
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_level" in data

    async def test_suggestions_endpoint(self, client, seeded_user):
        with patch("routers.analytics.retrieve_top_k", return_value=["Take care."]):
            resp = await client.get(f"/api/analytics/{seeded_user.id}/suggestions")
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data


# ── Notifications ─────────────────────────────────────────────

@pytest.mark.asyncio
class TestNotificationsEndpoints:
    async def test_get_notifications(self, client, db_session, seeded_user):
        from models.models import Notification

        notification = Notification(
            user_id=seeded_user.id,
            from_user_id=None,
            type="follow",
            message="You have a new follower",
        )
        db_session.add(notification)
        await db_session.commit()

        async def override_get_current_user():
            return seeded_user

        app.dependency_overrides[get_current_user] = override_get_current_user
        try:
            resp = await client.get("/api/notifications")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["message"] == "You have a new follower"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    async def test_mark_notification_read(self, client, db_session, seeded_user):
        from models.models import Notification

        notification = Notification(
            user_id=seeded_user.id,
            from_user_id=None,
            type="comment",
            message="Someone commented on your post",
        )
        db_session.add(notification)
        await db_session.commit()
        await db_session.refresh(notification)

        async def override_get_current_user():
            return seeded_user

        app.dependency_overrides[get_current_user] = override_get_current_user
        try:
            resp = await client.put(f"/api/notifications/{notification.id}/read")
            assert resp.status_code == 200
            assert resp.json()["is_read"] is True
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    async def test_delete_notification(self, client, db_session, seeded_user):
        from models.models import Notification

        notification = Notification(
            user_id=seeded_user.id,
            from_user_id=None,
            type="like",
            message="Your post was liked",
        )
        db_session.add(notification)
        await db_session.commit()
        await db_session.refresh(notification)

        async def override_get_current_user():
            return seeded_user

        app.dependency_overrides[get_current_user] = override_get_current_user
        try:
            resp = await client.delete(f"/api/notifications/{notification.id}")
            assert resp.status_code == 200
            assert resp.json()["success"] is True
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── Agents ───────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAgentsEndpoints:
    async def test_agent_status_no_data(self, client, seeded_user):
        resp = await client.get(f"/api/agents/status/{seeded_user.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_level"] == "low"
        assert data["decision"] == "monitor"

    async def test_agent_history_empty(self, client, seeded_user):
        resp = await client.get(f"/api/agents/history/{seeded_user.id}")
        assert resp.status_code == 200
        assert resp.json() == []


# ── Health ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestHealthEndpoints:
    async def test_root(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
