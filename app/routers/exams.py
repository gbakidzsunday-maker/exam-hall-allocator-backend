"""
Exam timetable + hall allocation.

Endpoints here let an admin:
  - Create/list the exam timetable (course_offering, date, start/end time).
  - Mark an exam completed/cancelled (visible to both admin and student).
  - Allocate one or more halls to an exam, each with one or more
    department+level+matric-range -> seat-range blocks (mixing departments
    in a single hall).
  - Trigger (re)computation of the actual per-student seat numbers.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.models import (
    CourseOffering,
    ExamSchedule,
    ExamStatus,
    Hall,
    HallAllocation,
    HallDepartmentRange,
    Semester,
    SemesterStatus,
    User,
)
from app.schemas import (
    ExamScheduleCreate,
    ExamScheduleOut,
    ExamStatusUpdate,
    HallAllocationCreate,
    HallAllocationOut,
)
from app.services.allocation import (
    generate_seat_allocations_for_exam,
    validate_no_seat_overlap,
)

router = APIRouter(tags=["Exams & Hall Allocation"])


# --- Exam timetable ----------------------------------------------------------
@router.post("/exams", response_model=ExamScheduleOut, status_code=201)
def create_exam_schedule(
    payload: ExamScheduleCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    offering = (
        db.query(CourseOffering)
        .filter(CourseOffering.id == payload.course_offering_id)
        .first()
    )
    if not offering:
        raise HTTPException(404, "Course offering not found")

    semester = db.query(Semester).filter(Semester.id == offering.semester_id).first()
    if semester.status == SemesterStatus.SUBMITTED:
        raise HTTPException(400, "Cannot schedule exams for a submitted (closed) semester")

    if offering.exam_schedule:
        raise HTTPException(400, "This course offering already has an exam scheduled")

    if payload.end_time <= payload.start_time:
        raise HTTPException(400, "end_time must be after start_time")

    exam = ExamSchedule(
        course_offering_id=offering.id,
        semester_id=offering.semester_id,
        exam_date=payload.exam_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status=ExamStatus.SCHEDULED,
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


@router.get("/exams", response_model=list[ExamScheduleOut])
def list_exam_schedules(
    semester_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(ExamSchedule)
    if semester_id:
        query = query.filter(ExamSchedule.semester_id == semester_id)
    return query.order_by(ExamSchedule.exam_date, ExamSchedule.start_time).all()


@router.get("/exams/{exam_id}", response_model=ExamScheduleOut)
def get_exam_schedule(exam_id: int, db: Session = Depends(get_db)):
    exam = db.query(ExamSchedule).filter(ExamSchedule.id == exam_id).first()
    if not exam:
        raise HTTPException(404, "Exam not found")
    return exam


@router.patch("/exams/{exam_id}/status", response_model=ExamScheduleOut)
def update_exam_status(
    exam_id: int,
    payload: ExamStatusUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Marks an exam completed/cancelled. Visible immediately to students
    via their seat-lookup and timetable endpoints."""
    exam = db.query(ExamSchedule).filter(ExamSchedule.id == exam_id).first()
    if not exam:
        raise HTTPException(404, "Exam not found")
    exam.status = payload.status
    db.commit()
    db.refresh(exam)
    return exam


