# LMS Grupo 3 — CS2032

Plataforma SaaS de gestión del aprendizaje (LMS) multi-tenant sobre AWS serverless.

## Arquitectura

5 microservicios independientes con API Gateway + Lambda + DynamoDB. Autenticación propia con PBKDF2 y sesiones opacas. Flujo de matrícula orquestado con Step Functions Express. Eventos asincrónicos con SNS → SQS.

```
infrastructure/          # S3, SNS, SQS, DLQ (recursos compartidos)
services/
  usuarios/              # Auth, Lambda Authorizer, gestión de usuarios
  cursos/                # CRUD de cursos
  matriculas/            # Step Functions + DynamoDB Streams + SQS consumer
  contenidos/            # Upload/download de archivos via S3 presigned URLs
  evaluaciones/          # CRUD de evaluaciones con preguntas
scripts/
  deploy.sh              # Despliegue en orden correcto
  bootstrap_tenants.py   # Crea admins iniciales por tenant
  seed_*.py              # 30,000 registros por tabla
```

## Stack

| Capa | Tecnología |
|---|---|
| Runtime | Python 3.12 en Lambda |
| API | API Gateway REST (integration: lambda) |
| Base de datos | DynamoDB (5 tablas, PAY_PER_REQUEST) |
| Auth | PBKDF2-HMAC-SHA256 + sesiones opacas |
| Orquestación | Step Functions Express |
| Eventos | SNS → SQS → Lambda (patrón Outbox) |
| Archivos | S3 privado + presigned URLs |
| IaC | Serverless Framework v3 |

## Tenants

| Tenant | Email admin | Variable de entorno |
|---|---|---|
| TENANT_A | admin@tenant-a.edu | `ADMIN_A_PASS` |
| TENANT_B | admin@tenant-b.edu | `ADMIN_B_PASS` |
| TENANT_C | admin@tenant-c.edu | `ADMIN_C_PASS` |

## Configuración antes de clonar

Dos valores están hardcodeados en todos los `serverless.yml` y deben actualizarse antes de desplegar:

### 1. Organización de Serverless Framework

Cada `serverless.yml` tiene en la línea 1:

```yaml
org: sebastianlizarraga
```

Reemplazar con tu organización de [Serverless Dashboard](https://app.serverless.com/), o eliminar la línea si no usas el dashboard.

Archivos a editar:
```
infrastructure/serverless.yml
services/usuarios/serverless.yml
services/cursos/serverless.yml
services/matriculas/serverless.yml
services/contenidos/serverless.yml
services/evaluaciones/serverless.yml
```

### 2. IAM Role

Cada `serverless.yml` referencia un rol de AWS Academy:

```yaml
role: arn:aws:iam::198909467842:role/LabRole
```

Reemplazar `198909467842` con tu Account ID y `LabRole` con el nombre del rol IAM que tenga permisos sobre Lambda, DynamoDB, S3, SNS, SQS y Step Functions. En AWS Academy usar el `LabRole` de tu propia cuenta.

Buscar y reemplazar en todos los `serverless.yml`:
```bash
# Ver todas las ocurrencias
grep -r "198909467842" .

# Reemplazar (Linux/Mac)
find . -name "serverless.yml" -exec sed -i 's/198909467842/TU_ACCOUNT_ID/g' {} +
```

---

## Despliegue

### Prerequisitos

```bash
npm install -g serverless
cd services/matriculas && serverless plugin install -n serverless-step-functions
```

Configurar credenciales AWS en `~/.aws/credentials` o como variables de entorno.

### Desplegar todo

```bash
export ADMIN_A_PASS="AdminA-Seguro-2026!"
export ADMIN_B_PASS="AdminB-Seguro-2026!"
export ADMIN_C_PASS="AdminC-Seguro-2026!"

./scripts/deploy.sh dev us-east-1
```

El script despliega los stacks en orden y pasa los ARNs entre servicios automáticamente.

### Seed de datos (150,000 registros)

```bash
cd scripts
python seed_usuarios.py    --stage dev
python seed_cursos.py      --stage dev
python seed_matriculas.py  --stage dev
python seed_contenidos.py  --stage dev
python seed_evaluaciones.py --stage dev
```

Contraseña de todos los usuarios seed: `Seed2026!`

## API

Base URL: `https://<api-id>.execute-api.us-east-1.amazonaws.com/v1`

Todos los endpoints privados requieren: `Authorization: Bearer <token>`

| Método | Endpoint | Auth | Descripción |
|---|---|---|---|
| POST | `/auth/login` | Público | Login |
| POST | `/auth/logout` | Privado | Logout |
| GET | `/me` | Privado | Perfil propio |
| POST | `/users` | Admin | Crear usuario |
| GET | `/users` | Admin | Listar usuarios |
| GET | `/users/{userId}` | Admin / propio | Obtener usuario |
| POST | `/courses` | Admin, Teacher | Crear curso |
| GET | `/courses` | Todos | Listar cursos |
| GET | `/courses/{courseId}` | Todos | Obtener curso |
| PATCH | `/courses/{courseId}` | Admin, Teacher dueño | Actualizar curso |
| POST | `/enrollments` | Admin, Student | Matricular |
| GET | `/enrollments` | Admin, Student, Teacher | Listar matrículas |
| POST | `/materials` | Admin, Teacher | Registrar material |
| POST | `/materials/{id}/upload-url` | Admin, Teacher | Presigned URL para subir |
| POST | `/materials/{id}/confirm` | Admin, Teacher | Confirmar upload |
| GET | `/materials` | Todos | Listar materiales |
| GET | `/materials/{id}/download-url` | Todos (student: si matriculado) | Presigned URL para bajar |
| POST | `/evaluations` | Admin, Teacher | Crear evaluación |
| PATCH | `/evaluations/{id}` | Admin, Teacher dueño | Actualizar evaluación |
| GET | `/evaluations` | Todos | Listar evaluaciones |
| GET | `/evaluations/{id}` | Todos (student: sin correctIndex) | Obtener evaluación |

## Notificaciones por email (SNS)

Cuando se crea una matrícula, el sistema publica un evento en SNS. Cualquier email suscrito al topic recibe una notificación.

### Agregar un correo

Editar `infrastructure/serverless.yml` y agregar un nuevo recurso de tipo `AWS::SNS::Subscription`:

```yaml
NombreSubscription:
  Type: AWS::SNS::Subscription
  Properties:
    TopicArn: !Ref EnrollmentTopic
    Protocol: email
    Endpoint: correo@ejemplo.com
```

Luego redesplegar:

```bash
cd infrastructure && serverless deploy --stage dev --region us-east-1
```

AWS enviará un email de confirmación a la dirección indicada. **El suscriptor debe hacer clic en "Confirm subscription"** para empezar a recibir notificaciones. Hasta que no confirme, los mensajes no llegan.

## Flujo de matrícula

```
POST /enrollments
  → Step Functions Express (síncrono)
      1. ValidateStudent  → Lambda validadora Usuarios
      2. ValidateCourse   → Lambda validadora Cursos
      3. CreateEnrollment → TransactWrite (ENROLLMENT + OUTBOX)
  → DynamoDB Streams detecta INSERT OUTBOX
  → publishOutbox → SNS → SQS → consumeEnrollment (idempotente)
```
