"""
Centralized ATS Scoring Configuration.

Defines all scoring weights, component maxima, thresholds, and penalty/bonus values.
Serves as the single source of truth across the entire platform.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ComponentMaxScores:
    """Maximum possible raw points for each category."""
    formatting: float = 20.0
    keywords: float = 25.0
    content: float = 25.0
    skill_validation: float = 15.0
    ats_compatibility: float = 15.0


@dataclass(frozen=True)
class CategoryWeights:
    """Percentage contribution of each category to the 100-point base score."""
    skills_and_keywords: float = 0.40  # 40%
    content_quality: float = 0.30      # 30%
    formatting: float = 0.15           # 15%
    ats_compatibility: float = 0.15    # 15%


@dataclass(frozen=True)
class FormattingScoringConfig:
    """Point allocations for resume formatting dimensions."""
    has_experience_pts: float = 3.0
    has_education_pts: float = 2.0
    has_skills_pts: float = 2.0
    has_summary_pts: float = 1.5
    has_projects_pts: float = 1.5
    bullet_tiers: Tuple[Tuple[int, float], ...] = (
        (15, 5.0),
        (10, 4.0),
        (5, 3.0),
        (3, 2.0),
        (1, 1.0),
    )
    sections_filled_tiers: Tuple[Tuple[int, float], ...] = (
        (4, 5.0),
        (3, 4.0),
        (2, 3.0),
        (1, 2.0),
    )


@dataclass(frozen=True)
class KeywordScoringConfig:
    """Point allocations for keyword and skill density."""
    keyword_tiers: Tuple[Tuple[int, float], ...] = (
        (20, 10.0),
        (15, 8.0),
        (10, 6.0),
        (5, 4.0),
        (3, 2.0),
    )
    skill_tiers: Tuple[Tuple[int, float], ...] = (
        (15, 10.0),
        (10, 8.0),
        (7, 6.0),
        (5, 4.0),
        (3, 2.0),
    )
    jd_match_tiers: Tuple[Tuple[float, float], ...] = (
        (0.7, 5.0),
        (0.5, 4.0),
        (0.3, 3.0),
        (0.2, 2.0),
        (0.1, 1.0),
    )
    no_jd_keyword_bonus: float = 3.0


@dataclass(frozen=True)
class ContentScoringConfig:
    """Point allocations for content, metrics, action verbs, and language quality."""
    action_verb_tiers: Tuple[Tuple[int, float], ...] = (
        (15, 10.0),
        (10, 8.0),
        (7, 6.0),
        (5, 4.0),
        (3, 2.0),
    )
    achievement_metric_tiers: Tuple[Tuple[int, float], ...] = (
        (10, 5.0),
        (7, 4.0),
        (5, 3.0),
        (3, 2.0),
        (1, 1.0),
    )
    max_grammar_pts: float = 10.0
    neutral_grammar_pts: float = 6.0


@dataclass(frozen=True)
class BonusPenaltyConfig:
    """Bonus additions and penalty deductions."""
    excellent_validation_pct_threshold: float = 0.90
    excellent_validation_bonus: float = 2.0
    good_validation_pct_threshold: float = 0.80
    good_validation_bonus: float = 1.0
    perfect_grammar_bonus: float = 1.0

    # JD missing keyword penalties
    jd_missing_severe_threshold: float = 0.70
    jd_missing_severe_penalty: float = 15.0
    jd_missing_moderate_threshold: float = 0.50
    jd_missing_moderate_penalty: float = 10.0
    jd_missing_mild_threshold: float = 0.30
    jd_missing_mild_penalty: float = 5.0


@dataclass
class ATSScoringConfig:
    """Aggregate scoring configuration for ATS analysis."""
    component_max: ComponentMaxScores = field(default_factory=ComponentMaxScores)
    weights: CategoryWeights = field(default_factory=CategoryWeights)
    formatting: FormattingScoringConfig = field(default_factory=FormattingScoringConfig)
    keywords: KeywordScoringConfig = field(default_factory=KeywordScoringConfig)
    content: ContentScoringConfig = field(default_factory=ContentScoringConfig)
    adjustments: BonusPenaltyConfig = field(default_factory=BonusPenaltyConfig)


# Canonical default scoring configuration instance
DEFAULT_SCORING_CONFIG = ATSScoringConfig()
