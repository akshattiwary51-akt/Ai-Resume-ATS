"""Tests for AI enhancer services (bullet rewriting, cover letter, interview prep)."""
import pytest
from backend.services.ai_enhancer import (
    rewrite_bullet_point,
    generate_cover_letter,
    generate_interview_prep,
)

def test_rewrite_bullet_point_deterministic():
    weak_bullet = "helped with building an API in python"
    result = rewrite_bullet_point(weak_bullet, target_role="Backend Engineer", target_skill="Python")

    assert "rewritten" in result
    assert "action_verb" in result
    assert "critique" in result
    assert len(result["suggested_metrics"]) >= 1
    # Check that passive phrasing was improved
    assert not result["rewritten"].lower().startswith("helped with")

def test_generate_cover_letter_deterministic():
    result = generate_cover_letter(
        candidate_name="Alex Smith",
        skills=["Python", "FastAPI", "Docker", "PostgreSQL"],
        experience_highlights=["engineered microservices handling 10M requests daily"],
        job_title="Senior Backend Engineer",
        company_name="CloudScale Inc",
    )

    letter = result.get("cover_letter", "")
    assert "Alex Smith" in letter
    assert "CloudScale Inc" in letter
    assert "Senior Backend Engineer" in letter
    assert "Python" in letter

def test_generate_interview_prep():
    result = generate_interview_prep(
        skills=["Kubernetes", "PostgreSQL", "Go"],
        job_title="DevOps Engineer",
        unvalidated_skills=["AWS Lambda"],
    )

    assert result["target_role"] == "DevOps Engineer"
    assert len(result["technical_questions"]) >= 2
    assert len(result["behavioral_questions"]) >= 1
    assert len(result["unvalidated_skill_tips"]) >= 1
    assert "AWS Lambda" in result["unvalidated_skill_tips"][0]
