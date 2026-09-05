from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.models import Hall, User
from app.schemas import HallCreate, HallOut

router = APIRouter(prefix="/halls", tags=["Halls"])


@router.post("", response_model=HallOut, status_code=201)
def create_hall(
    payload: HallCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    if db.query(Hall).filter(Hall.code == payload.code).first():
        raise HTTPException(400, "Hall code already exists")
    if db.query(Hall).filter(Hall.name == payload.name).first():
        raise HTTPException(400, "Hall name already exists")
    hall = Hall(
        name=payload.name,
        code=payload.code,
        total_seats=payload.total_seats,
        rows=payload.rows,
        columns=payload.columns,
    )
    db.add(hall)
    db.commit()
    db.refresh(hall)
    return hall


@router.get("", response_model=list[HallOut])
def list_halls(db: Session = Depends(get_db)):
    return db.query(Hall).order_by(Hall.name).all()


@router.get("/{hall_id}", response_model=HallOut)
def get_hall(hall_id: int, db: Session = Depends(get_db)):
    hall = db.query(Hall).filter(Hall.id == hall_id).first()
    if not hall:
        raise HTTPException(404, "Hall not found")
    return hall


@router.put("/{hall_id}", response_model=HallOut)
def update_hall(
    hall_id: int,
    payload: HallCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    hall = db.query(Hall).filter(Hall.id == hall_id).first()
    if not hall:
        raise HTTPException(404, "Hall not found")
    hall.name = payload.name
    hall.code = payload.code
    hall.total_seats = payload.total_seats
    hall.rows = payload.rows
    hall.columns = payload.columns
    db.commit()
    db.refresh(hall)
    return hall


@router.delete("/{hall_id}", status_code=204)
def delete_hall(
    hall_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    hall = db.query(Hall).filter(Hall.id == hall_id).first()
    if not hall:
        raise HTTPException(404, "Hall not found")
    db.delete(hall)
    db.commit()
    return None
