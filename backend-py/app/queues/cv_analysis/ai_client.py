"""CV/JD parsing and AI summary generation for the CV analysis pipeline,
built on top of the generic multi-provider gateway
(app/shared/services/ai_gateway.py). This module owns the CV-analysis
prompts and response parsing; it doesn't know or care which model/provider
actually answers them - that's OPENROUTER_MODEL's job.
"""

from __future__ import annotations

import json

from app.logging import get_logger
from app.queues.cv_analysis.scoring import JobRequirements, ParsedCv, ScoreResult, verdict_for_score
from app.shared.services import ai_gateway

logger = get_logger(__name__)

_CV_PARSE_PROMPT = """You are analyzing a document that was uploaded as a job application resume/CV.

Carefully determine:
1. What type of document this actually is (documentType) - e.g. "resume", "cover_letter",
   "transcript", "certificate", "id_document", "blank_page", "other".
2. Whether it is genuinely a CV/resume (isCvOrResume: true/false) and your confidence (0-1).
3. A brief rationale for your classification.

If (and only if) it is a CV/resume, extract:
- listedSkills: skills explicitly listed (e.g. in a "Skills" section)
- projectTechnologies: technologies mentioned in project/experience descriptions
- impliedSkills: skills reasonably inferred from context (e.g. a GitHub URL implies "Git",
  a Firebase project implies "Firebase", a deployment platform mention implies that platform)
- certifications: any certifications listed
- totalExperienceYears: best-estimate total professional experience in years (number)
- jobLevel: one of "intern", "entry", "junior", "mid", "senior", "lead", or null if unclear

Respond with ONLY a JSON object with keys: documentType, isCvOrResume, confidence, rationale,
listedSkills, projectTechnologies, impliedSkills, certifications, totalExperienceYears, jobLevel.
"""

_JD_PARSE_PROMPT = """Extract structured hiring requirements from this job description.

Determine:
- minExperienceYears: minimum years of experience required (number, 0 if not specified)
- jobLevel: one of "intern", "entry", "junior", "mid", "senior", "lead", or null if unclear
- requiredCertifications: any certifications explicitly required (array of strings)

Respond with ONLY a JSON object with keys: minExperienceYears, jobLevel, requiredCertifications.

Job description:
{description}
"""

_SUMMARY_PROMPT = """Given this candidate's parsed CV data, the job's requirements, and a
pre-computed match score, write a concise hiring summary.

The verdict field MUST be exactly "{verdict}" (it is determined by the score, not your judgment).

Respond with ONLY a JSON object with keys: quickSummary (1-2 sentences), strengths (array of
short strings), gaps (array of short strings), hiringSignal (1 sentence), verdict (must be
"{verdict}").

Candidate data: {parsed_cv}
Job requirements: {job_requirements}
Score: {score}
"""


async def parse_cv(pdf_bytes: bytes) -> ParsedCv:
    text = await ai_gateway.complete(
        messages=[
            {
                "role": "user",
                "content": [
                    ai_gateway.pdf_content_part(filename="resume.pdf", pdf_bytes=pdf_bytes),
                    {"type": "text", "text": _CV_PARSE_PROMPT},
                ],
            }
        ],
        plugins=[ai_gateway.pdf_parser_plugin()],
    )
    data = json.loads(ai_gateway.strip_markdown_fences(text))
    return ParsedCv(
        document_type=data["documentType"],
        is_cv_or_resume=data["isCvOrResume"],
        confidence=data["confidence"],
        rationale=data.get("rationale", ""),
        listed_skills=data.get("listedSkills", []),
        project_technologies=data.get("projectTechnologies", []),
        implied_skills=data.get("impliedSkills", []),
        certifications=data.get("certifications", []),
        total_experience_years=data.get("totalExperienceYears", 0),
        job_level=data.get("jobLevel"),
    )


async def parse_jd(description: str) -> dict:
    text = await ai_gateway.complete(
        messages=[{"role": "user", "content": _JD_PARSE_PROMPT.format(description=description)}]
    )
    data = json.loads(ai_gateway.strip_markdown_fences(text))
    return {
        "minExperienceYears": data.get("minExperienceYears", 0),
        "jobLevel": data.get("jobLevel"),
        "requiredCertifications": data.get("requiredCertifications", []),
    }


async def generate_ai_summary(
    parsed_cv: ParsedCv, job_requirements: JobRequirements, score: ScoreResult
) -> dict | None:
    """Non-fatal: any error here is logged and swallowed - the rest of the
    analysis still saves without an AI summary."""
    try:
        verdict = verdict_for_score(score.match_score)
        text = await ai_gateway.complete(
            messages=[
                {
                    "role": "user",
                    "content": _SUMMARY_PROMPT.format(
                        verdict=verdict,
                        parsed_cv=parsed_cv,
                        job_requirements=job_requirements,
                        score=score.match_score,
                    ),
                }
            ]
        )
        data = json.loads(ai_gateway.strip_markdown_fences(text))
        data["verdict"] = verdict
        return data
    except Exception:  # noqa: BLE001
        logger.warning("failed to generate AI summary, continuing without it", exc_info=True)
        return None
