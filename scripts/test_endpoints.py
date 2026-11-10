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

# Configuración

BASE_U  = "https://bqr9yndpkh.execute-api.us-east-1.amazonaws.com/dev"
BASE_C  = "https://290ukd638e.execute-api.us-east-1.amazonaws.com/dev"
BASE_M  = "https://hg230hgizk.execute-api.us-east-1.amazonaws.com/dev"
BASE_CO = "https://ainxkn7mq0.execute-api.us-east-1.amazonaws.com/dev"
BASE_E  = "https://c1b3902w19.execute-api.us-east-1.amazonaws.com/dev"

ADMIN_EMAIL    = "admin@tenant-a.edu"
ADMIN_PASS     = "AdminA-Seguro-2026!"
ADMIN_B_EMAIL  = "admin@tenant-b.edu"
ADMIN_B_PASS   = "AdminB-Seguro-2026!"
TEACHER_EMAIL  = "teacher00001@tenant-a.edu"
TEACHER_PASS   = "Seed2026!"
TEACHER2_EMAIL = "teacher00002@tenant-a.edu"
TEACHER2_PASS  = "Seed2026!"
STUDENT_EMAIL  = "student00201@tenant-a.edu"
STUDENT_PASS   = "Seed2026!"
STUDENT2_EMAIL = "student00202@tenant-a.edu"
STUDENT2_PASS  = "Seed2026!"

# Helpers

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
results = []


def req(method, url, body=None, token=None, raw_body=None, extra_headers=None):
    if raw_body is not None:
        data = raw_body
        headers = {}
    else:
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"} if body else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
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
    print(f"  {icon}  {name:<58} {detail}")
    return body


# Tests

print("\n══════════════════════════════════════════════════════════")
print("  LMS Grupo 3 — Test integral de endpoints")
print("══════════════════════════════════════════════════════════\n")

# 1. Usuarios
print("── 1. Usuarios ──────────────────────────────────────────")

s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": ADMIN_EMAIL, "password": ADMIN_PASS})
check("POST /v1/auth/login (admin)", s, b, 200, "accessToken")
admin_token   = b.get("data", {}).get("accessToken", "")
admin_user_id = b.get("data", {}).get("user", {}).get("userId", "")

s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": ADMIN_EMAIL, "password": "wrong"})
check("POST /v1/auth/login (bad pass) → INVALID_CREDENTIALS", s, b, 200, "INVALID_CREDENTIALS")

s, b = req("GET", f"{BASE_U}/v1/me", token=admin_token)
check("GET  /v1/me", s, b, 200, "userId")
check("GET  /v1/me — sin campos sensibles", s, b, 200, expect_no_key="passwordHashB64")

s, b = req("GET", f"{BASE_U}/v1/me")
check("GET  /v1/me (sin token) → 401", s, b, 401)

s, b = req("POST", f"{BASE_U}/v1/users",
           {"email": "teacher_new@tenant-a.edu", "password": "Teacher2026!", "role": "teacher"},
           token=admin_token)
new_user_created = s == 200 or "CONFLICT" in str(b)
print(f"  {'✓' if new_user_created else '✗'}  POST /v1/users (crear teacher)                             status={s}")
results.append(new_user_created)
new_teacher_id = b.get("data", {}).get("userId", "")

s, b = req("POST", f"{BASE_U}/v1/users",
           {"email": "bad@tenant-a.edu", "password": "X", "role": "superadmin"},
           token=admin_token)
check("POST /v1/users (rol inválido) → INVALID_BODY", s, b, 200, "INVALID_BODY")

s, b = req("GET", f"{BASE_U}/v1/users", token=admin_token)
check("GET  /v1/users (listar)", s, b, 200, "items")

if admin_user_id:
    s, b = req("GET", f"{BASE_U}/v1/users/{admin_user_id}", token=admin_token)
    check("GET  /v1/users/{userId}", s, b, 200, "userId")

s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": TEACHER_EMAIL, "password": TEACHER_PASS})
check("POST /v1/auth/login (teacher)", s, b, 200, "accessToken")
teacher_token   = b.get("data", {}).get("accessToken", "")
teacher_user_id = b.get("data", {}).get("user", {}).get("userId", "")

s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": TEACHER2_EMAIL, "password": TEACHER2_PASS})
teacher2_token   = b.get("data", {}).get("accessToken", "")
teacher2_user_id = b.get("data", {}).get("user", {}).get("userId", "")

s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": STUDENT_EMAIL, "password": STUDENT_PASS})
check("POST /v1/auth/login (student)", s, b, 200, "accessToken")
student_token   = b.get("data", {}).get("accessToken", "")
student_user_id = b.get("data", {}).get("user", {}).get("userId", "")

s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": STUDENT2_EMAIL, "password": STUDENT2_PASS})
student2_token   = b.get("data", {}).get("accessToken", "")
student2_user_id = b.get("data", {}).get("user", {}).get("userId", "")

