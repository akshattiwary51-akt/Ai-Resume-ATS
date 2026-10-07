"""Tests for ATS scoring algorithms, privacy checks, and bonuses/penalties."""
import pytest
from backend.services.ats_scorer import (
    _tier_score,
    _calc_formatting_score,
    _calc_keywords_score,
    _calc_content_score,
    _calc_ats_compatibility_score,
    calculate_overall_score,
    generate_strengths,
)

def test_tier_score():
    tiers = [(10, 5.0), (5, 3.0), (1, 1.0)]
    assert _tier_score(15, tiers) == 5.0
    assert _tier_score(7, tiers) == 3.0
    assert _tier_score(2, tiers) == 1.0
    assert _tier_score(0, tiers) == 0.0

def test_calc_formatting_score():
    parsed = {
        "experience": [{"job_title": "Engineer", "description": "Developed backend systems."}],
        "education": [{"degree": "BS CS", "institution": "Tech University"}],
        "skills": ["Python", "Docker", "SQL", "Git"],
        "professional_summary": "Experienced engineer specializing in cloud architectures.",
        "projects": [{"title": "Project A", "description": "Built search engine."}],
    }
    text = "• Developed backend\n• Optimized DB\n• Built APIs"
    score = _calc_formatting_score(parsed, text)
    assert 10.0 <= score <= 20.0

def test_grammar_unavailable_no_bonus():
    """Verify that unavailable grammar does NOT award unearned perfect grammar bonus."""
    grammar_results = {
        "total_errors": 0,
        "_component_status": "unavailable",
        "checked": False,
    }
    location_results = {
        "penalty_applied": 0.0,
        "privacy_risk": "none",
    }
    skill_validation = {
        "validation_percentage": 0.85,
        "validation_score": 12.0,
    }
    parsed = {
        "experience": [{"job_title": "Dev", "description": "Code"}],
        "education": [],
        "skills": ["Python"],
        "professional_summary": "",
        "projects": [],
    }

    scores = calculate_overall_score(
        text="Sample resume text",
        parsed_resume=parsed,
        skills=["Python"],
        keywords=["Python"],
        action_verbs=["developed"],
        skill_validation_results=skill_validation,
        grammar_results=grammar_results,
        location_results=location_results,
    )

    assert "perfect_grammar" not in scores["bonuses"]

def test_generate_strengths_handles_empty():
    empty_scores = {
        "formatting_score": 5.0,
        "keywords_score": 5.0,
        "content_score": 5.0,
        "skill_validation_score": 5.0,
        "ats_compatibility_score": 5.0,
    }
    strengths = generate_strengths(empty_scores, {}, {"checked": False, "total_errors": 0})
    assert len(strengths) >= 1
