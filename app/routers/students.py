"""
Student-facing endpoints.

Students self-register with full name, matric number, department, level and
(current) semester — no admin approval needed. Registration:
  - Is blocked if the chosen semester is not ACTIVE (either still DRAFT or
    already SUBMITTED/closed).
  - Auto-computes the student's course list from every CourseOffering that
    matches their department + level + semester.
  - Issues a lightweight JWT ("student token") the student uses for
    subsequent seat-lookup/timetable calls, so no password is required.

Re-registering with the same matric number just refreshes the student's
details/courses (useful if they mistyped something) rather than erroring.
"""
from datetime import date as date_cls
from datetime import time as time_cls

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_student
from app.models import (
    CourseOffering,
    ExamSchedule,
    HallAllocation,
    Semester,
    SemesterStatus,
    SeatAllocation,
    Student,
    StudentCourseAllocation,
)
from app.schemas import (
    SeatInfoOut,
    StudentCourseOut,
    StudentLoginRequest,
    StudentOut,
    StudentRegisterRequest,
    StudentToken,
    TimetableEntryOut,
)
from app.security import create_access_token
from app.services.allocation import generate_seat_allocations_for_exam

router = APIRouter(prefix="/students", tags=["Students"])


def _sync_student_courses(db: Session, student: Student) -> None:
    """(Re)computes the CourseOffering rows matching this student's
    department + level + semester and stores them as
    StudentCourseAllocation rows."""
    db.query(StudentCourseAllocation).filter(
        StudentCourseAllocation.student_id == student.id
    ).delete()

    offerings = (
        db.query(CourseOffering)
        .filter(
            CourseOffering.department_id == student.department_id,
            CourseOffering.level == student.level,
            CourseOffering.semester_id == student.semester_id,
        )
        .all()
    )
    for offering in offerings:
        db.add(
            StudentCourseAllocation(
                student_id=student.id, course_offering_id=offering.id
            )
        )
    db.commit()


@router.post("/register", response_model=StudentToken, status_code=201)
def register_student(payload: StudentRegisterRequest, db: Session = Depends(get_db)):
    semester = db.query(Semester).filter(Semester.id == payload.semester_id).first()
    if not semester:
        raise HTTPException(404, "Semester not found")
    if semester.status != SemesterStatus.ACTIVE:
        raise HTTPException(
            400,
            "Registration is closed for this semester "
            f"(status: {semester.status.value}). Only an active semester "
            "accepts registrations.",
        )

    student = (
        db.query(Student).filter(Student.matric_no == payload.matric_no.strip()).first()
    )
    if student:
        # Refresh details in case of a correction / re-registration.
        student.full_name = payload.full_name
        student.department_id = payload.department_id
        student.level = payload.level
        student.semester_id = payload.semester_id
    else:
        student = Student(
            full_name=payload.full_name,
            matric_no=payload.matric_no.strip(),
            department_id=payload.department_id,
            level=payload.level,
            semester_id=payload.semester_id,
        )
        db.add(student)

    db.commit()
    db.refresh(student)

    _sync_student_courses(db, student)

    # Re-run seat allocation for any already-scheduled exams this student's
    # department/level is part of, so a late registration still gets a
    # seat if capacity allows.
    exams = (
        db.query(ExamSchedule)
        .join(CourseOffering, ExamSchedule.course_offering_id == CourseOffering.id)
        .filter(
            CourseOffering.department_id == student.department_id,
            CourseOffering.level == student.level,
            CourseOffering.semester_id == student.semester_id,
        )
        .all()
    )
    for exam in exams:
        if exam.hall_department_ranges:
            generate_seat_allocations_for_exam(db, exam)

    token = create_access_token({"sub": str(student.id), "type": "student"})
    return StudentToken(access_token=token, student=student)


@router.post("/login", response_model=StudentToken)
def student_login(payload: StudentLoginRequest, db: Session = Depends(get_db)):
    """Lightweight 'login' for a returning, already-registered student:
    verifies matric number + full name match, then issues a token."""
    student = (
        db.query(Student).filter(Student.matric_no == payload.matric_no.strip()).first()
    )
    if not student or student.full_name.strip().lower() != payload.full_name.strip().lower():
        raise HTTPException(401, "No matching registration found. Please register first.")
    token = create_access_token({"sub": str(student.id), "type": "student"})
    return StudentToken(access_token=token, student=student)


