import json
from datetime import datetime

from app.core.extensions import db


SURVEY_FIELD_TYPES = {
    "short_text": "Короткий текст",
    "long_text": "Развёрнутый текст",
    "number": "Число",
    "date": "Дата",
    "choice": "Один вариант из списка",
    "multiple_choice": "Несколько вариантов из списка",
    "yes_no": "Да / Нет",
    "choice_other": "Один вариант из списка + иной вариант",
    "file": "Загрузка документов",
}


class AdditionalEducationSurvey(db.Model):
    __tablename__ = "additional_education_survey"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    public_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    short_code = db.Column(db.String(40), nullable=True, unique=True, index=True)
    is_published = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    questions = db.relationship(
        "AdditionalEducationSurveyQuestion",
        backref="survey",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="AdditionalEducationSurveyQuestion.sort_order",
    )
    submissions = db.relationship(
        "AdditionalEducationSurveySubmission",
        backref="survey",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    access_grants = db.relationship(
        "AdditionalEducationSurveyAccess",
        backref="survey",
        lazy="select",
        cascade="all, delete-orphan",
    )


class AdditionalEducationSurveyAccess(db.Model):
    __tablename__ = "additional_education_survey_access"
    __table_args__ = (
        db.UniqueConstraint(
            "survey_id",
            "user_id",
            name="uq_add_edu_survey_access_survey_user",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(
        db.Integer,
        db.ForeignKey("additional_education_survey.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    granted_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])
    granted_by = db.relationship("User", foreign_keys=[granted_by_user_id])


class AdditionalEducationSurveyQuestion(db.Model):
    __tablename__ = "additional_education_survey_question"

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(
        db.Integer,
        db.ForeignKey("additional_education_survey.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = db.Column(db.String(500), nullable=False)
    help_text = db.Column(db.String(500), nullable=True)
    field_type = db.Column(db.String(30), nullable=False, default="short_text")
    options_json = db.Column(db.Text, nullable=True)
    is_required = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    answers = db.relationship(
        "AdditionalEducationSurveyAnswer",
        backref="question",
        lazy="select",
        cascade="all, delete-orphan",
    )

    @property
    def options(self):
        if not self.options_json:
            return []
        try:
            value = json.loads(self.options_json)
        except (TypeError, ValueError):
            return []
        return [str(item) for item in value] if isinstance(value, list) else []

    def set_options(self, options):
        self.options_json = json.dumps(list(options), ensure_ascii=False) if options else None


class AdditionalEducationSurveySubmission(db.Model):
    __tablename__ = "additional_education_survey_submission"

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(
        db.Integer,
        db.ForeignKey("additional_education_survey.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    receipt_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    answers = db.relationship(
        "AdditionalEducationSurveyAnswer",
        backref="submission",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="AdditionalEducationSurveyAnswer.id",
    )

    @property
    def answers_by_question_id(self):
        return {answer.question_id: answer for answer in self.answers}


class AdditionalEducationSurveyAnswer(db.Model):
    __tablename__ = "additional_education_survey_answer"
    __table_args__ = (
        db.UniqueConstraint("submission_id", "question_id", name="uq_add_edu_answer_submission_question"),
    )

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(
        db.Integer,
        db.ForeignKey("additional_education_survey_submission.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = db.Column(
        db.Integer,
        db.ForeignKey("additional_education_survey_question.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value_text = db.Column(db.Text, nullable=True)

    attachments = db.relationship(
        "AdditionalEducationSurveyAttachment",
        backref="answer",
        lazy="select",
        cascade="all, delete-orphan",
    )


class AdditionalEducationSurveyAttachment(db.Model):
    __tablename__ = "additional_education_survey_attachment"

    id = db.Column(db.Integer, primary_key=True)
    answer_id = db.Column(
        db.Integer,
        db.ForeignKey("additional_education_survey_answer.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)
    content_type = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
