"""
Advanced Skill Detection and Evidence Validation Engine.

Provides multi-domain skill taxonomy lookup, deterministic normalization,
section-aware extraction, and evidence-backed validation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# Constants & Taxonomy Loading
# ────────────────────────────────────────────────────────────────

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "data" / "skill_taxonomy.json"

class EvidenceStatus(str, Enum):
    SUPPORTED_BY_EXPERIENCE = "supported_by_experience"
    SUPPORTED_BY_PROJECT = "supported_by_project"
    SUPPORTED_BY_CERTIFICATION = "supported_by_certification"
    MENTIONED_IN_SKILLS_ONLY = "mentioned_in_skills_only"
    MENTIONED_WITHOUT_STRONG_EVIDENCE = "mentioned_without_strong_evidence"


# Confidence definitions:
# 0.95: Supported by both project and experience
# 0.90: Supported by work experience bullet points
# 0.85: Supported by concrete project implementation
# 0.80: Supported by formal certification/license
# 0.40: Listed only in a skills inventory section
# 0.30: Mentioned in summary/education without project/work evidence
CONFIDENCE_MAP = {
    "multi_evidence": 0.95,
    EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value: 0.90,
    EvidenceStatus.SUPPORTED_BY_PROJECT.value: 0.85,
    EvidenceStatus.SUPPORTED_BY_CERTIFICATION.value: 0.80,
    EvidenceStatus.MENTIONED_IN_SKILLS_ONLY.value: 0.40,
    EvidenceStatus.MENTIONED_WITHOUT_STRONG_EVIDENCE.value: 0.30,
}

# Generic verbs and false-positive terms to suppress
GENERIC_ACTION_VERBS: Set[str] = {
    "developed", "develop", "developing", "built", "build", "building",
    "created", "create", "creating", "designed", "design", "designing",
    "implemented", "implement", "implementing", "managed", "manage", "managing",
    "led", "lead", "leading", "analyzed", "analyze", "analyzing",
    "calculated", "calculate", "calculating", "maintained", "maintain",
    "coordinated", "coordinate", "collaborated", "collaborate",
    "established", "establish", "optimized", "optimize", "generated", "generate",
    "assisted", "assist", "evaluated", "evaluate", "monitored", "monitor",
    "supported", "support", "delivered", "deliver", "improved", "improve",
}

# Organizations, locations, and degree stopwords to avoid false matches
FALSE_POSITIVE_TERMS: Set[str] = {
    "university", "college", "school", "institute", "academy", "polytechnic",
    "bachelor", "master", "doctor", "phd", "btech", "mtech", "bsc", "msc",
    "company", "corporation", "corp", "inc", "ltd", "llc", "technologies",
    "solutions", "enterprises", "consulting", "services", "global", "systems",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "present", "current",
}


def load_raw_taxonomy() -> Dict[str, Dict[str, Any]]:
    """Load taxonomy from JSON file with graceful fallback."""
    if TAXONOMY_PATH.exists():
        try:
            with open(TAXONOMY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load taxonomy from {TAXONOMY_PATH}: {e}")
    return {}


# Global taxonomy instance
RAW_TAXONOMY = load_raw_taxonomy()


# ────────────────────────────────────────────────────────────────
# Skill Normalization & Disambiguation Maps
# ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TaxonomyEntry:
    canonical: str
    category: str
    aliases: List[str]
    compiled_pattern: re.Pattern


class SkillTaxonomyRegistry:
    """Fast, deterministic registry for multi-domain skill normalization."""

    def __init__(self, raw_data: Optional[Dict[str, Dict[str, Any]]] = None):
        self._entries: List[TaxonomyEntry] = []
        self._alias_to_canonical: Dict[str, str] = {}
        self._canonical_to_category: Dict[str, str] = {}
        self._init_registry(raw_data or RAW_TAXONOMY)

    def _init_registry(self, raw_data: Dict[str, Dict[str, Any]]) -> None:
        entries = []
        for category, skills in raw_data.items():
            for key, info in skills.items():
                canonical = info["canonical"]
                aliases = info.get("aliases", [])
                self._canonical_to_category[canonical] = category

                # Canonical itself is an alias
                all_aliases = list(set([key, canonical] + aliases))
                for alias in all_aliases:
                    self._alias_to_canonical[alias.lower().strip()] = canonical

                # Compile a pattern for this skill
                # We sort aliases by length descending so longer phrases match first
                sorted_aliases = sorted(all_aliases, key=len, reverse=True)
                pattern_parts = []
                for a in sorted_aliases:
                    esc = re.escape(a.strip())
                    # Disambiguation guards for very short terms
                    if a.lower() in ("r", "c"):
                        # Must be surrounded by whitespace, commas, or parentheses, and not part of R&D
                        pattern_parts.append(r'(?<![a-zA-Z0-9&])' + esc + r'(?![a-zA-Z0-9&])')
                    elif a.lower() == "go":
                        # Match Go programming language, Golang, or 'Go,' in technical contexts
                        pattern_parts.append(r'\b(?:golang|go(?:\s+programming|\s+language)?)\b')
                    elif a.lower() == "c++":
                        pattern_parts.append(r'(?<![a-zA-Z0-9])(?:c\+\+|cpp)(?![a-zA-Z0-9])')
                    elif a.lower() == "c#":
                        pattern_parts.append(r'(?<![a-zA-Z0-9])(?:c#|csharp)(?![a-zA-Z0-9])')
                    elif a.lower() == ".net":
                        pattern_parts.append(r'(?<![a-zA-Z0-9])\.net(?![a-zA-Z0-9])')
                    elif a.lower() == "nlp":
                        # Match NLP as standalone acronym
                        pattern_parts.append(r'\b(?:nlp|natural\s+language\s+processing)\b')
                    elif len(a) <= 2:
                        pattern_parts.append(r'(?<![a-zA-Z0-9])' + esc + r'(?![a-zA-Z0-9])')
                    else:
                        pattern_parts.append(r'\b' + esc + r'\b')

                full_pattern = re.compile("|".join(pattern_parts), re.IGNORECASE)
                entries.append(TaxonomyEntry(
                    canonical=canonical,
                    category=category,
                    aliases=aliases,
                    compiled_pattern=full_pattern,
                ))

        self._entries = entries

    @property
    def entries(self) -> List[TaxonomyEntry]:
        return self._entries

    def get_category(self, canonical: str) -> str:
        return self._canonical_to_category.get(canonical, "other")

    def normalize(self, term: str, context: str = "") -> str:
        """Deterministic normalization of any skill term or alias."""
        clean = term.strip().lower()
        if not clean:
            return ""

        # Context-aware check for NLP
        if clean == "nlp":
            if context and any(w in context.lower() for w in ("neuro", "psychology", "hypnosis", "therapy")):
                return "Neuro-Linguistic Programming"
            return "Natural Language Processing (NLP)"

        # Direct map
        if clean in self._alias_to_canonical:
            return self._alias_to_canonical[clean]

        # Fuzzy punctuation stripping for normalized match
        compressed = re.sub(r'[\s\-_.]', '', clean)
        for alias, canon in self._alias_to_canonical.items():
            if re.sub(r'[\s\-_.]', '', alias) == compressed:
                return canon

        # Clean title-cased fallback
        return term.strip()


# Global Registry Instance
REGISTRY = SkillTaxonomyRegistry()


# ────────────────────────────────────────────────────────────────
# Structured Skill Mentions & Records
# ────────────────────────────────────────────────────────────────

@dataclass
class SkillMention:
    section: str
    text: str
    term_matched: str


@dataclass
class ValidatedSkillRecord:
    skill: str
    canonical: str
    category: str
    mentions: List[SkillMention] = field(default_factory=list)
    evidence_status: str = EvidenceStatus.MENTIONED_WITHOUT_STRONG_EVIDENCE.value
    confidence: float = 0.30
    evidence_type: str = "none"
    supporting_evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill": self.canonical,
            "canonical": self.canonical,
            "category": self.category,
            "mentions": [
                {
                    "section": m.section,
                    "text": m.text,
                    "term_matched": m.term_matched,
                }
                for m in self.mentions
            ],
            "evidence_status": self.evidence_status,
            "confidence": round(self.confidence, 2),
            "evidence_type": self.evidence_type,
            "supporting_evidence": self.supporting_evidence,
        }


# ────────────────────────────────────────────────────────────────
# Section-Aware Skill Extraction & Evidence Validation
# ────────────────────────────────────────────────────────────────

def extract_skills_from_structured_sections(
    sections: Dict[str, str],
    header_text: str = "",
    registry: Optional[SkillTaxonomyRegistry] = None,
) -> Dict[str, ValidatedSkillRecord]:
    """
    Extract skills from structured resume sections, linking each mention to its
    source section, original text, and context snippet.
    """
    reg = registry or REGISTRY
    records: Dict[str, ValidatedSkillRecord] = {}

    # Map of section names to process
    active_sections = dict(sections)
    if header_text and "header" not in active_sections:
        active_sections["header"] = header_text

    for section_name, content in active_sections.items():
        if not content or not content.strip():
            continue

        # Split content into lines / sentences to provide exact snippets
        lines = [ln.strip() for ln in content.split("\n") if ln.strip()]

        for entry in reg.entries:
            canonical = entry.canonical
            category = entry.category

            for line in lines:
                # Filter out generic action verbs standing alone or headings
                if line.lower() in GENERIC_ACTION_VERBS:
                    continue

                # Check if the line matches the skill pattern
                match = entry.compiled_pattern.search(line)
                if match:
                    matched_term = match.group().strip()

                    # False positive guard: Discard match if it's an institution/company stopword
                    # e.g., "Amazon" when it's just "Amazon Web Services" or "Google" when "Google Cloud"
                    line_lower = line.lower()
                    if matched_term.lower() in ("r", "c") and any(fp in line_lower for fp in ("r&d", "c/o", "c.c.")):
                        continue

                    # Record the mention
                    if canonical not in records:
                        records[canonical] = ValidatedSkillRecord(
                            skill=canonical,
                            canonical=canonical,
                            category=category,
                        )

                    records[canonical].mentions.append(
                        SkillMention(
                            section=section_name,
                            text=line,
                            term_matched=matched_term,
                        )
                    )

    # Classify evidence status and compute confidence for each detected skill
    for record in records.values():
        sections_found = {m.section for m in record.mentions}
        
        has_experience = "experience" in sections_found
        has_project = "projects" in sections_found
        has_certification = "certifications" in sections_found
        has_skills = "skills" in sections_found

        # Find best supporting evidence text
        best_evidence = ""
        evidence_type = "none"

        if has_experience and has_project:
            record.evidence_status = EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value
            record.confidence = CONFIDENCE_MAP["multi_evidence"]
            evidence_type = "experience_and_project"
            # Prefer experience bullet as primary supporting text
            exp_mentions = [m.text for m in record.mentions if m.section == "experience"]
            best_evidence = exp_mentions[0] if exp_mentions else ""
        elif has_experience:
            record.evidence_status = EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value
            record.confidence = CONFIDENCE_MAP[EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value]
            evidence_type = "experience"
            exp_mentions = [m.text for m in record.mentions if m.section == "experience"]
            best_evidence = exp_mentions[0] if exp_mentions else ""
        elif has_project:
            record.evidence_status = EvidenceStatus.SUPPORTED_BY_PROJECT.value
            record.confidence = CONFIDENCE_MAP[EvidenceStatus.SUPPORTED_BY_PROJECT.value]
            evidence_type = "project"
            proj_mentions = [m.text for m in record.mentions if m.section == "projects"]
            best_evidence = proj_mentions[0] if proj_mentions else ""
        elif has_certification:
            record.evidence_status = EvidenceStatus.SUPPORTED_BY_CERTIFICATION.value
            record.confidence = CONFIDENCE_MAP[EvidenceStatus.SUPPORTED_BY_CERTIFICATION.value]
            evidence_type = "certification"
            cert_mentions = [m.text for m in record.mentions if m.section == "certifications"]
            best_evidence = cert_mentions[0] if cert_mentions else ""
        elif has_skills and len(sections_found) == 1:
            record.evidence_status = EvidenceStatus.MENTIONED_IN_SKILLS_ONLY.value
            record.confidence = CONFIDENCE_MAP[EvidenceStatus.MENTIONED_IN_SKILLS_ONLY.value]
            evidence_type = "skills_list"
            skill_mentions = [m.text for m in record.mentions if m.section == "skills"]
            best_evidence = skill_mentions[0] if skill_mentions else ""
        else:
            record.evidence_status = EvidenceStatus.MENTIONED_WITHOUT_STRONG_EVIDENCE.value
            record.confidence = CONFIDENCE_MAP[EvidenceStatus.MENTIONED_WITHOUT_STRONG_EVIDENCE.value]
            evidence_type = "summary_or_education"
            best_evidence = record.mentions[0].text if record.mentions else ""

        record.evidence_type = evidence_type
        record.supporting_evidence = best_evidence

    return records


# ────────────────────────────────────────────────────────────────
# Full Evidence Validation Service
# ────────────────────────────────────────────────────────────────

def validate_skills_and_evidence(
    skills_list: List[str],
    structured_sections: Dict[str, str],
    projects: Optional[List[Dict[str, Any]]] = None,
    experience_entries: Optional[List[Dict[str, Any]]] = None,
    header_text: str = "",
    registry: Optional[SkillTaxonomyRegistry] = None,
) -> Dict[str, Any]:
    """
    Main entry point for multi-domain skill detection and evidence validation.

    Guarantees backward compatibility with existing ATS scorer while enriching
    output with structured records, validation statuses, and category metrics.
    """
    reg = registry or REGISTRY

    # 1. Extract all skills across sections
    detected_records = extract_skills_from_structured_sections(
        sections=structured_sections,
        header_text=header_text,
        registry=reg,
    )

    # 2. Also ensure every explicitly provided skill in skills_list is represented
    # and normalized
    normalized_input_skills: Dict[str, str] = {}
    for s in skills_list:
        clean_s = s.strip()
        if clean_s:
            canon = reg.normalize(clean_s)
            normalized_input_skills[canon] = clean_s

    # Combine input skills with detected skills
    all_canonicals = set(detected_records.keys()) | set(normalized_input_skills.keys())

    # Build targets from structured project and experience entries if sections dict is sparse
    candidate_targets: List[Tuple[str, str]] = []
    if projects:
        for p in projects:
            title = p.get("title", "Project")
            desc = p.get("description", "")
            candidate_targets.append((title, f"{title} {desc}"))
    if experience_entries:
        for e in experience_entries:
            role = e.get("job_title", "Experience")
            company = e.get("company", "")
            desc = e.get("description", "")
            candidate_targets.append((f"{role} at {company}".strip(), f"{role} {company} {desc}"))

    validated_skills_for_scorer = []
    unvalidated_skills_for_scorer = []
    skill_project_mapping = {}
    detailed_records = []
    category_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {
        EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value: 0,
        EvidenceStatus.SUPPORTED_BY_PROJECT.value: 0,
        EvidenceStatus.SUPPORTED_BY_CERTIFICATION.value: 0,
        EvidenceStatus.MENTIONED_IN_SKILLS_ONLY.value: 0,
        EvidenceStatus.MENTIONED_WITHOUT_STRONG_EVIDENCE.value: 0,
    }

    # Evaluate each canonical skill
    for canon in sorted(all_canonicals):
        if canon in detected_records:
            rec = detected_records[canon]
        else:
            # Skill was in skills_list but not caught in section regexes
            category = reg.get_category(canon)
            rec = ValidatedSkillRecord(
                skill=canon,
                canonical=canon,
                category=category,
                mentions=[SkillMention(section="skills", text=canon, term_matched=canon)],
                evidence_status=EvidenceStatus.MENTIONED_IN_SKILLS_ONLY.value,
                confidence=0.40,
                evidence_type="skills_list",
                supporting_evidence=canon,
            )

        # Check candidate targets for extra evidence if available
        matched_projects = []
        for name, text in candidate_targets:
            # Word-boundary check for this skill
            canon_esc = re.escape(canon.lower())
            if re.search(r'\b' + canon_esc + r'\b', text.lower()):
                matched_projects.append(name)

        if matched_projects and rec.evidence_status in (
            EvidenceStatus.MENTIONED_IN_SKILLS_ONLY.value,
            EvidenceStatus.MENTIONED_WITHOUT_STRONG_EVIDENCE.value,
        ):
            rec.evidence_status = EvidenceStatus.SUPPORTED_BY_PROJECT.value
            rec.confidence = 0.85
            rec.evidence_type = "project"
            rec.supporting_evidence = matched_projects[0]

        is_validated = rec.evidence_status in (
            EvidenceStatus.SUPPORTED_BY_EXPERIENCE.value,
            EvidenceStatus.SUPPORTED_BY_PROJECT.value,
            EvidenceStatus.SUPPORTED_BY_CERTIFICATION.value,
        )

        supporting_names = matched_projects or [
            m.text[:60] for m in rec.mentions if m.section in ("projects", "experience", "certifications")
        ]

        if is_validated:
            validated_skills_for_scorer.append({
                "skill": canon,
                "projects": supporting_names or ["Demonstrated in Resume"],
                "similarity": round(rec.confidence, 2),
                "category": rec.category,
                "status": rec.evidence_status,
            })
            skill_project_mapping[canon] = supporting_names or ["Demonstrated in Resume"]
        else:
            unvalidated_skills_for_scorer.append(canon)
            skill_project_mapping[canon] = []

        rec_dict = rec.to_dict()
        detailed_records.append(rec_dict)

        # Increment counts
        category_counts[rec.category] = category_counts.get(rec.category, 0) + 1
        status_counts[rec.evidence_status] = status_counts.get(rec.evidence_status, 0) + 1

    total_skills = len(all_canonicals)
    val_percentage = (
        len(validated_skills_for_scorer) / total_skills
        if total_skills > 0
        else 0.0
    )

    # Validation score (scaled out of max 15.0)
    validation_score = round(val_percentage * 15.0, 2)

    warnings = []
    if total_skills == 0:
        warnings.append("No technical or domain-specific skills were detected.")
    elif val_percentage < 0.3:
        warnings.append(
            f"Low evidence rate: only {len(validated_skills_for_scorer)} of {total_skills} "
            "skills have verifiable project, experience, or certification evidence."
        )

    return {
        "validated_skills": validated_skills_for_scorer,
        "unvalidated_skills": unvalidated_skills_for_scorer,
        "validation_percentage": round(val_percentage, 4),
        "validation_score": validation_score,
        "skill_project_mapping": skill_project_mapping,
        "skill_records": detailed_records,
        "total_skills": total_skills,
        "validated_count": len(validated_skills_for_scorer),
        "category_counts": category_counts,
        "status_counts": status_counts,
        "warnings": warnings,
    }
