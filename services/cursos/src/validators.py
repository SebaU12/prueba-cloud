import boto3
import os

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])


def handler(event, context):
    """
    Invocado por Step Functions de Matrículas.

    Input esperado:
    {
        "tenantId": "TENANT_A",
        "courseId": "CRS-A-00001"
    }

    Output en éxito:
    {
        "courseId":  "CRS-A-00001",
        "tenantId":  "TENANT_A",
        "teacherId": "USR-A-00020",
        "status":    "published"
    }

    Lanza excepción nombrada si falla — Step Functions la captura con Catch.
    """
    tenant_id = event.get('tenantId')
    course_id = event.get('courseId')

    if not tenant_id or not course_id:
        raise ValidationError('Missing tenantId or courseId')

    response = table.get_item(
        Key={
            'pk': f'TENANT#{tenant_id}',
            'sk': f'COURSE#{course_id}',
        },
        ConsistentRead=True,
    )

    item = response.get('Item')

    if not item:
        raise CourseNotFound(f'Course {course_id} not found in tenant {tenant_id}')

    if item.get('tenantId') != tenant_id:
        raise TenantMismatch(f'Course {course_id} does not belong to tenant {tenant_id}')

    if item.get('status') != 'published':
        raise CourseNotPublished(f'Course {course_id} is not published')

    return {
        'courseId':  item['courseId'],
        'tenantId':  item['tenantId'],
        'teacherId': item['teacherId'],
        'status':    item['status'],
    }


# ─── Excepciones nombradas (Step Functions las captura por nombre) ─────────────

class ValidationError(Exception):
    pass

class CourseNotFound(Exception):
    pass

class CourseNotPublished(Exception):
    pass

class TenantMismatch(Exception):
    pass
