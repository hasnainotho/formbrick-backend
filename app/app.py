from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import SessionLocal, init_db
from . import crud, models
from . import schemas
from .email_utils import send_email
import os
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')

app = FastAPI(title='Formbricks - FastAPI Backend')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event('startup')
def on_startup():
    init_db()


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.post('/forms')
def create_form(form: schemas.FormCreate, db: Session = Depends(get_db)):
    created = crud.create_form(db, form.dict())
    return {'form': {'id': created.id, 'title': created.title}}


@app.get('/forms')
def list_forms(form_type: str | None = None, db: Session = Depends(get_db)):
    forms = crud.get_forms(db, form_type)
    result = []
    for f in forms:
        result.append(
            {
                'id': f.id, 
                'title': f.title,
                'form_type': f.form_type, 
                "created_at": f.created_at, 
                "questions": len(f.questions)
            }
        )
    return {'forms': result}


@app.get('/forms/{form_id}')
def get_form(form_id: str, db: Session = Depends(get_db)):
    f = crud.get_form(db, form_id)
    if not f:
        raise HTTPException(status_code=404, detail='Form not found')
    # convert questions
    questions = []
    for q in f.questions:
        questions.append({
            'id': q.id,
            'question_text': q.question_text,
            'question_type': q.question_type,
            'options': q.options,
            'validation_rules': q.validation_rules,
            'conditional_logic': q.conditional_logic,
            'is_required': q.is_required,
            'order_index': q.order_index,
            'section': q.section,
            'help_text': q.help_text,
        })
    return {
        'form': {
            'id': f.id,
            'title': f.title,
            'description': f.description,
            'form_type': f.form_type,
            'questions': sorted(questions, key=lambda x: x['order_index']),
        }
    }


@app.put('/forms/{form_id}')
def update_form(form_id: str, form: schemas.FormCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Form).filter(models.Form.id == form_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail='Form not found')
    existing.title = form.title
    existing.description = form.description
    existing.form_type = form.form_type
    existing.is_template = form.is_template
    existing.is_active = form.is_active
    existing.settings = form.settings
    db.commit()
    db.refresh(existing)
    return {'form': {'id': existing.id, 'title': existing.title}}


@app.delete('/forms/{form_id}')
def delete_form(form_id: str, db: Session = Depends(get_db)):
    existing = db.query(models.Form).filter(models.Form.id == form_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail='Form not found')
    db.delete(existing)
    db.commit()
    return {'ok': True}


@app.post('/forms/{form_id}/questions')
def create_questions_endpoint(form_id: str, questions: list[dict], db: Session = Depends(get_db)):
    form = crud.get_form(db, form_id)
    if not form:
        raise HTTPException(status_code=404, detail='Form not found')
    created = crud.create_questions(db, form_id, questions)
    return {'created': [q.id for q in created]}


@app.put('/questions/{question_id}')
def update_question(question_id: str, updates: dict, db: Session = Depends(get_db)):
    updated = crud.update_question(db, question_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail='Question not found')
    return {'question': {'id': updated.id}}


@app.delete('/questions/{question_id}')
def delete_question(question_id: str, db: Session = Depends(get_db)):
    ok = crud.delete_question(db, question_id)
    if not ok:
        raise HTTPException(status_code=404, detail='Question not found')
    return {'ok': True}


@app.get('/responses')
def list_responses(form_id: str | None = None, db: Session = Depends(get_db)):
    if not form_id:
        raise HTTPException(status_code=400, detail='form_id is required')
    responses = crud.get_responses(db, form_id)
    result = []
    for r in responses:
        result.append({'id': r.id, 'status': r.status, 'respondent_email': r.respondent_email, 'submitted_at': r.submitted_at})
    return {'responses': result}


@app.get('/responses/{response_id}')
def get_response(response_id: str, db: Session = Depends(get_db)):
    r = crud.get_response(db, response_id)
    if not r:
        raise HTTPException(status_code=404, detail='Response not found')
    answers = []
    for a in r.answers:
        answers.append({'id': a.id, 'question_id': a.question_id, 'answer_text': a.answer_text, 'answer_number': a.answer_number, 'answer_json': a.answer_json})
    return {'response': {'id': r.id, 'status': r.status, 'answers': answers}}


@app.put('/responses/{response_id}')
def update_response(response_id: str, updates: dict, db: Session = Depends(get_db)):
    updated = crud.update_response(db, response_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail='Response not found')
    return {'response': {'id': updated.id, 'status': updated.status}}


@app.put('/responses/{response_id}/answers')
def update_response_answers(response_id: str, answers: list[dict], db: Session = Depends(get_db)):
    resp = crud.get_response(db, response_id)
    if not resp:
        raise HTTPException(status_code=404, detail='Response not found')
    created = crud.update_answers(db, response_id, answers)
    return {'updated': [c.id for c in created]}


