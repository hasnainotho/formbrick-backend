from sqlalchemy.orm import Session
from . import models
import uuid
from typing import List, Optional, Any


def gen_id() -> str:
    return str(uuid.uuid4())


def create_form(db: Session, form_data: dict) -> models.Form:
    form_id = form_data.get('id') or gen_id()
    form = models.Form(
        id=form_id,
        title=form_data['title'],
        description=form_data.get('description'),
        form_type=form_data.get('form_type'),
        is_template=form_data.get('is_template', False),
        is_active=form_data.get('is_active', True),
        settings=form_data.get('settings'),
    )
    db.add(form)
    db.flush()

    questions = form_data.get('questions') or []
    for idx, q in enumerate(questions):
        qid = q.get('id') or gen_id()
        question = models.Question(
            id=qid,
            form_id=form.id,
            question_text=q.get('question_text') or q.get('questionText'),
            question_type=q.get('question_type') or q.get('questionType'),
            options=q.get('options'),
            validation_rules=q.get('validation_rules') or q.get('validationRules'),
            conditional_logic=q.get('conditional_logic') or q.get('conditionalLogic'),
            is_required=q.get('is_required') or q.get('isRequired', False),
            order_index=q.get('order_index') or q.get('orderIndex') or idx,
            section=q.get('section'),
            help_text=q.get('help_text') or q.get('helpText'),
        )
        db.add(question)

    db.commit()
    db.refresh(form)
    return form


def get_forms(db: Session, form_type: Optional[str] = None) -> List[models.Form]:
    q = db.query(models.Form).order_by(models.Form.created_at.desc())
    if form_type:
        q = q.filter(models.Form.form_type == form_type)
    return q.all()


def get_form(db: Session, form_id: str) -> Optional[models.Form]:
    return db.query(models.Form).filter(models.Form.id == form_id).first()


def create_ticket(db: Session, email: Optional[str], initial_form_id: Optional[str]) -> models.Ticket:
    ticket_id = gen_id()
    ticket = models.Ticket(id=ticket_id, email=email, assigned_form_id=None)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def assign_form_to_ticket(db: Session, ticket_id: str, form_id: str):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        return None
    ticket.assigned_form_id = form_id
    db.commit()
    db.refresh(ticket)
    return ticket


def submit_response(db: Session, payload: dict) -> models.FormResponse:
    rid = gen_id()
    response = models.FormResponse(
        id=rid,
        form_id=payload['formId'],
        respondent_id=payload.get('respondentId'),
        respondent_email=payload.get('respondentEmail'),
        reference_id=payload.get('referenceId'),
        reference_type=payload.get('referenceType'),
        status=payload.get('status') or 'submitted',
    )
    db.add(response)
    db.flush()

    answers = payload.get('answers', [])
    for a in answers:
        aid = gen_id()
        ans = models.Answer(
            id=aid,
            response_id=response.id,
            question_id=a['questionId'],
            answer_text=a.get('answerText'),
            answer_number=a.get('answerNumber'),
            answer_date=a.get('answerDate'),
            answer_json=a.get('answerJson'),
        )
        db.add(ans)

    db.commit()
    db.refresh(response)
    return response


def _evaluate_condition(condition: dict, answer_value: Any) -> bool:
    op = condition.get('operator')
    val = condition.get('value')
    # simple operators supported
    try:
        if op == 'equals':
            return answer_value == val
        if op == 'not_equals':
            return answer_value != val
        if op == 'contains':
            return val is not None and str(val) in str(answer_value or '')
        if op == 'greater_than':
            return float(answer_value) > float(val)
        if op == 'less_than':
            return float(answer_value) < float(val)
    except Exception:
        return False
    return False


