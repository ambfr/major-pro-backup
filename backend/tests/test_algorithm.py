from datetime import datetime
from unittest.mock import MagicMock

from services.algorithm import (
    should_inject_wellness,
    _inject_wellness_posts,
    _matches_wellness_content,
    silent_ai_adjustment,
)


def make_post(post_id=1, content="", sentiment="positive", risk_score=0.1):
    post = MagicMock()
    post.id = post_id
    post.content = content
    post.sentiment = sentiment
    post.risk_score = risk_score
    post.topics = []
    return post


class TestShouldInjectWellness:
    def test_injects_only_for_at_risk_users(self):
        assert should_inject_wellness(0.7, 5) is True
        assert should_inject_wellness(0.7, 10) is True
        assert should_inject_wellness(0.7, 3) is False
        assert should_inject_wellness(0.5, 5) is False


class TestInjectWellnessPosts:
    def test_injection_positions_inserts_at_5_and_10(self):
        posts = [make_post(post_id=i) for i in range(1, 15)]
        wellness = [make_post(post_id=100, content="self-care reminder"), make_post(post_id=101, content="mindfulness tip")]

        injected = _inject_wellness_posts(posts, wellness, user_risk=0.8)

        assert injected[4].id == 100
        assert injected[10].id == 101
        assert len(injected) == len(posts) + 2
        assert all(getattr(item, "is_wellness", False) for item in injected if item.id in {100, 101})

    def test_no_injection_when_no_candidates(self):
        posts = [make_post(post_id=i) for i in range(1, 10)]
        injected = _inject_wellness_posts(posts, [], user_risk=0.8)
        assert injected == posts

    def test_does_not_duplicate_existing_post(self):
        posts = [make_post(post_id=i) for i in range(1, 15)]
        wellness = [make_post(post_id=5, content="wellness tip")]
        injected = _inject_wellness_posts(posts, wellness, user_risk=0.8)
        assert len(injected) == len(posts)
        assert all(post.id != 5 or post is posts[4] for post in injected)


class TestMatchWellnessContent:
    def test_matches_by_keyword_in_content(self):
        post = make_post(content="This wellness moment is so calm and mindful.")
        assert _matches_wellness_content(post) is True

    def test_matches_by_keyword_in_topics(self):
        post = make_post(content="Fresh post", sentiment="positive")
        post.topics = ["mindfulness", "relaxation"]
        assert _matches_wellness_content(post) is True

    def test_rejects_non_wellness_posts(self):
        post = make_post(content="Just a regular update about my day.")
        assert _matches_wellness_content(post) is False


class TestSilentAIAdjustment:
    def test_positive_low_risk_post_gets_boost_for_at_risk_user(self):
        post = make_post(risk_score=0.1, sentiment="positive")
        boost = silent_ai_adjustment(post, user_risk=0.7)
        assert boost > 0
        assert abs(boost - 0.06) < 1e-6

    def test_positive_boost_not_applied_below_threshold(self):
        post = make_post(risk_score=0.1, sentiment="positive")
        assert silent_ai_adjustment(post, user_risk=0.5) == 0.0

    def test_high_risk_post_penalty_for_at_risk_user(self):
        post = make_post(risk_score=0.8, sentiment="negative")
        penalty = silent_ai_adjustment(post, user_risk=0.7)
        assert penalty < 0
