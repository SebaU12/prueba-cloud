import boto3
import os
import time
import uuid

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])


def handler(event, context):
    """
    Invocado por Step Functions — estado CreateEnrollmentRecord.

    Input esperado (acumulado por Step Functions):
    {
        "tenantId":          "TENANT_A",
        "courseId":          "CRS-A-00001",
        "studentId":         "USR-A-00101",
        "studentValidation": { ... },   <- resultado de ValidateStudent
        "courseValidation":  { ... }    <- resultado de ValidateCourse
    }

    Output en éxito:
    {
        "enrollmentId": "ENR-uuid",
        "courseId":     "CRS-A-00001",
        "studentId":    "USR-A-00101",
        "status":       "active",
        "createdAt":    "..."
    }

    Lanza EnrollmentDuplicate si ya existe la matrícula.
    """
    tenant_id  = event['tenantId']
    course_id  = event['courseId']
    student_id = event['studentId']

    enrollment_id = f'ENR-{uuid.uuid4()}'
    event_id      = str(uuid.uuid4())
    now           = _now_iso()
    ttl_outbox    = int(time.time()) + 7 * 24 * 3600  # 7 días

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

    try:
        table.transact_write_items(
            TransactItems=[
                {
                    'Put': {
                        'TableName': table.name,
                        'Item':      enrollment_item,
                        'ConditionExpression': 'attribute_not_exists(pk) AND attribute_not_exists(sk)',
                    },
                },
                {
                    'Put': {
                        'TableName': table.name,
                        'Item':      outbox_item,
                    },
                },
            ]
        )
    except dynamodb.meta.client.exceptions.TransactionCanceledException as e:
        reasons = e.response.get('CancellationReasons', [])
        if reasons and reasons[0].get('Code') == 'ConditionalCheckFailed':
            raise EnrollmentDuplicate(
                f'Student {student_id} is already enrolled in course {course_id}'
            )
        raise

    return {
        'enrollmentId': enrollment_id,
        'courseId':     course_id,
        'studentId':    student_id,
        'status':       'active',
        'createdAt':    now,
    }


def _now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


# ─── Excepción nombrada (Step Functions la captura con Catch) ──────────────────

class EnrollmentDuplicate(Exception):
    pass
