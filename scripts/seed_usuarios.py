#!/usr/bin/env python3
"""
Seed de 30,000 usuarios (10,000 por tenant).
  - Usuarios 00001–00200  → teacher
  - Usuarios 00201–10000  → student

Todos los usuarios seed tienen la misma contraseña: Seed2026!
(El hash se calcula una sola vez para no tardar horas)

Uso:
    python seed_usuarios.py --stage dev --region us-east-1
"""
import argparse
import base64
import hashlib
import os
import sys
import time

import boto3

sys.path.insert(0, os.path.dirname(__file__))
from seed_utils import batch_write, print_progress

TENANTS        = ['TENANT_A', 'TENANT_B', 'TENANT_C']
USERS_PER_TENANT = 10_000
TEACHERS_COUNT   = 200
SEED_PASSWORD    = 'Seed2026!'


def hash_password_once(password):
    salt = os.urandom(16)
    dk   = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 310_000)
    return base64.b64encode(dk).decode(), base64.b64encode(salt).decode()


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def seed(stage, region):
    client     = boto3.client('dynamodb', region_name=region)
    table_name = f'lms-users-{stage}'

    print(f'Tabla: {table_name}')
    print('Hasheando contraseña seed (una sola vez)...')
    hash_b64, salt_b64 = hash_password_once(SEED_PASSWORD)
    now = now_iso()

    for tenant_id in TENANTS:
        letter = tenant_id.split('_')[-1]
        items  = []

        for n in range(1, USERS_PER_TENANT + 1):
            user_id = f'USR-{letter}-{n:05d}'
            role    = 'teacher' if n <= TEACHERS_COUNT else 'student'
            email   = f'{role}{n:05d}@tenant-{letter.lower()}.edu'

            user_item = {
                'pk':                 {'S': f'TENANT#{tenant_id}'},
                'sk':                 {'S': f'USER#{user_id}'},
                'entityType':         {'S': 'USER'},
                'userId':             {'S': user_id},
                'tenantId':           {'S': tenant_id},
                'email':              {'S': email},
                'role':               {'S': role},
                'status':             {'S': 'active'},
                'passwordHashB64':    {'S': hash_b64},
                'passwordSaltB64':    {'S': salt_b64},
                'passwordIterations': {'N': '310000'},
                'failedAttempts':     {'N': '0'},
                'createdAt':          {'S': now},
            }

            lookup_item = {
                'pk':       {'S': f'EMAIL#{email}'},
                'sk':       {'S': 'LOOKUP'},
                'userId':   {'S': user_id},
                'tenantId': {'S': tenant_id},
            }

            items.append(user_item)
            items.append(lookup_item)

            if n % 500 == 0:
                print_progress(n, USERS_PER_TENANT, label=tenant_id)
                batch_write(client, table_name, items)
                items = []

        if items:
            batch_write(client, table_name, items)

        print_progress(USERS_PER_TENANT, USERS_PER_TENANT, label=tenant_id)
        print(f'  ✓ {tenant_id} — {USERS_PER_TENANT} usuarios')

    print('\nSeed usuarios completado.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage',  default='dev')
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()
    seed(args.stage, args.region)
