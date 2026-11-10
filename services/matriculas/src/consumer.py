import boto3
import json
import os
import time

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['TABLE_NAME'])


def handler(event, context):
    """
    Triggered por SQS (batch size 5, ReportBatchItemFailures habilitado).
    Procesa cada mensaje de forma idempotente:
    - Si el evento ya fue procesado (PROCESSED_EVENT existe) → skip silencioso.
    - Si no → registrar PROCESSED_EVENT con PutItem condicional.
    """
    failures = []

    for record in event.get('Records', []):
        message_id = record['messageId']
        try:
            _process_record(record)
        except Exception as e:
            print(f'ERROR processing message {message_id}: {e}')
            failures.append({'itemIdentifier': message_id})

    # ReportBatchItemFailures: solo los fallidos vuelven a la cola
    return {'batchItemFailures': failures}


def _process_record(record):
    body    = json.loads(record['body'])
    payload = body.get('payload', {})

    event_id      = body.get('eventId', '')
    enrollment_id = payload.get('enrollmentId', '')
    tenant_id     = payload.get('tenantId', '')
    course_id     = payload.get('courseId', '')
    student_id    = payload.get('studentId', '')

    if not event_id or not enrollment_id:
        # Mensaje malformado — no reintentar
        print(f'Malformed message, skipping: {body}')
        return

    ttl = int(time.time()) + 30 * 24 * 3600  # 30 días

    try:
        # PutItem condicional — falla si ya existe (idempotencia)
        table.put_item(
            Item={
                'pk':           f'PROCESSED#{event_id}',
                'sk':           'META',
                'entityType':   'PROCESSED_EVENT',
                'eventId':      event_id,
                'enrollmentId': enrollment_id,
                'tenantId':     tenant_id,
                'courseId':     course_id,
                'studentId':    student_id,
                'processedAt':  time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'ttl':          ttl,
            },
            ConditionExpression='attribute_not_exists(pk)',
        )
        print(f'Processed event {event_id} for enrollment {enrollment_id}')

    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        # Ya procesado — skip silencioso (idempotencia)
        print(f'Event {event_id} already processed, skipping')
