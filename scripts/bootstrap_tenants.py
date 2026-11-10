#!/usr/bin/env python3
"""
Crea un usuario tenant_admin por cada tenant en la tabla lms-users-{stage}.
Requiere las variables de entorno:
    ADMIN_A_PASS, ADMIN_B_PASS, ADMIN_C_PASS

Uso:
    python bootstrap_tenants.py --stage dev --region us-east-1
"""
import argparse
import base64
import hashlib
import os
import time

import boto3

TENANTS = [
    {
        'tenantId':     'TENANT_A',
        'tenantLetter': 'A',
        'name':         'universidad-alfa',
        'email':        'admin@tenant-a.edu',
        'passEnvVar':   'ADMIN_A_PASS',
    },
    {
        'tenantId':     'TENANT_B',
        'tenantLetter': 'B',
        'name':         'instituto-beta',
        'email':        'admin@tenant-b.edu',
        'passEnvVar':   'ADMIN_B_PASS',
    },
    {
        'tenantId':     'TENANT_C',
        'tenantLetter': 'C',
        'name':         'colegio-gamma',
        'email':        'admin@tenant-c.edu',
        'passEnvVar':   'ADMIN_C_PASS',
    },
]


def hash_password(password):
    salt = os.urandom(16)
    dk   = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 310_000)
    return base64.b64encode(dk).decode(), base64.b64encode(salt).decode()


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def bootstrap(stage, region):
    dynamodb   = boto3.resource('dynamodb', region_name=region)
    table_name = f'lms-users-{stage}'
    table      = dynamodb.Table(table_name)

    print(f'Tabla: {table_name} | Region: {region}\n')

    for tenant in TENANTS:
        tenant_id  = tenant['tenantId']
        letter     = tenant['tenantLetter']
        email      = tenant['email']
        password   = os.environ.get(tenant['passEnvVar'])

        if not password:
            print(f'  [SKIP] {tenant_id} — falta {tenant["passEnvVar"]}')
            continue

        user_id    = f'USR-ADMIN-{tenant_id}'
        hash_b64, salt_b64 = hash_password(password)
        now        = now_iso()

        # Verificar si ya existe
        existing = table.get_item(
            Key={'pk': f'TENANT#{tenant_id}', 'sk': f'USER#{user_id}'},
        ).get('Item')

        if existing:
            print(f'  [SKIP] {tenant_id} — admin ya existe ({user_id})')
            continue

        # TransactWrite: USER + EMAIL_LOOKUP
        dynamodb.meta.client.transact_write_items(
            TransactItems=[
                {
                    'Put': {
                        'TableName': table_name,
                        'Item': {
                            'pk':                 f'TENANT#{tenant_id}',
                            'sk':                 f'USER#{user_id}',
                            'entityType':         'USER',
                            'userId':             user_id,
                            'tenantId':           tenant_id,
                            'email':              email,
                            'role':               'tenant_admin',
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
                        'TableName': table_name,
                        'Item': {
                            'pk':       f'EMAIL#{email}',
                            'sk':       'LOOKUP',
                            'userId':   user_id,
                            'tenantId': tenant_id,
                        },
                        'ConditionExpression': 'attribute_not_exists(pk)',
                    },
                },
            ]
        )

        print(f'  [OK] {tenant_id} — admin creado: {user_id} ({email})')

    print('\nBootstrap completado.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage',  default='dev')
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()

    bootstrap(args.stage, args.region)
