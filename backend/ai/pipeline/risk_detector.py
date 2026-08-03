"""
Depression / Suicide-Risk Detector
------------------------------------
Scope, deliberately narrow:
This module is a SCREENING AID that feeds the Decision Agent's rule matrix.
It does not diagnose, and its output must never be shown to the user as a
score or label — consistent with MindGram's silent, non-stigmatizing design.
Its only job is to make sure unambiguous high-risk language is never diluted
by ML averaging, and to give the Decision Agent a graduated signal for
everything short of that.

Two-tier design:

1. HARD-FLOOR BYPASS (rule-based, deliberately NOT ML)
   A small set of unambiguous high-risk patterns (explicit intent, means,
   farewell/goodbye language) bypass instant_risk / LSTM blending entirely
   and route straight to the highest intervention tier. This is intentional:
   a subtle model average must never be allowed to soften an unambiguous
   signal. Kept as explicit rules (not embeddings) because this tier needs
   to be maximally conservative and 100% auditable — a false negative here
   is the worst-case failure mode for this whole project.

2. GRADUATED TIER (embedding similarity)
   Everything else - passive ideation, hopelessness, depressive language
   short of explicit intent - is scored via similarity to reference
   sentences, same pattern as numbness_detector.py, reusing the shared
   embedder.

IMPORTANT / TODO before this goes anywhere near real users:
- The reference sentences below are a small hand-curated starter set, not a
  substitute for a real corpus. Before relying on this for anything beyond
  local testing, replace/expand using an established dataset such as:
    * Reddit SuicideWatch + depression subreddit corpus (commonly used in
      CLPsych-style research; search "Suicide and Depression Detection"
      dataset)
    * CLPsych shared task data (requires a data use agreement - check
      access requirements before using)
  Sample a large, diverse set from these, embed them, and either keep the
  full embedding matrix (if inference cost allows) or reduce via k-means
  cluster centroids per risk tier.
- This module's thresholds are unvalidated placeholders. Before citing any
  precision/recall numbers in your writeup, evaluate against a held-out
  labeled sample - ideally from the same corpus used for the reference set,
  not the same sentences used to build it.
- Get a second pair of eyes (advisor, or someone with relevant clinical
  background) on the hard-floor phrase list specifically. Missing an
  unambiguous phrase there is a more serious failure than a missed
  borderline case in the graduated tier.
"""

from __future__ import annotations

import re
import numpy as np
from dataclasses import dataclass
from enum import Enum
from ai.pipeline.loader import get_model


class RiskTier(str, Enum):
    NONE = "none"
    LOW = "low"                 # mild hopelessness / low mood language
    MODERATE = "moderate"       # passive ideation ("what's the point")
    HIGH = "high"                # active ideation without explicit means/plan
    CRITICAL = "critical"        # hard-floor bypass: explicit intent/means/farewell


@dataclass
class RiskDetectionResult:
    tier: RiskTier
    score: float                 # ∈ [0,1], meaningful only for LOW..HIGH
    hard_floor_triggered: bool
    matched_phrase: str | None   # for hard-floor tier
    closest_reference: str | None  # for graduated tier
    similarity: float | None


# ---------------------------------------------------------------------------
# TIER: CRITICAL — hard-floor bypass patterns
# ---------------------------------------------------------------------------
# Deliberately explicit and conservative. These should read as unambiguous
# to a human reviewer with no context. Err on the side of over-inclusion —
# false positives here cost a gentle check-in prompt; false negatives cost
# far more.
_HARD_FLOOR_PATTERNS = [
    r"\bkill myself\b",
    r"\bend my life\b",
    r"\bwant(?:ed)? to die\b",
    r"\bdon'?t want to (?:be alive|live anymore|exist anymore)\b",
    r"\bsuicidal?\b",
    r"\bplan(?:ning)? to (?:kill|hurt|end)\b",
    r"\bgoodbye (?:everyone|world|forever)\b",
    r"\bthis is (?:my )?(?:last|final) (?:post|goodbye|message)\b",
    r"\bwon'?t be (?:here|around) (?:much longer|anymore)\b",
    r"\bbetter off without me\b",
    r"\beveryone would be better off if i (?:was|were) gone\b",
    r"\bno (?:reason|point) (?:to|in) (?:living|continuing|going on)\b",
]
_HARD_FLOOR_RE = re.compile("|".join(_HARD_FLOOR_PATTERNS), flags=re.IGNORECASE)


