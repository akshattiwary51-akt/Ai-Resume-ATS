"""
Unit and regression tests for Phase 3: Advanced Skill Detection and Evidence Validation.
"""

import pytest
from backend.services.skill_validator import (
    REGISTRY,
    EvidenceStatus,
    extract_skills_from_structured_sections,
    validate_skills_and_evidence,
)
from backend.services.skill_taxonomy import (
    normalize_skill_name,
    extract_skills_from_text,
    match_skills,
)
from backend.services.ats_scorer import validate_skills_with_projects


# ────────────────────────────────────────────────────────────────
# 1. Multi-Domain Normalization & Alias Tests
# ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw_term,expected_canonical", [
    ("js", "JavaScript"),
    ("JS", "JavaScript"),
    ("typescript", "TypeScript"),
    ("TS", "TypeScript"),
    ("postgres", "PostgreSQL"),
    ("pgsql", "PostgreSQL"),
    ("MS Excel", "Microsoft Excel"),
    ("excel", "Microsoft Excel"),
    ("powerbi", "Power BI"),
    ("k8s", "Kubernetes"),
    ("golang", "Go"),
    ("django rest framework", "Django"),
    ("drf", "Django"),
    ("aws", "Amazon Web Services (AWS)"),
    ("gcp", "Google Cloud Platform (GCP)"),
    ("financial models", "Financial Modeling"),
    ("gaap", "Financial Reporting"),
    ("qbo", "QuickBooks"),
    ("six sigma", "Process Improvement"),
    ("scrum master", "Agile Methodology"),
    ("pmp", "Project Management"),
])
def test_multi_domain_normalization(raw_term, expected_canonical):
    assert normalize_skill_name(raw_term) == expected_canonical


def test_context_aware_nlp_normalization():
    tech_context = "Built sentiment analysis pipeline with NLP and transformers."
    assert normalize_skill_name("nlp", context=tech_context) == "Natural Language Processing (NLP)"

    psych_context = "Certified practitioner of NLP and hypnotherapy."
    assert normalize_skill_name("nlp", context=psych_context) == "Neuro-Linguistic Programming"


def test_deduplication_of_normalized_skills():
    resume_skills = ["JS", "JavaScript", "js", "Postgres", "PostgreSQL", "pgsql"]
    normalized = list({normalize_skill_name(s) for s in resume_skills})
    assert len(normalized) == 2
    assert "JavaScript" in normalized
    assert "PostgreSQL" in normalized


# ────────────────────────────────────────────────────────────────
# 2. Software Resume: Supported vs Skills-Only Mentions
# ────────────────────────────────────────────────────────────────

def test_software_resume_evidence_validation():
    sections = {
        "summary": "Full Stack Software Engineer with 4 years building web services.",
        "skills": "Python, FastAPI, SQL, Docker, Redis",
        "experience": (
            "Senior Backend Engineer at CloudTech (2022 - Present)\n"
            "- Architected microservices with Python and FastAPI handling 10k req/sec.\n"
            "- Managed deployment containers using Docker on Kubernetes."
        ),
        "projects": (
            "Distributed Key-Value Store\n"
            "- Implemented a distributed caching layer using Redis."
        ),
        "certifications": "AWS Certified Solutions Architect",
    }

    res = validate_skills_and_evidence(
        skills_list=["Python", "FastAPI", "SQL", "Docker", "Redis"],
        structured_sections=sections,
    )

    records = {r["skill"]: r for r in res["skill_records"]}

    # Python & FastAPI -> Supported by experience
    assert records["Python"]["evidence_status"] == EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value
    assert records["Python"]["confidence"] >= 0.90
    assert "FastAPI" in records
    assert records["FastAPI"]["evidence_status"] == EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value

    # Redis -> Supported by project
    assert records["Redis"]["evidence_status"] == EvidenceStatus.SUPPORTED_BY_PROJECT.value
    assert records["Redis"]["confidence"] >= 0.85

    # SQL -> Mentioned in skills section only (no bullet evidence)
    assert records["SQL"]["evidence_status"] == EvidenceStatus.MENTIONED_IN_SKILLS_ONLY.value
    assert records["SQL"]["confidence"] <= 0.50
    assert "SQL" in res["unvalidated_skills"]


# ────────────────────────────────────────────────────────────────
# 3. Non-Software Domain: Accounting & Finance Resume
# ────────────────────────────────────────────────────────────────

