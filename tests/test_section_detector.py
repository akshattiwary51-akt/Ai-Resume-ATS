"""
Unit and regression tests for section_detector and Phase 2 resume structure detection.
"""
import pytest
from backend.services.section_detector import detect_sections, DetectedSections
from backend.services.groq_parser import parse_resume_deterministic
from backend.services.feedback_engine import analyze_issues
from backend.services.recommendation_engine import generate_formatting_recommendations


# ────────────────────────────────────────────────────────────────
# 1. Standard Heading Recognition (All 7 Canonical Sections)
# ────────────────────────────────────────────────────────────────

def test_detect_all_seven_canonical_sections():
    resume_text = """John Doe
john.doe@example.com

SUMMARY
Passionate software engineer with 5 years experience.

EXPERIENCE
Software Engineer at Acme Corp (2020 - Present)
- Built microservices in Python and FastAPI.

EDUCATION
B.S. in Computer Science, State University, 2019

SKILLS
Python, Docker, SQL, Git, AWS

PROJECTS
Task Manager App
- Built with React and Node.js.

CERTIFICATIONS
AWS Certified Solutions Architect

ACHIEVEMENTS
First place in State Hackathon 2021
"""
    detected = detect_sections(resume_text)

    assert isinstance(detected, DetectedSections)
    assert detected.has_section("summary")
    assert detected.has_section("experience")
    assert detected.has_section("education")
    assert detected.has_section("skills")
    assert detected.has_section("projects")
    assert detected.has_section("certifications")
    assert detected.has_section("achievements")

    assert "John Doe" in detected.header
    assert "john.doe@example.com" in detected.header
    assert "Passionate software engineer" in detected.get_section("summary")
    assert "Acme Corp" in detected.get_section("experience")
    assert "State University" in detected.get_section("education")
    assert "Python, Docker" in detected.get_section("skills")
    assert "Task Manager App" in detected.get_section("projects")
    assert "AWS Certified Solutions Architect" in detected.get_section("certifications")
    assert "First place in State Hackathon" in detected.get_section("achievements")

    assert detected.missing_core_sections == []
    assert detected.missing_optional_sections == []
    assert len(detected.detected_names) == 7


# ────────────────────────────────────────────────────────────────
# 2. Heading Variations Recognition
# ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("heading,expected_canonical", [
    ("Summary", "summary"),
    ("Professional Summary", "summary"),
    ("Career Objective", "summary"),
    ("Objective", "summary"),
    ("About Me", "summary"),
    ("Profile Summary", "summary"),
    ("Personal Statement", "summary"),
    ("Executive Summary", "summary"),
    ("Career Summary", "summary"),
    ("Overview", "summary"),
    ("Experience", "experience"),
    ("Work Experience", "experience"),
    ("Professional Experience", "experience"),
    ("Employment History", "experience"),
    ("Work History", "experience"),
    ("Career History", "experience"),
    ("Internships", "experience"),
    ("Relevant Experience", "experience"),
    ("Industry Experience", "experience"),
    ("Education", "education"),
    ("Educational Background", "education"),
    ("Academic Background", "education"),
    ("Academic Qualifications", "education"),
    ("Qualifications", "education"),
    ("Degrees", "education"),
    ("Academic Credentials", "education"),
    ("Skills", "skills"),
    ("Technical Skills", "skills"),
    ("Core Competencies", "skills"),
    ("Technologies", "skills"),
    ("Tools & Technologies", "skills"),
    ("Tools and Frameworks", "skills"),
    ("Technical Proficiency", "skills"),
    ("Key Skills", "skills"),
    ("Areas of Expertise", "skills"),
    ("Skill Set", "skills"),
    ("Projects", "projects"),
    ("Personal Projects", "projects"),
    ("Academic Projects", "projects"),
    ("Key Projects", "projects"),
    ("Selected Projects", "projects"),
    ("Portfolio", "projects"),
    ("Open Source Contributions", "projects"),
    ("Side Projects", "projects"),
    ("Certifications", "certifications"),
    ("Licenses and Certifications", "certifications"),
    ("Professional Certifications", "certifications"),
    ("Credentials", "certifications"),
    ("Training & Certifications", "certifications"),
    ("Achievements", "achievements"),
    ("Accomplishments", "achievements"),
    ("Awards & Honors", "achievements"),
    ("Honors & Awards", "achievements"),
    ("Recognitions", "achievements"),
    ("Distinctions", "achievements"),
    ("Extracurriculars", "achievements"),
])
def test_heading_variations(heading, expected_canonical):
    text = f"""Header Name
email@domain.com

{heading}
Details and content under this section heading.
"""
    detected = detect_sections(text)
    assert detected.has_section(expected_canonical), f"Failed to detect {heading} as {expected_canonical}"
    assert "Details and content" in detected.get_section(expected_canonical)