def check_hard_floor(text: str) -> tuple[bool, str | None]:
    """Returns (triggered, matched_phrase). Rule-based and intentionally so —
    see module docstring for rationale."""
    if not text:
        return False, None
    match = _HARD_FLOOR_RE.search(text)
    if match:
        return True, match.group(0)
    return False, None


# ---------------------------------------------------------------------------
# TIER: LOW / MODERATE / HIGH — embedding similarity
# ---------------------------------------------------------------------------
# Placeholder starter set — see module docstring TODO. Organized by tier so
# the closest match also tells you which tier it nudges toward.
_REFERENCE_BY_TIER: dict[RiskTier, list[str]] = {
    RiskTier.LOW: [
        "I've been feeling really low and hopeless lately.",
        "Nothing feels worth doing anymore, I just feel stuck.",
        "I feel like a burden to everyone around me.",
        "I'm so tired of feeling this way every single day.",
    ],
    RiskTier.MODERATE: [
        "Sometimes I wonder what's even the point of going on like this.",
        "I feel like nothing would really change if I just wasn't here.",
        "I keep thinking that everyone would move on fine without me.",
        "I don't see things getting better, no matter what I do.",
        "I feel like I'm just waiting for something to end.",
    ],
    RiskTier.HIGH: [
        "I keep thinking about not being here anymore.",
        "I don't know how much longer I can keep doing this.",
        "Some nights I think everyone would be relieved if I disappeared.",
        "I've been having thoughts about just ending it all.",
    ],
}

_TIER_ORDER = [RiskTier.LOW, RiskTier.MODERATE, RiskTier.HIGH]
_TIER_BASE_SCORE = {RiskTier.LOW: 0.35, RiskTier.MODERATE: 0.6, RiskTier.HIGH: 0.85}
_SIMILARITY_THRESHOLD = 0.5


class RiskDetector:
    def __init__(self, threshold: float = _SIMILARITY_THRESHOLD):
        self.threshold = threshold
        self._embedder = get_model("embedder")

        self._tier_sentences: list[str] = []
        self._tier_labels: list[RiskTier] = []
        for tier in _TIER_ORDER:
            for sentence in _REFERENCE_BY_TIER[tier]:
                self._tier_sentences.append(sentence)
                self._tier_labels.append(tier)

        self._reference_embeddings = self._embedder.encode(
            self._tier_sentences, normalize_embeddings=True
        )

    def score(self, text: str) -> RiskDetectionResult:
        # Hard floor check first — always, regardless of embedding result.
        triggered, phrase = check_hard_floor(text)
        if triggered:
            return RiskDetectionResult(
                tier=RiskTier.CRITICAL,
                score=1.0,
                hard_floor_triggered=True,
                matched_phrase=phrase,
                closest_reference=None,
                similarity=None,
            )

        if not text or not text.strip():
            return RiskDetectionResult(RiskTier.NONE, 0.0, False, None, None, None)

        query_embedding = self._embedder.encode([text], normalize_embeddings=True)[0]
        similarities = self._reference_embeddings @ query_embedding
        best_idx = int(np.argmax(similarities))
        best_score = float(similarities[best_idx])

        if best_score < self.threshold:
            return RiskDetectionResult(RiskTier.NONE, 0.0, False, None, None,
                                        round(best_score, 4))

        matched_tier = self._tier_labels[best_idx]
        base = _TIER_BASE_SCORE[matched_tier]
        # Scale slightly within tier based on how strong the match was.
        span = max(1e-6, 1.0 - self.threshold)
        adjust = 0.1 * ((best_score - self.threshold) / span)
        final_score = round(min(1.0, base + adjust), 4)

        return RiskDetectionResult(
            tier=matched_tier,
            score=final_score,
            hard_floor_triggered=False,
            matched_phrase=None,
            closest_reference=self._tier_sentences[best_idx],
            similarity=round(best_score, 4),
        )


_detector: RiskDetector | None = None


def detect_depression_suicide_risk(text: str) -> RiskDetectionResult:
    global _detector
    if _detector is None:
        _detector = RiskDetector()
    return _detector.score(text)
