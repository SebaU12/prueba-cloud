#!/usr/bin/env python3
"""
Seed de 30,000 evaluaciones (10,000 por tenant).
Una evaluación publicada por curso con 3 preguntas.

Uso:
    python seed_evaluaciones.py --stage dev --region us-east-1
"""
import argparse
import json
import os
import sys
import time
import uuid

import boto3

sys.path.insert(0, os.path.dirname(__file__))
from seed_utils import batch_write, print_progress

TENANTS               = ['TENANT_A', 'TENANT_B', 'TENANT_C']
EVALUATIONS_PER_TENANT = 10_000

SAMPLE_QUESTIONS = [
    {
        'questionId':   'Q1',
        'text':         '¿Qué significa SaaS?',
        'options':      ['Software as a Service', 'Storage as a System', 'Server as a Service'],
        'correctIndex': 0,
    },
    {
        'questionId':   'Q2',
        'text':         '¿Cuál es la ventaja principal de serverless?',
        'options':      ['Pago por uso', 'Mayor control del servidor', 'Menor latencia siempre'],
        'correctIndex': 0,
    },
    {
        'questionId':   'Q3',
        'text':         '¿Qué servicio de AWS se usa para colas de mensajes?',
        'options':      ['S3', 'SQS', 'SNS'],
        'correctIndex': 1,
    },
]


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def seed(stage, region):
    client     = boto3.client('dynamodb', region_name=region)
    table_name = f'lms-evaluations-{stage}'
    now        = now_iso()

    print(f'Tabla: {table_name}')

    for tenant_id in TENANTS:
        letter = tenant_id.split('_')[-1]
        items  = []

        for n in range(1, EVALUATIONS_PER_TENANT + 1):
            course_id = f'CRS-{letter}-{n:05d}'
            eval_id   = f'EVL-{uuid.uuid4()}'
            teacher_n = ((n - 1) // 50) + 1  # teacher dueño del curso
            teacher_id = f'USR-{letter}-{teacher_n:05d}'

            # Serializar questions como DynamoDB List of Maps
            questions_dynamo = {'L': [
                {'M': {
                    'questionId':   {'S': q['questionId']},
                    'text':         {'S': q['text']},
                    'options':      {'L': [{'S': opt} for opt in q['options']]},
                    'correctIndex': {'N': str(q['correctIndex'])},
                }}
                for q in SAMPLE_QUESTIONS
            ]}

            item = {
                'pk':           {'S': f'TENANT#{tenant_id}#COURSE#{course_id}'},
                'sk':           {'S': f'EVAL#{eval_id}'},
                'entityType':   {'S': 'EVALUATION'},
                'evaluationId': {'S': eval_id},
                'tenantId':     {'S': tenant_id},
                'courseId':     {'S': course_id},
                'teacherId':    {'S': teacher_id},
                'title':        {'S': f'Quiz 1 — Curso {n:05d}'},
                'status':       {'S': 'published'},
                'fechaLimite':  {'S': '2026-12-31T23:59:00Z'},
                'questions':    questions_dynamo,
                'createdAt':    {'S': now},
                'GSI1PK':       {'S': f'TENANT#{tenant_id}#EVAL#{eval_id}'},
                'GSI1SK':       {'S': 'META'},
            }

            items.append(item)

            if len(items) >= 500:
                print_progress(n, EVALUATIONS_PER_TENANT, label=tenant_id)
                batch_write(client, table_name, items)
                items = []

        if items:
            batch_write(client, table_name, items)

        print_progress(EVALUATIONS_PER_TENANT, EVALUATIONS_PER_TENANT, label=tenant_id)
        print(f'  ✓ {tenant_id} — {EVALUATIONS_PER_TENANT} evaluaciones')

    print('\nSeed evaluaciones completado.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage',  default='dev')
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()
    seed(args.stage, args.region)
