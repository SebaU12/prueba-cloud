#!/usr/bin/env python3
"""
Seed de 30,000 cursos (10,000 por tenant).
Cada uno de los 200 teachers tiene 50 cursos.
200 teachers × 50 cursos = 10,000 por tenant.

Uso:
    python seed_cursos.py --stage dev --region us-east-1
"""
import argparse
import os
import sys
import time
import uuid

import boto3

sys.path.insert(0, os.path.dirname(__file__))
from seed_utils import batch_write, print_progress

TENANTS          = ['TENANT_A', 'TENANT_B', 'TENANT_C']
COURSES_PER_TENANT = 10_000
TEACHERS_COUNT     = 200
COURSES_PER_TEACHER = COURSES_PER_TENANT // TEACHERS_COUNT  # 50

STATUSES = ['draft', 'published', 'published', 'published', 'archived']  # mayoría published


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def seed(stage, region):
    client     = boto3.client('dynamodb', region_name=region)
    table_name = f'lms-courses-{stage}'
    now        = now_iso()

    print(f'Tabla: {table_name}')

    for tenant_id in TENANTS:
        letter = tenant_id.split('_')[-1]
        items  = []
        n      = 0

        for t in range(1, TEACHERS_COUNT + 1):
            teacher_id = f'USR-{letter}-{t:05d}'

            for c in range(1, COURSES_PER_TEACHER + 1):
                n         += 1
                course_id  = f'CRS-{letter}-{n:05d}'
                status     = STATUSES[n % len(STATUSES)]

                item = {
                    'pk':          {'S': f'TENANT#{tenant_id}'},
                    'sk':          {'S': f'COURSE#{course_id}'},
                    'entityType':  {'S': 'COURSE'},
                    'courseId':    {'S': course_id},
                    'tenantId':    {'S': tenant_id},
                    'teacherId':   {'S': teacher_id},
                    'title':       {'S': f'Curso {n:05d} — {tenant_id}'},
                    'description': {'S': f'Descripción del curso {course_id}'},
                    'status':      {'S': status},
                    'createdAt':   {'S': now},
                    'GSI1PK':      {'S': f'TENANT#{tenant_id}#TEACHER#{teacher_id}'},
                    'GSI1SK':      {'S': f'COURSE#{course_id}'},
                }

                items.append(item)

                if len(items) >= 500:
                    print_progress(n, COURSES_PER_TENANT, label=tenant_id)
                    batch_write(client, table_name, items)
                    items = []

        if items:
            batch_write(client, table_name, items)

        print_progress(COURSES_PER_TENANT, COURSES_PER_TENANT, label=tenant_id)
        print(f'  ✓ {tenant_id} — {COURSES_PER_TENANT} cursos')

    print('\nSeed cursos completado.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage',  default='dev')
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()
    seed(args.stage, args.region)
