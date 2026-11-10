#!/usr/bin/env python3
"""
Seed de 30,000 matrículas (10,000 por tenant).
Distribuye 10,000 students en 10,000 courses: student_i → course_i.
(Students van de USR-X-00201 a USR-X-10000, Courses de CRS-X-00001 a CRS-X-10000)

Uso:
    python seed_matriculas.py --stage dev --region us-east-1
"""
import argparse
import os
import sys
import time
import uuid

import boto3

sys.path.insert(0, os.path.dirname(__file__))
from seed_utils import batch_write, print_progress

TENANTS              = ['TENANT_A', 'TENANT_B', 'TENANT_C']
ENROLLMENTS_PER_TENANT = 10_000
STUDENT_OFFSET         = 201  # students van de 00201 en adelante


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def seed(stage, region):
    client     = boto3.client('dynamodb', region_name=region)
    table_name = f'lms-enrollments-{stage}'
    now        = now_iso()

    print(f'Tabla: {table_name}')

    for tenant_id in TENANTS:
        letter = tenant_id.split('_')[-1]
        items  = []

        for i in range(1, ENROLLMENTS_PER_TENANT + 1):
            student_n     = STUDENT_OFFSET + (i - 1)
            student_id    = f'USR-{letter}-{student_n:05d}'
            course_id     = f'CRS-{letter}-{i:05d}'
            enrollment_id = f'ENR-{uuid.uuid4()}'

            item = {
                'pk':           {'S': f'TENANT#{tenant_id}#COURSE#{course_id}'},
                'sk':           {'S': f'STUDENT#{student_id}'},
                'entityType':   {'S': 'ENROLLMENT'},
                'enrollmentId': {'S': enrollment_id},
                'tenantId':     {'S': tenant_id},
                'courseId':     {'S': course_id},
                'studentId':    {'S': student_id},
                'status':       {'S': 'active'},
                'createdAt':    {'S': now},
                'GSI1PK':       {'S': f'TENANT#{tenant_id}#STUDENT#{student_id}'},
                'GSI1SK':       {'S': f'COURSE#{course_id}'},
            }

            items.append(item)

            if len(items) >= 500:
                print_progress(i, ENROLLMENTS_PER_TENANT, label=tenant_id)
                batch_write(client, table_name, items)
                items = []

        if items:
            batch_write(client, table_name, items)

        print_progress(ENROLLMENTS_PER_TENANT, ENROLLMENTS_PER_TENANT, label=tenant_id)
        print(f'  ✓ {tenant_id} — {ENROLLMENTS_PER_TENANT} matrículas')

    print('\nSeed matrículas completado.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage',  default='dev')
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()
    seed(args.stage, args.region)
