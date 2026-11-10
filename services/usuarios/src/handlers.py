import base64
import boto3
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid

from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])


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

def _hash_password(password):
    salt = os.urandom(16)
    dk   = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 310_000)
    return base64.b64encode(dk).decode(), base64.b64encode(salt).decode()

def _verify_password(password, hash_b64, salt_b64, iterations=310_000):
    salt     = base64.b64decode(salt_b64)
    stored   = base64.b64decode(hash_b64)
    computed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, int(iterations))
    return hmac.compare_digest(computed, stored)

def _safe_user(item):
    """Devuelve el usuario sin campos sensibles."""
    return {k: v for k, v in item.items()
            if k not in ('passwordHashB64', 'passwordSaltB64', 'passwordIterations', 'failedAttempts')}


# ─── Handlers ─────────────────────────────────────────────────────────────────

def login(event, context):
    body     = _body(event)
    email    = (body.get('email') or '').strip().lower()
    password = body.get('password', '')

    # DEBUG temporal — ver en CloudWatch
    print(f"DEBUG body type: {type(body)}")
    print(f"DEBUG email: {repr(email)}")
    print(f"DEBUG password len: {len(password)}, repr: {repr(password)}")

    if not email or not password:
        return _error('INVALID_BODY', 'email and password are required')

    # 1. Lookup por email
    lookup = table.get_item(
        Key={'pk': f'EMAIL#{email}', 'sk': 'LOOKUP'},
        ConsistentRead=True,
    ).get('Item')

    if not lookup:
        return _error('INVALID_CREDENTIALS', 'Invalid email or password')

    tenant_id = lookup['tenantId']
    user_id   = lookup['userId']

    # 2. Obtener usuario
    user = table.get_item(
        Key={'pk': f'TENANT#{tenant_id}', 'sk': f'USER#{user_id}'},
        ConsistentRead=True,
    ).get('Item')

    if not user or user.get('status') != 'active':
        return _error('INVALID_CREDENTIALS', 'Invalid email or password')

    # 3. Verificar bloqueo por intentos fallidos
    if int(user.get('failedAttempts', 0)) >= 5:
        return _error('TOO_MANY_ATTEMPTS', 'Account temporarily locked')

    # 4. Verificar contraseña
    if not _verify_password(password, user['passwordHashB64'], user['passwordSaltB64'], user.get('passwordIterations', 310_000)):
        table.update_item(
            Key={'pk': f'TENANT#{tenant_id}', 'sk': f'USER#{user_id}'},
            UpdateExpression='SET failedAttempts = failedAttempts + :one',
            ExpressionAttributeValues={':one': 1},
        )
        return _error('INVALID_CREDENTIALS', 'Invalid email or password')

    # 5. Crear sesión
    token      = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    ttl        = int(time.time()) + 8 * 3600

    table.update_item(
        Key={'pk': f'TENANT#{tenant_id}', 'sk': f'USER#{user_id}'},
        UpdateExpression='SET failedAttempts = :zero',
        ExpressionAttributeValues={':zero': 0},
    )
    table.put_item(Item={
        'pk':         f'SESSION#{token_hash}',
        'sk':         'META',
        'entityType': 'SESSION',
        'userId':     user_id,
        'tenantId':   tenant_id,
        'role':       user['role'],
        'createdAt':  _now_iso(),
        'ttl':        ttl,
    })

    return _ok({
        'accessToken': token,
        'tokenType':   'Bearer',
        'expiresIn':   28800,
        'user': {
            'userId':   user_id,
            'email':    user['email'],
            'role':     user['role'],
            'tenantId': tenant_id,
        },
    })


def logout(event, context):
    auth       = _auth(event)
    user_id    = auth.get('userId')
    tenant_id  = auth.get('tenantId')

    # Recuperar el token del header para eliminarlo
    headers    = event.get('headers') or {}
    auth_header = headers.get('Authorization') or headers.get('authorization', '')
    token      = auth_header[len('Bearer '):]
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    table.delete_item(Key={'pk': f'SESSION#{token_hash}', 'sk': 'META'})

    return _ok({})


