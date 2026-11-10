#!/usr/bin/env python3
"""
Seed de 30,000 contenidos (10,000 por tenant).
Un contenido PDF por curso (CRS-X-00001 a CRS-X-10000).

Uso:
    python seed_contenidos.py --stage dev --region us-east-1
"""
import argparse
import os
import sys
import time
import uuid

import boto3

sys.path.insert(0, os.path.dirname(__file__))
from seed_utils import batch_write, print_progress

TENANTS             = ['TENANT_A', 'TENANT_B', 'TENANT_C']
CONTENTS_PER_TENANT = 10_000


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def seed(stage, region):
    client     = boto3.client('dynamodb', region_name=region)
    table_name = f'lms-contents-{stage}'
    now        = now_iso()

    print(f'Tabla: {table_name}')

    for tenant_id in TENANTS:
        letter = tenant_id.split('_')[-1]
        items  = []

        for n in range(1, CONTENTS_PER_TENANT + 1):
            course_id  = f'CRS-{letter}-{n:05d}'
            content_id = f'CNT-{uuid.uuid4()}'
            s3_key     = f'{tenant_id}/{course_id}/{content_id}/material.pdf'

            item = {
                'pk':           {'S': f'TENANT#{tenant_id}#COURSE#{course_id}'},
                'sk':           {'S': f'CONTENT#{content_id}'},
                'entityType':   {'S': 'CONTENT'},
                'contentId':    {'S': content_id},
                'tenantId':     {'S': tenant_id},
                'courseId':     {'S': course_id},
                'uploadedBy':   {'S': f'USR-ADMIN-{tenant_id}'},
                'title':        {'S': f'Material Semana 1 — Curso {n:05d}'},
                's3Key':        {'S': s3_key},
                'mimeType':     {'S': 'application/pdf'},
                'sizeBytes':    {'N': '204800'},
                'uploadStatus': {'S': 'confirmed'},
                'createdAt':    {'S': now},
                'GSI1PK':       {'S': f'TENANT#{tenant_id}#CONTENT#{content_id}'},
                'GSI1SK':       {'S': 'META'},
            }

            items.append(item)

            if len(items) >= 500:
                print_progress(n, CONTENTS_PER_TENANT, label=tenant_id)
                batch_write(client, table_name, items)
                items = []

        if items:
            batch_write(client, table_name, items)

        print_progress(CONTENTS_PER_TENANT, CONTENTS_PER_TENANT, label=tenant_id)
        print(f'  ✓ {tenant_id} — {CONTENTS_PER_TENANT} contenidos')

    print('\nSeed contenidos completado.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage',  default='dev')
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()
    seed(args.stage, args.region)
