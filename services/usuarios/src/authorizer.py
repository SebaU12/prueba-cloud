import boto3
import hashlib
import os
import time

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])


def handler(event, context):
    try:
        token = _extract_token(event)
        session = _get_session(token)
        return _allow(
            method_arn=event['methodArn'],
            principal_id=session['userId'],
            tenant_id=session['tenantId'],
            user_id=session['userId'],
            role=session['role'],
        )
    except Exception:
        return _deny(event.get('methodArn', '*'))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_token(event):
    headers = event.get('headers') or {}
    auth_header = headers.get('Authorization') or headers.get('authorization', '')

    if not auth_header.startswith('Bearer '):
        raise ValueError('Missing or invalid Authorization header')

    return auth_header[len('Bearer '):]


def _get_session(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    response = table.get_item(
        Key={'pk': f'SESSION#{token_hash}', 'sk': 'META'},
        ConsistentRead=True,
    )

    item = response.get('Item')
    if not item:
        raise ValueError('Session not found')

    if int(item.get('ttl', 0)) < int(time.time()):
        raise ValueError('Session expired')

    return item


def _allow(method_arn, principal_id, tenant_id, user_id, role):
    # Wildcard en stage/método/recurso — evita problemas de caché con TTL=0
    arn_parts = method_arn.split(':')
    region  = arn_parts[3]
    account = arn_parts[4]
    api_id  = arn_parts[5].split('/')[0]
    stage   = arn_parts[5].split('/')[1]

    resource_arn = f'arn:aws:execute-api:{region}:{account}:{api_id}/{stage}/*/*'

    return {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': 'Allow',
                'Resource': resource_arn,
            }],
        },
        'context': {
            'tenantId': tenant_id,
            'userId': user_id,
            'role': role,
        },
    }


def _deny(method_arn):
    return {
        'principalId': 'unauthorized',
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': 'Deny',
                'Resource': method_arn,
            }],
        },
    }