# Token inválido después de logout (revocación)
s, b = req("POST", f"{BASE_U}/v1/auth/logout", token=admin_token)
check("POST /v1/auth/logout", s, b, 200)
s, b = req("GET", f"{BASE_U}/v1/me", token=admin_token)
check("GET  /v1/me (token revocado post-logout) → 403", s, b, 403)
# Re-login
s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": ADMIN_EMAIL, "password": ADMIN_PASS})
admin_token = b.get("data", {}).get("accessToken", "")

# Admin TENANT_B (aislamiento multi-tenant)
s, b = req("POST", f"{BASE_U}/v1/auth/login",
           {"email": ADMIN_B_EMAIL, "password": ADMIN_B_PASS})
admin_b_token   = b.get("data", {}).get("accessToken", "")
admin_b_user_id = b.get("data", {}).get("user", {}).get("userId", "")

# 2. Cursos
print("\n── 2. Cursos ────────────────────────────────────────────")

s, b = req("POST", f"{BASE_C}/v1/courses",
           {"title": "Test Course", "description": "Integration test course"},
           token=teacher_token)
check("POST /v1/courses (teacher)", s, b, 200, "courseId")
course_id = b.get("data", {}).get("courseId", "")

s, b = req("POST", f"{BASE_C}/v1/courses",
           {"title": "X"}, token=student_token)
check("POST /v1/courses (student) → FORBIDDEN", s, b, 200, "FORBIDDEN")

s, b = req("GET", f"{BASE_C}/v1/courses", token=admin_token)
check("GET  /v1/courses", s, b, 200, "items")

# Listar cursos por teacherId (GSI)
if teacher_user_id:
    s, b = req("GET", f"{BASE_C}/v1/courses?teacherId={teacher_user_id}", token=admin_token)
    check("GET  /v1/courses?teacherId=... (GSI)", s, b, 200, "items")

if course_id:
    s, b = req("GET", f"{BASE_C}/v1/courses/{course_id}", token=teacher_token)
    check("GET  /v1/courses/{courseId}", s, b, 200, "courseId")

    s, b = req("PATCH", f"{BASE_C}/v1/courses/{course_id}",
               {"status": "published"}, token=teacher_token)
    check("PATCH /v1/courses/{courseId} (publish)", s, b, 200)

    # Teacher distinto no puede editar curso ajeno → FORBIDDEN
    if teacher2_token:
        s, b = req("PATCH", f"{BASE_C}/v1/courses/{course_id}",
                   {"title": "Hacked"}, token=teacher2_token)
        check("PATCH /v1/courses/{courseId} (otro teacher) → FORBIDDEN", s, b, 200, "FORBIDDEN")

# TENANT_B no puede ver cursos de TENANT_A (aislamiento)
if admin_b_token and course_id:
    s, b = req("GET", f"{BASE_C}/v1/courses/{course_id}", token=admin_b_token)
    check("GET  /v1/courses/{courseId} (TENANT_B) → NOT_FOUND", s, b, 200, "NOT_FOUND")

# 3. Matrículas
print("\n── 3. Matrículas ────────────────────────────────────────")

s, b = req("GET", f"{BASE_C}/v1/courses", token=student_token)
published_course_id = ""
for item in b.get("data", {}).get("items", []):
    if item.get("status") == "published":
        published_course_id = item["courseId"]
        break
if not published_course_id and course_id:
    published_course_id = course_id

if published_course_id and student_user_id:
    s, b = req("POST", f"{BASE_M}/v1/enrollments",
               {"courseId": published_course_id}, token=student_token)
    enrolled = s == 200 or "CONFLICT" in str(b)
    print(f"  {'✓' if enrolled else '✗'}  POST /v1/enrollments (student)                             status={s}")
    results.append(enrolled)

    # Matrícula duplicada → CONFLICT
    s, b = req("POST", f"{BASE_M}/v1/enrollments",
               {"courseId": published_course_id}, token=student_token)
    check("POST /v1/enrollments (duplicada) → CONFLICT", s, b, 200, "CONFLICT")

s, b = req("GET", f"{BASE_M}/v1/enrollments?studentId={student_user_id}", token=student_token)
check("GET  /v1/enrollments (student)", s, b, 200, "items")

s, b = req("GET", f"{BASE_M}/v1/enrollments?courseId={published_course_id}", token=admin_token)
check("GET  /v1/enrollments (admin)", s, b, 200, "items")

# Student no puede ver matrículas de otro student → FORBIDDEN
if student2_token and student_user_id:
    s, b = req("GET", f"{BASE_M}/v1/enrollments?studentId={student_user_id}", token=student2_token)
    check("GET  /v1/enrollments (otro student) → FORBIDDEN", s, b, 200, "FORBIDDEN")

# 4. Contenidos
print("\n── 4. Contenidos ────────────────────────────────────────")