def test_accounting_finance_resume_evidence_validation():
    sections = {
        "summary": "Senior Accountant with 7 years of financial management experience.",
        "skills": "Financial Reporting, QuickBooks, Microsoft Excel, Budgeting, Payroll",
        "experience": (
            "Senior Accountant at Global FinCorp\n"
            "- Led annual budgeting process and monthly financial reporting under GAAP standards.\n"
            "- Processed bi-weekly payroll for 250+ employees using QuickBooks."
        ),
        "education": "B.S. in Accounting, State University",
        "certifications": "CPA License",
    }

    res = validate_skills_and_evidence(
        skills_list=["Financial Reporting", "QuickBooks", "Microsoft Excel", "Budgeting", "Payroll"],
        structured_sections=sections,
    )

    records = {r["skill"]: r for r in res["skill_records"]}

    # Financial Reporting & Budgeting & Payroll -> Supported by experience
    assert records["Financial Reporting"]["evidence_status"] == EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value
    assert records["Budgeting & Forecasting"]["evidence_status"] == EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value
    assert records["Payroll Administration"]["evidence_status"] == EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value
    assert records["QuickBooks"]["evidence_status"] == EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value

    # Excel only in skills list
    assert records["Microsoft Excel"]["evidence_status"] == EvidenceStatus.MENTIONED_IN_SKILLS_ONLY.value

    # Check category counts
    cat_counts = res["category_counts"]
    assert "finance_and_accounting" in cat_counts
    assert cat_counts["finance_and_accounting"] >= 3


# ────────────────────────────────────────────────────────────────
# 4. False-Positive and Disambiguation Guards
# ────────────────────────────────────────────────────────────────

def test_generic_verbs_not_extracted_as_skills():
    text = (
        "Experienced professional who developed, analyzed, and calculated core metrics.\n"
        "Managed cross-functional teams and optimized operational throughput."
    )
    extracted = extract_skills_from_text(text)
    names = [s["name"].lower() for s in extracted]

    assert "developed" not in names
    assert "analyzed" not in names
    assert "calculated" not in names
    assert "managed" not in names
    assert "optimized" not in names


def test_company_and_university_names_not_confused_as_skills():
    sections = {
        "experience": "Warehouse Associate at Amazon Logistics Fulfillment Center.",
        "education": "Studied Business Administration at Columbia College.",
    }
    extracted = extract_skills_from_structured_sections(sections)

    # Should NOT extract AWS simply because "Amazon" appeared in employer name
    assert "Amazon Web Services (AWS)" not in extracted


def test_short_terms_word_boundaries():
    # "Good", "Right", "Company", "Target" should NOT match Go, R, C
    text = (
        "Good communication skills with the right attitude.\n"
        "Worked at Target corporation providing customer care.\n"
        "Responsible for R&D initiatives."
    )
    extracted = extract_skills_from_text(text)
    names = [s["name"] for s in extracted]

    assert "Go" not in names
    assert "C" not in names


# ────────────────────────────────────────────────────────────────
# 5. Zero-Skills & Edge Cases
# ────────────────────────────────────────────────────────────────

def test_zero_skills_graceful_handling():
    res = validate_skills_and_evidence(
        skills_list=[],
        structured_sections={},
    )
    assert res["total_skills"] == 0
    assert res["validated_count"] == 0
    assert res["validation_percentage"] == 0.0
    assert res["validation_score"] == 0.0
    assert len(res["warnings"]) >= 1


def test_empty_sections_handling():
    res = validate_skills_and_evidence(
        skills_list=["Python", "Docker"],
        structured_sections={"skills": "Python, Docker"},
    )
    assert res["total_skills"] == 2
    assert res["validated_count"] == 0
    assert res["validation_percentage"] == 0.0
    assert len(res["unvalidated_skills"]) == 2


def test_unicode_and_multiline_text():
    sections = {
        "skills": "Python • Docker — PostgreSQL",
        "experience": (
            "Développeur chez TechCo:\n"
            "• Implemented multi-lingual API with Python 🐍\n"
            "• Managed database schemas on PostgreSQL."
        ),
    }
    res = validate_skills_and_evidence(
        skills_list=["Python", "Docker", "PostgreSQL"],
        structured_sections=sections,
    )
    records = {r["skill"]: r for r in res["skill_records"]}
    assert records["Python"]["evidence_status"] == EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value
    assert records["PostgreSQL"]["evidence_status"] == EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value
    assert records["Docker"]["evidence_status"] == EvidenceStatus.MENTIONED_IN_SKILLS_ONLY.value


# ────────────────────────────────────────────────────────────────
# 6. ATS Scorer Integration Compatibility
# ────────────────────────────────────────────────────────────────

def test_ats_scorer_validate_skills_with_projects_contract():
    skills = ["Python", "Docker", "FastAPI"]
    projects = [
        {"title": "FastAPI Web App", "description": "Built using Python and FastAPI."}
    ]
    experience = [
        {"job_title": "Developer", "company": "Tech", "description": "Used Docker daily."}
    ]

    res = validate_skills_with_projects(
        skills=skills,
        projects=projects,
        experience_entries=experience,
    )

    # Core backward compatibility keys
    assert "validated_skills" in res
    assert "unvalidated_skills" in res
    assert "validation_percentage" in res
    assert "skill_project_mapping" in res
    assert "validation_score" in res

    # Phase 3 enriched keys
    assert "skill_records" in res
    assert "category_counts" in res
    assert "status_counts" in res
    assert "warnings" in res

    # Validation calculations
    assert res["validation_percentage"] == 1.0
    assert res["validation_score"] == 15.0
    assert len(res["validated_skills"]) == 3
    assert len(res["unvalidated_skills"]) == 0
