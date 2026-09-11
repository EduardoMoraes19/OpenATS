"""baseline schema - 33 tables, 16 enums

Ports the *final* state of backend/drizzle/0000..0027 verbatim (column
types, constraints, ON DELETE behaviors, and every named index), rather
than mechanically replaying 28 incremental migrations. Two tables that
existed transiently in that history (`active_logs`, `company_google_tokens`)
were created and later dropped by the TS migrations - they are correctly
absent here. Applying this to a fresh database produces the exact schema
a fully-migrated TS deployment has today.

Revision ID: 0001_baseline
Revises:
Create Date: 2025-01-01 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_ENUMS: list[str] = [
    "CREATE TYPE \"employment_type\" AS ENUM('full_time', 'part_time', 'contract', 'internship', 'freelance')",
    "CREATE TYPE \"salary_type\" AS ENUM('range', 'fixed')",
    "CREATE TYPE \"pay_frequency\" AS ENUM('hourly', 'daily', 'weekly', 'monthly', 'yearly')",
    "CREATE TYPE \"job_status\" AS ENUM('draft', 'inactive', 'published', 'closed', 'archived')",
    "CREATE TYPE \"stage_type\" AS ENUM('screening', 'interview', 'offer')",
    "CREATE TYPE \"offer_mode\" AS ENUM('auto_draft', 'auto_send')",
    "CREATE TYPE \"offer_status\" AS ENUM('draft', 'sent', 'viewed', 'accepted', 'declined', 'expired')",
    "CREATE TYPE \"candidate_activity_type\" AS ENUM('offer_created', 'offer_updated', 'offer_sent', 'offer_viewed', 'offer_accepted', 'offer_declined', 'candidate_hired')",
    "CREATE TYPE \"rejection_email_status\" AS ENUM('not_sent', 'draft', 'sent')",
    "CREATE TYPE \"interview_outcome\" AS ENUM('pending', 'pass', 'fail')",
    "CREATE TYPE \"candidate_status\" AS ENUM('active', 'rejected', 'offered', 'hired', 'withdrawn')",
    "CREATE TYPE \"question_type\" AS ENUM('short_answer', 'long_answer', 'checkbox', 'radio', 'multiple_choice')",
    "CREATE TYPE \"template_type\" AS ENUM('email', 'event')",
    "CREATE TYPE \"assessment_status\" AS ENUM('pending', 'started', 'completed', 'expired')",
    "CREATE TYPE \"cv_analysis_status\" AS ENUM('pending', 'done', 'failed')",
    "CREATE TYPE \"meeting_provider\" AS ENUM('google_meet')",
]

_TABLES: list[str] = [
    # 1. company
    """CREATE TABLE "company" (
        "id" serial PRIMARY KEY NOT NULL,
        "name" varchar(255) NOT NULL,
        "email" varchar(255) NOT NULL,
        "website" varchar(500),
        "phone" varchar(50),
        "address" text,
        "description" text,
        "logo_url" varchar(1000),
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 2. departments
    """CREATE TABLE "departments" (
        "id" serial PRIMARY KEY NOT NULL,
        "company_id" integer NOT NULL REFERENCES "company"("id") ON DELETE CASCADE,
        "name" varchar(255) NOT NULL,
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "departments_company_id_name_unique" UNIQUE("company_id","name")
    )""",
    # 3. users
    """CREATE TABLE "users" (
        "id" serial PRIMARY KEY NOT NULL,
        "asgardeo_user_id" varchar(255) NOT NULL,
        "first_name" varchar(100) NOT NULL,
        "last_name" varchar(100) NOT NULL,
        "email" varchar(255) NOT NULL,
        "avatar_url" varchar(1000),
        "is_active" boolean DEFAULT true NOT NULL,
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "users_asgardeo_user_id_unique" UNIQUE("asgardeo_user_id"),
        CONSTRAINT "users_email_unique" UNIQUE("email")
    )""",
    # 4. templates
    """CREATE TABLE "templates" (
        "id" serial PRIMARY KEY NOT NULL,
        "name" varchar(255) NOT NULL,
        "type" "template_type" NOT NULL,
        "subject" varchar(500) NOT NULL,
        "body_json" jsonb DEFAULT '[]'::jsonb NOT NULL,
        "created_by" integer NOT NULL REFERENCES "users"("id"),
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 5. jobs
    """CREATE TABLE "jobs" (
        "id" serial PRIMARY KEY NOT NULL,
        "slug" varchar(255) NOT NULL,
        "title" varchar(255) NOT NULL,
        "department_id" integer NOT NULL REFERENCES "departments"("id"),
        "employment_type" "employment_type" NOT NULL,
        "location" varchar(255),
        "description" text,
        "salary_type" "salary_type",
        "currency" varchar(3),
        "pay_frequency" "pay_frequency",
        "salary_fixed" numeric(12, 2),
        "salary_min" numeric(12, 2),
        "salary_max" numeric(12, 2),
        "status" "job_status" DEFAULT 'draft' NOT NULL,
        "application_email_template_id" integer REFERENCES "templates"("id") ON DELETE SET NULL,
        "created_by" integer NOT NULL REFERENCES "users"("id"),
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "jobs_slug_unique" UNIQUE("slug"),
        CONSTRAINT "chk_salary_range" CHECK ("salary_type" != 'range' OR ("salary_min" IS NOT NULL AND "salary_max" IS NOT NULL)),
        CONSTRAINT "chk_salary_fixed" CHECK ("salary_type" != 'fixed' OR "salary_fixed" IS NOT NULL),
        CONSTRAINT "chk_salary_currency" CHECK ("salary_type" IS NULL OR "currency" IS NOT NULL),
        CONSTRAINT "chk_salary_min_max" CHECK ("salary_min" IS NULL OR "salary_max" IS NULL OR "salary_max" >= "salary_min")
    )""",
    # 6. job_skills
    """CREATE TABLE "job_skills" (
        "id" serial PRIMARY KEY NOT NULL,
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE CASCADE,
        "skill" varchar(100) NOT NULL,
        CONSTRAINT "job_skills_job_id_skill_unique" UNIQUE("job_id","skill")
    )""",
    # 7. pipeline_stage_templates
    """CREATE TABLE "pipeline_stage_templates" (
        "id" serial PRIMARY KEY NOT NULL,
        "name" varchar(100) NOT NULL,
        "position" integer NOT NULL,
        "stage_type" "stage_type" DEFAULT 'screening' NOT NULL,
        "is_deletable" boolean DEFAULT true NOT NULL,
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "pipeline_stage_templates_name_unique" UNIQUE("name")
    )""",
    # 8. job_pipeline_stages
    """CREATE TABLE "job_pipeline_stages" (
        "id" serial PRIMARY KEY NOT NULL,
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE CASCADE,
        "name" varchar(100) NOT NULL,
        "position" integer NOT NULL,
        "stage_type" "stage_type" DEFAULT 'screening' NOT NULL,
        "source_template_id" integer REFERENCES "pipeline_stage_templates"("id") ON DELETE SET NULL,
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "job_pipeline_stages_job_id_position_unique" UNIQUE("job_id","position")
    )""",
    # 9. job_hiring_team
    """CREATE TABLE "job_hiring_team" (
        "id" serial PRIMARY KEY NOT NULL,
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE CASCADE,
        "user_id" integer NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
        "added_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "job_hiring_team_job_id_user_id_unique" UNIQUE("job_id","user_id")
    )""",
    # 10. assessments
    """CREATE TABLE "assessments" (
        "id" serial PRIMARY KEY NOT NULL,
        "title" varchar(255) NOT NULL,
        "description" text,
        "time_limit" integer NOT NULL,
        "created_by" integer NOT NULL REFERENCES "users"("id"),
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 11. assessment_questions
    """CREATE TABLE "assessment_questions" (
        "id" serial PRIMARY KEY NOT NULL,
        "assessment_id" integer NOT NULL REFERENCES "assessments"("id") ON DELETE CASCADE,
        "title" varchar(500) NOT NULL,
        "description" text,
        "question_type" "question_type" NOT NULL,
        "points" numeric(6, 2) DEFAULT 1 NOT NULL,
        "position" integer NOT NULL,
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 12. assessment_question_options
    """CREATE TABLE "assessment_question_options" (
        "id" serial PRIMARY KEY NOT NULL,
        "question_id" integer NOT NULL REFERENCES "assessment_questions"("id") ON DELETE CASCADE,
        "label" varchar(500) NOT NULL,
        "is_correct" boolean DEFAULT false NOT NULL,
        "position" integer NOT NULL,
        "created_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 13. job_custom_questions
    """CREATE TABLE "job_custom_questions" (
        "id" serial PRIMARY KEY NOT NULL,
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE CASCADE,
        "title" varchar(500) NOT NULL,
        "question_type" "question_type" NOT NULL,
        "is_required" boolean DEFAULT false NOT NULL,
        "position" integer NOT NULL,
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 14. job_custom_question_options
    """CREATE TABLE "job_custom_question_options" (
        "id" serial PRIMARY KEY NOT NULL,
        "question_id" integer NOT NULL REFERENCES "job_custom_questions"("id") ON DELETE CASCADE,
        "label" varchar(500) NOT NULL,
        "is_correct" boolean DEFAULT false NOT NULL,
        "position" integer NOT NULL,
        "created_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 15. job_assessment_attachments
    """CREATE TABLE "job_assessment_attachments" (
        "id" serial PRIMARY KEY NOT NULL,
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE CASCADE,
        "assessment_id" integer NOT NULL REFERENCES "assessments"("id") ON DELETE CASCADE,
        "trigger_stage_id" integer NOT NULL REFERENCES "job_pipeline_stages"("id") ON DELETE CASCADE,
        "created_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "job_assessment_attachments_job_id_trigger_stage_id_unique" UNIQUE("job_id","trigger_stage_id")
    )""",
    # 16. candidates
    """CREATE TABLE "candidates" (
        "id" serial PRIMARY KEY NOT NULL,
        "first_name" varchar(100) NOT NULL,
        "last_name" varchar(100) NOT NULL,
        "email" varchar(255) NOT NULL,
        "phone" varchar(50),
        "resume_url" varchar(1000),
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE RESTRICT,
        "current_stage_id" integer REFERENCES "job_pipeline_stages"("id") ON DELETE SET NULL,
        "status" "candidate_status" DEFAULT 'active' NOT NULL,
        "applied_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "candidates_job_id_email_unique" UNIQUE("job_id","email")
    )""",
    # 17. candidate_stage_history
    """CREATE TABLE "candidate_stage_history" (
        "id" serial PRIMARY KEY NOT NULL,
        "candidate_id" integer NOT NULL REFERENCES "candidates"("id") ON DELETE CASCADE,
        "stage_id" integer NOT NULL REFERENCES "job_pipeline_stages"("id") ON DELETE RESTRICT,
        "moved_by" integer REFERENCES "users"("id") ON DELETE SET NULL,
        "moved_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 18. candidate_custom_answers
    """CREATE TABLE "candidate_custom_answers" (
        "id" serial PRIMARY KEY NOT NULL,
        "candidate_id" integer NOT NULL REFERENCES "candidates"("id") ON DELETE CASCADE,
        "question_id" integer NOT NULL REFERENCES "job_custom_questions"("id") ON DELETE CASCADE,
        "answer_text" text,
        "created_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "candidate_custom_answers_candidate_id_question_id_unique" UNIQUE("candidate_id","question_id")
    )""",
    # 19. candidate_custom_answer_selections
    """CREATE TABLE "candidate_custom_answer_selections" (
        "id" serial PRIMARY KEY NOT NULL,
        "candidate_id" integer NOT NULL REFERENCES "candidates"("id") ON DELETE CASCADE,
        "question_id" integer NOT NULL REFERENCES "job_custom_questions"("id") ON DELETE CASCADE,
        "option_id" integer NOT NULL REFERENCES "job_custom_question_options"("id") ON DELETE CASCADE,
        "created_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "candidate_custom_answer_selections_candidate_id_question_id_option_id_unique" UNIQUE("candidate_id","question_id","option_id")
    )""",
    # 20. candidate_assessment_attempts
    """CREATE TABLE "candidate_assessment_attempts" (
        "id" serial PRIMARY KEY NOT NULL,
        "candidate_id" integer NOT NULL REFERENCES "candidates"("id") ON DELETE CASCADE,
        "assessment_id" integer NOT NULL REFERENCES "assessments"("id") ON DELETE CASCADE,
        "token" varchar(255) NOT NULL,
        "status" "assessment_status" DEFAULT 'pending' NOT NULL,
        "expires_at" timestamp NOT NULL,
        "started_at" timestamp,
        "completed_at" timestamp,
        "score_raw" numeric(8, 2),
        "score_total" numeric(8, 2),
        "score_percentage" numeric(5, 2),
        "passed" boolean,
        "candidate_name_input" varchar(255),
        "candidate_email_input" varchar(255),
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "candidate_assessment_attempts_token_unique" UNIQUE("token")
    )""",
    # 21. candidate_assessment_answers
    """CREATE TABLE "candidate_assessment_answers" (
        "id" serial PRIMARY KEY NOT NULL,
        "attempt_id" integer NOT NULL REFERENCES "candidate_assessment_attempts"("id") ON DELETE CASCADE,
        "question_id" integer NOT NULL REFERENCES "assessment_questions"("id") ON DELETE CASCADE,
        "answer_text" text,
        "points_earned" numeric(6, 2),
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "candidate_assessment_answers_attempt_id_question_id_unique" UNIQUE("attempt_id","question_id")
    )""",
    # 22. candidate_assessment_answer_selections
    """CREATE TABLE "candidate_assessment_answer_selections" (
        "id" serial PRIMARY KEY NOT NULL,
        "answer_id" integer NOT NULL REFERENCES "candidate_assessment_answers"("id") ON DELETE CASCADE,
        "option_id" integer NOT NULL REFERENCES "assessment_question_options"("id") ON DELETE CASCADE,
        "created_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "candidate_assessment_answer_selections_answer_id_option_id_unique" UNIQUE("answer_id","option_id")
    )""",
    # 23. candidate_cv_analysis
    """CREATE TABLE "candidate_cv_analysis" (
        "id" serial PRIMARY KEY NOT NULL,
        "candidate_id" integer NOT NULL REFERENCES "candidates"("id") ON DELETE CASCADE,
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE CASCADE,
        "match_score" numeric(5, 2),
        "matched_skills" text[],
        "missing_skills" text[],
        "score_breakdown" jsonb,
        "ai_summary" jsonb,
        "extracted_text" text,
        "status" "cv_analysis_status" DEFAULT 'pending' NOT NULL,
        "error_message" text,
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "candidate_cv_analysis_candidate_id_unique" UNIQUE("candidate_id")
    )""",
    # 24. offers
    """CREATE TABLE "offers" (
        "id" serial PRIMARY KEY NOT NULL,
        "candidate_id" integer NOT NULL REFERENCES "candidates"("id") ON DELETE CASCADE,
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE RESTRICT,
        "template_id" integer REFERENCES "templates"("id") ON DELETE SET NULL,
        "status" "offer_status" DEFAULT 'draft' NOT NULL,
        "salary" numeric(12, 2),
        "currency" varchar(3),
        "employment_type" "employment_type",
        "start_date" date,
        "reporting_manager" varchar(255),
        "benefits" text,
        "offer_letter_html" text,
        "review_token" varchar(100),
        "sent_at" timestamp,
        "viewed_at" timestamp,
        "accepted_at" timestamp,
        "declined_at" timestamp,
        "created_by" integer NOT NULL REFERENCES "users"("id"),
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "offers_review_token_unique" UNIQUE("review_token"),
        CONSTRAINT "offers_candidate_id_job_id_unique" UNIQUE("candidate_id","job_id")
    )""",
    # 25. candidate_activities
    """CREATE TABLE "candidate_activities" (
        "id" serial PRIMARY KEY NOT NULL,
        "candidate_id" integer NOT NULL REFERENCES "candidates"("id") ON DELETE CASCADE,
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE CASCADE,
        "offer_id" integer REFERENCES "offers"("id") ON DELETE SET NULL,
        "stage_id" integer REFERENCES "job_pipeline_stages"("id") ON DELETE SET NULL,
        "actor_id" integer REFERENCES "users"("id") ON DELETE SET NULL,
        "event_type" "candidate_activity_type" NOT NULL,
        "metadata" jsonb,
        "created_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 26. email_messages
    """CREATE TABLE "email_messages" (
        "id" serial PRIMARY KEY NOT NULL,
        "candidate_id" integer NOT NULL REFERENCES "candidates"("id") ON DELETE CASCADE,
        "sent_by" integer REFERENCES "users"("id") ON DELETE SET NULL,
        "template_id" integer REFERENCES "templates"("id") ON DELETE SET NULL,
        "subject" varchar(500) NOT NULL,
        "body_html" text NOT NULL,
        "recipient_email" varchar(255) NOT NULL,
        "sent_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 27. job_chat_messages
    """CREATE TABLE "job_chat_messages" (
        "id" serial PRIMARY KEY NOT NULL,
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE CASCADE,
        "sender_id" integer NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
        "message" text,
        "reply_to_id" integer REFERENCES "job_chat_messages"("id") ON DELETE SET NULL,
        "sent_at" timestamp DEFAULT now() NOT NULL,
        "is_system_message" boolean DEFAULT false NOT NULL,
        "is_deleted" boolean DEFAULT false NOT NULL
    )""",
    # 28. candidate_chat_messages
    """CREATE TABLE "candidate_chat_messages" (
        "id" serial PRIMARY KEY NOT NULL,
        "candidate_id" integer NOT NULL REFERENCES "candidates"("id") ON DELETE CASCADE,
        "sender_id" integer NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
        "message" text,
        "reply_to_id" integer REFERENCES "candidate_chat_messages"("id") ON DELETE SET NULL,
        "sent_at" timestamp DEFAULT now() NOT NULL,
        "is_system_message" boolean DEFAULT false NOT NULL,
        "is_deleted" boolean DEFAULT false NOT NULL
    )""",
    # 29. candidate_rejections
    """CREATE TABLE "candidate_rejections" (
        "id" serial PRIMARY KEY NOT NULL,
        "candidate_id" integer NOT NULL REFERENCES "candidates"("id") ON DELETE CASCADE,
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE RESTRICT,
        "from_stage_id" integer REFERENCES "job_pipeline_stages"("id") ON DELETE SET NULL,
        "rejected_by" integer REFERENCES "users"("id") ON DELETE SET NULL,
        "reason" varchar(255),
        "internal_note" text,
        "template_id" integer REFERENCES "templates"("id") ON DELETE SET NULL,
        "email_status" "rejection_email_status" DEFAULT 'not_sent' NOT NULL,
        "sent_at" timestamp,
        "rejected_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 30. candidate_interviews
    """CREATE TABLE "candidate_interviews" (
        "id" serial PRIMARY KEY NOT NULL,
        "candidate_id" integer NOT NULL REFERENCES "candidates"("id") ON DELETE CASCADE,
        "stage_id" integer NOT NULL REFERENCES "job_pipeline_stages"("id") ON DELETE RESTRICT,
        "job_id" integer NOT NULL REFERENCES "jobs"("id") ON DELETE RESTRICT,
        "event_name" varchar(255),
        "event_type" varchar(20) DEFAULT 'virtual',
        "meeting_url" varchar(1000),
        "meeting_provider" "meeting_provider",
        "location" varchar(500),
        "body_text" text,
        "interviewer_id" integer REFERENCES "users"("id") ON DELETE SET NULL,
        "time_slots" jsonb,
        "status" varchar(30) DEFAULT 'pending_schedule' NOT NULL,
        "outcome" "interview_outcome" DEFAULT 'pending',
        "public_token" varchar(100),
        "token_expires_at" timestamp,
        "google_event_id" varchar(255),
        "provider_meeting_id" varchar(255),
        "scheduled_at" timestamp,
        "duration_minutes" integer,
        "notes" text,
        "created_by" integer REFERENCES "users"("id") ON DELETE SET NULL,
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "candidate_interviews_public_token_unique" UNIQUE("public_token")
    )""",
    # 31. interview_feedback
    """CREATE TABLE "interview_feedback" (
        "id" serial PRIMARY KEY NOT NULL,
        "interview_id" integer NOT NULL REFERENCES "candidate_interviews"("id") ON DELETE CASCADE,
        "author_id" integer NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
        "content" text NOT NULL,
        "rating" integer,
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL
    )""",
    # 32. integration_connections
    """CREATE TABLE "integration_connections" (
        "id" serial PRIMARY KEY NOT NULL,
        "user_id" integer NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
        "provider" "meeting_provider" NOT NULL,
        "access_token_encrypted" text NOT NULL,
        "refresh_token_encrypted" text NOT NULL,
        "expires_at" timestamp NOT NULL,
        "scopes" jsonb,
        "provider_account_email" varchar(255),
        "created_at" timestamp DEFAULT now() NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL,
        CONSTRAINT "integration_connections_user_id_provider_unique" UNIQUE("user_id","provider")
    )""",
    # 33. public_page_settings
    """CREATE TABLE "public_page_settings" (
        "id" serial PRIMARY KEY NOT NULL,
        "allowed_origins" text[] DEFAULT ARRAY[]::text[] NOT NULL,
        "updated_at" timestamp DEFAULT now() NOT NULL
    )""",
]

_INDEXES: list[str] = [
    'CREATE INDEX "idx_jobs_department_id" ON "jobs" USING btree ("department_id")',
    'CREATE INDEX "idx_jobs_created_by" ON "jobs" USING btree ("created_by")',
    'CREATE INDEX "idx_job_hiring_team_user_id" ON "job_hiring_team" USING btree ("user_id")',
    'CREATE INDEX "idx_candidates_job_id" ON "candidates" USING btree ("job_id")',
    'CREATE INDEX "idx_candidates_current_stage_id" ON "candidates" USING btree ("current_stage_id")',
    'CREATE INDEX "idx_candidate_stage_history_candidate_id" ON "candidate_stage_history" USING btree ("candidate_id")',
    'CREATE INDEX "idx_candidate_stage_history_stage_id" ON "candidate_stage_history" USING btree ("stage_id")',
    'CREATE INDEX "idx_assessment_attempts_candidate_id" ON "candidate_assessment_attempts" USING btree ("candidate_id")',
    'CREATE INDEX "idx_offers_job_id" ON "offers" USING btree ("job_id")',
    'CREATE INDEX "idx_offers_created_by" ON "offers" USING btree ("created_by")',
    'CREATE INDEX "idx_candidate_activities_candidate_id" ON "candidate_activities" USING btree ("candidate_id")',
    'CREATE INDEX "idx_candidate_activities_job_id" ON "candidate_activities" USING btree ("job_id")',
    'CREATE INDEX "idx_email_messages_candidate_id" ON "email_messages" USING btree ("candidate_id")',
    'CREATE INDEX "idx_job_chat_messages_job_id" ON "job_chat_messages" USING btree ("job_id")',
    'CREATE INDEX "idx_candidate_chat_messages_candidate_id" ON "candidate_chat_messages" USING btree ("candidate_id")',
    'CREATE INDEX "idx_candidate_interviews_candidate_id" ON "candidate_interviews" USING btree ("candidate_id")',
    'CREATE INDEX "idx_candidate_interviews_job_id" ON "candidate_interviews" USING btree ("job_id")',
    'CREATE INDEX "idx_candidate_interviews_stage_id" ON "candidate_interviews" USING btree ("stage_id")',
    'CREATE INDEX "idx_candidate_interviews_interviewer_id" ON "candidate_interviews" USING btree ("interviewer_id")',
    'CREATE INDEX "idx_interview_feedback_interview_id" ON "interview_feedback" USING btree ("interview_id")',
    'CREATE INDEX "idx_interview_feedback_author_id" ON "interview_feedback" USING btree ("author_id")',
]


def upgrade() -> None:
    for statement in [*_ENUMS, *_TABLES, *_INDEXES]:
        op.execute(sa.text(statement))


def downgrade() -> None:
    tables_reverse_order = [
        "public_page_settings", "integration_connections", "interview_feedback",
        "candidate_interviews", "candidate_rejections", "candidate_chat_messages",
        "job_chat_messages", "email_messages", "candidate_activities", "offers",
        "candidate_cv_analysis", "candidate_assessment_answer_selections",
        "candidate_assessment_answers", "candidate_assessment_attempts",
        "candidate_custom_answer_selections", "candidate_custom_answers",
        "candidate_stage_history", "candidates", "job_assessment_attachments",
        "job_custom_question_options", "job_custom_questions",
        "assessment_question_options", "assessment_questions", "assessments",
        "job_hiring_team", "job_pipeline_stages", "pipeline_stage_templates",
        "job_skills", "jobs", "templates", "users", "departments", "company",
    ]
    for table in tables_reverse_order:
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
    for enum_type in [
        "meeting_provider", "cv_analysis_status", "assessment_status", "template_type",
        "question_type", "candidate_status", "interview_outcome", "rejection_email_status",
        "candidate_activity_type", "offer_status", "offer_mode", "stage_type", "job_status",
        "pay_frequency", "salary_type", "employment_type",
    ]:
        op.execute(sa.text(f'DROP TYPE IF EXISTS "{enum_type}"'))
