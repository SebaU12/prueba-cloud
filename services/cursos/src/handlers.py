import base64
import boto3
import decimal
import json
import logging
import os
import time
import uuid

from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

VALID_STATUSES = ('draft', 'published', 'archived')

log = logging.getLogger()
log.setLevel(logging.INFO)


# Helpers de evento

def _body(event):
    b = event.get('body') or '{}'
    return json.loads(b) if isinstance(b, str) else (b or {})

def _path(event):
    return event.get('pathParameters') or event.get('params', {}).get('path', {}) or {}

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


# Helpers internos

def _now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def _public_course(item):
    return {k: v for k, v in item.items() if k not in ('pk', 'sk', 'GSI1PK', 'GSI1SK')}


# Handlers

def create_course(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    user_id   = auth.get('userId')
    role      = auth.get('role')

    if role not in ('tenant_admin', 'teacher'):
        return _error('FORBIDDEN', 'Only admins and teachers can create courses')

    body  = _body(event)
    title = (body.get('title') or '').strip()
    desc  = (body.get('description') or '').strip()

    if not title:
        return _error('INVALID_BODY', 'title is required')

    tenant_letter = tenant_id.split('_')[-1]
    course_id     = f'CRS-{tenant_letter}-{uuid.uuid4().hex[:8].upper()}'
    now           = _now_iso()

    item = {
        'pk':          f'TENANT#{tenant_id}',
        'sk':          f'COURSE#{course_id}',
        'entityType':  'COURSE',
        'courseId':    course_id,
        'tenantId':    tenant_id,
        'teacherId':   user_id,
        'title':       title,
        'description': desc,
        'status':      'draft',
        'createdAt':   now,
        'GSI1PK':      f'TENANT#{tenant_id}#TEACHER#{user_id}',
        'GSI1SK':      f'COURSE#{course_id}',
    }

    table.put_item(Item=item)

    log.info(json.dumps({'action': 'create_course_ok', 'courseId': course_id, 'teacherId': user_id, 'tenantId': tenant_id}))

    return _ok(_public_course(item))


def list_courses(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')

    query      = _query(event)
    limit      = min(int(query.get('limit', 20)), 100)
    cursor     = query.get('nextToken')
    teacher_id = query.get('teacherId')

    if teacher_id:
        kwargs = {
            'IndexName': 'GSI_BY_TEACHER',
            'KeyConditionExpression': Key('GSI1PK').eq(f'TENANT#{tenant_id}#TEACHER#{teacher_id}'),
            'Limit': limit,
        }
    else:
        kwargs = {
            'KeyConditionExpression': Key('pk').eq(f'TENANT#{tenant_id}') & Key('sk').begins_with('COURSE#'),
            'Limit': limit,
        }

    if cursor:
        kwargs['ExclusiveStartKey'] = json.loads(base64.b64decode(cursor).decode())

    result     = table.query(**kwargs)
    items      = [_public_course(i) for i in result.get('Items', [])]
    last_key   = result.get('LastEvaluatedKey')
    next_token = base64.b64encode(json.dumps(last_key).encode()).decode() if last_key else None

    return _ok({'items': items, 'nextToken': next_token})


def get_course(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    course_id = _path(event).get('courseId')

    item = table.get_item(
        Key={'pk': f'TENANT#{tenant_id}', 'sk': f'COURSE#{course_id}'},
    ).get('Item')

    if not item:
        return _error('NOT_FOUND', 'Course not found')

    return _ok(_public_course(item))


def update_course(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    user_id   = auth.get('userId')
    role      = auth.get('role')
    course_id = _path(event).get('courseId')

    item = table.get_item(
        Key={'pk': f'TENANT#{tenant_id}', 'sk': f'COURSE#{course_id}'},
    ).get('Item')

    if not item:
        return _error('NOT_FOUND', 'Course not found')

    if role == 'teacher' and item.get('teacherId') != user_id:
        log.warning(json.dumps({'action': 'update_course_forbidden', 'courseId': course_id, 'userId': user_id, 'tenantId': tenant_id}))
        return _error('FORBIDDEN', 'Teachers can only update their own courses')

    body       = _body(event)
    updates    = []
    attr_names = {}
    attr_vals  = {}

    if 'title' in body:
        updates.append('#title = :title')
        attr_names['#title'] = 'title'
        attr_vals[':title']  = body['title'].strip()

    if 'description' in body:
        updates.append('description = :desc')
        attr_vals[':desc'] = body['description'].strip()

    if 'status' in body:
        if body['status'] not in VALID_STATUSES:
            return _error('INVALID_BODY', f'status must be one of {VALID_STATUSES}')
        updates.append('#status = :status')
        attr_names['#status'] = 'status'
        attr_vals[':status']  = body['status']

    if not updates:
        return _error('INVALID_BODY', 'No valid fields to update')

    updates.append('updatedAt = :updatedAt')
    attr_vals[':updatedAt'] = _now_iso()

    kwargs = {
        'Key':                       {'pk': f'TENANT#{tenant_id}', 'sk': f'COURSE#{course_id}'},
        'UpdateExpression':          'SET ' + ', '.join(updates),
        'ExpressionAttributeValues': attr_vals,
        'ReturnValues':              'ALL_NEW',
    }
    if attr_names:
        kwargs['ExpressionAttributeNames'] = attr_names

    result = table.update_item(**kwargs)

    log.info(json.dumps({'action': 'update_course_ok', 'courseId': course_id, 'userId': user_id, 'tenantId': tenant_id}))

    return _ok(_public_course(result['Attributes']))
