"""
Exam Seat & Hall Allocation System — FastAPI entrypoint.

Run with:
    uvicorn app.main:app --reload

Interactive docs: http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth, courses, departments, exams, halls, semesters, students

# Create tables if they don't exist yet. For real production use, prefer
# Alembic migrations instead of create_all.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Exam Seat & Hall Allocation System",
    description=(
        "Backend API for generating exam seat numbers and hall allocations "
        "for ND1/ND2/HND1/HND2 students, with admin and student roles."
    ),
    version="1.0.0",
)

# Reads ALLOWED_ORIGINS from the environment (comma-separated). Defaults to
# "*" for local development; set it to your Vercel URL(s) in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # No cookies are used (auth is a Bearer token in the Authorization
    # header), so credentials aren't needed and are left off to keep the
    # wildcard-origin default valid per the CORS spec.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(departments.router)
app.include_router(semesters.router)
app.include_router(courses.router)
app.include_router(halls.router)
app.include_router(exams.router)
app.include_router(students.router)


@app.get("/", tags=["Health"])
def root():
    return {
        "status": "ok",
        "service": "Exam Seat & Hall Allocation System",
        "docs": "/docs",
    }
