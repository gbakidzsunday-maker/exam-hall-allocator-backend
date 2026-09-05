"""
Admin authentication: register (superadmin-only after the first bootstrap
admin exists) and login.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin, require_superadmin
from app.models import User, UserRole
from app.schemas import AdminCreate, AdminOut, Token
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Admin Auth"])


@router.post("/register", response_model=AdminOut, status_code=status.HTTP_201_CREATED)
def register_admin(
    payload: AdminCreate,
    db: Session = Depends(get_db),
):
    """
    Creates an admin account.

    Bootstrap rule: if no admin exists yet in the system, this endpoint is
    open (so you can create the first superadmin). Once at least one admin
    exists, creating further admins requires a superadmin token.
    """
    any_admin_exists = db.query(User).first() is not None

    if any_admin_exists:
        # Require a valid superadmin bearer token for subsequent registrations.
        # We re-implement the check inline (rather than Depends) so the
        # bootstrap case above can skip auth entirely.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "An admin already exists. Use POST /auth/register-additional "
                "(superadmin only) to add more admins."
            ),
        )

    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=UserRole.SUPERADMIN,  # first admin is always superadmin
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/register-additional", response_model=AdminOut, status_code=status.HTTP_201_CREATED
)
def register_additional_admin(
    payload: AdminCreate,
    db: Session = Depends(get_db),
    _superadmin: User = Depends(require_superadmin),
):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login_admin(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Admin account is disabled")

    token = create_access_token({"sub": str(user.id), "type": "admin", "role": user.role.value})
    return Token(access_token=token, role=user.role.value)


@router.get("/me", response_model=AdminOut)
def get_me(current_admin: User = Depends(get_current_admin)):
    return current_admin