def process_workflows(db: Session, response: models.FormResponse, answers_map: dict):
    """
    Evaluate conditional logic on the form's questions and perform simple workflow actions.

    The conditional logic stored on a question may include a `workflow` key which is a list
    of actions, e.g.:
      { "workflow": [ { "type": "set_response_status", "status": "pending_approval" }, { "type": "create_ticket", "email": "..." } ] }

    Supported actions: set_response_status, create_ticket, send_email
    """
    form = get_form(db, response.form_id)
    if not form:
        return

    result: dict = {}

    # iterate questions stored on form (SQLAlchemy objects)
    for q in form.questions:
        cl = q.conditional_logic or {}
        if not cl or not cl.get('enabled'):
            continue

        conditions = cl.get('conditions') or []
        if not conditions:
            continue

        # evaluate all conditions
        all_met = True
        for cond in conditions:
            dependent_qid = cond.get('questionId')
            ans = answers_map.get(dependent_qid)
            if not _evaluate_condition(cond, ans):
                all_met = False
                break

        matched = all_met
        # action may be 'show' or 'hide' - workflows run when matched for 'show'
        if cl.get('action') == 'hide':
            matched = not all_met

        if not matched:
            continue

        # run workflow actions
        workflow = cl.get('workflow') or []
        for act in workflow:
            t = act.get('type')
            if t == 'set_response_status':
                status = act.get('status')
                if status:
                    update_response_status(db, response.id, status)
            elif t == 'create_ticket':
                email = act.get('email') or response.respondent_email
                initial_form = act.get('initial_form_id')
                ticket = create_ticket(db, email, initial_form)
                # optionally notify
                if act.get('notify_email') and email:
                    try:
                        from .email_utils import send_email

                        send_email(email, act.get('email_subject', 'Ticket created'), act.get('email_body', f'Ticket {ticket.id} created'))
                    except Exception:
                        # don't let email failures crash workflow
                        pass
            elif t == 'send_email':
                to = act.get('email') or response.respondent_email
                if to:
                    try:
                        from .email_utils import send_email

                        send_email(to, act.get('subject', 'Notification'), act.get('body', ''))
                    except Exception:
                        pass
            elif t == 'set_next_form':
                # store requested next form id so caller can act on it
                next_form_id = act.get('next_form_id') or act.get('nextFormId')
                if next_form_id:
                    result['next_form_id'] = next_form_id
            # extend with other actions as needed
    return result


def get_response(db: Session, response_id: str) -> Optional[models.FormResponse]:
    return db.query(models.FormResponse).filter(models.FormResponse.id == response_id).first()


def update_response_status(db: Session, response_id: str, status: str):
    resp = db.query(models.FormResponse).filter(models.FormResponse.id == response_id).first()
    if not resp:
        return None
    resp.status = status
    db.commit()
    db.refresh(resp)
    return resp


def update_response(db: Session, response_id: str, updates: dict):
    resp = db.query(models.FormResponse).filter(models.FormResponse.id == response_id).first()
    if not resp:
        return None
    for k, v in updates.items():
        if hasattr(resp, k):
            setattr(resp, k, v)
    db.commit()
    db.refresh(resp)
    return resp


def update_answers(db: Session, response_id: str, answers: List[dict]):
    # naive approach: delete existing and recreate
    existing = db.query(models.Answer).filter(models.Answer.response_id == response_id).all()
    for e in existing:
        db.delete(e)
    created = []
    for a in answers:
        aid = gen_id()
        ans = models.Answer(
            id=aid,
            response_id=response_id,
            question_id=a['questionId'],
            answer_text=a.get('answerText'),
            answer_number=a.get('answerNumber'),
            answer_date=a.get('answerDate'),
            answer_json=a.get('answerJson'),
        )
        db.add(ans)
        created.append(ans)
    db.commit()
    return created


def create_questions(db: Session, form_id: str, questions: List[dict]):
    created = []
    for idx, q in enumerate(questions):
        qid = q.get('id') or gen_id()
        question = models.Question(
            id=qid,
            form_id=form_id,
            question_text=q.get('question_text') or q.get('questionText'),
            question_type=q.get('question_type') or q.get('questionType'),
            options=q.get('options'),
            validation_rules=q.get('validation_rules') or q.get('validationRules'),
            conditional_logic=q.get('conditional_logic') or q.get('conditionalLogic'),
            is_required=q.get('is_required') or q.get('isRequired', False),
            order_index=q.get('order_index') or q.get('orderIndex') or idx,
            section=q.get('section'),
            help_text=q.get('help_text') or q.get('helpText'),
        )
        db.add(question)
        created.append(question)
    db.commit()
    return created


def get_responses(db: Session, form_id: str):
    return db.query(models.FormResponse).filter(models.FormResponse.form_id == form_id).order_by(models.FormResponse.submitted_at.desc()).all()


def update_question(db: Session, question_id: str, updates: dict):
    q = db.query(models.Question).filter(models.Question.id == question_id).first()
    if not q:
        return None
    for k, v in updates.items():
        if hasattr(q, k):
            setattr(q, k, v)
    db.commit()
    db.refresh(q)
    return q


def delete_question(db: Session, question_id: str):
    q = db.query(models.Question).filter(models.Question.id == question_id).first()
    if not q:
        return False
    db.delete(q)
    db.commit()
    return True