# ────────────────────────────────────────────────────────────────
# 3. Inconsistent Capitalization and Formatting
# ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("heading", [
    "work experience",
    "WORK EXPERIENCE",
    "Work Experience",
    "wOrK eXpErIeNcE",
    "SKILLS",
    "skills",
    "Skills",
    "sKiLLs",
    "EDUCATION",
    "education",
    "Education",
])
def test_capitalization_insensitivity(heading):
    text = f"""Jane Doe

{heading}
Line item 1
Line item 2
"""
    detected = detect_sections(text)
    detected_keys = detected.detected_names
    assert len(detected_keys) == 1
    assert "Line item 1" in detected.get_section(detected_keys[0])


# ────────────────────────────────────────────────────────────────
# 4. Decorated Headings and Trailing Colons
# ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("decorated_heading,expected_canonical", [
    ("--- WORK EXPERIENCE ---", "experience"),
    ("=== Education ===", "education"),
    ("*** SKILLS ***", "skills"),
    ("## Professional Summary ##", "summary"),
    ("• Key Projects •", "projects"),
    ("Experience:", "experience"),
    ("Technical Skills :", "skills"),
    ("▸ Certifications", "certifications"),
    ("◆ Achievements ◆", "achievements"),
])
def test_decorated_headings(decorated_heading, expected_canonical):
    text = f"""Contact Info

{decorated_heading}
Relevant details here.
"""
    detected = detect_sections(text)
    assert detected.has_section(expected_canonical)
    assert "Relevant details here." in detected.get_section(expected_canonical)


# ────────────────────────────────────────────────────────────────
# 5. Empty / Blank Sections
# ────────────────────────────────────────────────────────────────

def test_empty_section_handling():
    text = """Candidate Name

EXPERIENCE

EDUCATION
B.S. Computer Science

SKILLS
Python, SQL
"""
    detected = detect_sections(text)

    # Experience heading was present but body is empty
    assert not detected.has_section("experience")
    assert "experience" in detected.missing_core_sections
    assert detected.has_section("education")
    assert detected.has_section("skills")
    assert "experience" not in detected.detected_names


def test_all_empty_sections():
    text = """Only Header Here

SUMMARY

SKILLS

EXPERIENCE
"""
    detected = detect_sections(text)
    assert detected.detected_names == []
    assert set(detected.missing_core_sections) == {"experience", "education", "skills"}


# ────────────────────────────────────────────────────────────────
# 6. False Positive / Length Guard
# ────────────────────────────────────────────────────────────────

def test_long_line_containing_keyword_not_detected_as_heading():
    text = """John Doe
john@example.com

SUMMARY
I am a software engineer with extensive experience in architecting distributed systems and cloud backends.

EXPERIENCE
Lead Developer at Alpha Inc.
- Spearheaded development of our core payment service.
"""
    detected = detect_sections(text)
    assert detected.has_section("summary")
    assert detected.has_section("experience")
    # Verify the long sentence was preserved in summary, not treated as another experience heading
    summary_text = detected.get_section("summary")
    assert "extensive experience in architecting" in summary_text
    assert "Alpha Inc" in detected.get_section("experience")


