"""Re-exports every ORM model so importing this module registers all 33
tables on `Base.metadata` - required before Alembic autogeneration or
`Base.metadata.create_all()` and before relationships with string-based
class references (e.g. "Job", "User") can be resolved.
"""

from app.db.models.assessments import (
    Assessment,
    AssessmentQuestion,
    AssessmentQuestionOption,
    JobAssessmentAttachment,
    JobCustomQuestion,
    JobCustomQuestionOption,
)
from app.db.models.candidate_activities import CandidateActivity
from app.db.models.candidates import (
    Candidate,
    CandidateAssessmentAnswer,
    CandidateAssessmentAnswerSelection,
    CandidateAssessmentAttempt,
    CandidateCustomAnswer,
    CandidateCustomAnswerSelection,
    CandidateCvAnalysis,
    CandidateStageHistory,
)
from app.db.models.communications import CandidateChatMessage, EmailMessage, JobChatMessage
from app.db.models.company import Company, Department
from app.db.models.integrations import IntegrationConnection
from app.db.models.interview_feedback import InterviewFeedback
from app.db.models.interviews import CandidateInterview
from app.db.models.jobs import Job, JobSkill
from app.db.models.offers import Offer
from app.db.models.page_settings import PublicPageSettings
from app.db.models.pipeline import JobHiringTeam, JobPipelineStage, PipelineStageTemplate
from app.db.models.rejections import CandidateRejection
from app.db.models.templates import Template
from app.db.models.users import User

__all__ = [
    "Assessment",
    "AssessmentQuestion",
    "AssessmentQuestionOption",
    "Candidate",
    "CandidateActivity",
    "CandidateAssessmentAnswer",
    "CandidateAssessmentAnswerSelection",
    "CandidateAssessmentAttempt",
    "CandidateChatMessage",
    "CandidateCustomAnswer",
    "CandidateCustomAnswerSelection",
    "CandidateCvAnalysis",
    "CandidateInterview",
    "CandidateRejection",
    "CandidateStageHistory",
    "Company",
    "Department",
    "EmailMessage",
    "IntegrationConnection",
    "InterviewFeedback",
    "Job",
    "JobAssessmentAttachment",
    "JobChatMessage",
    "JobCustomQuestion",
    "JobCustomQuestionOption",
    "JobHiringTeam",
    "JobPipelineStage",
    "JobSkill",
    "Offer",
    "PipelineStageTemplate",
    "PublicPageSettings",
    "Template",
    "User",
]
