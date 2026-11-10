import boto3
import json
import logging
import os
import time

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['TABLE_NAME'])

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, context):
    failures = []

    for record in event.get('Records', []):
        message_id = record['messageId']
        try:
            _process_record(record)
        except Exception as e:
            log.error(json.dumps({'action': 'consumer_error', 'messageId': message_id, 'error': str(e)}))
            failures.append({'itemIdentifier': message_id})

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
        log.warning(json.dumps({'action': 'consumer_malformed', 'body': str(body)[:200]}))
        return

    ttl = int(time.time()) + 30 * 24 * 3600

    try:
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
        log.info(json.dumps({'action': 'consumer_processed', 'eventId': event_id, 'enrollmentId': enrollment_id, 'studentId': student_id, 'courseId': course_id}))

    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        log.info(json.dumps({'action': 'consumer_duplicate_skipped', 'eventId': event_id}))
