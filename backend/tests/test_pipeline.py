"""
Unit tests for the AI analysis pipeline.

These tests mock the HuggingFace models so they run without GPU/downloads.
"""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock


# ── Helpers ──────────────────────────────────────────────────

def make_hf_result(label, score):
    return [[{"label": label, "score": score}]]


# ── Sentiment ────────────────────────────────────────────────

class TestRunSentiment:
    def test_positive_text(self):
        mock_model = MagicMock(return_value=[{"label": "LABEL_2", "score": 0.92}])
        with patch("ai.pipeline.analyzer.get_model", return_value=mock_model):
            from ai.pipeline.analyzer import run_sentiment
            label, score = run_sentiment("I feel amazing today!")
        assert label == "positive"
        assert score > 0

    def test_negative_text(self):
        mock_model = MagicMock(return_value=[{"label": "LABEL_0", "score": 0.87}])
        with patch("ai.pipeline.analyzer.get_model", return_value=mock_model):
            from ai.pipeline.analyzer import run_sentiment
            label, score = run_sentiment("Everything is terrible")
        assert label == "negative"
        assert score < 0

    def test_neutral_text(self):
        mock_model = MagicMock(return_value=[{"label": "LABEL_1", "score": 0.75}])
        with patch("ai.pipeline.analyzer.get_model", return_value=mock_model):
            from ai.pipeline.analyzer import run_sentiment
            label, score = run_sentiment("The sky is blue")
        assert label == "neutral"
        assert score == pytest.approx(0.0)

    def test_score_bounds(self):
        for raw_label, direction in [("LABEL_0", -1), ("LABEL_1", 0), ("LABEL_2", 1)]:
            mock_model = MagicMock(return_value=[{"label": raw_label, "score": 0.9}])
            with patch("ai.pipeline.analyzer.get_model", return_value=mock_model):
                from ai.pipeline.analyzer import run_sentiment
                _, score = run_sentiment("text")
            assert -1.0 <= score <= 1.0


# ── Emotion ──────────────────────────────────────────────────

class TestRunEmotion:
    @pytest.mark.parametrize("label,expected", [
        ("joy", "joy"), ("sadness", "sadness"), ("anger", "anger"),
        ("fear", "fear"), ("disgust", "disgust"), ("surprise", "surprise"),
        ("neutral", "neutral"), ("UNKNOWN", "neutral"),
    ])
    def test_emotion_labels(self, label, expected):
        mock_model = MagicMock(return_value=[{"label": label, "score": 0.8}])
        with patch("ai.pipeline.analyzer.get_model", return_value=mock_model):
            from ai.pipeline.analyzer import run_emotion
            result_label, result_score = run_emotion("some text")
        assert result_label == expected
        assert 0.0 <= result_score <= 1.0


# ── Sarcasm ──────────────────────────────────────────────────

class TestRunSarcasm:
    def test_sarcasm_detected(self):
        mock_model = MagicMock(return_value=[{"label": "irony", "score": 0.88}])
        with patch("ai.pipeline.analyzer.get_model", return_value=mock_model):
            from ai.pipeline.analyzer import run_sarcasm
            is_sarcastic, score = run_sarcasm("Oh great, another Monday!")
        assert is_sarcastic is True
        assert score == pytest.approx(0.88)

    def test_no_sarcasm(self):
        mock_model = MagicMock(return_value=[{"label": "non_irony", "score": 0.95}])
        with patch("ai.pipeline.analyzer.get_model", return_value=mock_model):
            from ai.pipeline.analyzer import run_sarcasm
            is_sarcastic, score = run_sarcasm("I love sunny days!")
        assert is_sarcastic is False


# ── Instant Risk ─────────────────────────────────────────────

class TestInstantRisk:
    def test_positive_sentiment_low_risk(self):
        from ai.pipeline.analyzer import compute_instant_risk
        risk = compute_instant_risk(0.85, "joy", 0.9, False)
        assert risk < 0.15

    def test_negative_sentiment_high_risk(self):
        from ai.pipeline.analyzer import compute_instant_risk
        risk = compute_instant_risk(-0.90, "sadness", 0.85, False)
        assert risk > 0.4

    def test_sarcasm_boosts_risk_on_positive_sentiment(self):
        from ai.pipeline.analyzer import compute_instant_risk
        risk_plain    = compute_instant_risk(0.5, "neutral", 0.6, False)
        risk_sarcastic = compute_instant_risk(0.5, "neutral", 0.6, True)
        assert risk_sarcastic > risk_plain

    def test_risk_always_in_bounds(self):
        from ai.pipeline.analyzer import compute_instant_risk
        for s in [-1.0, -0.5, 0.0, 0.5, 1.0]:
            risk = compute_instant_risk(s, "neutral", 0.5, False)
            assert 0.0 <= risk <= 1.0


# ── Feed Score ───────────────────────────────────────────────

class TestFeedScore:
    def test_positive_gets_higher_score(self):
        from ai.pipeline.analyzer import compute_feed_score
        high = compute_feed_score(0.9, 0.02, 100, 20)
        low  = compute_feed_score(-0.9, 0.8,  0,  0)
        assert high > low

    def test_score_in_bounds(self):
        from ai.pipeline.analyzer import compute_feed_score
        for s, r in [(-1, 1), (0, 0.5), (1, 0)]:
            score = compute_feed_score(s, r)
            assert 0.0 <= score <= 1.0

    def test_high_risk_reduces_score(self):
        from ai.pipeline.analyzer import compute_feed_score
        base   = compute_feed_score(0.0, 0.0)
        risky  = compute_feed_score(0.0, 0.9)
        assert risky < base


# ── Full Pipeline (mocked) ───────────────────────────────────

class TestAnalyzeText:
    def _patch_all(self):
        """Context manager that mocks all three HF models."""
        sentiment_mock = MagicMock(return_value=[{"label": "LABEL_0", "score": 0.82}])
        emotion_mock   = MagicMock(return_value=[{"label": "sadness", "score": 0.75}])
        sarcasm_mock   = MagicMock(return_value=[{"label": "non_irony", "score": 0.9}])

        def side_effect(name):
            if name == "sentiment":
                return sentiment_mock
            if name == "emotion":
                return emotion_mock
            if name == "sarcasm":
                return sarcasm_mock
            if name == "lstm":
                m = MagicMock()
                import numpy as np
                m.predict = MagicMock(return_value=np.array([[0.65]]))
                return m
            if name == "embedder":
                embedder = MagicMock()
                embedder.encode = MagicMock(side_effect=lambda texts, normalize_embeddings=True, show_progress_bar=False: np.zeros((len(texts), 8), dtype=np.float32))
                return embedder

        return patch("ai.pipeline.analyzer.get_model", side_effect=side_effect)

    def test_returns_pipeline_result(self):
        with self._patch_all():
            from ai.pipeline.analyzer import analyze_text
            result = analyze_text("I feel really sad today")
        assert result.sentiment == "negative"
        assert result.sentiment_score < 0
        assert result.emotion == "sadness"
        assert 0.0 <= result.risk_score <= 1.0
        assert 0.0 <= result.feed_score <= 1.0

    def test_with_empty_history(self):
        with self._patch_all():
            from ai.pipeline.analyzer import analyze_text
            result = analyze_text("Some text", user_risk_history=[])
        assert result is not None

    def test_with_long_history(self):
        with self._patch_all():
            from ai.pipeline.analyzer import analyze_text
            history = [0.3, 0.4, 0.6, 0.7, 0.8, 0.75, 0.65, 0.5] * 5
            result = analyze_text("Some text", user_risk_history=history)
        assert result is not None
