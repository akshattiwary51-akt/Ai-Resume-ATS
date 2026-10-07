from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class ComponentScores(BaseModel):
    formatting: float
    keywords: float
    content: float
    skill_validation: float
    ats_compatibility: float

class JDComparison(BaseModel):
    match_percentage: float
    semantic_similarity: float
    matched_keywords: List[str]
    missing_keywords: List[str]
    skills_gap: List[str]

class SkillValidationDetails(BaseModel):
    validated: List[Dict[str, Any]] = []       # [{'skill': str, 'projects': [str]}]
    unvalidated: List[str] = []                # ['Flask', 'A/B Testing', ...]
    total: int = 0
    validated_count: int = 0
    validation_pct: float = 0.0

class IssueDetail(BaseModel):
    issue_title: str
    severity_level: str
    ats_impact: str
    explanation: str
    where_it_appears: str
    how_to_fix: str
    action_items: List[str] = []
    example_improvement: str

class AnalysisResponse(BaseModel):
    ATS_score: float
    component_scores: ComponentScores
    issues_summary: List[str]
    detailed_feedback: List[IssueDetail]
    jd_match_analysis: Optional[JDComparison] = None
    skill_validation_details: Optional[SkillValidationDetails] = None

    ats_score: float
    keyword_match: float = 0.0
    missing_keywords: List[str] = []
    matched_keywords: List[str] = []
    suggestions: List[str] = []
    strengths: List[str] = []
    critical_issues: List[str] = []
    skills: List[str] = []
    jd_comparison: Optional[JDComparison] = None
    warnings: List[str] = []
    interpretation: str = ""
    recommendations: List[Dict[str, Any]] = []
    recommendations_summary: str = ""


class RewriteBulletRequest(BaseModel):
    bullet: str
    target_role: Optional[str] = None
    target_skill: Optional[str] = None


class RewriteBulletResponse(BaseModel):
    original: str
    rewritten: str
    action_verb: str
    critique: str
    suggested_metrics: List[str] = []
    _source: str = "deterministic"


class CoverLetterRequest(BaseModel):
    candidate_name: str = "Candidate"
    skills: List[str] = []
    experience_highlights: List[str] = []
    job_title: str = "Software Engineer"
    company_name: str = "Target Company"
    job_description: Optional[str] = None


class CoverLetterResponse(BaseModel):
    cover_letter: str
    _source: str = "deterministic"


class InterviewPrepRequest(BaseModel):
    skills: List[str] = []
    job_title: Optional[str] = None
    unvalidated_skills: List[str] = []


class InterviewPrepResponse(BaseModel):
    target_role: str
    technical_questions: List[Dict[str, Any]] = []
    behavioral_questions: List[Dict[str, Any]] = []
    unvalidated_skill_tips: List[str] = []

