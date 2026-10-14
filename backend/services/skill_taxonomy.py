"""
Skill Taxonomy and Alias Normalization Engine.

Maps variations, acronyms, and abbreviations to canonical skill names,
categorizes skills across multiple technical and business domains,
and matches skills across resumes and job descriptions.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.services.skill_validator import (
    RAW_TAXONOMY,
    REGISTRY,
    extract_skills_from_structured_sections,
    load_raw_taxonomy,
)

# Friendly display names for taxonomy categories
CATEGORY_DISPLAY_NAMES = {
    "programming_languages": "Languages",
    "frameworks_and_libraries": "Frameworks & Libraries",
    "databases": "Databases",
    "cloud_and_devops": "Cloud & DevOps",
    "ai_and_machine_learning": "AI & Machine Learning",
    "data_analytics_and_bi": "Data Analytics & BI",
    "software_engineering_tools": "Software Tools & Testing",
    "finance_and_accounting": "Finance & Accounting",
    "business_operations": "Business Operations",
    "office_productivity": "Productivity & Office",
    "project_management": "Project Management",
    "communication_and_leadership": "Leadership & Communication",
}

# Build flat SKILL_TAXONOMY dictionary for backward compatibility with routes and legacy callers
SKILL_TAXONOMY: Dict[str, Dict[str, Any]] = {}

for cat_key, skills_dict in RAW_TAXONOMY.items():
    cat_display = CATEGORY_DISPLAY_NAMES.get(cat_key, cat_key.replace("_", " ").title())
    for skill_key, skill_info in skills_dict.items():
        SKILL_TAXONOMY[skill_key] = {
            "canonical": skill_info["canonical"],
            "category": cat_display,
            "aliases": skill_info.get("aliases", []),
        }

# Reverse lookup map: alias_lower -> canonical_name
_ALIAS_LOOKUP: Dict[str, str] = {}
for key, data in SKILL_TAXONOMY.items():
    canonical = data["canonical"]
    _ALIAS_LOOKUP[key] = canonical
    _ALIAS_LOOKUP[canonical.lower()] = canonical
    for alias in data["aliases"]:
        _ALIAS_LOOKUP[alias.lower()] = canonical


def normalize_skill_name(skill: str, context: str = "") -> str:
    """
    Given any skill variation, return its canonical name if known;
    otherwise return cleanly trimmed/capitalized skill.
    """
    return REGISTRY.normalize(skill, context=context)


def extract_skills_from_text(text: str) -> List[Dict[str, str]]:
    """
    Scan text using taxonomy patterns to extract all detected technical and domain skills.
    Returns list of dicts: [{'name': 'PostgreSQL', 'category': 'Databases', 'matched_as': 'postgres'}]
    """
    records = extract_skills_from_structured_sections({"body": text}, header_text="")
    results: List[Dict[str, str]] = []

    for canon, rec in records.items():
        cat_display = CATEGORY_DISPLAY_NAMES.get(rec.category, rec.category.replace("_", " ").title())
        matched_as = rec.mentions[0].term_matched if rec.mentions else canon
        results.append({
            "name": canon,
            "category": cat_display,
            "matched_as": matched_as,
        })

    return sorted(results, key=lambda x: (x["category"], x["name"]))


def match_skills(resume_skills: List[str], jd_skills: List[str]) -> Dict[str, Any]:
    """
    Compare resume skills against JD skills using canonical normalization.
    Returns matched, missing, and additional skill lists.
    """
    resume_canonical_map = {normalize_skill_name(s): s for s in resume_skills if s.strip()}
    jd_canonical_map = {normalize_skill_name(s): s for s in jd_skills if s.strip()}

    matched = []
    missing = []

    for canonical, original_jd in jd_canonical_map.items():
        if canonical in resume_canonical_map:
            matched.append({
                "skill": canonical,
                "resume_term": resume_canonical_map[canonical],
                "jd_term": original_jd,
            })
        else:
            missing.append({
                "skill": canonical,
                "jd_term": original_jd,
            })

    additional = [
        canonical for canonical in resume_canonical_map.keys()
        if canonical not in jd_canonical_map
    ]

    total_jd = len(jd_canonical_map)
    match_pct = round((len(matched) / total_jd * 100), 1) if total_jd > 0 else 100.0

    return {
        "matched": matched,
        "missing": missing,
        "additional": additional,
        "match_percentage": match_pct,
        "matched_count": len(matched),
        "missing_count": len(missing),
        "total_required": total_jd,
    }
