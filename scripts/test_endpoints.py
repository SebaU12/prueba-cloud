#!/usr/bin/env python3
"""
LMS Grupo 3 — Test integral de endpoints
Uso: python test_endpoints.py
"""
import json
import ssl
import sys
import urllib.request
import urllib.error

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

# ─── Configuración ────────────────────────────────────────────────────────────

BASE_U  = "https://bqr9yndpkh.execute-api.us-east-1.amazonaws.com/dev"
BASE_C  = "https://290ukd638e.execute-api.us-east-1.amazonaws.com/dev"
BASE_M  = "https://hg230hgizk.execute-api.us-east-1.amazonaws.com/dev"
BASE_CO = "https://ainxkn7mq0.execute-api.us-east-1.amazonaws.com/dev"
BASE_E  = "https://c1b3902w19.execute-api.us-east-1.amazonaws.com/dev"

ADMIN_EMAIL    = "admin@tenant-a.edu"
ADMIN_PASS     = "AdminA-Seguro-2026!"
TEACHER_EMAIL  = "teacher00001@tenant-a.edu"
TEACHER_PASS   = "Seed2026!"
STUDENT_EMAIL  = "student00201@tenant-a.edu"
STUDENT_PASS   = "Seed2026!"

# ─── Helpers ──────────────────────────────────────────────────────────────────

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
results = []


def req(method, url, body=None, token=None):
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30, context=_ctx) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {}


def check(name, status, body, expect_status=200, expect_key=None, expect_no_key=None):
    ok = status == expect_status
    if expect_key:
        ok = ok and expect_key in str(body)
    if expect_no_key:
        ok = ok and expect_no_key not in str(body)
    icon = PASS if ok else FAIL
    results.append(ok)
    detail = f"status={status}"
    if not ok:
        detail += f"  body={json.dumps(body)[:200]}"
    print(f"  {icon}  {name:<55} {detail}")
    return body


# ─── Tests ────────────────────────────────────────────────────────────────────

print("\n══════════════════════════════════════════════════════════")
print("  LMS Grupo 3 — Test integral de endpoints")
print("══════════════════════════════════════════════════════════\n")

# ── 1. USUARIOS ───────────────────────────────────────────────────────────────
print("── 1. Usuarios ──────────────────────────────────────────")

# Login admin
s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": ADMIN_EMAIL, "password": ADMIN_PASS})
check("POST /v1/auth/login (admin)", s, b, 200, "accessToken")
admin_token   = b.get("data", {}).get("accessToken", "")
admin_user_id = b.get("data", {}).get("user", {}).get("userId", "")

# Login bad password
s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": ADMIN_EMAIL, "password": "wrong"})
check("POST /v1/auth/login (bad pass) → INVALID_CREDENTIALS", s, b, 200, "INVALID_CREDENTIALS")

# GET /me
s, b = req("GET", f"{BASE_U}/v1/me", token=admin_token)
check("GET  /v1/me", s, b, 200, "userId")
check("GET  /v1/me — sin campos sensibles", s, b, 200,
      expect_no_key="passwordHashB64")

# GET /me sin token → 401
s, b = req("GET", f"{BASE_U}/v1/me")
check("GET  /v1/me (sin token) → 401", s, b, 401)

# Crear usuario teacher_new
s, b = req("POST", f"{BASE_U}/v1/users",
           {"email": "teacher_new@tenant-a.edu", "password": "Teacher2026!", "role": "teacher"},
           token=admin_token)
new_user_created = s == 200 or "CONFLICT" in str(b)
print(f"  {'✓' if new_user_created else '✗'}  POST /v1/users (crear teacher)                          status={s}")
results.append(new_user_created)
new_teacher_id = b.get("data", {}).get("userId", "")

# Crear usuario — rol inválido
s, b = req("POST", f"{BASE_U}/v1/users",
           {"email": "bad@tenant-a.edu", "password": "X", "role": "superadmin"},
           token=admin_token)
check("POST /v1/users (rol inválido) → INVALID_BODY", s, b, 200, "INVALID_BODY")

# Listar usuarios
s, b = req("GET", f"{BASE_U}/v1/users", token=admin_token)
check("GET  /v1/users (listar)", s, b, 200, "items")

# GET /users/{userId}
if admin_user_id:
    s, b = req("GET", f"{BASE_U}/v1/users/{admin_user_id}", token=admin_token)
    check("GET  /v1/users/{userId}", s, b, 200, "userId")

# Login teacher
s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": TEACHER_EMAIL, "password": TEACHER_PASS})
check("POST /v1/auth/login (teacher)", s, b, 200, "accessToken")
teacher_token   = b.get("data", {}).get("accessToken", "")
teacher_user_id = b.get("data", {}).get("user", {}).get("userId", "")

# Login student
s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": STUDENT_EMAIL, "password": STUDENT_PASS})
check("POST /v1/auth/login (student)", s, b, 200, "accessToken")
student_token   = b.get("data", {}).get("accessToken", "")
student_user_id = b.get("data", {}).get("user", {}).get("userId", "")

# Logout
s, b = req("POST", f"{BASE_U}/v1/auth/logout", token=admin_token)
check("POST /v1/auth/logout", s, b, 200)
# Re-login para seguir usando admin_token
s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": ADMIN_EMAIL, "password": ADMIN_PASS})
admin_token = b.get("data", {}).get("accessToken", "")

# ── 2. CURSOS ─────────────────────────────────────────────────────────────────
print("\n── 2. Cursos ────────────────────────────────────────────")

# Crear curso como teacher
s, b = req("POST", f"{BASE_C}/v1/courses",
           {"title": "Test Course", "description": "Integration test course"},
           token=teacher_token)
check("POST /v1/courses (teacher)", s, b, 200, "courseId")
course_id = b.get("data", {}).get("courseId", "")

