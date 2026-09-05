from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.models import Department, User
from app.schemas import DepartmentCreate, DepartmentOut

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.post("", response_model=DepartmentOut, status_code=201)
def create_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    if db.query(Department).filter(Department.code == payload.code).first():
        raise HTTPException(400, "Department code already exists")
    if db.query(Department).filter(Department.name == payload.name).first():
        raise HTTPException(400, "Department name already exists")
    dept = Department(name=payload.name, code=payload.code)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


@router.get("", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db)):
    # Public: students need this list to register.
    return db.query(Department).order_by(Department.name).all()


@router.get("/{department_id}", response_model=DepartmentOut)
def get_department(department_id: int, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(404, "Department not found")
    return dept


@router.put("/{department_id}", response_model=DepartmentOut)
def update_department(
    department_id: int,
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(404, "Department not found")
    dept.name = payload.name
    dept.code = payload.code
    db.commit()
    db.refresh(dept)
    return dept


@router.delete("/{department_id}", status_code=204)
def delete_department(
    department_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(404, "Department not found")
    db.delete(dept)
    db.commit()
    return None
