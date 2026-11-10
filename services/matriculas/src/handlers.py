import base64
import boto3
import decimal
import json
import logging
import os
import uuid

from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['TABLE_NAME'])
sfn      = boto3.client('stepfunctions')

STATE_MACHINE_ARN = os.environ['STATE_MACHINE_ARN']

log = logging.getLogger()
log.setLevel(logging.INFO)


# Helpers de evento

def _body(event):
    b = event.get('body') or '{}'
    return json.loads(b) if isinstance(b, str) else (b or {})

def _query(event):
    return event.get('queryStringParameters') or event.get('params', {}).get('querystring', {}) or {}

def _auth(event):
    return event.get('requestContext', {}).get('authorizer', {}) or {}


# Helpers de respuesta

_CORS = {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}

class _Enc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)

def _ok(data):
    return {
        'statusCode': 200,
        'headers': _CORS,
        'body': json.dumps({'data': data, 'requestId': str(uuid.uuid4())}, cls=_Enc),
    }

def _error(code, message):
    return {
        'statusCode': 200,
        'headers': _CORS,
        'body': json.dumps({'error': {'code': code, 'message': message}, 'requestId': str(uuid.uuid4())}, cls=_Enc),
    }


# Handlers

def create_enrollment(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    user_id   = auth.get('userId')
    role      = auth.get('role')

    body      = _body(event)
    course_id = (body.get('courseId') or '').strip()

    if not course_id:
        return _error('INVALID_BODY', 'courseId is required')

    if role == 'student':
        student_id = user_id
    elif role == 'tenant_admin':
        student_id = (body.get('studentId') or '').strip()
        if not student_id:
            return _error('INVALID_BODY', 'studentId is required for admins')
    else:
        return _error('FORBIDDEN', 'Only students and admins can create enrollments')

    log.info(json.dumps({'action': 'enrollment_start', 'studentId': student_id, 'courseId': course_id, 'tenantId': tenant_id}))

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
        log.error(json.dumps({'action': 'enrollment_sfn_error', 'studentId': student_id, 'courseId': course_id, 'error': str(e)}))
        return _error('INTERNAL_ERROR', str(e))

    if response['status'] == 'SUCCEEDED':
        output = json.loads(response['output'])
        log.info(json.dumps({'action': 'enrollment_ok', 'studentId': student_id, 'courseId': course_id, 'tenantId': tenant_id}))
        return _ok(output.get('enrollment', output))

    error = response.get('error', 'UNKNOWN_ERROR')
    cause = response.get('cause', 'An error occurred')

    log.warning(json.dumps({'action': 'enrollment_failed', 'studentId': student_id, 'courseId': course_id, 'sfnError': error}))

    error_map = {
        'StudentNotFound':     ('NOT_FOUND', 'Student not found or inactive'),
        'StudentInactive':     ('NOT_FOUND', 'Student not found or inactive'),
        'TenantMismatch':      ('NOT_FOUND', 'Resource not found'),
        'CourseNotFound':      ('NOT_FOUND', 'Course not found or not published'),
        'CourseNotPublished':  ('NOT_FOUND', 'Course not found or not published'),
        'EnrollmentDuplicate': ('CONFLICT',  'Student is already enrolled in this course'),
    }

    code, message = error_map.get(error, ('INTERNAL_ERROR', cause))
    return _error(code, message)


def list_enrollments(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    user_id   = auth.get('userId')
    role      = auth.get('role')

    query      = _query(event)
    course_id  = query.get('courseId')
    student_id = query.get('studentId')
    limit      = min(int(query.get('limit', 20)), 100)
    cursor     = query.get('nextToken')

    if not course_id and not student_id:
        return _error('INVALID_BODY', 'courseId or studentId query param is required')

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

    items      = [_public_enrollment(i) for i in result.get('Items', [])]
    last_key   = result.get('LastEvaluatedKey')
    next_token = base64.b64encode(json.dumps(last_key).encode()).decode() if last_key else None

    return _ok({'items': items, 'nextToken': next_token})


def _public_enrollment(item):
    return {k: v for k, v in item.items() if k not in ('pk', 'sk', 'GSI1PK', 'GSI1SK')}
