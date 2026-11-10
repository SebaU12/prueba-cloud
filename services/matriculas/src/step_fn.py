import boto3
import json
import logging
import os
import time
import uuid

from boto3.dynamodb.types import TypeSerializer as _TS
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(os.environ['TABLE_NAME'])
_ddb_cli = dynamodb.meta.client
_ser     = _TS()

log = logging.getLogger()
log.setLevel(logging.INFO)


def _ddb(item):
    return {k: _ser.serialize(v) for k, v in item.items()}


def handler(event, context):
    tenant_id  = event['tenantId']
    course_id  = event['courseId']
    student_id = event['studentId']

    enrollment_id = f'ENR-{uuid.uuid4()}'
    event_id      = str(uuid.uuid4())
    now           = _now_iso()
    ttl_outbox    = int(time.time()) + 7 * 24 * 3600

    enrollment_item = {
        'pk':           f'TENANT#{tenant_id}#COURSE#{course_id}',
        'sk':           f'STUDENT#{student_id}',
        'entityType':   'ENROLLMENT',
        'enrollmentId': enrollment_id,
        'tenantId':     tenant_id,
        'courseId':     course_id,
        'studentId':    student_id,
        'status':       'active',
        'createdAt':    now,
        'GSI1PK':       f'TENANT#{tenant_id}#STUDENT#{student_id}',
        'GSI1SK':       f'COURSE#{course_id}',
    }

    outbox_item = {
        'pk':           'OUTBOX#PENDING',
        'sk':           f'EVT#{event_id}#{now}',
        'entityType':   'OUTBOX',
        'eventId':      event_id,
        'eventVersion': '1.0',
        'payload':      {
            'enrollmentId': enrollment_id,
            'tenantId':     tenant_id,
            'courseId':     course_id,
            'studentId':    student_id,
            'status':       'active',
            'createdAt':    now,
        },
        'createdAt':    now,
        'ttl':          ttl_outbox,
    }

    enrollment_ddb = {
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

    try:
        _ddb_cli.transact_write_items(TransactItems=[
            {
                'Put': {
                    'TableName': table.name,
                    'Item':      enrollment_ddb,
                    'ConditionExpression': 'attribute_not_exists(enrollmentId)',
                },
            },
            {
                'Put': {
                    'TableName': table.name,
                    'Item':      _ddb(outbox_item),
                },
            },
        ])
    except ClientError as e:
        if e.response['Error']['Code'] == 'TransactionCanceledException':
            reasons = e.response.get('CancellationReasons', [])
            codes   = [r.get('Code', 'None') for r in reasons]
            # El primer item del transact es el enrollment — solo es duplicado si ese falla la condición
            if reasons and reasons[0].get('Code') == 'ConditionalCheckFailed':
                log.warning(json.dumps({'action': 'enrollment_duplicate', 'studentId': student_id, 'courseId': course_id, 'tenantId': tenant_id}))
                raise EnrollmentDuplicate(
                    f'Student {student_id} is already enrolled in course {course_id}'
                )
            log.error(json.dumps({'action': 'enrollment_transaction_cancelled', 'studentId': student_id, 'courseId': course_id, 'cancellationReasons': codes}))
        else:
            log.error(json.dumps({'action': 'enrollment_transaction_error', 'studentId': student_id, 'courseId': course_id, 'error': str(e)}))
        raise

    log.info(json.dumps({'action': 'enrollment_created', 'enrollmentId': enrollment_id, 'studentId': student_id, 'courseId': course_id, 'tenantId': tenant_id}))

    return {
        'enrollmentId': enrollment_id,
        'courseId':     course_id,
        'studentId':    student_id,
        'status':       'active',
        'createdAt':    now,
    }


def _now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


class EnrollmentDuplicate(Exception):
    pass
