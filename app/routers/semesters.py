"""
Academic sessions & semesters.

Flow:
  1. Admin creates an AcademicSession (e.g. "2025/2026") once.
  2. Admin "starts a new semester" -> POST /semesters (status=DRAFT), then
     POST /semesters/{id}/start -> status=ACTIVE. Only one semester may be
     ACTIVE at a time; starting a new one auto-marks any other ACTIVE
     semester as SUBMITTED (closed) first.
  3. While ACTIVE: students can register and courses/exams can be set up.
  4. Admin "submits" the semester -> POST /semesters/{id}/submit ->
     status=SUBMITTED. Once submitted, no new student registrations and no
     new seat-allocation lookups are permitted for that semester (exams for
     it are considered over).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.models import AcademicSession, Semester, SemesterStatus, User
from app.schemas import SemesterCreate, SemesterOut, SessionCreate, SessionOut

router = APIRouter(tags=["Sessions & Semesters"])


# --- Academic sessions -----------------------------------------------------
@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    if db.query(AcademicSession).filter(AcademicSession.name == payload.name).first():
        raise HTTPException(400, "Session already exists")
    session_obj = AcademicSession(name=payload.name)
    db.add(session_obj)
    db.commit()
    db.refresh(session_obj)
    return session_obj


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(db: Session = Depends(get_db)):
    return db.query(AcademicSession).order_by(AcademicSession.name.desc()).all()


# --- Semesters ---------------------------------------------------------------
@router.post("/semesters", response_model=SemesterOut, status_code=201)
def create_semester(
    payload: SemesterCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    session_obj = (
        db.query(AcademicSession).filter(AcademicSession.id == payload.session_id).first()
    )
    if not session_obj:
        raise HTTPException(404, "Academic session not found")

    existing = (
        db.query(Semester)
        .filter(Semester.session_id == payload.session_id, Semester.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(400, "This semester already exists for that session")

    semester = Semester(
        session_id=payload.session_id, name=payload.name, status=SemesterStatus.DRAFT
    )
    db.add(semester)
    db.commit()
    db.refresh(semester)
    return semester


@router.get("/semesters", response_model=list[SemesterOut])
def list_semesters(db: Session = Depends(get_db)):
    return db.query(Semester).order_by(Semester.id.desc()).all()


@router.get("/semesters/active", response_model=SemesterOut)
def get_active_semester(db: Session = Depends(get_db)):
    """Public convenience endpoint so the student registration form can
    default to 'the current semester'."""
    semester = (
        db.query(Semester).filter(Semester.status == SemesterStatus.ACTIVE).first()
    )
    if not semester:
        raise HTTPException(404, "No active semester at the moment")
    return semester


@router.post("/semesters/{semester_id}/start", response_model=SemesterOut)
def start_semester(
    semester_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(404, "Semester not found")
    if semester.status == SemesterStatus.SUBMITTED:
        raise HTTPException(400, "Cannot restart a submitted (closed) semester")

    # Close out any other currently-active semester first.
    others = db.query(Semester).filter(
        Semester.status == SemesterStatus.ACTIVE, Semester.id != semester_id
    )
    for other in others:
        other.status = SemesterStatus.SUBMITTED
        other.submitted_at = datetime.utcnow()

    semester.status = SemesterStatus.ACTIVE
    semester.started_at = datetime.utcnow()
    db.commit()
    db.refresh(semester)
    return semester


@router.post("/semesters/{semester_id}/submit", response_model=SemesterOut)
def submit_semester(
    semester_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Closes the semester: exams are considered over, so students can no
    longer register or fetch seat/hall allocations for it."""
    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(404, "Semester not found")
    if semester.status != SemesterStatus.ACTIVE:
        raise HTTPException(400, "Only an active semester can be submitted")

    semester.status = SemesterStatus.SUBMITTED
    semester.submitted_at = datetime.utcnow()
    db.commit()
    db.refresh(semester)
    return semester
