import base64
import boto3
import json
import os
import uuid

from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['TABLE_NAME'])
sfn      = boto3.client('stepfunctions')

STATE_MACHINE_ARN = os.environ['STATE_MACHINE_ARN']


# ─── Helpers de evento ────────────────────────────────────────────────────────

def _body(event):
    return event.get('body') or {}

def _query(event):
    return event.get('queryStringParameters') or event.get('params', {}).get('querystring', {}) or {}

def _auth(event):
    return event.get('requestContext', {}).get('authorizer', {}) or {}


# ─── Helpers de respuesta ─────────────────────────────────────────────────────

def _ok(data):
    return {'data': data, 'requestId': str(uuid.uuid4())}

def _error(code, message):
    return {'error': {'code': code, 'message': message}, 'requestId': str(uuid.uuid4())}


# ─── Handlers ─────────────────────────────────────────────────────────────────

def create_enrollment(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    user_id   = auth.get('userId')
    role      = auth.get('role')

    body      = _body(event)
    course_id = (body.get('courseId') or '').strip()

    if not course_id:
        return _error('INVALID_BODY', 'courseId is required')

    # El student solo puede matricularse a sí mismo
    if role == 'student':
        student_id = user_id
    elif role == 'tenant_admin':
        student_id = (body.get('studentId') or '').strip()
        if not student_id:
            return _error('INVALID_BODY', 'studentId is required for admins')
    else:
        return _error('FORBIDDEN', 'Only students and admins can create enrollments')

    # Iniciar Step Functions Express (síncrono — espera el resultado)
    sfn_input = json.dumps({
        'tenantId':  tenant_id,
        'courseId':  course_id,
        'studentId': student_id,
    })

    try:
        response = sfn.start_sync_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            input=sfn_input,
        )
    except Exception as e:
        return _error('INTERNAL_ERROR', str(e))

    if response['status'] == 'SUCCEEDED':
        output = json.loads(response['output'])
        return _ok(output.get('enrollment', output))

    # Mapear errores de Step Functions a respuestas HTTP
    error = response.get('error', 'UNKNOWN_ERROR')
    cause = response.get('cause', 'An error occurred')

    error_map = {
        'StudentNotFound':    ('NOT_FOUND',  'Student not found or inactive'),
        'StudentInactive':    ('NOT_FOUND',  'Student not found or inactive'),
        'TenantMismatch':     ('NOT_FOUND',  'Resource not found'),
        'CourseNotFound':     ('NOT_FOUND',  'Course not found or not published'),
        'CourseNotPublished': ('NOT_FOUND',  'Course not found or not published'),
        'EnrollmentDuplicate': ('CONFLICT',  'Student is already enrolled in this course'),
    }

    code, message = error_map.get(error, ('INTERNAL_ERROR', cause))
    return _error(code, message)


def list_enrollments(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    user_id   = auth.get('userId')
    role      = auth.get('role')

    query     = _query(event)
    course_id = query.get('courseId')
    student_id = query.get('studentId')
    limit     = min(int(query.get('limit', 20)), 100)
    cursor    = query.get('nextToken')

    if not course_id and not student_id:
        return _error('INVALID_BODY', 'courseId or studentId query param is required')

    # Verificar permisos
    if student_id and role == 'student' and student_id != user_id:
        return _error('FORBIDDEN', 'Students can only list their own enrollments')

    kwargs = {'Limit': limit}

    if cursor:
        kwargs['ExclusiveStartKey'] = json.loads(base64.b64decode(cursor).decode())

    if course_id:
        kwargs['KeyConditionExpression'] = (
            Key('pk').eq(f'TENANT#{tenant_id}#COURSE#{course_id}') &
            Key('sk').begins_with('STUDENT#')
        )
        result = table.query(**kwargs)
    else:
        kwargs['IndexName'] = 'GSI_BY_STUDENT'
        kwargs['KeyConditionExpression'] = (
            Key('GSI1PK').eq(f'TENANT#{tenant_id}#STUDENT#{student_id}')
        )
        result = table.query(**kwargs)

    items    = [_public_enrollment(i) for i in result.get('Items', [])]
    last_key = result.get('LastEvaluatedKey')
    next_token = base64.b64encode(json.dumps(last_key).encode()).decode() if last_key else None

    return _ok({'items': items, 'nextToken': next_token})


def _public_enrollment(item):
    return {k: v for k, v in item.items() if k not in ('pk', 'sk', 'GSI1PK', 'GSI1SK')}