# ────────────────────────────────────────────────────────────────
# 7. Document Order and Header Preservation
# ────────────────────────────────────────────────────────────────

def test_section_order_and_header():
    text = """Alice Smith
Frontend Developer
alice@example.com

SKILLS
TypeScript, React, CSS

PROJECTS
Personal Portfolio Site

EDUCATION
B.A. in Design, 2020

EXPERIENCE
UI Engineer at WebAgency
"""
    detected = detect_sections(text)

    assert detected.section_order == ["skills", "projects", "education", "experience"]
    assert detected.header.strip() == "Alice Smith\nFrontend Developer\nalice@example.com"
    assert detected.raw_text == text


# ────────────────────────────────────────────────────────────────
# 8. DetectedSections API and Serialization
# ────────────────────────────────────────────────────────────────

def test_detected_sections_api_and_dict():
    text = """Bob
bob@email.com

SKILLS
Go, Docker

EXPERIENCE
DevOps Engineer
"""
    detected = detect_sections(text)

    assert detected.get_section("skills") == "Go, Docker"
    assert detected.get_section("nonexistent", default="N/A") == "N/A"
    assert "education" in detected.missing_core_sections
    assert "summary" in detected.missing_optional_sections

    d = detected.to_dict()
    assert isinstance(d, dict)
    assert "sections" in d
    assert "header" in d
    assert "section_order" in d
    assert "detected" in d
    assert "missing_core" in d
    assert "missing_optional" in d
    assert "confidence" in d
    assert d["sections"]["skills"] == "Go, Docker"
    assert "education" in d["missing_core"]


# ────────────────────────────────────────────────────────────────
# 9. Integration with Groq Parser
# ────────────────────────────────────────────────────────────────

def test_groq_parser_includes_detected_sections():
    sample = """Jane Doe
jane.doe@email.com

Professional Summary
Experienced backend engineer.

Skills
Python, FastAPI, Docker

Work Experience
Senior Engineer at TechCo
- Built distributed storage service.

Education
B.S. in Software Engineering
"""
    parsed = parse_resume_deterministic(sample)

    assert "_detected_sections" in parsed
    detected = parsed["_detected_sections"]
    assert isinstance(detected, DetectedSections)
    assert detected.has_section("summary")
    assert detected.has_section("skills")
    assert detected.has_section("experience")
    assert detected.has_section("education")


# ────────────────────────────────────────────────────────────────
# 10. Regression: Never mark section as missing when parser found it
# ────────────────────────────────────────────────────────────────

def test_feedback_engine_honors_detected_sections():
    """Ensure feedback engine does NOT flag missing experience even if body lacks common buzzwords."""
    text = """Resume
EXPERIENCE
Contributed to proprietary internal tooling at a private firm.
"""
    detected = detect_sections(text)
    assert detected.has_section("experience")

    # Pass detected_sections to analyze_issues
    issues = analyze_issues(
        resume_text=text,
        parsed_resume={"experience": []},
        skills=[],
        projects=[],
        action_verbs=[],
        skill_validation={},
        scores={},
        detected_sections=detected,
    )

    issue_titles = [getattr(i, "issue_title", "") for i in issues]
    assert "Missing Work Experience Section" not in issue_titles


def test_recommendation_engine_honors_detected_sections():
    """Ensure recommendation engine does NOT recommend adding a section that exists."""
    text = """Resume
SKILLS
Python, PyTorch

PROJECTS
Image classifier tool using PyTorch.

EDUCATION
B.Sc in Computing
"""
    detected = detect_sections(text)
    assert detected.has_section("projects")
    assert detected.has_section("education")
    assert detected.has_section("skills")

    recs = generate_formatting_recommendations(
        score_results={"formatting_score": 15.0},
        sections=detected.sections,
        detected_sections=detected,
    )

    rec_titles = [getattr(r, "title", "") for r in recs]
    assert "Add a Projects Section" not in rec_titles
    assert "Add an Education Section" not in rec_titles
    assert "Add a Skills Section" not in rec_titles