# --- Hall allocation ----------------------------------------------------------
@router.post("/hall-allocations", response_model=HallAllocationOut, status_code=201)
def allocate_hall(
    payload: HallAllocationCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """
    Books `hall_id` for one sitting and adds one or more department/course
    blocks to it. If a HallAllocation already exists for this exact hall +
    date/time (e.g. an earlier call already booked this hall for this
    sitting), the new department_ranges are appended to it instead of
    creating a duplicate booking - this is how an admin "mixes two or more
    departments" into the same hall over multiple calls.
    """
    hall = db.query(Hall).filter(Hall.id == payload.hall_id).first()
    if not hall:
        raise HTTPException(404, "Hall not found")

    # Resolve + validate every referenced exam schedule up front.
    exams_by_id: dict[int, ExamSchedule] = {}
    for rng in payload.department_ranges:
        if rng.exam_schedule_id not in exams_by_id:
            exam = (
                db.query(ExamSchedule)
                .filter(ExamSchedule.id == rng.exam_schedule_id)
                .first()
            )
            if not exam:
                raise HTTPException(
                    404, f"Exam schedule {rng.exam_schedule_id} not found"
                )
            exams_by_id[rng.exam_schedule_id] = exam

    # All blocks in one hall allocation must share the same date/time -
    # they physically sit in the same room at once.
    distinct_slots = {
        (e.exam_date, e.start_time, e.end_time) for e in exams_by_id.values()
    }
    if len(distinct_slots) > 1:
        raise HTTPException(
            400,
            "All department_ranges in one hall allocation must reference exam "
            "schedules with the exact same exam_date/start_time/end_time "
            "(they share the room at the same time).",
        )
    exam_date, start_time, end_time = next(iter(distinct_slots))

    # Prevent double-booking the hall for a *different* sitting that overlaps
    # in time.
    overlapping = (
        db.query(HallAllocation)
        .filter(
            HallAllocation.hall_id == payload.hall_id,
            HallAllocation.exam_date == exam_date,
            HallAllocation.start_time < end_time,
            HallAllocation.end_time > start_time,
        )
        .first()
    )

    if overlapping and (
        overlapping.start_time != start_time or overlapping.end_time != end_time
    ):
        raise HTTPException(
            400,
            "This hall is already booked for a different, overlapping sitting.",
        )

    hall_alloc = overlapping
    if hall_alloc is None:
        hall_alloc = HallAllocation(
            hall_id=hall.id,
            exam_date=exam_date,
            start_time=start_time,
            end_time=end_time,
        )
        db.add(hall_alloc)
        db.flush()

    existing_ranges = list(hall_alloc.department_ranges)
    created_ranges = []
    for rng in payload.department_ranges:
        if rng.seat_end_no > hall.total_seats:
            raise HTTPException(
                400,
                f"Seat range end ({rng.seat_end_no}) exceeds hall capacity "
                f"({hall.total_seats})",
            )
        try:
            validate_no_seat_overlap(existing_ranges + created_ranges, rng.model_dump())
        except ValueError as exc:
            raise HTTPException(400, str(exc))

        row = HallDepartmentRange(
            hall_allocation_id=hall_alloc.id,
            exam_schedule_id=rng.exam_schedule_id,
            department_id=rng.department_id,
            level=rng.level,
            matric_start=rng.matric_start,
            matric_end=rng.matric_end,
            seat_start_no=rng.seat_start_no,
            seat_end_no=rng.seat_end_no,
        )
        db.add(row)
        created_ranges.append(row)

    db.commit()
    db.refresh(hall_alloc)

    # Immediately (re)compute per-student seats for every affected exam.
    for exam in exams_by_id.values():
        generate_seat_allocations_for_exam(db, exam)
    db.refresh(hall_alloc)

    return hall_alloc


@router.get("/hall-allocations/exam/{exam_id}", response_model=list[HallAllocationOut])
def list_hall_allocations_for_exam(exam_id: int, db: Session = Depends(get_db)):
    """Every hall allocation that has at least one department block sitting
    this exam."""
    return (
        db.query(HallAllocation)
        .join(HallDepartmentRange, HallDepartmentRange.hall_allocation_id == HallAllocation.id)
        .filter(HallDepartmentRange.exam_schedule_id == exam_id)
        .distinct()
        .all()
    )


@router.get("/hall-allocations", response_model=list[HallAllocationOut])
def list_hall_allocations(db: Session = Depends(get_db)):
    return db.query(HallAllocation).order_by(HallAllocation.exam_date, HallAllocation.start_time).all()


@router.post("/hall-allocations/exam/{exam_id}/recompute-seats")
def recompute_seats(
    exam_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Re-runs seat computation for an exam, e.g. after new students
    registered or ranges were edited. Reports any overflow (more students
    than seats reserved in a range) back to the admin."""
    exam = db.query(ExamSchedule).filter(ExamSchedule.id == exam_id).first()
    if not exam:
        raise HTTPException(404, "Exam not found")
    result = generate_seat_allocations_for_exam(db, exam)
    return {
        "allocated": result.allocated,
        "overflow_students": result.overflow_students,
        "warnings": result.errors,
    }


@router.delete("/hall-allocations/department-ranges/{range_id}", status_code=204)
def delete_department_range(
    range_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Removes a single department/course block from a hall allocation
    (e.g. to fix a mistake) without dropping the whole hall booking."""
    rng = (
        db.query(HallDepartmentRange).filter(HallDepartmentRange.id == range_id).first()
    )
    if not rng:
        raise HTTPException(404, "Department range not found")
    exam = rng.exam_schedule
    hall_alloc = rng.hall_allocation
    db.delete(rng)
    db.commit()
    if exam:
        generate_seat_allocations_for_exam(db, exam)
    # Clean up an emptied hall allocation.
    if hall_alloc and not hall_alloc.department_ranges:
        db.delete(hall_alloc)
        db.commit()
    return None


@router.delete("/hall-allocations/{hall_allocation_id}", status_code=204)
def delete_hall_allocation(
    hall_allocation_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    hall_alloc = (
        db.query(HallAllocation).filter(HallAllocation.id == hall_allocation_id).first()
    )
    if not hall_alloc:
        raise HTTPException(404, "Hall allocation not found")
    affected_exams = list({rng.exam_schedule for rng in hall_alloc.department_ranges})
    db.delete(hall_alloc)
    db.commit()
    for exam in affected_exams:
        generate_seat_allocations_for_exam(db, exam)
    return None
