"""
Courses & CourseOfferings.

A "course offering" is what actually appears on a level/semester/department
timetable: it links a Course to a Department, for a given Level and
Semester. Creating an offering can either reference an existing Course by
id, or create the course inline in the same call (via course_code/title).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.models import Course, CourseOffering, Department, Semester, User
from app.schemas import (
    CourseCreate,
    CourseOfferingCreate,
    CourseOfferingOut,
    CourseOut,
)

router = APIRouter(tags=["Courses"])


# --- Plain courses -----------------------------------------------------------
@router.post("/courses", response_model=CourseOut, status_code=201)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    if db.query(Course).filter(Course.code == payload.code).first():
        raise HTTPException(400, "Course code already exists")
    course = Course(code=payload.code, title=payload.title, unit=payload.unit)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("/courses", response_model=list[CourseOut])
def list_courses(db: Session = Depends(get_db)):
    return db.query(Course).order_by(Course.code).all()


# --- Course offerings (course <-> department/level/semester link) ----------
@router.post("/course-offerings", response_model=CourseOfferingOut, status_code=201)
def create_course_offering(
    payload: CourseOfferingCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    department = db.query(Department).filter(Department.id == payload.department_id).first()
    if not department:
        raise HTTPException(404, "Department not found")

    semester = db.query(Semester).filter(Semester.id == payload.semester_id).first()
    if not semester:
        raise HTTPException(404, "Semester not found")

    course = None
    if payload.course_id:
        course = db.query(Course).filter(Course.id == payload.course_id).first()
        if not course:
            raise HTTPException(404, "Course not found")
    elif payload.course_code and payload.course_title:
        course = db.query(Course).filter(Course.code == payload.course_code).first()
        if not course:
            course = Course(
                code=payload.course_code,
                title=payload.course_title,
                unit=payload.course_unit,
            )
            db.add(course)
            db.flush()
    else:
        raise HTTPException(
            400, "Provide either course_id, or course_code + course_title"
        )

    existing = (
        db.query(CourseOffering)
        .filter(
            CourseOffering.course_id == course.id,
            CourseOffering.department_id == payload.department_id,
            CourseOffering.level == payload.level,
            CourseOffering.semester_id == payload.semester_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            400, "This course is already linked to that department/level/semester"
        )

    offering = CourseOffering(
        course_id=course.id,
        department_id=payload.department_id,
        level=payload.level,
        semester_id=payload.semester_id,
    )
    db.add(offering)
    db.commit()
    db.refresh(offering)
    return offering


@router.get("/course-offerings", response_model=list[CourseOfferingOut])
def list_course_offerings(
    department_id: int | None = None,
    level: str | None = None,
    semester_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(CourseOffering)
    if department_id:
        query = query.filter(CourseOffering.department_id == department_id)
    if level:
        query = query.filter(CourseOffering.level == level)
    if semester_id:
        query = query.filter(CourseOffering.semester_id == semester_id)
    return query.all()


@router.delete("/course-offerings/{offering_id}", status_code=204)
def delete_course_offering(
    offering_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    offering = db.query(CourseOffering).filter(CourseOffering.id == offering_id).first()
    if not offering:
        raise HTTPException(404, "Course offering not found")
    db.delete(offering)
    db.commit()
    return None
