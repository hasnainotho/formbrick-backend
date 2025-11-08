from sqlalchemy import Column, String, Integer, ForeignKey, Boolean, DateTime, Text, JSON, func
from sqlalchemy.orm import relationship
import enum
from .database import Base


class ResponseStatus(str, enum.Enum):
    draft = 'draft'
    submitted = 'submitted'
    pending_approval = 'pending_approval'
    approved = 'approved'
    rejected = 'rejected'


class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)


class Form(Base):
    __tablename__ = 'forms'
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    form_type = Column(String, index=True)
    is_template = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    settings = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    questions = relationship('Question', back_populates='form', cascade='all, delete-orphan')


class Question(Base):
    __tablename__ = 'questions'
    id = Column(String, primary_key=True)
    form_id = Column(String, ForeignKey('forms.id', ondelete='CASCADE'), nullable=False)
    question_text = Column(Text)
    question_type = Column(String)
    options = Column(JSON)
    validation_rules = Column(JSON)
    conditional_logic = Column(JSON)
    is_required = Column(Boolean, default=False)
    order_index = Column(Integer, default=0)
    section = Column(String, nullable=True)
    help_text = Column(String, nullable=True)
    form = relationship('Form', back_populates='questions')


class Ticket(Base):
    __tablename__ = 'tickets'
    id = Column(String, primary_key=True)
    email = Column(String, nullable=True)
    base_response_id = Column(String, ForeignKey('form_responses.id', ondelete='SET NULL'), nullable=True)
    assigned_form_id = Column(String, ForeignKey('forms.id', ondelete='SET NULL'), nullable=True)
    status = Column(String, default='open')
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FormResponse(Base):
    __tablename__ = 'form_responses'
    id = Column(String, primary_key=True)
    form_id = Column(String, ForeignKey('forms.id', ondelete='CASCADE'), nullable=False)
    respondent_id = Column(String, ForeignKey('users.id'), nullable=True)
    respondent_email = Column(String, nullable=True)
    reference_id = Column(String, nullable=True)
    reference_type = Column(String, nullable=True)
    status = Column(String, default=ResponseStatus.submitted.value)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    answers = relationship('Answer', back_populates='response', cascade='all, delete-orphan')


class Answer(Base):
    __tablename__ = 'answers'
    id = Column(String, primary_key=True)
    response_id = Column(String, ForeignKey('form_responses.id', ondelete='CASCADE'), nullable=False)
    question_id = Column(String, ForeignKey('questions.id'), nullable=False)
    answer_text = Column(Text, nullable=True)
    answer_number = Column(Integer, nullable=True)
    answer_date = Column(String, nullable=True)
    answer_json = Column(JSON, nullable=True)
    response = relationship('FormResponse', back_populates='answers')


class Workflow(Base):
    __tablename__ = 'workflows'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    # mapping rules could be stored as JSON, e.g., map ticket attributes to form id
    rules = Column(JSON)
