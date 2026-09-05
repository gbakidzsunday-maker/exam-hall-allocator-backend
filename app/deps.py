"""
Shared FastAPI dependencies: DB session re-export, current-admin and
current-student resolution from JWT bearer tokens.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Student, User, UserRole
from app.security import decode_access_token

oauth2_admin_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
oauth2_student_scheme = OAuth2PasswordBearer(tokenUrl="/students/login", auto_error=False)


def get_current_admin(
    token: str = Depends(oauth2_admin_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate admin credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    payload = decode_access_token(token)
    if not payload or payload.get("type") != "admin":
        raise credentials_exception
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user


def require_superadmin(user: User = Depends(get_current_admin)) -> User:
    if user.role != UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin privileges required",
        )
    return user


def get_current_student(
    token: str = Depends(oauth2_student_scheme), db: Session = Depends(get_db)
) -> Student:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate student credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    payload = decode_access_token(token)
    if not payload or payload.get("type") != "student":
        raise credentials_exception
    student_id = payload.get("sub")
    student = db.query(Student).filter(Student.id == int(student_id)).first()
    if not student:
        raise credentials_exception
    return student
