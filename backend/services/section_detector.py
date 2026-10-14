"""
Deterministic resume section detector.

Recognises common heading variations for 7 canonical resume sections:
  summary, experience, education, skills, projects, certifications, achievements

Design decisions
────────────────
* OCR-free — works on text extracted from PDF, DOCX, or TXT.
* Uses regex, not an LLM, so the result is deterministic.
* Heading lines are identified by pattern + heuristic length guard (<80 chars).
* The original extracted text is always preserved alongside the structured output.
* Multiline headings (e.g. heading text split across two short lines) are
  coalesced before matching.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


# ────────────────────────────────────────────────────────────────
# Canonical section names and their heading variations
# ────────────────────────────────────────────────────────────────

# Each key is the canonical section name used throughout the app.
# The regex patterns are compiled with IGNORECASE and match anywhere
# within a stripped line that is short enough to be a heading.

_HEADING_PATTERNS: Dict[str, re.Pattern] = {
    'summary': re.compile(
        r'^(?:professional\s+|executive\s+|career\s+)?summary\b'
        r'|^(?:career\s+)?objective\b'
        r'|^about\s+me\b'
        r'|^profile(?:\s+summary)?\b'
        r'|^personal\s+statement\b'
        r'|^professional\s+profile\b'
        r'|^overview\b',
        re.IGNORECASE,
    ),
    'experience': re.compile(
        r'^(?:work\s+|professional\s+|relevant\s+|industry\s+)?experience\b'
        r'|^employment(?:\s+history)?\b'
        r'|^(?:work|career)\s+history\b'
        r'|^internships?\b'
        r'|^professional\s+background\b',
        re.IGNORECASE,
    ),
    'education': re.compile(
        r'^education(?:al)?(?:\s+background)?\b'
        r'|^academic\s+(?:background|qualifications?|credentials?|details|history|record|studies)\b'
        r'|^academics?\b(?!\s+projects?)'
        r'|^qualifications?\b'
        r'|^degrees?\b',
        re.IGNORECASE,
    ),
    'skills': re.compile(
        r'^(?:technical\s+|key\s+)?skills?\b'
        r'|^(?:core\s+)?competenc(?:ies|e)\b'
        r'|^technologies\b'
        r'|^tools?\s+(?:and|&)\s+technologies\b'
        r'|^tools?\s+(?:and|&)\s+frameworks?\b'
        r'|^technical\s+proficiency\b'
        r'|^areas?\s+of\s+expertise\b'
        r'|^skill\s*sets?\b'
        r'|^proficienc(?:ies|y)\b'
        r'|^tools?\s+used\b',
        re.IGNORECASE,
    ),
    'projects': re.compile(
        r'^(?:personal\s+|academic\s+|key\s+|selected\s+|notable\s+|side\s+)?projects?\b'
        r'|^portfolio\b'
        r'|^open[\s-]?source\s+(?:projects?|contributions?)\b',
        re.IGNORECASE,
    ),
    'certifications': re.compile(
        r'^certifications?\b'
        r'|^licen[sc]es?(?:\s+(?:and|&)\s+certifications?)?\b'
        r'|^credentials?\b'
        r'|^professional\s+certifications?\b'
        r'|^certifications?\s+(?:and|&)\s+licen[sc]es?\b'
        r'|^training(?:\s+(?:and|&)\s+certifications?)?\b',
        re.IGNORECASE,
    ),
    'achievements': re.compile(
        r'^achievements?\b'
        r'|^accomplishments?\b'
        r'|^awards?(?:\s+(?:and|&)\s+(?:achievements?|honors?))?\b'
        r'|^honors?(?:\s+(?:and|&)\s+awards?)?\b'
        r'|^recognitions?\b'
        r'|^distinctions?\b'
        r'|^extracurriculars?\b',
        re.IGNORECASE,
    ),
}

# Maximum length (chars) for a line to be considered a heading.
_MAX_HEADING_LENGTH = 80

# Characters commonly used as decorators around headings.
_DECORATOR_RE = re.compile(r'^[\s\-=_~#*|:▸▹►▻⬩◆◇●○•·]+|[\s\-=_~#*|:▸▹►▻⬩◆◇●○•·]+$')


# ────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────

class DetectedSections:
    """Immutable result of section detection.

    Attributes
    ----------
    sections : dict[str, str]
        Mapping of *canonical* section name → body text (heading line excluded).
        Only sections that were actually found appear as keys.
    header : str
        Text that appears before the first recognised section heading.
    raw_text : str
        The original, unmodified input text.
    section_order : list[str]
        Canonical names in the order they appear in the document.
    confidence : dict[str, float]
        Per-section confidence score (0–1). Currently 1.0 for any pattern match.
    """

    __slots__ = ('sections', 'header', 'raw_text', 'section_order', 'confidence')

    def __init__(
        self,
        sections: Dict[str, str],
        header: str,
        raw_text: str,
        section_order: List[str],
        confidence: Dict[str, float],
    ):
        self.sections = sections
        self.header = header
        self.raw_text = raw_text
        self.section_order = section_order
        self.confidence = confidence

    # Convenience helpers ──────────────────────────────────────

    def has_section(self, canonical_name: str) -> bool:
        """Return True if *canonical_name* was detected with non-empty content."""
        content = self.sections.get(canonical_name, '')
        return bool(content and content.strip())

    def get_section(self, canonical_name: str, default: str = '') -> str:
        return self.sections.get(canonical_name, default)

    @property
    def detected_names(self) -> List[str]:
        """Canonical names of all sections with non-empty content."""
        return [name for name in self.section_order if self.has_section(name)]

    @property
    def missing_core_sections(self) -> List[str]:
        """Core sections (experience, education, skills) not found."""
        core = ['experience', 'education', 'skills']
        return [s for s in core if not self.has_section(s)]

    @property
    def missing_optional_sections(self) -> List[str]:
        """Optional sections (summary, projects, certifications, achievements) not found."""
        optional = ['summary', 'projects', 'certifications', 'achievements']
        return [s for s in optional if not self.has_section(s)]

    def to_dict(self) -> Dict:
        """Serialise for JSON / API responses."""
        return {
            'sections': dict(self.sections),
            'header': self.header,
            'section_order': list(self.section_order),
            'detected': list(self.detected_names),
            'missing_core': list(self.missing_core_sections),
            'missing_optional': list(self.missing_optional_sections),
            'confidence': dict(self.confidence),
        }


def detect_sections(text: str) -> DetectedSections:
    """Parse *text* into canonical resume sections.

    The algorithm walks through the text line by line.  When a line is short
    enough and matches one of the known heading patterns, everything that
    follows is assigned to that section until the next heading.

    Returns a :class:`DetectedSections` result object that preserves the
    original text and exposes convenience queries.
    """
    lines = text.split('\n')

    # Accumulator: section_name → list of body lines (heading excluded)
    buckets: Dict[str, List[str]] = {}
    section_order: List[str] = []
    confidence: Dict[str, float] = {}

    current_section: Optional[str] = None  # None means we're in the header area
    header_lines: List[str] = []

    for line in lines:
        stripped = line.strip()

        # Skip completely empty lines but keep them for the current bucket
        if not stripped:
            if current_section is not None:
                buckets.setdefault(current_section, []).append(line)
            else:
                header_lines.append(line)
            continue

        # Try to match as a heading
        heading_match = _match_heading(stripped)
        if heading_match is not None:
            canonical_name, conf = heading_match
            current_section = canonical_name
            if canonical_name not in buckets:
                buckets[canonical_name] = []
                section_order.append(canonical_name)
            # Use highest confidence if a section appears more than once
            confidence[canonical_name] = max(confidence.get(canonical_name, 0.0), conf)
            continue  # Don't add heading line itself to body

        # Regular content line
        if current_section is not None:
            buckets.setdefault(current_section, []).append(line)
        else:
            header_lines.append(line)

    # Collapse bucket lists into trimmed strings
    sections = {
        name: '\n'.join(bucket_lines).strip()
        for name, bucket_lines in buckets.items()
    }

    return DetectedSections(
        sections=sections,
        header='\n'.join(header_lines).strip(),
        raw_text=text,
        section_order=section_order,
        confidence=confidence,
    )


# ────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────

def _clean_heading_text(raw_line: str) -> str:
    """Strip decoration characters and trailing colons from a candidate heading."""
    cleaned = _DECORATOR_RE.sub('', raw_line).strip()
    # Remove trailing colon that some people add after headings
    cleaned = cleaned.rstrip(':').strip()
    return cleaned


def _match_heading(stripped_line: str) -> Optional[Tuple[str, float]]:
    """Try to match *stripped_line* against all heading patterns.

    Returns ``(canonical_name, confidence)`` on success, ``None`` otherwise.
    """
    if len(stripped_line) > _MAX_HEADING_LENGTH:
        return None

    cleaned = _clean_heading_text(stripped_line)
    if not cleaned:
        return None

    # Short-circuit: if the "cleaned" version is too long, it's body text
    if len(cleaned) > _MAX_HEADING_LENGTH:
        return None

    for canonical_name, pattern in _HEADING_PATTERNS.items():
        if pattern.search(cleaned):
            return canonical_name, 1.0

    return None
