"""
Numbness / Dissociation Detector
---------------------------------
Replaces the earlier regex-based detect_numbness_signal() with embedding
similarity, reusing the same SentenceTransformers model already loaded for
the RAG pipeline (see ai/pipeline/loader.py -> get_model("embedder")).

Why embedding similarity instead of keywords:
Regex/keyword lists only catch phrasings you've already written down. A post
like "I feel like a ghost in my own life" or "everything's on mute" describes
the same dissociative/numb pattern as "everything feels unreal" but shares no
keywords with it. Embedding similarity compares meaning, not exact wording,
so it generalizes to phrasings never seen at reference-set authoring time.

Explainability is preserved: for every flagged post we return the closest-
matching reference sentence and its similarity score, so the Decision Agent
/ rule matrix (and your presentation) can still point to *why* something
was flagged, without needing exact string matches.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from ai.pipeline.loader import get_model

# ---------------------------------------------------------------------------
# Reference sentence set
# ---------------------------------------------------------------------------
# NOTE: This is a small, hand-curated starter set (not a substitute for a
# real corpus). It exists so the detector works out of the box and so the
# similarity-threshold logic can be tuned/tested immediately.
#
# TODO (tracked in project notes): replace / expand this with sentences
# sampled from an established corpus (e.g. Reddit SuicideWatch/depression
# dataset, CLPsych shared task data) filtered down to dissociation/numbness-
# specific posts, so the reference embeddings reflect real linguistic
# diversity rather than sentences one person wrote in one sitting. Aim for
# at least a few hundred examples once real data is sourced, clustered down
# to a representative subset if the reference set gets large (to keep
# inference cheap) using k-means centroids over the embeddings.
NUMBNESS_REFERENCE_SENTENCES = [
    "Everything around me feels unreal, like I'm watching my life from outside.",
    "I feel disconnected from everyone, even the people I love.",
    "I don't recognize myself anymore when I look in the mirror.",
    "It's like I'm going through the motions without actually feeling anything.",
    "The tears just stopped coming, even when I wanted to cry.",
    "I feel numb, like nothing really reaches me anymore.",
    "Nothing excites me the way it used to, everything feels flat.",
    "I smile because it's easier than explaining that I feel empty inside.",
    "I say I'm fine so often that I've started to believe it myself.",
    "Everything feels like it's happening on mute, distant and far away.",
    "I feel like a stranger in my own life.",
    "It's like watching myself from a distance, not really here.",
    "I can't remember the last time I felt something strongly, good or bad.",
    "I'm just going through the motions, day after day, feeling nothing.",
    "It feels like I'm floating outside of my own body.",
    "I feel like a ghost walking through my own life.",
    "Everyone thinks I'm okay because I've gotten so good at pretending.",
    "I'm holding it together on the outside, but I feel hollow inside.",
    "I feel like I'm falling apart quietly while everyone else sees me smiling.",
    "There's a fog between me and everything that used to matter to me.",
]

_SIMILARITY_THRESHOLD = 0.55  # tune against validation examples before shipping


@dataclass
class NumbnessResult:
    flagged: bool
    strength: float          # ∈ [0, 1], derived from max cosine similarity
    closest_reference: str | None
    similarity: float        # raw cosine similarity of best match


class NumbnessDetector:
    """
    Loads once, reused across requests. Embeds the reference set at
    construction time so per-request cost is a single embedding + a
    vectorized cosine-similarity comparison against a small matrix.
    """

    def __init__(self, reference_sentences: list[str] | None = None,
                 threshold: float = _SIMILARITY_THRESHOLD):
        self.reference_sentences = reference_sentences or NUMBNESS_REFERENCE_SENTENCES
        self.threshold = threshold
        self._embedder = get_model("embedder")  # existing SentenceTransformers model
        self._reference_embeddings = self._embedder.encode(
            self.reference_sentences, normalize_embeddings=True
        )

    def score(self, text: str) -> NumbnessResult:
        if not text or not text.strip():
            return NumbnessResult(False, 0.0, None, 0.0)

        query_embedding = self._embedder.encode([text], normalize_embeddings=True)[0]

        # Cosine similarity == dot product since embeddings are normalized.
        similarities = self._reference_embeddings @ query_embedding
        best_idx = int(np.argmax(similarities))
        best_score = float(similarities[best_idx])

        if best_score < self.threshold:
            return NumbnessResult(False, 0.0, None, round(best_score, 4))

        # Map similarity range [threshold, 1.0] -> strength range [0.3, 1.0]
        # so a borderline match doesn't carry the same weight as a near-exact
        # semantic match.
        span = max(1e-6, 1.0 - self.threshold)
        strength = 0.3 + 0.7 * ((best_score - self.threshold) / span)
        strength = round(min(1.0, strength), 4)

        return NumbnessResult(
            flagged=True,
            strength=strength,
            closest_reference=self.reference_sentences[best_idx],
            similarity=round(best_score, 4),
        )


# Module-level singleton so pipeline.py doesn't re-embed the reference set
# on every call. Loader/model caching pattern mirrors get_model() elsewhere
# in the codebase.
_detector: NumbnessDetector | None = None


def detect_numbness_signal(text: str) -> tuple[bool, float]:
    """
    Drop-in replacement for the old regex-based function of the same name.
    Returns (flagged, strength) to keep pipeline.py's call site unchanged.
    Use get_numbness_detail() instead if you also want the matched reference
    sentence / similarity score for logging or the Decision Agent's
    explanation surface.
    """
    global _detector
    if _detector is None:
        _detector = NumbnessDetector()
    result = _detector.score(text)
    return result.flagged, result.strength


def get_numbness_detail(text: str) -> NumbnessResult:
    """Full result including the closest matching reference sentence, for
    explainability in logs / the Decision Agent / analytics."""
    global _detector
    if _detector is None:
        _detector = NumbnessDetector()
    return _detector.score(text)
