#!/bin/bash
set -euo pipefail

# Argumentos
STAGE=${1:-dev}
REGION=${2:-us-east-1}

echo "=================================================="
echo " LMS Grupo 3 — Despliegue completo"
echo " Stage:  $STAGE"
echo " Region: $REGION"
echo "=================================================="

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Helper: leer un Output de CloudFormation
get_output() {
  local stack_name=$1
  local output_key=$2
  aws cloudformation describe-stacks \
    --stack-name "$stack_name" \
    --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue" \
    --output text \
    --region "$REGION"
}

# 1. Infrastructure (S3, SNS, SQS, DLQ)
echo ""
echo "[1/6] Desplegando infrastructure..."
cd "$ROOT_DIR/infrastructure"
serverless deploy --stage "$STAGE" --region "$REGION" --force
echo "      ✓ infrastructure desplegado"

# 2. Usuarios (Authorizer + Validador)
echo ""
echo "[2/6] Desplegando usuarios..."
cd "$ROOT_DIR/services/usuarios"
serverless deploy --stage "$STAGE" --region "$REGION" --force

AUTHORIZER_LAMBDA_ARN=$(get_output "lms-usuarios-$STAGE" "AuthorizerLambdaArn")
VALIDATOR_USUARIOS_ARN=$(get_output "lms-usuarios-$STAGE" "ValidatorUsuariosArn")
export AUTHORIZER_LAMBDA_ARN
export VALIDATOR_USUARIOS_ARN

echo "      ✓ usuarios desplegado"
echo "        AuthorizerArn:         $AUTHORIZER_LAMBDA_ARN"
echo "        ValidatorUsuariosArn:  $VALIDATOR_USUARIOS_ARN"

# 3. Cursos (Validador para Step Functions)
echo ""
echo "[3/6] Desplegando cursos..."
cd "$ROOT_DIR/services/cursos"
serverless deploy --stage "$STAGE" --region "$REGION" --force

VALIDATOR_CURSOS_ARN=$(get_output "lms-cursos-$STAGE" "ValidatorCursosArn")
export VALIDATOR_CURSOS_ARN

echo "      ✓ cursos desplegado"
echo "        ValidatorCursosArn:    $VALIDATOR_CURSOS_ARN"

# 4. Matrículas (Step Functions + Streams + SQS)
echo ""
echo "[4/6] Desplegando matriculas..."
cd "$ROOT_DIR/services/matriculas"
serverless deploy --stage "$STAGE" --region "$REGION" --force
echo "      ✓ matriculas desplegado"

# 5. Contenidos (S3 presigned URLs)
echo ""
echo "[5/6] Desplegando contenidos..."
cd "$ROOT_DIR/services/contenidos"
serverless deploy --stage "$STAGE" --region "$REGION" --force
echo "      ✓ contenidos desplegado"

# 6. Evaluaciones
echo ""
echo "[6/6] Desplegando evaluaciones..."
cd "$ROOT_DIR/services/evaluaciones"
serverless deploy --stage "$STAGE" --region "$REGION" --force
echo "      ✓ evaluaciones desplegado"

# 7. Bootstrap tenants (crea admins en DynamoDB)
echo ""
echo "[7/7] Ejecutando bootstrap de tenants..."

if [[ -z "${ADMIN_A_PASS:-}" || -z "${ADMIN_B_PASS:-}" || -z "${ADMIN_C_PASS:-}" ]]; then
  echo ""
  echo "  ERROR: Faltan variables de entorno para las contraseñas de los admins."
  echo "  Exporta antes de correr el script:"
  echo ""
  echo "    export ADMIN_A_PASS='AdminA-Seguro-2026!'"
  echo "    export ADMIN_B_PASS='AdminB-Seguro-2026!'"
  echo "    export ADMIN_C_PASS='AdminC-Seguro-2026!'"
  echo ""
  exit 1
fi

cd "$ROOT_DIR/scripts"
python bootstrap_tenants.py --stage "$STAGE" --region "$REGION"
echo "      ✓ tenants inicializados"

# Resumen de recursos
echo ""
echo "=================================================="
echo " Despliegue completado exitosamente"
echo " Stage: $STAGE | Region: $REGION"
echo "=================================================="

echo ""
echo "── S3 ───────────────────────────────────────────"
echo "  Bucket materiales: $(get_output "lms-infrastructure-$STAGE" "S3BucketName")"

echo ""
echo "── SNS / SQS ────────────────────────────────────"
echo "  SNS Topic ARN:     $(get_output "lms-infrastructure-$STAGE" "SnsTopicArn")"
echo "  SQS Queue URL:     $(get_output "lms-infrastructure-$STAGE" "SqsQueueUrl")"
echo "  SQS DLQ ARN:       $(get_output "lms-infrastructure-$STAGE" "SqsDlqArn")"

echo ""
echo "── DynamoDB ─────────────────────────────────────"
echo "  lms-users-$STAGE"
echo "  lms-courses-$STAGE"
echo "  lms-enrollments-$STAGE"
echo "  lms-contents-$STAGE"
echo "  lms-evaluations-$STAGE"

echo ""
echo "── Step Functions ───────────────────────────────"
echo "  State Machine:     arn:aws:states:$REGION:$(aws sts get-caller-identity --query Account --output text):stateMachine:lms-enrollment-$STAGE"

echo ""
echo "── Lambda Authorizer ────────────────────────────"
echo "  ARN: $AUTHORIZER_LAMBDA_ARN"

echo ""
echo "── API Endpoints ────────────────────────────────"
echo "  Usuarios:"
aws cloudformation describe-stacks --stack-name "lms-usuarios-$STAGE" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ServiceEndpoint'].OutputValue" --output text \
  | sed 's/^/    /'

echo "  Cursos:"
aws cloudformation describe-stacks --stack-name "lms-cursos-$STAGE" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ServiceEndpoint'].OutputValue" --output text \
  | sed 's/^/    /'

echo "  Matriculas:"
aws cloudformation describe-stacks --stack-name "lms-matriculas-$STAGE" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ServiceEndpoint'].OutputValue" --output text \
  | sed 's/^/    /'

echo "  Contenidos:"
aws cloudformation describe-stacks --stack-name "lms-contenidos-$STAGE" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ServiceEndpoint'].OutputValue" --output text \
  | sed 's/^/    /'

echo "  Evaluaciones:"
aws cloudformation describe-stacks --stack-name "lms-evaluaciones-$STAGE" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ServiceEndpoint'].OutputValue" --output text \
  | sed 's/^/    /'

echo ""
echo "=================================================="
