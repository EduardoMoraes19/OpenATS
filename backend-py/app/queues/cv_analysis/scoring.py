"""Deterministic (non-AI) CV/JD match scoring, ported verbatim from
backend/src/modules/candidate/cv-analysis.service.ts's scoreCV().

Four weighted dimensions summing to 100, each rounded independently before
the final sum is rounded again - both rounding points matter since the
per-dimension breakdown is stored in `score_breakdown` and shown in the UI.
A missing requirement on any dimension scores full marks for that
dimension, not zero - this rule repeats across all four.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ~39 synonym groups so e.g. a JD requiring "React" matches a CV listing
# "reactjs". Any member of a matched group satisfies the requirement.
SKILL_GROUPS: list[list[str]] = [
    ["git", "github", "gitlab", "bitbucket", "svn"],
    ["javascript", "js", "es6", "ecmascript"],
    ["typescript", "ts"],
    ["node.js", "node", "nodejs", "node js"],
    ["postgresql", "postgres", "psql", "pg"],
    ["mysql", "mariadb"],
    ["react", "reactjs", "react.js"],
    ["next.js", "nextjs", "next"],
    ["vue.js", "vue", "vuejs"],
    ["angular", "angularjs"],
    ["svelte", "sveltekit"],
    ["docker", "containerization"],
    ["kubernetes", "k8s"],
    ["mongodb", "mongo"],
    ["graphql", "gql", "apollo"],
    ["python", "py"],
    ["c#", "csharp", "c sharp"],
    [".net", "dotnet", "asp.net", "asp net"],
    ["java"],
    ["spring boot", "spring"],
    ["redis", "ioredis", "upstash redis"],
    ["aws", "amazon web services"],
    ["gcp", "google cloud", "google cloud platform"],
    ["azure", "microsoft azure"],
    ["terraform", "iac", "infrastructure as code"],
    ["tailwind", "tailwindcss", "tailwind css"],
    ["express", "express.js", "expressjs"],
    ["rest api", "rest", "restful", "restful api"],
    ["websocket", "websockets", "socket.io", "ws"],
    ["jest", "vitest", "jasmine", "mocha"],
    ["linux", "unix", "ubuntu", "debian"],
    ["ci/cd", "ci-cd", "github actions", "gitlab ci", "jenkins", "circleci", "devops"],
    ["html", "html5"],
    ["css", "css3", "scss", "sass"],
    ["flutter", "dart"],
    ["firebase", "firestore"],
    ["bullmq", "bull", "job queue"],
    ["drizzle", "drizzle orm"],
    ["prisma", "prisma orm"],
]

_LEVEL_TIERS = {
    "intern": 1,
    "entry": 2,
    "junior": 3,
    "mid": 4,
    "senior": 5,
    "lead": 6,
}

_CERT_ALIASES = {
    "aws": "amazon web services",
    "gcp": "google cloud",
    "azure": "microsoft azure",
}


@dataclass(frozen=True)
class ParsedCv:
    document_type: str
    is_cv_or_resume: bool
    confidence: float
    rationale: str
    listed_skills: list[str] = field(default_factory=list)
    project_technologies: list[str] = field(default_factory=list)
    implied_skills: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    total_experience_years: float = 0
    job_level: str | None = None


@dataclass(frozen=True)
class JobRequirements:
    skills: list[str]
    min_experience_years: float = 0
    job_level: str | None = None
    required_certifications: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScoreBreakdown:
    skills: float
    experience: float
    level: float
    certs: float


@dataclass(frozen=True)
class ScoreResult:
    match_score: int
    breakdown: ScoreBreakdown
    matched_skills: list[str]
    missing_skills: list[str]


def _canonicalize(term: str) -> str:
    return term.strip().lower()


def _skill_group_for(term: str) -> list[str] | None:
    canonical = _canonicalize(term)
    for group in SKILL_GROUPS:
        if canonical in group:
            return group
    return None


def _skill_matches(required_skill: str, candidate_terms: set[str]) -> bool:
    canonical_required = _canonicalize(required_skill)
    if canonical_required in candidate_terms:
        return True
    group = _skill_group_for(canonical_required)
    if group is None:
        return False
    return any(member in candidate_terms for member in group)


def _score_skills(job_skills: list[str], parsed_cv: ParsedCv) -> tuple[float, list[str], list[str]]:
    if not job_skills:
        return 55.0, [], []

    candidate_terms = {
        _canonicalize(term)
        for term in (*parsed_cv.listed_skills, *parsed_cv.project_technologies, *parsed_cv.implied_skills)
    }

    matched, missing = [], []
    for skill in job_skills:
        if _skill_matches(skill, candidate_terms):
            matched.append(skill)
        else:
            missing.append(skill)

    score = (len(matched) / len(job_skills)) * 55
    return score, matched, missing


def _score_experience(min_years: float, candidate_years: float) -> float:
    if min_years <= 0:
        return 25.0
    return min(candidate_years / min_years, 1) * 25


def _score_job_level(required_level: str | None, candidate_level: str | None) -> float:
    if not required_level:
        return 15.0
    required_tier = _LEVEL_TIERS.get(required_level)
    candidate_tier = _LEVEL_TIERS.get(candidate_level) if candidate_level else None
    if required_tier is None or candidate_tier is None:
        return 0.0

    distance = candidate_tier - required_tier
    if required_tier <= 2:
        # Junior/entry roles: penalize under- AND over-qualification symmetrically.
        if distance == 0:
            return 15.0
        if abs(distance) == 1:
            return 7.0
        return 0.0

    # Mid+ roles: no penalty for being more senior than required.
    if distance >= 0:
        return 15.0
    if distance == -1:
        return 7.0
    return 0.0


def _normalize_cert_name(name: str) -> str:
    normalized = re.sub(r"[^\w\s]", "", name.strip().lower())
    for alias, expansion in _CERT_ALIASES.items():
        normalized = re.sub(rf"\b{alias}\b", expansion, normalized)
    return normalized


def _has_cert_match(required: str, candidate_certs: list[str]) -> bool:
    normalized_required = _normalize_cert_name(required)
    for cert in candidate_certs:
        normalized_cert = _normalize_cert_name(cert)
        if normalized_required == normalized_cert:
            return True
        if normalized_required in normalized_cert or normalized_cert in normalized_required:
            return True
    return False


def _score_certifications(required_certs: list[str], candidate_certs: list[str]) -> float:
    if not required_certs:
        return 5.0
    matched = sum(1 for cert in required_certs if _has_cert_match(cert, candidate_certs))
    return (matched / len(required_certs)) * 5


def score_cv(parsed_cv: ParsedCv, job_requirements: JobRequirements) -> ScoreResult:
    skills_score, matched_skills, missing_skills = _score_skills(job_requirements.skills, parsed_cv)
    experience_score = _score_experience(
        job_requirements.min_experience_years, parsed_cv.total_experience_years
    )
    level_score = _score_job_level(job_requirements.job_level, parsed_cv.job_level)
    cert_score = _score_certifications(job_requirements.required_certifications, parsed_cv.certifications)

    breakdown = ScoreBreakdown(
        skills=round(skills_score),
        experience=round(experience_score),
        level=round(level_score),
        certs=round(cert_score),
    )
    match_score = round(breakdown.skills + breakdown.experience + breakdown.level + breakdown.certs)

    return ScoreResult(
        match_score=match_score,
        breakdown=breakdown,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
    )


def verdict_for_score(score: int) -> str:
    if score >= 75:
        return "strong_fit"
    if score >= 50:
        return "moderate_fit"
    if score >= 25:
        return "weak_fit"
    return "not_recommended"
