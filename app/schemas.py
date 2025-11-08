from pydantic import BaseModel, EmailStr
from typing import List, Optional, Any
from datetime import datetime


class QuestionCreate(BaseModel):
    id: Optional[str] = None
    question_text: str
    question_type: str
    options: Optional[Any] = None
    validation_rules: Optional[Any] = None
    conditional_logic: Optional[Any] = None
    is_required: Optional[bool] = False
    order_index: Optional[int] = 0
    section: Optional[str] = None
    help_text: Optional[str] = None


class FormCreate(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    form_type: Optional[str] = 'custom'
    is_template: Optional[bool] = False
    is_active: Optional[bool] = True
    settings: Optional[Any] = None
    questions: Optional[List[QuestionCreate]] = None


class AnswerPayload(BaseModel):
    questionId: str
    answerText: Optional[str] = None
    answerNumber: Optional[int] = None
    answerDate: Optional[str] = None
    answerJson: Optional[Any] = None


class SubmitResponse(BaseModel):
    formId: str
    respondentEmail: Optional[EmailStr] = None
    respondentId: Optional[str] = None
    referenceId: Optional[str] = None
    referenceType: Optional[str] = None
    status: Optional[str] = 'submitted'
    answers: List[AnswerPayload]


class TicketCreate(BaseModel):
    email: Optional[EmailStr] = None
    initial_form_id: Optional[str] = None


class AssignFormPayload(BaseModel):
    form_id: str


class ApprovePayload(BaseModel):
    approve: bool
    comment: Optional[str] = None
