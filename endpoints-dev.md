# LMS Grupo 3 — Recursos desplegados (dev)

## S3

| Recurso | Valor |
|---|---|
| Bucket materiales | `lms-materiales-198909467842-dev` |

## SNS / SQS

| Recurso | Valor |
|---|---|
| SNS Topic ARN | `arn:aws:sns:us-east-1:198909467842:lms-enrollment-created-dev` |
| SQS Queue URL | `https://sqs.us-east-1.amazonaws.com/198909467842/lms-enrollment-events-dev` |
| SQS DLQ ARN | `arn:aws:sqs:us-east-1:198909467842:lms-enrollment-dlq-dev` |

## DynamoDB

| Tabla |
|---|
| `lms-users-dev` |
| `lms-courses-dev` |
| `lms-enrollments-dev` |
| `lms-contents-dev` |
| `lms-evaluations-dev` |

## Step Functions

| Recurso | Valor |
|---|---|
| State Machine ARN | `arn:aws:states:us-east-1:198909467842:stateMachine:lms-enrollment-dev` |

## Lambda Authorizer

| Recurso | Valor |
|---|---|
| Authorizer ARN | `arn:aws:lambda:us-east-1:198909467842:function:lms-usuarios-dev-authorizer` |
| Validator Usuarios ARN | `arn:aws:lambda:us-east-1:198909467842:function:lms-usuarios-dev-validatorUsuarios` |
| Validator Cursos ARN | `arn:aws:lambda:us-east-1:198909467842:function:lms-cursos-dev-validatorCursos` |

## API Endpoints

### Usuarios — `https://bqr9yndpkh.execute-api.us-east-1.amazonaws.com/dev`

| Método | Path | Auth | Descripción |
|---|---|---|---|
| POST | `/v1/auth/login` | Público | Login |
| POST | `/v1/auth/logout` | Bearer | Logout |
| GET | `/v1/me` | Bearer | Perfil propio |
| POST | `/v1/users` | Bearer (admin) | Crear usuario |
| GET | `/v1/users` | Bearer (admin) | Listar usuarios |
| GET | `/v1/users/{userId}` | Bearer | Obtener usuario |

### Cursos — `https://290ukd638e.execute-api.us-east-1.amazonaws.com/dev`

| Método | Path | Auth | Descripción |
|---|---|---|---|
| POST | `/v1/courses` | Bearer (admin/teacher) | Crear curso |
| GET | `/v1/courses` | Bearer | Listar cursos |
| GET | `/v1/courses/{courseId}` | Bearer | Obtener curso |
| PATCH | `/v1/courses/{courseId}` | Bearer (admin/teacher dueño) | Actualizar curso |

### Matrículas — `https://hg230hgizk.execute-api.us-east-1.amazonaws.com/dev`

| Método | Path | Auth | Descripción |
|---|---|---|---|
| POST | `/v1/enrollments` | Bearer (admin/student) | Matricular |
| GET | `/v1/enrollments` | Bearer | Listar matrículas |

### Contenidos — `https://ainxkn7mq0.execute-api.us-east-1.amazonaws.com/dev`

| Método | Path | Auth | Descripción |
|---|---|---|---|
| POST | `/v1/materials` | Bearer (admin/teacher) | Registrar material |
| GET | `/v1/materials` | Bearer | Listar materiales |
| POST | `/v1/materials/{contentId}/upload-url` | Bearer | Presigned URL para subir |
| POST | `/v1/materials/{contentId}/confirm` | Bearer | Confirmar upload |
| GET | `/v1/materials/{contentId}/download-url` | Bearer | Presigned URL para bajar |

### Evaluaciones — `https://c1b3902w19.execute-api.us-east-1.amazonaws.com/dev`

| Método | Path | Auth | Descripción |
|---|---|---|---|
| POST | `/v1/evaluations` | Bearer (admin/teacher) | Crear evaluación |
| GET | `/v1/evaluations` | Bearer | Listar evaluaciones |
| GET | `/v1/evaluations/{evaluationId}` | Bearer | Obtener evaluación |
| PATCH | `/v1/evaluations/{evaluationId}` | Bearer (admin/teacher dueño) | Actualizar evaluación |

## Credenciales de prueba

| Tenant | Email | Password | Role |
|---|---|---|---|
| TENANT_A | `admin@tenant-a.edu` | `AdminA-Seguro-2026!` | tenant_admin |
| TENANT_B | `admin@tenant-b.edu` | `AdminB-Seguro-2026!` | tenant_admin |
| TENANT_C | `admin@tenant-c.edu` | `AdminC-Seguro-2026!` | tenant_admin |
| TENANT_A | `teacher00001@tenant-a.edu` | `Seed2026!` | teacher |
| TENANT_A | `student00201@tenant-a.edu` | `Seed2026!` | student |