content_id  = ""
upload_url  = ""
if published_course_id:
    s, b = req("POST", f"{BASE_CO}/v1/materials",
               {"courseId": published_course_id, "title": "Test PDF",
                "fileName": "test.pdf", "mimeType": "application/pdf"},
               token=teacher_token)
    check("POST /v1/materials", s, b, 200, "contentId")
    content_id = b.get("data", {}).get("contentId", "")

    if content_id:
        s, b = req("POST", f"{BASE_CO}/v1/materials/{content_id}/upload-url",
                   token=teacher_token)
        check("POST /v1/materials/{id}/upload-url", s, b, 200, "uploadUrl")
        upload_url = b.get("data", {}).get("uploadUrl", "")

        # Subir archivo real a S3 con la presigned URL
        if upload_url:
            fake_pdf = b"%PDF-1.4 test content"
            s_s3, _ = req("PUT", upload_url,
                          raw_body=fake_pdf,
                          extra_headers={"Content-Type": "application/pdf"})
            uploaded = s_s3 in (200, 204)
            print(f"  {'✓' if uploaded else '✗'}  PUT presigned URL (upload S3)                              status={s_s3}")
            results.append(uploaded)

            if uploaded:
                # Confirmar upload
                s, b = req("POST", f"{BASE_CO}/v1/materials/{content_id}/confirm",
                           token=teacher_token)
                check("POST /v1/materials/{id}/confirm", s, b, 200, "confirmed")

                # Download URL como student matriculado
                s, b = req("GET", f"{BASE_CO}/v1/materials/{content_id}/download-url",
                           token=student_token)
                check("GET  /v1/materials/{id}/download-url (enrolled)", s, b, 200, "downloadUrl")
                download_url = b.get("data", {}).get("downloadUrl", "")

                # Descarga real desde S3 con la presigned URL (sin headers extra)
                if download_url:
                    s_s3, _ = req("GET", download_url)
                    downloaded = s_s3 in (200, 206)
                    print(f"  {'✓' if downloaded else '✗'}  GET presigned URL (download S3)                            status={s_s3}")
                    results.append(downloaded)

                # Download URL como student NO matriculado → FORBIDDEN
                if student2_token:
                    s, b = req("GET", f"{BASE_CO}/v1/materials/{content_id}/download-url",
                               token=student2_token)
                    check("GET  /v1/materials/{id}/download-url (not enrolled) → FORBIDDEN",
                          s, b, 200, "FORBIDDEN")

        s, b = req("GET", f"{BASE_CO}/v1/materials?courseId={published_course_id}",
                   token=student_token)
        check("GET  /v1/materials?courseId=...", s, b, 200, "items")

# 5. Evaluaciones
print("\n── 5. Evaluaciones ──────────────────────────────────────")

if published_course_id:
    questions = [
        {"text": "¿Qué es Python?", "options": ["Lenguaje", "IDE", "DB", "SO"], "correctIndex": 0},
        {"text": "¿Qué es AWS?",    "options": ["Nube", "Lenguaje", "DB", "SO"], "correctIndex": 0},
        {"text": "¿Qué es Lambda?", "options": ["FaaS", "DB", "VM", "CDN"],     "correctIndex": 0},
    ]
    s, b = req("POST", f"{BASE_E}/v1/evaluations",
               {"courseId": published_course_id, "title": "Test Quiz", "questions": questions},
               token=teacher_token)
    check("POST /v1/evaluations", s, b, 200, "evaluationId")
    eval_id = b.get("data", {}).get("evaluationId", "")

    if eval_id:
        s, b = req("GET", f"{BASE_E}/v1/evaluations/{eval_id}", token=student_token)
        check("GET  /v1/evaluations/{id} (student — sin correctIndex)", s, b, 200,
              expect_no_key="correctIndex")

        s, b = req("GET", f"{BASE_E}/v1/evaluations/{eval_id}", token=teacher_token)
        check("GET  /v1/evaluations/{id} (teacher — con correctIndex)", s, b, 200, "correctIndex")

        s, b = req("PATCH", f"{BASE_E}/v1/evaluations/{eval_id}",
                   {"status": "published"}, token=teacher_token)
        check("PATCH /v1/evaluations/{id} (publish)", s, b, 200)

        # Teacher distinto no puede editar evaluación ajena → FORBIDDEN
        if teacher2_token:
            s, b = req("PATCH", f"{BASE_E}/v1/evaluations/{eval_id}",
                       {"title": "Hacked"}, token=teacher2_token)
            check("PATCH /v1/evaluations/{id} (otro teacher) → FORBIDDEN", s, b, 200, "FORBIDDEN")

        # Student no matriculado no puede ver evaluación → NOT_FOUND (security-by-obscurity)
        if student2_token:
            s, b = req("GET", f"{BASE_E}/v1/evaluations/{eval_id}", token=student2_token)
            check("GET  /v1/evaluations/{id} (not enrolled) → NOT_FOUND", s, b, 200, "NOT_FOUND")

    s, b = req("GET", f"{BASE_E}/v1/evaluations?courseId={published_course_id}", token=student_token)
    check("GET  /v1/evaluations", s, b, 200, "items")

# Resumen
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
