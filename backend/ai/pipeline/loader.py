"""
AI Model Loader — singleton pattern so models load once at startup.

Models used:
  - cardiffnlp/twitter-roberta-base-sentiment  → sentiment
  - j-hartmann/emotion-english-distilroberta-base → emotion
  - cardiffnlp/twitter-roberta-base-irony       → sarcasm/irony
  - all-MiniLM-L6-v2 (sentence-transformers)   → RAG embeddings
  - Keras LSTM (built locally)                  → temporal risk scoring
"""

import logging
import numpy as np

try:
    from transformers import pipeline as hf_pipeline
except Exception:  # pragma: no cover - optional dependency in lightweight environments
    hf_pipeline = None

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional dependency in lightweight environments
    SentenceTransformer = None

logger = logging.getLogger("mindgram.loader")

# Global model handles
_models = {}


class _FallbackClassifier:
    """Lightweight fallback used when the heavyweight ML stack is unavailable."""

    def __call__(self, text):
        return [[{"label": "neutral", "score": 0.5}]]


class _FallbackEmbedder:
    """Simple deterministic embedding fallback for local/offline use."""

    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        if isinstance(texts, str):
            texts = [texts]

        embeddings = []
        for text in texts:
            values = [0.0] * 8
            if text:
                for ch in text.lower():
                    values[ord(ch) % 8] += 1.0
                total = max(1.0, sum(values))
                values = [value / total for value in values]
            embeddings.append(values)
        return np.array(embeddings, dtype=np.float32)


class _FallbackLSTM:
    def predict(self, arr, verbose=0):
        return np.zeros((arr.shape[0], 1), dtype=np.float32)


def preload_models():
    """Load all HuggingFace + sentence-transformer models into memory."""
    logger.info("Loading sentiment model (RoBERTa)...")
    if hf_pipeline is None:
        logger.warning("transformers not available; using fallback sentiment model")
        _models["sentiment"] = _FallbackClassifier()
    else:
        try:
            _models["sentiment"] = hf_pipeline(
                "text-classification",
                model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                top_k=1,
                truncation=True,
                max_length=512,
            )
        except Exception as exc:
            logger.warning("Falling back to sentiment classifier: %s", exc)
            _models["sentiment"] = _FallbackClassifier()

    logger.info("Loading emotion model (distilRoBERTa)...")
    if hf_pipeline is None:
        logger.warning("transformers not available; using fallback emotion model")
        _models["emotion"] = _FallbackClassifier()
    else:
        try:
            _models["emotion"] = hf_pipeline(
                "text-classification",
                model="j-hartmann/emotion-english-distilroberta-base",
                top_k=1,
                truncation=True,
                max_length=512,
            )
        except Exception as exc:
            logger.warning("Falling back to emotion classifier: %s", exc)
            _models["emotion"] = _FallbackClassifier()

    logger.info("Loading sarcasm/irony model (RoBERTa)...")
    if hf_pipeline is None:
        logger.warning("transformers not available; using fallback sarcasm model")
        _models["sarcasm"] = _FallbackClassifier()
    else:
        try:
            _models["sarcasm"] = hf_pipeline(
                "text-classification",
                model="cardiffnlp/twitter-roberta-base-irony",
                top_k=1,
                truncation=True,
                max_length=512,
            )
        except Exception as exc:
            logger.warning("Falling back to sarcasm classifier: %s", exc)
            _models["sarcasm"] = _FallbackClassifier()

    logger.info("Loading sentence-transformer (MiniLM)...")
    if SentenceTransformer is None:
        logger.warning("sentence-transformers not available; using fallback embedder")
        _models["embedder"] = _FallbackEmbedder()
    else:
        try:
            _models["embedder"] = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as exc:
            logger.warning("Falling back to embedder: %s", exc)
            _models["embedder"] = _FallbackEmbedder()

    logger.info("Building / loading Keras LSTM risk model...")
    try:
        from ai.pipeline.lstm_risk import build_or_load_lstm
        _models["lstm"] = build_or_load_lstm()
    except Exception as exc:
        logger.warning("Falling back to LSTM risk model: %s", exc)
        _models["lstm"] = _FallbackLSTM()

    logger.info("✅ AI pipeline ready (using fallbacks where required).")


def get_model(name: str):
    if name not in _models:
        raise RuntimeError(f"Model '{name}' not loaded. Call preload_models() first.")
    return _models[name]
