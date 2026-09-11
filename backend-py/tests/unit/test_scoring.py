from app.queues.cv_analysis.scoring import JobRequirements, ParsedCv, score_cv, verdict_for_score


def _cv(**overrides) -> ParsedCv:
    base = dict(
        document_type="resume",
        is_cv_or_resume=True,
        confidence=0.9,
        rationale="looks like a resume",
    )
    base.update(overrides)
    return ParsedCv(**base)


def test_no_requirements_score_full_marks_on_every_dimension():
    result = score_cv(_cv(), JobRequirements(skills=[]))
    assert result.match_score == 100
    assert result.breakdown.skills == 55
    assert result.breakdown.experience == 25
    assert result.breakdown.level == 15
    assert result.breakdown.certs == 5


def test_skill_synonym_matching_via_skill_groups():
    cv = _cv(listed_skills=["reactjs", "node"])
    result = score_cv(cv, JobRequirements(skills=["React", "Node.js"]))
    assert result.matched_skills == ["React", "Node.js"]
    assert result.missing_skills == []
    assert result.breakdown.skills == 55


def test_missing_skill_is_reported():
    cv = _cv(listed_skills=["python"])
    result = score_cv(cv, JobRequirements(skills=["React", "Python"]))
    assert result.matched_skills == ["Python"]
    assert result.missing_skills == ["React"]
    assert result.breakdown.skills == round(1 / 2 * 55)


def test_experience_is_capped_no_bonus_for_exceeding():
    cv = _cv(total_experience_years=10)
    result = score_cv(cv, JobRequirements(skills=[], min_experience_years=2))
    assert result.breakdown.experience == 25


def test_experience_partial_credit():
    cv = _cv(total_experience_years=1)
    result = score_cv(cv, JobRequirements(skills=[], min_experience_years=2))
    assert result.breakdown.experience == round(0.5 * 25)


def test_job_level_junior_role_penalizes_overqualified_candidate():
    cv = _cv(job_level="senior")
    result = score_cv(cv, JobRequirements(skills=[], job_level="entry"))
    # entry=2, senior=5 -> distance 3 -> 0 points, not full marks.
    assert result.breakdown.level == 0


def test_job_level_junior_role_off_by_one_either_direction_is_partial():
    cv_over = _cv(job_level="junior")  # entry=2, junior=3 -> distance 1
    cv_under = _cv(job_level="intern")  # entry=2, intern=1 -> distance -1
    over = score_cv(cv_over, JobRequirements(skills=[], job_level="entry"))
    under = score_cv(cv_under, JobRequirements(skills=[], job_level="entry"))
    assert over.breakdown.level == 7
    assert under.breakdown.level == 7


def test_job_level_senior_role_no_penalty_for_more_senior_candidate():
    cv = _cv(job_level="lead")
    result = score_cv(cv, JobRequirements(skills=[], job_level="senior"))
    assert result.breakdown.level == 15


def test_job_level_senior_role_one_tier_below_is_partial():
    cv = _cv(job_level="mid")
    result = score_cv(cv, JobRequirements(skills=[], job_level="senior"))
    assert result.breakdown.level == 7


def test_certification_alias_matching():
    cv = _cv(certifications=["AWS Certified Solutions Architect"])
    result = score_cv(cv, JobRequirements(skills=[], required_certifications=["aws"]))
    assert result.breakdown.certs == 5


def test_verdict_thresholds():
    assert verdict_for_score(80) == "strong_fit"
    assert verdict_for_score(60) == "moderate_fit"
    assert verdict_for_score(30) == "weak_fit"
    assert verdict_for_score(10) == "not_recommended"
