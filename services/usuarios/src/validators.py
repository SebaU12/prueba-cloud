import boto3
import json
import logging
import os

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, context):
    tenant_id = event.get('tenantId')
    user_id   = event.get('studentId') or event.get('userId')

    if not tenant_id or not user_id:
        raise ValidationError('Missing tenantId or studentId')

    response = table.get_item(
        Key={
            'pk': f'TENANT#{tenant_id}',
            'sk': f'USER#{user_id}',
        },
        ConsistentRead=True,
    )

    item = response.get('Item')

    if not item:
        log.warning(json.dumps({'action': 'validate_student_not_found', 'userId': user_id, 'tenantId': tenant_id}))
        raise StudentNotFound(f'User {user_id} not found in tenant {tenant_id}')

    if item.get('tenantId') != tenant_id:
        log.warning(json.dumps({'action': 'validate_student_tenant_mismatch', 'userId': user_id, 'tenantId': tenant_id}))
        raise TenantMismatch(f'User {user_id} does not belong to tenant {tenant_id}')

    if item.get('role') != 'student':
        log.warning(json.dumps({'action': 'validate_student_not_student', 'userId': user_id, 'role': item.get('role')}))
        raise StudentNotFound(f'User {user_id} is not a student')

    if item.get('status') != 'active':
        log.warning(json.dumps({'action': 'validate_student_inactive', 'userId': user_id, 'tenantId': tenant_id}))
        raise StudentInactive(f'User {user_id} is inactive')

    log.info(json.dumps({'action': 'validate_student_ok', 'userId': user_id, 'tenantId': tenant_id}))

    return {
        'userId':   item['userId'],
        'tenantId': item['tenantId'],
        'role':     item['role'],
        'status':   item['status'],
    }


class ValidationError(Exception):
    pass

class StudentNotFound(Exception):
    pass

class StudentInactive(Exception):
    pass

class TenantMismatch(Exception):
    pass
