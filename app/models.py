"""
SQLAlchemy ORM models for the Exam Seat & Hall Allocation System.

Domain overview
----------------
- Department: e.g. Computer Science, Statistics.
- AcademicSession / Semester: an admin "starts a new semester" (creates a
  Semester row with status=ACTIVE) and later "submits" it (status=SUBMITTED)
  which locks it: students can no longer register or fetch seat allocations
  for that semester once it is submitted.
- Course / CourseOffering: a Course (code + title) is offered to a specific
  Department + Level + Semester via a CourseOffering row. This is how an
  admin "adds a course for a level/semester" and "links a course to a
  department" at the same time.
- Hall: a physical exam hall with a fixed seat capacity.
- ExamSchedule: the timetable entry for a CourseOffering (date/time),
  independently markable as completed.
- HallAllocation: ties an ExamSchedule to one (or more) Hall(s).
- HallDepartmentRange: within a HallAllocation, a block of seats reserved
  for a Department + Level whose matric numbers fall within a given range.
  This is how an admin "mixes two or more departments" in one hall.
- Student: a lightweight, self-registered profile (full name, matric no,
  department, level, semester). Registering auto-computes the student's
  courses from CourseOffering rows.
- SeatAllocation: the computed (student, exam) -> (hall, seat number)
  mapping, derived from HallDepartmentRange at lookup/generation time.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class Level(str, enum.Enum):
    ND1 = "ND1"
    ND2 = "ND2"
    HND1 = "HND1"
    HND2 = "HND2"


class SemesterName(str, enum.Enum):
    FIRST = "First"
    SECOND = "Second"


class SemesterStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUBMITTED = "submitted"  # locked: exams over, no new registration/lookup


class ExamStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Admin users
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.ADMIN, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------
class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=False)  # e.g. "CSD"
    created_at = Column(DateTime, default=datetime.utcnow)

    course_offerings = relationship("CourseOffering", back_populates="department")
    students = relationship("Student", back_populates="department")


# ---------------------------------------------------------------------------
# Academic session / semester
# ---------------------------------------------------------------------------
class AcademicSession(Base):
    __tablename__ = "academic_sessions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(20), unique=True, nullable=False)  # e.g. "2025/2026"
    created_at = Column(DateTime, default=datetime.utcnow)

    semesters = relationship(
        "Semester", back_populates="session", cascade="all, delete-orphan"
    )


class Semester(Base):
    __tablename__ = "semesters"
    __table_args__ = (UniqueConstraint("session_id", "name", name="uq_session_semester"),)

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("academic_sessions.id"), nullable=False)
    name = Column(Enum(SemesterName), nullable=False)
    status = Column(Enum(SemesterStatus), default=SemesterStatus.DRAFT, nullable=False)
    started_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("AcademicSession", back_populates="semesters")
    course_offerings = relationship("CourseOffering", back_populates="semester")
    students = relationship("Student", back_populates="semester")
    exam_schedules = relationship("ExamSchedule", back_populates="semester")


# ---------------------------------------------------------------------------
# Courses & offerings
# ---------------------------------------------------------------------------
class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False)  # e.g. "COM211"
    title = Column(String(200), nullable=False)
    unit = Column(Integer, default=2)
    created_at = Column(DateTime, default=datetime.utcnow)

    offerings = relationship(
        "CourseOffering", back_populates="course", cascade="all, delete-orphan"
    )


class CourseOffering(Base):
    """
    Links a Course to a Department + Level + Semester.
    This is the unit that a student's course list is computed from, and the
    unit an ExamSchedule (timetable entry) is created against.
    """

    __tablename__ = "course_offerings"
    __table_args__ = (
        UniqueConstraint(
            "course_id", "department_id", "level", "semester_id",
            name="uq_course_offering",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    level = Column(Enum(Level), nullable=False)
    semester_id = Column(Integer, ForeignKey("semesters.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", back_populates="offerings")
    department = relationship("Department", back_populates="course_offerings")
    semester = relationship("Semester", back_populates="course_offerings")
    student_allocations = relationship(
        "StudentCourseAllocation", back_populates="course_offering",
        cascade="all, delete-orphan",
    )
    exam_schedule = relationship(
        "ExamSchedule", back_populates="course_offering", uselist=False,
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# Halls
# ---------------------------------------------------------------------------
class Hall(Base):
    __tablename__ = "halls"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=False)
    total_seats = Column(Integer, nullable=False)
    # Optional layout hint for the frontend, e.g. 10 rows x 12 columns.
    rows = Column(Integer, nullable=True)
    columns = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    hall_allocations = relationship("HallAllocation", back_populates="hall")


# ---------------------------------------------------------------------------
# Exam timetable
# ---------------------------------------------------------------------------
class ExamSchedule(Base):
    __tablename__ = "exam_schedules"

    id = Column(Integer, primary_key=True, index=True)
    course_offering_id = Column(
        Integer, ForeignKey("course_offerings.id"), unique=True, nullable=False
    )
    semester_id = Column(Integer, ForeignKey("semesters.id"), nullable=False)
    exam_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    status = Column(Enum(ExamStatus), default=ExamStatus.SCHEDULED, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    course_offering = relationship("CourseOffering", back_populates="exam_schedule")
    semester = relationship("Semester", back_populates="exam_schedules")
    hall_department_ranges = relationship(
        "HallDepartmentRange", back_populates="exam_schedule", cascade="all, delete-orphan"
    )
    seat_allocations = relationship(
        "SeatAllocation", back_populates="exam_schedule", cascade="all, delete-orphan"
    )


class HallAllocation(Base):
    """
    A hall booked for one physical "sitting": a specific hall at a specific
    date/start/end time. Several different departments can write different
    courses in the same hall during the same sitting (very common in
    practice) - each such department/course block is a HallDepartmentRange
    underneath this HallAllocation. A hall can be reused for a different
    sitting at a different date/time via a separate HallAllocation row.
    """

    __tablename__ = "hall_allocations"
    __table_args__ = (
        UniqueConstraint(
            "hall_id", "exam_date", "start_time", "end_time", name="uq_hall_sitting"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    hall_id = Column(Integer, ForeignKey("halls.id"), nullable=False)
    exam_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    hall = relationship("Hall", back_populates="hall_allocations")
    department_ranges = relationship(
        "HallDepartmentRange", back_populates="hall_allocation",
        cascade="all, delete-orphan",
    )


class HallDepartmentRange(Base):
    """
    Within one HallAllocation (one hall, one sitting), reserves a
    contiguous block of seats (seat_start_no..seat_end_no) for students of
    a given Department + Level, sitting a specific ExamSchedule (course),
    whose matric number falls within [matric_start, matric_end]
    (lexicographic/string comparison, since matric numbers are
    alphanumeric).

    This is what lets an admin "mix two or more departments" (each writing
    their own course) in the same hall, and assign a "matric number range
    of department and level to a hall".
    """

    __tablename__ = "hall_department_ranges"

    id = Column(Integer, primary_key=True, index=True)
    hall_allocation_id = Column(Integer, ForeignKey("hall_allocations.id"), nullable=False)
    exam_schedule_id = Column(Integer, ForeignKey("exam_schedules.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    level = Column(Enum(Level), nullable=False)
    matric_start = Column(String(40), nullable=False)
    matric_end = Column(String(40), nullable=False)
    seat_start_no = Column(Integer, nullable=False)
    seat_end_no = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    hall_allocation = relationship("HallAllocation", back_populates="department_ranges")
    exam_schedule = relationship("ExamSchedule", back_populates="hall_department_ranges")
    department = relationship("Department")


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------
class Student(Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("matric_no", name="uq_student_matric"),)

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), nullable=False)
    matric_no = Column(String(40), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    level = Column(Enum(Level), nullable=False)
    semester_id = Column(Integer, ForeignKey("semesters.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department", back_populates="students")
    semester = relationship("Semester", back_populates="students")
    course_allocations = relationship(
        "StudentCourseAllocation", back_populates="student", cascade="all, delete-orphan"
    )
    seat_allocations = relationship(
        "SeatAllocation", back_populates="student", cascade="all, delete-orphan"
    )


class StudentCourseAllocation(Base):
    """Computed at registration time: every CourseOffering matching the
    student's department + level + semester."""

    __tablename__ = "student_course_allocations"
    __table_args__ = (
        UniqueConstraint("student_id", "course_offering_id", name="uq_student_course"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    course_offering_id = Column(Integer, ForeignKey("course_offerings.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="course_allocations")
    course_offering = relationship("CourseOffering", back_populates="student_allocations")


class SeatAllocation(Base):
    """Computed (student, exam) -> (hall, seat number) mapping."""

    __tablename__ = "seat_allocations"
    __table_args__ = (
        UniqueConstraint("student_id", "exam_schedule_id", name="uq_student_exam_seat"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    exam_schedule_id = Column(Integer, ForeignKey("exam_schedules.id"), nullable=False)
    hall_id = Column(Integer, ForeignKey("halls.id"), nullable=False)
    hall_department_range_id = Column(
        Integer, ForeignKey("hall_department_ranges.id"), nullable=False
    )
    seat_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="seat_allocations")
    exam_schedule = relationship("ExamSchedule", back_populates="seat_allocations")
    hall = relationship("Hall")
    hall_department_range = relationship("HallDepartmentRange")
