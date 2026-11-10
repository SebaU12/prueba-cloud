import base64
import boto3
import decimal
import json
import os
import time
import uuid

from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['TABLE_NAME'])

VALID_STATUSES = ('draft', 'published', 'closed')


# ─── Helpers de evento ────────────────────────────────────────────────────────

def _body(event):
    b = event.get('body') or '{}'
    return json.loads(b) if isinstance(b, str) else (b or {})

def _path(event):
    return event.get('pathParameters') or event.get('params', {}).get('path', {}) or {}

def _query(event):
    return event.get('queryStringParameters') or event.get('params', {}).get('querystring', {}) or {}

def _auth(event):
    return event.get('requestContext', {}).get('authorizer', {}) or {}


# ─── Helpers de respuesta ─────────────────────────────────────────────────────

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


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def _public_eval(item, role):
    """Elimina correctIndex para estudiantes."""
    result = {k: v for k, v in item.items() if k not in ('pk', 'sk', 'GSI1PK', 'GSI1SK')}
    if role == 'student' and 'questions' in result:
        result['questions'] = [
            {k: v for k, v in q.items() if k != 'correctIndex'}
            for q in result['questions']
        ]
    return result

def _validate_questions(questions):
    if not questions or len(questions) < 3:
        return 'At least 3 questions are required to publish'
    for q in questions:
        if not q.get('text'):
            return 'Each question must have text'
        options = q.get('options', [])
        if len(options) < 2:
            return 'Each question must have at least 2 options'
        if not isinstance(q.get('correctIndex'), int) or q['correctIndex'] >= len(options):
            return 'Each question must have a valid correctIndex'
    return None

def _get_eval_by_id(tenant_id, eval_id):
    result = table.query(
        IndexName='GSI_BY_EVALUATION',
        KeyConditionExpression=Key('GSI1PK').eq(f'TENANT#{tenant_id}#EVAL#{eval_id}'),
        Limit=1,
    )
    items = result.get('Items', [])
    return items[0] if items else None

def _is_enrolled(tenant_id, course_id, student_id):
    enrollments_table_name = os.environ['TABLE_NAME'].replace('evaluations', 'enrollments')
    enroll_table = dynamodb.Table(enrollments_table_name)
    item = enroll_table.get_item(
        Key={
            'pk': f'TENANT#{tenant_id}#COURSE#{course_id}',
            'sk': f'STUDENT#{student_id}',
        }
    ).get('Item')
    return item is not None and item.get('status') == 'active'


# ─── Handlers ─────────────────────────────────────────────────────────────────

def create_evaluation(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    user_id   = auth.get('userId')
    role      = auth.get('role')

    if role not in ('tenant_admin', 'teacher'):
        return _error('FORBIDDEN', 'Only admins and teachers can create evaluations')

    body      = _body(event)
    course_id = (body.get('courseId') or '').strip()
    title     = (body.get('title') or '').strip()
    questions = body.get('questions', [])
    deadline  = body.get('fechaLimite')

    if not course_id or not title:
        return _error('INVALID_BODY', 'courseId and title are required')

    eval_id = f'EVL-{uuid.uuid4()}'
    now     = _now_iso()

    item = {
        'pk':           f'TENANT#{tenant_id}#COURSE#{course_id}',
        'sk':           f'EVAL#{eval_id}',
        'entityType':   'EVALUATION',
        'evaluationId': eval_id,
        'tenantId':     tenant_id,
        'courseId':     course_id,
        'teacherId':    user_id,
        'title':        title,
        'status':       'draft',
        'questions':    questions,
        'createdAt':    now,
        'GSI1PK':       f'TENANT#{tenant_id}#EVAL#{eval_id}',
        'GSI1SK':       'META',
    }

    if deadline:
        item['fechaLimite'] = deadline

    table.put_item(Item=item)

    return _ok(_public_eval(item, role))


def update_evaluation(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    user_id   = auth.get('userId')
    role      = auth.get('role')
    eval_id   = _path(event).get('evaluationId')

    item = _get_eval_by_id(tenant_id, eval_id)
    if not item:
        return _error('NOT_FOUND', 'Evaluation not found')

    if role == 'teacher' and item.get('teacherId') != user_id:
        return _error('FORBIDDEN', 'Teachers can only update their own evaluations')

    body      = _body(event)
    updates   = []
    attr_names = {}
    attr_vals  = {}

    if 'title' in body:
        updates.append('#title = :title')
        attr_names['#title'] = 'title'
        attr_vals[':title']  = body['title'].strip()

    if 'questions' in body:
        updates.append('questions = :questions')
        attr_vals[':questions'] = body['questions']

    if 'fechaLimite' in body:
        updates.append('fechaLimite = :fechaLimite')
        attr_vals[':fechaLimite'] = body['fechaLimite']

    if 'status' in body:
        new_status = body['status']
        if new_status not in VALID_STATUSES:
            return _error('INVALID_BODY', f'status must be one of {VALID_STATUSES}')

        # Validar preguntas antes de publicar
        if new_status == 'published':
            questions = body.get('questions', item.get('questions', []))
            error_msg = _validate_questions(questions)
            if error_msg:
                return _error('INVALID_BODY', error_msg)

        updates.append('#status = :status')
        attr_names['#status'] = 'status'
        attr_vals[':status']  = new_status

    if not updates:
        return _error('INVALID_BODY', 'No valid fields to update')

    updates.append('updatedAt = :updatedAt')
    attr_vals[':updatedAt'] = _now_iso()

    kwargs = {
        'Key':                       {'pk': item['pk'], 'sk': item['sk']},
        'UpdateExpression':          'SET ' + ', '.join(updates),
        'ExpressionAttributeValues': attr_vals,
        'ReturnValues':              'ALL_NEW',
    }
    if attr_names:
        kwargs['ExpressionAttributeNames'] = attr_names

    result = table.update_item(**kwargs)

    return _ok(_public_eval(result['Attributes'], role))


def list_evaluations(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    role      = auth.get('role')
    course_id = _query(event).get('courseId')

    if not course_id:
        return _error('INVALID_BODY', 'courseId query param is required')

    kwargs = {
        'KeyConditionExpression': (
            Key('pk').eq(f'TENANT#{tenant_id}#COURSE#{course_id}') &
            Key('sk').begins_with('EVAL#')
        ),
    }

    # Estudiantes solo ven evaluaciones publicadas
    if role == 'student':
        kwargs['FilterExpression']        = '#status = :published'
        kwargs['ExpressionAttributeNames'] = {'#status': 'status'}
        kwargs['ExpressionAttributeValues'] = {':published': 'published'}

    result = table.query(**kwargs)
    items  = [_public_eval(i, role) for i in result.get('Items', [])]

    return _ok({'items': items})


def get_evaluation(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    user_id   = auth.get('userId')
    role      = auth.get('role')
    eval_id   = _path(event).get('evaluationId')

    item = _get_eval_by_id(tenant_id, eval_id)
    if not item:
        return _error('NOT_FOUND', 'Evaluation not found')

    # Estudiante: solo puede ver publicadas y si está matriculado
    if role == 'student':
        if item.get('status') != 'published':
            return _error('NOT_FOUND', 'Evaluation not found')
        if not _is_enrolled(tenant_id, item['courseId'], user_id):
            return _error('FORBIDDEN', 'You are not enrolled in this course')

    return _ok(_public_eval(item, role))
