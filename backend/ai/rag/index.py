"""
RAG System: FAISS + SentenceTransformers
Retrieves supportive mental health suggestions based on user context.
"""

import numpy as np
import logging
import json
import os
from typing import List

from ai.pipeline.loader import get_model

logger = logging.getLogger("mindgram.rag")

# Mental health knowledge base — curated supportive suggestions
KNOWLEDGE_BASE = [
    # Sadness / depression context
    {"id": 1, "context": "feeling sad lonely depressed hopeless",
     "suggestion": "It's okay to feel sad sometimes. Consider journaling your feelings, taking a short walk outside, or reaching out to someone you trust. Small acts of self-care can make a difference."},
    {"id": 2, "context": "feeling down low energy unmotivated worthless",
     "suggestion": "You deserve kindness — especially from yourself. Try the 5-4-3-2-1 grounding technique: name 5 things you see, 4 you hear, 3 you can touch, 2 you smell, 1 you taste."},
    {"id": 3, "context": "depression mental health struggle grief loss",
     "suggestion": "Grief and sadness are natural responses to difficulty. Speaking with a counsellor or therapist can provide a safe, judgment-free space to process emotions."},

    # Anxiety context
    {"id": 4, "context": "anxious worried nervous panic overthinking stress",
     "suggestion": "When anxiety peaks, try box breathing: inhale 4 counts, hold 4, exhale 4, hold 4. Repeat 4 times. It activates the parasympathetic nervous system and calms the body."},
    {"id": 5, "context": "overwhelmed too much pressure can't cope anxiety",
     "suggestion": "Break large tasks into tiny steps. Focus only on the very next action. Progress — not perfection — builds momentum and reduces overwhelm."},

    # Anger context
    {"id": 6, "context": "angry frustrated rage irritated furious",
     "suggestion": "Anger is a signal, not a verdict. Try the STOP technique: Stop, Take a breath, Observe your feelings, Proceed mindfully. Physical movement like a brisk walk can also help release tension."},
    {"id": 7, "context": "resentment conflict argument fight hurt anger",
     "suggestion": "Before responding in anger, give yourself 24 hours. Writing unsent letters can help process feelings without escalating conflict."},

    # Fear context
    {"id": 8, "context": "scared afraid fear frightened insecure",
     "suggestion": "Fear narrows our focus. Try to identify whether the fear is present-moment (respond now) or anticipatory (future-focused, likely catastrophising). Most feared outcomes don't occur."},

    # Positive reinforcement
    {"id": 9, "context": "happy joyful grateful thankful content proud",
     "suggestion": "Savour this moment of positivity. Research shows writing 3 specific things you're grateful for each day can significantly increase long-term wellbeing."},
    {"id": 10, "context": "motivated inspired energetic optimistic excited",
     "suggestion": "Channel this energy into a meaningful goal. Setting a concrete intention now — while motivation is high — increases follow-through significantly."},

    # Crisis / high risk
    {"id": 11, "context": "hopeless suicidal crisis want to die can't go on",
     "suggestion": "You are not alone, and help is available right now. Please reach out to iCall India (9152987821), Vandrevala Foundation (1860-2662-345), or text 'HELLO' to 741741. You matter."},
    {"id": 12, "context": "self harm hurting myself cutting pain",
     "suggestion": "Please reach out to a trusted person or professional immediately. iCall: 9152987821. Your pain is real and deserves care — from a trained professional who can truly help."},

    # Loneliness / social context
    {"id": 13, "context": "lonely isolated alone no friends no one cares",
     "suggestion": "Loneliness is more common than it appears — many people feel this way. Consider joining a community group, volunteering, or trying an online hobby community to rebuild connection gradually."},
    {"id": 14, "context": "social media comparison jealousy envy not good enough",
     "suggestion": "Social media shows highlights, not reality. Try a 24-hour social media break. Use the time for an activity that makes you feel genuinely competent or connected."},

    # Sleep / fatigue
    {"id": 15, "context": "can't sleep insomnia tired exhausted fatigue",
     "suggestion": "Poor sleep amplifies every negative emotion. Try maintaining a consistent sleep schedule, avoiding screens 1 hour before bed, and using a 10-minute body-scan meditation before sleep."},

    # General wellness
    {"id": 16, "context": "burnout work stress overworked no balance",
     "suggestion": "Burnout is your mind-body's distress signal. Schedule deliberate recovery time — even 15 minutes of non-productive rest daily reduces cortisol significantly over weeks."},
    {"id": 17, "context": "mindfulness meditation calm peace present",
     "suggestion": "Even 5 minutes of mindfulness daily reshapes neural pathways over time. Apps like Insight Timer (free) offer guided sessions for beginners."},
    {"id": 18, "context": "relationship breakup heartbreak rejection",
     "suggestion": "Heartbreak activates the same brain regions as physical pain — your feelings are real and valid. Allow yourself to grieve without judgment. Time, support, and gentle self-care are the path forward."},
    {"id": 19, "context": "eating disorder body image food weight",
     "suggestion": "If food or body image feels consuming, please speak with a professional. iCall (9152987821) can refer you to specialist support. You deserve a healthy relationship with your body."},
    {"id": 20, "context": "identity purpose meaning lost confused direction",
     "suggestion": "Feeling lost about identity or purpose is a deeply human experience. Exploring values-based exercises (like the VIA Character Strengths survey — free online) can provide helpful clarity."},
]

