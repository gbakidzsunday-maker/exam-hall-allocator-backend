"""
Optional convenience script: creates the first superadmin account directly
in the database (bypassing the HTTP bootstrap rule), so you don't have to
rely on POST /auth/register being open only before any admin exists.

Usage:
    python seed.py
"""
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import User, UserRole
from app.security import hash_password


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == settings.DEFAULT_ADMIN_USERNAME).first()
        if existing:
            print(f"Admin '{settings.DEFAULT_ADMIN_USERNAME}' already exists. Nothing to do.")
            return

        admin = User(
            username=settings.DEFAULT_ADMIN_USERNAME,
            email=settings.DEFAULT_ADMIN_EMAIL,
            hashed_password=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
            role=UserRole.SUPERADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print(
            f"Created superadmin '{settings.DEFAULT_ADMIN_USERNAME}' "
            f"with password '{settings.DEFAULT_ADMIN_PASSWORD}'. "
            "Change this password immediately in production."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
