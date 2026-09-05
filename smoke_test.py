"""
End-to-end smoke test using FastAPI's TestClient against a throwaway
SQLite DB. Exercises: admin bootstrap -> department -> session/semester ->
course offering -> hall -> exam schedule -> hall allocation (mixing two
departments) -> student registration (x3) -> seat lookup -> timetable ->
mark exam completed -> submit semester -> registration/lookup now blocked.
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./smoke_test.db"
if os.path.exists("smoke_test.db"):
    os.remove("smoke_test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def check(condition, msg):
    if not condition:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"OK: {msg}")


# 1. Bootstrap admin
r = client.post(
    "/auth/register",
    json={"username": "admin", "email": "admin@mapoly.edu.ng", "password": "SuperSecret1"},
)
check(r.status_code == 201, f"admin bootstrap ({r.status_code}: {r.text})")

r = client.post("/auth/login", data={"username": "admin", "password": "SuperSecret1"})
check(r.status_code == 200, f"admin login ({r.status_code}: {r.text})")
admin_token = r.json()["access_token"]
H = {"Authorization": f"Bearer {admin_token}"}

# 2. Departments
r = client.post("/departments", json={"name": "Computer Science", "code": "CSD"}, headers=H)
check(r.status_code == 201, f"create dept CSD ({r.text})")
csd_id = r.json()["id"]

r = client.post("/departments", json={"name": "Statistics", "code": "STA"}, headers=H)
check(r.status_code == 201, f"create dept STA ({r.text})")
sta_id = r.json()["id"]

# 3. Session + semester
r = client.post("/sessions", json={"name": "2025/2026"}, headers=H)
check(r.status_code == 201, f"create session ({r.text})")
session_id = r.json()["id"]

r = client.post("/semesters", json={"session_id": session_id, "name": "First"}, headers=H)
check(r.status_code == 201, f"create semester ({r.text})")
semester_id = r.json()["id"]

r = client.post(f"/semesters/{semester_id}/start", headers=H)
check(r.status_code == 200 and r.json()["status"] == "active", f"start semester ({r.text})")

r = client.get("/semesters/active")
check(r.status_code == 200, f"public active-semester lookup ({r.text})")

# 4. Course offerings for both departments, level ND2
r = client.post(
    "/course-offerings",
    json={
        "course_code": "COM211",
        "course_title": "Data Structures",
        "course_unit": 3,
        "department_id": csd_id,
        "level": "ND2",
        "semester_id": semester_id,
    },
    headers=H,
)
check(r.status_code == 201, f"course offering CSD ({r.text})")
csd_offering_id = r.json()["id"]

r = client.post(
    "/course-offerings",
    json={
        "course_code": "STA201",
        "course_title": "Probability I",
        "course_unit": 2,
        "department_id": sta_id,
        "level": "ND2",
        "semester_id": semester_id,
    },
    headers=H,
)
check(r.status_code == 201, f"course offering STA ({r.text})")
sta_offering_id = r.json()["id"]

# 5. Hall
r = client.post(
    "/halls", json={"name": "Hall A", "code": "HA", "total_seats": 100}, headers=H
)
check(r.status_code == 201, f"create hall ({r.text})")
hall_id = r.json()["id"]

# 6. Exam schedules: CSD and STA courses in the SAME slot (so they can
#    legitimately share one hall at the same sitting).
r = client.post(
    "/exams",
    json={
        "course_offering_id": csd_offering_id,
        "exam_date": "2026-11-10",
        "start_time": "09:00:00",
        "end_time": "11:00:00",
    },
    headers=H,
)
check(r.status_code == 201, f"create CSD exam schedule ({r.text})")
exam_id = r.json()["id"]

r = client.post(
    "/exams",
    json={
        "course_offering_id": sta_offering_id,
        "exam_date": "2026-11-10",
        "start_time": "09:00:00",
        "end_time": "11:00:00",
    },
    headers=H,
)
check(r.status_code == 201, f"create STA exam schedule ({r.text})")
sta_exam_id = r.json()["id"]

# 7. Hall allocation mixing CSD + STA (different courses, same sitting) in one hall
r = client.post(
    "/hall-allocations",
    json={
        "hall_id": hall_id,
        "department_ranges": [
            {
                "exam_schedule_id": exam_id,
                "department_id": csd_id,
                "level": "ND2",
                "matric_start": "CSD/ND/24/001",
                "matric_end": "CSD/ND/24/060",
                "seat_start_no": 1,
                "seat_end_no": 60,
            },
            {
                "exam_schedule_id": sta_exam_id,
                "department_id": sta_id,
                "level": "ND2",
                "matric_start": "STA/ND/24/001",
                "matric_end": "STA/ND/24/040",
                "seat_start_no": 61,
                "seat_end_no": 100,
            },
        ],
    },
    headers=H,
)
check(r.status_code == 201, f"hall allocation with mixed depts ({r.text})")

# 8. Register 3 students: 2 CSD (in-range), 1 STA (in-range)
def register(full_name, matric_no, dept_id, level="ND2", semester_id=semester_id):
    r = client.post(
        "/students/register",
        json={
            "full_name": full_name,
            "matric_no": matric_no,
            "department_id": dept_id,
            "level": level,
            "semester_id": semester_id,
        },
    )
    check(r.status_code == 201, f"register {matric_no} ({r.text})")
    return r.json()["access_token"]

tok_csd_1 = register("Adeola Grace Okon", "CSD/ND/24/015", csd_id)
tok_csd_2 = register("Bello Musa", "CSD/ND/24/003", csd_id)
tok_sta_1 = register("Chinwe Obi", "STA/ND/24/010", sta_id)

# 9. Courses auto-allocated
r = client.get("/students/me/courses", headers={"Authorization": f"Bearer {tok_csd_1}"})
check(r.status_code == 200 and len(r.json()) == 1 and r.json()[0]["course_code"] == "COM211",
      f"CSD student auto-allocated correct course ({r.text})")

r = client.get("/students/me/courses", headers={"Authorization": f"Bearer {tok_sta_1}"})
check(r.status_code == 200 and r.json()[0]["course_code"] == "STA201",
      f"STA student auto-allocated correct course ({r.text})")

# 10. Seat lookup — CSD students should be seats 1 & 2 (sorted by matric: 003 < 015)
r = client.get("/students/me/seats", headers={"Authorization": f"Bearer {tok_csd_2}"})
seats = r.json()
check(r.status_code == 200 and len(seats) == 1, f"CSD student 2 has a seat ({r.text})")
check(seats[0]["seat_number"] == 1 and seats[0]["hall_name"] == "Hall A",
      f"CSD/003 got seat 1 in Hall A (got {seats[0]})")

r = client.get("/students/me/seats", headers={"Authorization": f"Bearer {tok_csd_1}"})
seats = r.json()
check(seats[0]["seat_number"] == 2, f"CSD/015 got seat 2 (got {seats[0]})")

r = client.get("/students/me/seats", headers={"Authorization": f"Bearer {tok_sta_1}"})
seats = r.json()
check(seats[0]["seat_number"] == 61, f"STA/010 got seat 61 (got {seats[0]})")

# 11. Timetable (printable)
r = client.get("/students/me/timetable", headers={"Authorization": f"Bearer {tok_csd_1}"})
tt = r.json()
check(
    r.status_code == 200 and tt[0]["seat_number"] == 2 and tt[0]["exam_status"] == "scheduled",
    f"personalized timetable shows seat + scheduled status ({r.text})",
)

# 12. Mark exam completed -> visible on student side
r = client.patch(f"/exams/{exam_id}/status", json={"status": "completed"}, headers=H)
check(r.status_code == 200, f"mark exam completed ({r.text})")

r = client.get("/students/me/seats", headers={"Authorization": f"Bearer {tok_csd_1}"})
check(r.json()[0]["exam_status"] == "completed", "student sees exam marked completed")

# 13. Submit (close) the semester -> new registration blocked, seat lookup blocked
r = client.post(f"/semesters/{semester_id}/submit", headers=H)
check(r.status_code == 200 and r.json()["status"] == "submitted", f"submit semester ({r.text})")

r = client.post(
    "/students/register",
    json={
        "full_name": "Late Comer",
        "matric_no": "CSD/ND/24/099",
        "department_id": csd_id,
        "level": "ND2",
        "semester_id": semester_id,
    },
)
check(r.status_code == 400, f"registration blocked after semester submitted ({r.status_code})")

r = client.get("/students/me/seats", headers={"Authorization": f"Bearer {tok_csd_1}"})
check(r.status_code == 403, f"seat lookup blocked after semester submitted ({r.status_code})")

# 14. Overflow handling: allocate a too-small range and check it's reported
r = client.post(
    "/departments", json={"name": "Mass Communication", "code": "MAC"}, headers=H
)
mac_id = r.json()["id"]
r = client.post(
    "/semesters", json={"session_id": session_id, "name": "Second"}, headers=H
)
sem2_id = r.json()["id"]
r = client.post(f"/semesters/{sem2_id}/start", headers=H)
check(r.status_code == 200 and r.json()["status"] == "active", f"start semester 2 ({r.text})")
r = client.post(
    "/course-offerings",
    json={
        "course_code": "MAC101",
        "course_title": "Intro to Mass Comm",
        "department_id": mac_id,
        "level": "ND1",
        "semester_id": sem2_id,
    },
    headers=H,
)
mac_offering_id = r.json()["id"]
r = client.post(
    "/exams",
    json={
        "course_offering_id": mac_offering_id,
        "exam_date": "2026-12-01",
        "start_time": "09:00:00",
        "end_time": "10:00:00",
    },
    headers=H,
)
mac_exam_id = r.json()["id"]
r = client.post(
    "/halls", json={"name": "Hall B", "code": "HB", "total_seats": 10}, headers=H
)
hall_b_id = r.json()["id"]

for i in range(1, 4):
    register(f"Overflow Student {i}", f"MAC/ND/24/00{i}", mac_id, level="ND1", semester_id=sem2_id)

r = client.post(
    "/hall-allocations",
    json={
        "hall_id": hall_b_id,
        "department_ranges": [
            {
                "exam_schedule_id": mac_exam_id,
                "department_id": mac_id,
                "level": "ND1",
                "matric_start": "MAC/ND/24/001",
                "matric_end": "MAC/ND/24/003",
                "seat_start_no": 1,
                "seat_end_no": 2,  # only 2 seats for 3 students -> overflow
            }
        ],
    },
    headers=H,
)
check(r.status_code == 201, f"allocate undersized range ({r.text})")

r = client.post(f"/hall-allocations/exam/{mac_exam_id}/recompute-seats", headers=H)
body = r.json()
check(
    r.status_code == 200 and len(body["overflow_students"]) == 1,
    f"overflow correctly reported ({body})",
)

print("\nALL SMOKE TESTS PASSED")
