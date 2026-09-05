"""
Pydantic schemas (request/response models).
"""
from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ExamStatus, Level, SemesterName, SemesterStatus, UserRole


# ---------------------------------------------------------------------------
# Auth / Admin users
# ---------------------------------------------------------------------------
class AdminCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str
    password: str = Field(min_length=6)
    role: UserRole = UserRole.ADMIN


class AdminOut(BaseModel):
    id: int
    username: str
    email: str
    role: UserRole
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------
class DepartmentCreate(BaseModel):
    name: str
    code: str = Field(max_length=20)


class DepartmentOut(BaseModel):
    id: int
    name: str
    code: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Academic session / semester
# ---------------------------------------------------------------------------
class SessionCreate(BaseModel):
    name: str = Field(description='e.g. "2025/2026"')


class SessionOut(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class SemesterCreate(BaseModel):
    session_id: int
    name: SemesterName


class SemesterOut(BaseModel):
    id: int
    session_id: int
    name: SemesterName
    status: SemesterStatus
    started_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Course / CourseOffering
# ---------------------------------------------------------------------------
class CourseCreate(BaseModel):
    code: str
    title: str
    unit: int = 2


class CourseOut(BaseModel):
    id: int
    code: str
    title: str
    unit: int

    model_config = ConfigDict(from_attributes=True)


class CourseOfferingCreate(BaseModel):
    """Adds (or links) a course to a department, for a given level & semester."""

    course_id: Optional[int] = None
    # Convenience: create the course inline if it doesn't exist yet.
    course_code: Optional[str] = None
    course_title: Optional[str] = None
    course_unit: int = 2

    department_id: int
    level: Level
    semester_id: int

    @field_validator("course_id")
    @classmethod
    def _at_least_one_course_identifier(cls, v, info):
        return v


class CourseOfferingOut(BaseModel):
    id: int
    course: CourseOut
    department_id: int
    level: Level
    semester_id: int

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Hall
# ---------------------------------------------------------------------------
class HallCreate(BaseModel):
    name: str
    code: str
    total_seats: int = Field(gt=0)
    rows: Optional[int] = None
    columns: Optional[int] = None


class HallOut(BaseModel):
    id: int
    name: str
    code: str
    total_seats: int
    rows: Optional[int] = None
    columns: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Exam timetable
# ---------------------------------------------------------------------------
class ExamScheduleCreate(BaseModel):
    course_offering_id: int
    exam_date: date
    start_time: time
    end_time: time


class ExamScheduleOut(BaseModel):
    id: int
    course_offering_id: int
    semester_id: int
    exam_date: date
    start_time: time
    end_time: time
    status: ExamStatus

    model_config = ConfigDict(from_attributes=True)


class ExamStatusUpdate(BaseModel):
    status: ExamStatus


# ---------------------------------------------------------------------------
# Hall allocation & department seat ranges
# ---------------------------------------------------------------------------
class DepartmentRangeIn(BaseModel):
    exam_schedule_id: int = Field(description="Which course this department/level block is sitting")
    department_id: int
    level: Level
    matric_start: str
    matric_end: str
    seat_start_no: int = Field(gt=0)
    seat_end_no: int = Field(gt=0)

    @field_validator("seat_end_no")
    @classmethod
    def _end_after_start(cls, v, info):
        start = info.data.get("seat_start_no")
        if start is not None and v < start:
            raise ValueError("seat_end_no must be >= seat_start_no")
        return v


class HallAllocationCreate(BaseModel):
    """
    Books a hall for one sitting and (optionally) mixes several
    department/course blocks into it in the same call. All
    department_ranges must reference exam schedules sharing the exact same
    exam_date/start_time/end_time, since they physically share the room at
    the same time.
    """

    hall_id: int
    department_ranges: List[DepartmentRangeIn] = Field(min_length=1)


class DepartmentRangeOut(BaseModel):
    id: int
    exam_schedule_id: int
    department_id: int
    level: Level
    matric_start: str
    matric_end: str
    seat_start_no: int
    seat_end_no: int

    model_config = ConfigDict(from_attributes=True)


class HallAllocationOut(BaseModel):
    id: int
    hall_id: int
    exam_date: date
    start_time: time
    end_time: time
    department_ranges: List[DepartmentRangeOut]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------
class StudentRegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    matric_no: str = Field(min_length=3, max_length=40)
    department_id: int
    level: Level
    semester_id: int


class StudentOut(BaseModel):
    id: int
    full_name: str
    matric_no: str
    department_id: int
    level: Level
    semester_id: int

    model_config = ConfigDict(from_attributes=True)


class StudentLoginRequest(BaseModel):
    matric_no: str
    full_name: str


class StudentToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    student: StudentOut


class StudentCourseOut(BaseModel):
    course_offering_id: int
    course_code: str
    course_title: str
    unit: int
    level: Level
    semester_id: int


class SeatInfoOut(BaseModel):
    exam_schedule_id: int
    course_code: str
    course_title: str
    exam_date: date
    start_time: time
    end_time: time
    exam_status: ExamStatus
    hall_name: str
    hall_code: str
    seat_number: int


class TimetableEntryOut(BaseModel):
    course_code: str
    course_title: str
    exam_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    exam_status: Optional[ExamStatus] = None
    hall_name: Optional[str] = None
    seat_number: Optional[int] = None