# Crear curso como student → FORBIDDEN
s, b = req("POST", f"{BASE_C}/v1/courses",
           {"title": "X"}, token=student_token)
check("POST /v1/courses (student) → FORBIDDEN", s, b, 200, "FORBIDDEN")

# Listar cursos
s, b = req("GET", f"{BASE_C}/v1/courses", token=admin_token)
check("GET  /v1/courses", s, b, 200, "items")

# Obtener curso
if course_id:
    s, b = req("GET", f"{BASE_C}/v1/courses/{course_id}", token=teacher_token)
    check("GET  /v1/courses/{courseId}", s, b, 200, "courseId")

    # Publicar curso (PATCH status=published)
    s, b = req("PATCH", f"{BASE_C}/v1/courses/{course_id}",
               {"status": "published"}, token=teacher_token)
    check("PATCH /v1/courses/{courseId} (publish)", s, b, 200)

# ── 3. MATRÍCULAS ─────────────────────────────────────────────────────────────
print("\n── 3. Matrículas ────────────────────────────────────────")

# Buscar un curso publicado existente del seed para matricular
s, b = req("GET", f"{BASE_C}/v1/courses", token=student_token)
published_course_id = ""
for item in b.get("data", {}).get("items", []):
    if item.get("status") == "published":
        published_course_id = item["courseId"]
        break
if not published_course_id and course_id:
    published_course_id = course_id

# Matricular student
if published_course_id and student_user_id:
    s, b = req("POST", f"{BASE_M}/v1/enrollments",
               {"courseId": published_course_id},
               token=student_token)
    enrolled = s == 200 or "EnrollmentDuplicate" in str(b) or "CONFLICT" in str(b)
    print(f"  {'✓' if enrolled else '✗'}  POST /v1/enrollments (student)                          status={s}")
    results.append(enrolled)
    if not enrolled:
        print(f"       body={json.dumps(b)[:200]}")

# Listar matrículas
s, b = req("GET", f"{BASE_M}/v1/enrollments", token=student_token)
check("GET  /v1/enrollments (student)", s, b, 200, "items")

s, b = req("GET", f"{BASE_M}/v1/enrollments?courseId={published_course_id}", token=admin_token)
check("GET  /v1/enrollments (admin)", s, b, 200, "items")

# ── 4. CONTENIDOS ─────────────────────────────────────────────────────────────
print("\n── 4. Contenidos ────────────────────────────────────────")

# Registrar material
if published_course_id:
    s, b = req("POST", f"{BASE_CO}/v1/materials",
               {"courseId": published_course_id, "title": "Test PDF",
                "fileName": "test.pdf", "mimeType": "application/pdf"},
               token=teacher_token)
    check("POST /v1/materials", s, b, 200, "contentId")
    content_id = b.get("data", {}).get("contentId", "")

    if content_id:
        # Presigned URL para subir
        s, b = req("POST", f"{BASE_CO}/v1/materials/{content_id}/upload-url",
                   token=teacher_token)
        check("POST /v1/materials/{id}/upload-url", s, b, 200, "uploadUrl")

        # Listar materiales
        s, b = req("GET", f"{BASE_CO}/v1/materials?courseId={published_course_id}",
                   token=student_token)
        check("GET  /v1/materials?courseId=...", s, b, 200, "items")

# ── 5. EVALUACIONES ───────────────────────────────────────────────────────────
print("\n── 5. Evaluaciones ──────────────────────────────────────")

if published_course_id:
    questions = [
        {"text": "¿Qué es Python?", "options": ["Lenguaje", "IDE", "DB", "SO"], "correctIndex": 0},
        {"text": "¿Qué es AWS?", "options": ["Nube", "Lenguaje", "DB", "SO"], "correctIndex": 0},
        {"text": "¿Qué es Lambda?", "options": ["FaaS", "DB", "VM", "CDN"], "correctIndex": 0},
    ]
    s, b = req("POST", f"{BASE_E}/v1/evaluations",
               {"courseId": published_course_id, "title": "Test Quiz", "questions": questions},
               token=teacher_token)
    check("POST /v1/evaluations", s, b, 200, "evaluationId")
    eval_id = b.get("data", {}).get("evaluationId", "")

    if eval_id:
        # Obtener evaluación como student — no debe tener correctIndex
        s, b = req("GET", f"{BASE_E}/v1/evaluations/{eval_id}", token=student_token)
        check("GET  /v1/evaluations/{id} (student — sin correctIndex)", s, b, 200,
              expect_no_key="correctIndex")

        # Obtener como teacher — sí tiene correctIndex
        s, b = req("GET", f"{BASE_E}/v1/evaluations/{eval_id}", token=teacher_token)
        check("GET  /v1/evaluations/{id} (teacher — con correctIndex)", s, b, 200, "correctIndex")

        # Publicar evaluación
        s, b = req("PATCH", f"{BASE_E}/v1/evaluations/{eval_id}",
                   {"status": "published"}, token=teacher_token)
        check("PATCH /v1/evaluations/{id} (publish)", s, b, 200)

    # Listar evaluaciones
    s, b = req("GET", f"{BASE_E}/v1/evaluations", token=student_token)
    check("GET  /v1/evaluations", s, b, 200, "items")

# ─── Resumen ──────────────────────────────────────────────────────────────────
total  = len(results)
passed = sum(results)
failed = total - passed

print(f"\n══════════════════════════════════════════════════════════")
print(f"  Resultado: {passed}/{total} tests pasados", end="")
if failed:
    print(f"  ({failed} fallidos \033[91m✗\033[0m)")
else:
    print(f"  \033[92m— todo OK\033[0m")
print("══════════════════════════════════════════════════════════\n")

sys.exit(0 if failed == 0 else 1)