def get_me(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    user_id   = auth.get('userId')

    item = table.get_item(
        Key={'pk': f'TENANT#{tenant_id}', 'sk': f'USER#{user_id}'},
    ).get('Item')

    if not item:
        return _error('NOT_FOUND', 'User not found')

    return _ok(_safe_user(item))


def create_user(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    role      = auth.get('role')

    if role != 'tenant_admin':
        return _error('FORBIDDEN', 'Only tenant admins can create users')

    body     = _body(event)
    email    = (body.get('email') or '').strip().lower()
    password = body.get('password', '')
    new_role = body.get('role', 'student')

    if not email or not password:
        return _error('INVALID_BODY', 'email and password are required')

    if new_role not in ('student', 'teacher', 'tenant_admin'):
        return _error('INVALID_BODY', 'Invalid role')

    # Verificar si el email ya existe en el tenant
    existing = table.get_item(
        Key={'pk': f'EMAIL#{email}', 'sk': 'LOOKUP'},
        ConsistentRead=True,
    ).get('Item')

    if existing:
        return _error('CONFLICT', 'Email already exists')

    tenant_letter = tenant_id.split('_')[-1]
    user_id       = f'USR-{tenant_letter}-{uuid.uuid4().hex[:8].upper()}'
    hash_b64, salt_b64 = _hash_password(password)
    now = _now_iso()

    table.transact_write(Items=[
        {
            'Put': {
                'TableName': table.name,
                'Item': {
                    'pk':                 f'TENANT#{tenant_id}',
                    'sk':                 f'USER#{user_id}',
                    'entityType':         'USER',
                    'userId':             user_id,
                    'tenantId':           tenant_id,
                    'email':              email,
                    'role':               new_role,
                    'status':             'active',
                    'passwordHashB64':    hash_b64,
                    'passwordSaltB64':    salt_b64,
                    'passwordIterations': 310_000,
                    'failedAttempts':     0,
                    'createdAt':          now,
                },
                'ConditionExpression': 'attribute_not_exists(pk)',
            },
        },
        {
            'Put': {
                'TableName': table.name,
                'Item': {
                    'pk':       f'EMAIL#{email}',
                    'sk':       'LOOKUP',
                    'userId':   user_id,
                    'tenantId': tenant_id,
                },
                'ConditionExpression': 'attribute_not_exists(pk)',
            },
        },
    ])

    return _ok({'userId': user_id, 'email': email, 'role': new_role})


def list_users(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    role      = auth.get('role')

    if role != 'tenant_admin':
        return _error('FORBIDDEN', 'Only tenant admins can list users')

    query  = _query(event)
    limit  = min(int(query.get('limit', 20)), 100)
    cursor = query.get('nextToken')

    kwargs = {
        'KeyConditionExpression': Key('pk').eq(f'TENANT#{tenant_id}') & Key('sk').begins_with('USER#'),
        'Limit': limit,
    }

    if cursor:
        kwargs['ExclusiveStartKey'] = json.loads(base64.b64decode(cursor).decode())

    result     = table.query(**kwargs)
    items      = [_safe_user(i) for i in result.get('Items', [])]
    last_key   = result.get('LastEvaluatedKey')
    next_token = base64.b64encode(json.dumps(last_key).encode()).decode() if last_key else None

    return _ok({'items': items, 'nextToken': next_token})


def get_user(event, context):
    auth      = _auth(event)
    tenant_id = auth.get('tenantId')
    caller_id = auth.get('userId')
    role      = auth.get('role')

    target_id = _path(event).get('userId')

    if role != 'tenant_admin' and caller_id != target_id:
        return _error('FORBIDDEN', 'Access denied')

    item = table.get_item(
        Key={'pk': f'TENANT#{tenant_id}', 'sk': f'USER#{target_id}'},
    ).get('Item')

    if not item:
        return _error('NOT_FOUND', 'User not found')

    return _ok(_safe_user(item))