# Global RAG index and metadata
_index = None
_documents = []
_use_faiss = False


class _FallbackRAGIndex:
    def __init__(self, embeddings: np.ndarray):
        self.embeddings = embeddings
        self.ntotal = embeddings.shape[0]

    def search(self, query_vec: np.ndarray, top_k: int):
        # query_vec shape: (n_queries, dim)
        scores = self.embeddings @ query_vec.T
        # faiss returns top-k distances and indices for each query
        indices = np.argsort(-scores, axis=0)[:top_k].T
        top_scores = np.take_along_axis(scores.T, indices, axis=1)
        return top_scores, indices


def build_rag_index():
    """Build FAISS index from knowledge base."""
    global _index, _documents, _use_faiss

    embedder = get_model("embedder")
    texts = [doc["context"] for doc in KNOWLEDGE_BASE]
    embeddings = embedder.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    embeddings = np.array(embeddings, dtype=np.float32)
    dim = embeddings.shape[1]

    try:
        import faiss
    except ImportError:
        logger.warning("faiss not installed; using numpy fallback RAG index")
        _index = _FallbackRAGIndex(embeddings)
        _use_faiss = False
    else:
        _index = faiss.IndexFlatIP(dim)  # Inner product = cosine similarity on normalized vectors
        _index.add(embeddings)
        _use_faiss = True

    _documents = KNOWLEDGE_BASE
    logger.info(f"RAG index built: {len(_documents)} documents, dim={dim}, faiss={_use_faiss}")


def retrieve_suggestion(user_context: str, top_k: int = 1) -> str:
    """
    Given a user context string, retrieve the most relevant mental health suggestion.
    """
    if _index is None:
        return "Take care of yourself. Reach out to a trusted person if you need support."

    embedder = get_model("embedder")
    
    query_vec = embedder.encode([user_context], normalize_embeddings=True)
    query_vec = np.array(query_vec, dtype=np.float32)

    scores, indices = _index.search(query_vec, top_k)

    if len(indices[0]) == 0:
        return "Remember: it's okay to ask for help. Small steps forward still count."

    best_idx = int(indices[0][0])
    return _documents[best_idx]["suggestion"]


def retrieve_top_k(user_context: str, top_k: int = 3) -> List[str]:
    """Return multiple diverse suggestions."""
    if _index is None:
        return []

    embedder = get_model("embedder")

    query_vec = embedder.encode([user_context], normalize_embeddings=True)
    query_vec = np.array(query_vec, dtype=np.float32)

    scores, indices = _index.search(query_vec, top_k)
    return [_documents[int(i)]["suggestion"] for i in indices[0] if i >= 0]
