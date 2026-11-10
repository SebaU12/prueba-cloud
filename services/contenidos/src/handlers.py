import base64
import boto3
import json
import os
import time
import uuid

from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
s3       = boto3.client('s3')

table     = dynamodb.Table(os.environ['TABLE_NAME'])
S3_BUCKET = os.environ['S3_BUCKET']

ALLOWED_MIME_TYPES = (
    'application/pdf',
    'video/mp4',
    'image/jpeg',
    'image/png',
    'application/zip',
    'text/plain',
)


# ─── Helpers de evento ────────────────────────────────────────────────────────

def _body(event):
    return event.get('body') or {}

def _path(event):
    return event.get('pathParameters') or event.get('params', {}).get('path', {}) or {}

def _query(event):
    return event.get('queryStringParameters') or event.get('params', {}).get('querystring', {}) or {}

def _auth(event):
    return event.get('requestContext', {}).get('authorizer', {}) or {}


# ─── Helpers de respuesta ─────────────────────────────────────────────────────

def _ok(data):
    return {'data': data, 'requestId': str(uuid.uuid4())}

def _error(code, message):
    return {'error': {'code': code, 'message': message}, 'requestId': str(uuid.uuid4())}


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def _public_content(item):
    return {k: v for k, v in item.items() if k not in ('pk', 'sk', 'GSI1PK', 'GSI1SK')}

def _get_content_by_id(tenant_id, content_id):
    """Lookup por GSI para obtener contenido sin saber el courseId."""
    result = table.query(
        IndexName='GSI_BY_CONTENT',
        KeyConditionExpression=Key('GSI1PK').eq(f'TENANT#{tenant_id}#CONTENT#{content_id}'),
        Limit=1,
    )
    items = result.get('Items', [])
    return items[0] if items else None

def _is_enrolled(tenant_id, course_id, student_id):
    """Verifica si el estudiante está matriculado en el curso."""
    enrollments_table_name = os.environ['TABLE_NAME'].replace('contents', 'enrollments')
    enroll_table = dynamodb.Table(enrollments_table_name)
    item = enroll_table.get_item(
        Key={
            'pk': f'TENANT#{tenant_id}#COURSE#{course_id}',
            'sk': f'STUDENT#{student_id}',
        }
    ).get('Item')
    return item is not None and item.get('status') == 'active'


# ─── Handlers ─────────────────────────────────────────────────────────────────

def create_material(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    user_id   = auth.get('userId')
    role      = auth.get('role')

    if role not in ('tenant_admin', 'teacher'):
        return _error('FORBIDDEN', 'Only admins and teachers can upload materials')

    body      = _body(event)
    course_id = (body.get('courseId') or '').strip()
    title     = (body.get('title') or '').strip()
    file_name = (body.get('fileName') or '').strip()
    mime_type = (body.get('mimeType') or '').strip()
    size      = body.get('sizeBytes', 0)

    if not all([course_id, title, file_name, mime_type]):
        return _error('INVALID_BODY', 'courseId, title, fileName and mimeType are required')

    if mime_type not in ALLOWED_MIME_TYPES:
        return _error('INVALID_BODY', f'mimeType not allowed')

    content_id = f'CNT-{uuid.uuid4()}'
    s3_key     = f'{tenant_id}/{course_id}/{content_id}/{file_name}'
    now        = _now_iso()

    item = {
        'pk':           f'TENANT#{tenant_id}#COURSE#{course_id}',
        'sk':           f'CONTENT#{content_id}',
        'entityType':   'CONTENT',
        'contentId':    content_id,
        'tenantId':     tenant_id,
        'courseId':     course_id,
        'uploadedBy':   user_id,
        'title':        title,
        's3Key':        s3_key,
        'mimeType':     mime_type,
        'sizeBytes':    size,
        'uploadStatus': 'pending',
        'createdAt':    now,
        'GSI1PK':       f'TENANT#{tenant_id}#CONTENT#{content_id}',
        'GSI1SK':       'META',
    }

    table.put_item(Item=item)

    return _ok({'contentId': content_id, 'uploadStatus': 'pending'})


def get_upload_url(event, context):
    auth       = _auth(event)
    tenant_id  = auth.get('tenantId')
    user_id    = auth.get('userId')
    role       = auth.get('role')
    content_id = _path(event).get('contentId')

    if role not in ('tenant_admin', 'teacher'):
        return _error('FORBIDDEN', 'Only admins and teachers can get upload URLs')

    item = _get_content_by_id(tenant_id, content_id)
    if not item:
        return _error('NOT_FOUND', 'Content not found')

    if item.get('uploadStatus') == 'confirmed':
        return _error('CONFLICT', 'Content already uploaded')

    upload_url = s3.generate_presigned_url(
        'put_object',
        Params={
            'Bucket':      S3_BUCKET,
            'Key':         item['s3Key'],
            'ContentType': item['mimeType'],
        },
        ExpiresIn=300,
    )

    return _ok({'uploadUrl': upload_url, 'expiresIn': 300})


def confirm_upload(event, context):
    auth       = _auth(event)
    tenant_id  = auth.get('tenantId')
    content_id = _path(event).get('contentId')

    item = _get_content_by_id(tenant_id, content_id)
    if not item:
        return _error('NOT_FOUND', 'Content not found')

    # Verificar que el objeto existe en S3
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=item['s3Key'])
    except s3.exceptions.ClientError:
        return _error('BAD_REQUEST', 'File not found in S3, complete the upload first')

    table.update_item(
        Key={'pk': item['pk'], 'sk': item['sk']},
        UpdateExpression='SET uploadStatus = :confirmed, confirmedAt = :now',
        ExpressionAttributeValues={
            ':confirmed': 'confirmed',
            ':now':       _now_iso(),
        },
    )

    return _ok({'contentId': content_id, 'uploadStatus': 'confirmed'})


def list_materials(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    course_id = _query(event).get('courseId')

    if not course_id:
        return _error('INVALID_BODY', 'courseId query param is required')

    result = table.query(
        KeyConditionExpression=(
            Key('pk').eq(f'TENANT#{tenant_id}#COURSE#{course_id}') &
            Key('sk').begins_with('CONTENT#')
        ),
        FilterExpression='uploadStatus = :confirmed',
        ExpressionAttributeValues={':confirmed': 'confirmed'},
    )

    items = [_public_content(i) for i in result.get('Items', [])]
    return _ok({'items': items})


def get_download_url(event, context):
    auth       = _auth(event)
    tenant_id  = auth.get('tenantId')
    user_id    = auth.get('userId')
    role       = auth.get('role')
    content_id = _path(event).get('contentId')

    item = _get_content_by_id(tenant_id, content_id)
    if not item:
        return _error('NOT_FOUND', 'Content not found')

    if item.get('uploadStatus') != 'confirmed':
        return _error('NOT_FOUND', 'Content not found')

    # Verificar acceso: student debe estar matriculado
    if role == 'student':
        if not _is_enrolled(tenant_id, item['courseId'], user_id):
            return _error('FORBIDDEN', 'You are not enrolled in this course')

    download_url = s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': S3_BUCKET,
            'Key':    item['s3Key'],
        },
        ExpiresIn=60,
    )

    return _ok({'downloadUrl': download_url, 'expiresIn': 60})
