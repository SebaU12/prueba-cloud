import boto3
import os

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])


def handler(event, context):
    """
    Invocado por Step Functions de Matrículas.

    Input esperado:
    {
        "tenantId": "TENANT_A",
        "userId":   "USR-A-00001"
    }

    Output en éxito:
    {
        "userId":   "USR-A-00001",
        "tenantId": "TENANT_A",
        "role":     "student",
        "status":   "active"
    }

    Lanza excepción nombrada si falla — Step Functions la captura con Catch.
    """
    tenant_id = event.get('tenantId')
    user_id   = event.get('userId')

    if not tenant_id or not user_id:
        raise ValidationError('Missing tenantId or userId')

    response = table.get_item(
        Key={
            'pk': f'TENANT#{tenant_id}',
            'sk': f'USER#{user_id}',
        },
        ConsistentRead=True,
    )

    item = response.get('Item')

    if not item:
        raise StudentNotFound(f'User {user_id} not found in tenant {tenant_id}')

    if item.get('tenantId') != tenant_id:
        raise TenantMismatch(f'User {user_id} does not belong to tenant {tenant_id}')

    if item.get('role') != 'student':
        raise StudentNotFound(f'User {user_id} is not a student')

    if item.get('status') != 'active':
        raise StudentInactive(f'User {user_id} is inactive')

    return {
        'userId':   item['userId'],
        'tenantId': item['tenantId'],
        'role':     item['role'],
        'status':   item['status'],
    }


# ─── Excepciones nombradas (Step Functions las captura por nombre) ─────────────

class ValidationError(Exception):
    pass

class StudentNotFound(Exception):
    pass

class StudentInactive(Exception):
    pass

class TenantMismatch(Exception):
    pass