@app.post('/tickets')
def create_ticket(ticket: schemas.TicketCreate, db: Session = Depends(get_db)):
    # Create a ticket and send the base form link
    t = crud.create_ticket(db, ticket.email, ticket.initial_form_id)

    base_form_id = ticket.initial_form_id
    if base_form_id:
        link = f"{API_BASE_URL}/forms/fill/{base_form_id}?ticket_id={t.id}"
        if ticket.email:
            send_email(ticket.email, 'Please complete the base form', f'Please complete the form: {link}')

    return {'ticket': {'id': t.id, 'email': t.email}}


@app.post('/tickets/{ticket_id}/assign')
def assign_form(ticket_id: str, payload: schemas.AssignFormPayload, db: Session = Depends(get_db)):
    ticket = crud.assign_form_to_ticket(db, ticket_id, payload.form_id)
    if not ticket:
        raise HTTPException(status_code=404, detail='Ticket not found')

    # send email to the ticket holder
    if ticket.email:
        link = f"{API_BASE_URL}/forms/fill/{payload.form_id}?ticket_id={ticket.id}"
        send_email(ticket.email, 'Please complete the event-specific form', f'Please complete the form: {link}')

    return {'ticket': {'id': ticket.id, 'assigned_form_id': ticket.assigned_form_id}}


@app.post('/admin/forms/{form_id}/remap-conditions')
def remap_form_conditions(form_id: str, payload: dict, db: Session = Depends(get_db)):
    """
    Admin helper to remap conditional logic questionId references for an existing form.

    Payload shape:
      {
        "mappings": { "temp-123": "real-uuid-1", "temp-456": "real-uuid-2" },
        "dry_run": true    # optional, defaults to true
      }

    Returns a list of proposed changes; if dry_run is false the changes are persisted.
    """
    mappings = payload.get('mappings') or {}
    dry_run = payload.get('dry_run', True)

    if not mappings:
        return {'error': 'mappings required', 'mappings': mappings}

    form = crud.get_form(db, form_id)
    if not form:
        raise HTTPException(status_code=404, detail='Form not found')

    changes = []

    for q in form.questions:
        cl = q.conditional_logic or {}
        if not cl:
            continue
        modified = False
        try:
            conditions = cl.get('conditions') or []
            for cond in conditions:
                old = cond.get('questionId')
                if old in mappings and mappings[old]:
                    cond['questionId'] = mappings[old]
                    changes.append({'question_id': q.id, 'old': old, 'new': mappings[old]})
                    modified = True
        except Exception:
            continue

        if modified and not dry_run:
            # write back updated conditional_logic
            q.conditional_logic = cl
            db.add(q)

    if not dry_run and changes:
        db.commit()

    return {'form_id': form_id, 'dry_run': dry_run, 'changes': changes}


@app.post('/responses')
def submit_response(payload: schemas.SubmitResponse, db: Session = Depends(get_db)):
    # Create response and answers
    payload_dict = payload.dict()
    response = crud.submit_response(db, payload_dict)

    # Build a map of answers by questionId for workflow evaluation
    answers_list = payload_dict.get('answers', []) or []
    answers_map = {}
    for a in answers_list:
        qid = a.get('questionId')
        # pick a sensible single value representation
        answers_map[qid] = a.get('answerText') if a.get('answerText') is not None else (
            a.get('answerNumber') if a.get('answerNumber') is not None else (
                a.get('answerJson') if a.get('answerJson') is not None else a.get('answerDate')
            )
        )

    # Evaluate conditional logic workflows defined on questions (if any)
    workflow_result = None
    try:
        workflow_result = crud.process_workflows(db, response, answers_map)
    except Exception:
        # don't let workflow failures break the response submission
        workflow_result = None

    # If the response references a ticket, and the ticket has an assigned form, mark pending approval
    if payload.referenceType == 'ticket' and payload.referenceId:
        # If admin assigned a specific form, we could change status
        # For now, mark pending_approval when reference is present
        crud.update_response_status(db, response.id, 'pending_approval')

    result = {'response': {'id': response.id, 'status': response.status}}
    if workflow_result and isinstance(workflow_result, dict) and workflow_result.get('next_form_id'):
        result['next_form_id'] = workflow_result.get('next_form_id')
    return result


@app.post('/responses/{response_id}/approve')
def approve_response(response_id: str, payload: schemas.ApprovePayload, db: Session = Depends(get_db)):
    if payload.approve:
        updated = crud.update_response_status(db, response_id, 'approved')
    else:
        updated = crud.update_response_status(db, response_id, 'rejected')
    if not updated:
        raise HTTPException(status_code=404, detail='Response not found')
    return {'response': {'id': updated.id, 'status': updated.status}}