@router.get("/me", response_model=StudentOut)
def get_my_profile(student: Student = Depends(get_current_student)):
    return student


@router.get("/me/courses", response_model=list[StudentCourseOut])
def get_my_courses(
    student: Student = Depends(get_current_student), db: Session = Depends(get_db)
):
    allocations = (
        db.query(StudentCourseAllocation)
        .filter(StudentCourseAllocation.student_id == student.id)
        .all()
    )
    out = []
    for alloc in allocations:
        offering = alloc.course_offering
        out.append(
            StudentCourseOut(
                course_offering_id=offering.id,
                course_code=offering.course.code,
                course_title=offering.course.title,
                unit=offering.course.unit,
                level=offering.level,
                semester_id=offering.semester_id,
            )
        )
    return out


@router.get("/me/seats", response_model=list[SeatInfoOut])
def get_my_seat_allocations(
    student: Student = Depends(get_current_student), db: Session = Depends(get_db)
):
    """Returns this student's seat number + hall name for every exam they
    have a computed seat for. Blocked once the student's semester has been
    submitted (closed)."""
    semester = db.query(Semester).filter(Semester.id == student.semester_id).first()
    if semester and semester.status == SemesterStatus.SUBMITTED:
        raise HTTPException(
            403,
            "This semester has been closed by the administrator. "
            "Hall/seat allocation is no longer available.",
        )

    seat_allocs = (
        db.query(SeatAllocation).filter(SeatAllocation.student_id == student.id).all()
    )
    out = []
    for sa in seat_allocs:
        exam = sa.exam_schedule
        offering = exam.course_offering
        out.append(
            SeatInfoOut(
                exam_schedule_id=exam.id,
                course_code=offering.course.code,
                course_title=offering.course.title,
                exam_date=exam.exam_date,
                start_time=exam.start_time,
                end_time=exam.end_time,
                exam_status=exam.status,
                hall_name=sa.hall.name,
                hall_code=sa.hall.code,
                seat_number=sa.seat_number,
            )
        )
    return sorted(out, key=lambda s: (s.exam_date, s.start_time))


@router.get("/me/timetable", response_model=list[TimetableEntryOut])
def get_my_timetable(
    student: Student = Depends(get_current_student), db: Session = Depends(get_db)
):
    """Personalized exam timetable: every course the student is registered
    for, with exam date/time/hall/seat if scheduled/allocated yet (so it
    also doubles as a printable timetable before halls are assigned)."""
    allocations = (
        db.query(StudentCourseAllocation)
        .filter(StudentCourseAllocation.student_id == student.id)
        .all()
    )

    seat_by_exam = {
        sa.exam_schedule_id: sa
        for sa in db.query(SeatAllocation).filter(SeatAllocation.student_id == student.id)
    }

    entries = []
    for alloc in allocations:
        offering = alloc.course_offering
        exam = offering.exam_schedule
        entry = TimetableEntryOut(
            course_code=offering.course.code,
            course_title=offering.course.title,
        )
        if exam:
            entry.exam_date = exam.exam_date
            entry.start_time = exam.start_time
            entry.end_time = exam.end_time
            entry.exam_status = exam.status
            seat = seat_by_exam.get(exam.id)
            if seat:
                entry.hall_name = seat.hall.name
                entry.seat_number = seat.seat_number
        entries.append(entry)

    return sorted(
        entries,
        key=lambda e: (e.exam_date or date_cls.max, e.start_time or time_cls.min),
    )


@router.get("", response_model=list[StudentOut])
def list_students(
    department_id: int | None = None,
    level: str | None = None,
    semester_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Admin/roster view. (Left open here for convenience; wrap with
    get_current_admin in production if student rosters should be private.)"""
    query = db.query(Student)
    if department_id:
        query = query.filter(Student.department_id == department_id)
    if level:
        query = query.filter(Student.level == level)
    if semester_id:
        query = query.filter(Student.semester_id == semester_id)
    return query.all()
