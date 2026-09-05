"""
Core seat-allocation logic.

For a given ExamSchedule (one course, one date/time), we find every
HallDepartmentRange that points at it (rng.exam_schedule_id == exam.id) --
each range is a block of seats, in some hall, reserved for a
department+level whose matric numbers fall in [matric_start, matric_end].
Several such ranges (in the same or different halls) can exist for one
exam, and a single hall's sitting (HallAllocation) can itself hold ranges
for several different exams/departments happening simultaneously in that
room.

For every Student whose department+level matches a range, and whose
matric_no falls lexicographically within [matric_start, matric_end], we
rank all matching, registered students by matric_no and assign them
consecutive seat numbers starting at seat_start_no. If the number of
matching students exceeds the seats reserved in that range, the overflow
students are left unallocated and reported back to the admin (so they can
widen the range or add another block) rather than silently overwriting
someone else's seat.
"""
from dataclasses import dataclass, field
from typing import List

from sqlalchemy.orm import Session

from app.models import ExamSchedule, HallDepartmentRange, SeatAllocation, Student


@dataclass
class AllocationResult:
    allocated: int = 0
    overflow_students: List[str] = field(default_factory=list)  # matric numbers
    errors: List[str] = field(default_factory=list)


def _matric_in_range(matric_no: str, start: str, end: str) -> bool:
    """Case-insensitive lexicographic containment check."""
    m = matric_no.strip().upper()
    return start.strip().upper() <= m <= end.strip().upper()


def generate_seat_allocations_for_exam(
    db: Session, exam: ExamSchedule
) -> AllocationResult:
    """
    (Re)computes SeatAllocation rows for every HallDepartmentRange that
    points at this exam (across any hall/sitting it has been placed in).
    Existing seat allocations for this exam are cleared and recomputed, so
    this is safe to call again after an admin edits the ranges or more
    students register.
    """
    result = AllocationResult()

    db.query(SeatAllocation).filter(
        SeatAllocation.exam_schedule_id == exam.id
    ).delete()

    ranges: List[HallDepartmentRange] = (
        db.query(HallDepartmentRange)
        .filter(HallDepartmentRange.exam_schedule_id == exam.id)
        .all()
    )

    for rng in ranges:
        capacity = rng.seat_end_no - rng.seat_start_no + 1

        candidates: List[Student] = (
            db.query(Student)
            .filter(
                Student.department_id == rng.department_id,
                Student.level == rng.level,
            )
            .all()
        )
        matching = sorted(
            (
                s
                for s in candidates
                if _matric_in_range(s.matric_no, rng.matric_start, rng.matric_end)
            ),
            key=lambda s: s.matric_no.upper(),
        )

        if len(matching) > capacity:
            result.overflow_students.extend(s.matric_no for s in matching[capacity:])
            result.errors.append(
                f"Range {rng.matric_start}-{rng.matric_end} (hall_allocation_id="
                f"{rng.hall_allocation_id}) has {len(matching)} student(s) but "
                f"only {capacity} seat(s) reserved."
            )
            matching = matching[:capacity]

        for idx, student in enumerate(matching):
            seat_no = rng.seat_start_no + idx
            db.add(
                SeatAllocation(
                    student_id=student.id,
                    exam_schedule_id=exam.id,
                    hall_id=rng.hall_allocation.hall_id,
                    hall_department_range_id=rng.id,
                    seat_number=seat_no,
                )
            )
            result.allocated += 1

    db.commit()
    return result


def validate_no_seat_overlap(
    existing_ranges: List[HallDepartmentRange], new_range: dict
) -> None:
    """Raises ValueError if new_range's seat block overlaps an existing one
    within the same hall allocation (same hall + same sitting)."""
    new_start, new_end = new_range["seat_start_no"], new_range["seat_end_no"]
    for r in existing_ranges:
        if new_start <= r.seat_end_no and r.seat_start_no <= new_end:
            raise ValueError(
                f"Seat range {new_start}-{new_end} overlaps existing range "
                f"{r.seat_start_no}-{r.seat_end_no} in this hall allocation."
            )
