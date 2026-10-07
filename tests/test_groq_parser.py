"""Tests for groq_parser fallback parsing and JSON handling."""
import pytest
from backend.services.groq_parser import (
    parse_resume_deterministic,
    _parse_jd_deterministic,
    _try_parse_json,
    _validate_resume_result,
)

SAMPLE_RESUME = """
Jane Doe
jane.doe@email.com | 555-123-4567 | linkedin.com/in/janedoe | github.com/janedoe

Professional Summary
Senior Software Engineer with 6+ years of experience designing scalable microservices.

Skills
Python, TypeScript, FastAPI, React, Docker, Kubernetes, PostgreSQL, AWS, Git

Experience
Senior Backend Engineer at TechCorp
- Designed and deployed high-throughput event processing pipelines using Kafka and Python.
- Optimized PostgreSQL queries reducing latency by 35%.
- Mentored 4 junior developers and led code review sessions.

Education
B.S. in Computer Science, University of California, 2018

Projects
Cloud Monitor Tool
Built an open-source monitoring dashboard using React and FastAPI.
"""

def test_try_parse_json_markdown():
    wrapped = "```json\n{\"skills\": [\"Python\"]}\n```"
    result = _try_parse_json(wrapped)
    assert result == {"skills": ["Python"]}

    plain = "{\"skills\": [\"Python\"]}"
    assert _try_parse_json(plain) == {"skills": ["Python"]}

def test_fallback_resume_parser():
    parsed = parse_resume_deterministic(SAMPLE_RESUME)
    assert isinstance(parsed, dict)
    assert parsed.get("email") == "jane.doe@email.com"
    assert "janedoe" in parsed.get("github", "")
    assert len(parsed.get("skills", [])) >= 3
    assert any("python" in s.lower() for s in parsed.get("skills", []))
    assert len(parsed.get("action_verbs", [])) >= 1

def test_fallback_jd_parser():
    sample_jd = """
    Software Engineer - Backend
    Responsibilities:
    Build scalable APIs with Python, FastAPI, and PostgreSQL.
    Requirements:
    - 3+ years experience in Python and Docker
    - Strong database design skills
    """
    parsed = _parse_jd_deterministic(sample_jd)
    assert isinstance(parsed, dict)
    assert any("python" in s.lower() for s in parsed.get("required_skills", []))
    assert len(parsed.get("keywords", [])) >= 1

def test_validate_resume_result():
    incomplete = {"skills": "not_a_list"}
    validated = _validate_resume_result(incomplete)
    assert isinstance(validated["skills"], list)
    assert isinstance(validated["experience"], list)
    assert isinstance(validated["education"], list)
