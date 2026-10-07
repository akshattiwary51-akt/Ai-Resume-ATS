"""Tests for skill taxonomy, alias mapping, and skill matching."""
import pytest
from backend.services.skill_taxonomy import (
    normalize_skill_name,
    extract_skills_from_text,
    match_skills,
)

def test_normalize_skill_name():
    assert normalize_skill_name("k8s") == "Kubernetes"
    assert normalize_skill_name("K8S") == "Kubernetes"
    assert normalize_skill_name("postgres") == "PostgreSQL"
    assert normalize_skill_name("react.js") == "React"
    assert normalize_skill_name("reactjs") == "React"
    assert normalize_skill_name("ts") == "TypeScript"
    assert normalize_skill_name("golang") == "Go"
    assert normalize_skill_name("django rest framework") == "Django"

def test_normalize_unknown_skill_fallback():
    assert normalize_skill_name("CustomInternalTool") == "CustomInternalTool"

def test_extract_skills_from_text():
    sample_text = (
        "Full stack engineer proficient in Python, React, and Docker. "
        "Experienced in deploying to AWS using Kubernetes and managing Postgres databases."
    )
    extracted = extract_skills_from_text(sample_text)
    names = [s["name"] for s in extracted]

    assert "Python" in names
    assert "React" in names
    assert "Docker" in names
    assert "Kubernetes" in names
    assert "PostgreSQL" in names

def test_match_skills_with_aliases():
    resume_skills = ["Postgres", "K8s", "ReactJS", "Python"]
    jd_skills = ["PostgreSQL", "Kubernetes", "React", "AWS"]

    result = match_skills(resume_skills, jd_skills)
    matched_canonical = [m["skill"] for m in result["matched"]]
    missing_canonical = [m["skill"] for m in result["missing"]]

    assert "PostgreSQL" in matched_canonical
    assert "Kubernetes" in matched_canonical
    assert "React" in matched_canonical
    assert any("Amazon Web Services" in s for s in missing_canonical)
    assert result["match_percentage"] == 75.0
