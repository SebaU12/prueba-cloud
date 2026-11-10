import boto3
import json
import logging
import os

sns = boto3.client('sns')

SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']

log = logging.getLogger()
log.setLevel(logging.INFO)


def publish(event, context):
    for record in event.get('Records', []):
        new_image = record['dynamodb'].get('NewImage', {})
        event_id  = new_image.get('eventId', {}).get('S', '')
        message   = _deserialize(new_image.get('payload', {}))

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=json.dumps({
                'eventId':      event_id,
                'eventVersion': new_image.get('eventVersion', {}).get('S', '1.0'),
                'eventType':    'ENROLLMENT_CREATED',
                'payload':      message,
            }),
            MessageAttributes={
                'eventType': {
                    'DataType':    'String',
                    'StringValue': 'ENROLLMENT_CREATED',
                },
            },
        )

        log.info(json.dumps({'action': 'outbox_published', 'eventId': event_id}))


def _deserialize(dynamo_value):
    if 'M' in dynamo_value:
        return {k: _deserialize(v) for k, v in dynamo_value['M'].items()}
    if 'L' in dynamo_value:
        return [_deserialize(v) for v in dynamo_value['L']]
    if 'S' in dynamo_value:
        return dynamo_value['S']
    if 'N' in dynamo_value:
        return int(dynamo_value['N']) if '.' not in dynamo_value['N'] else float(dynamo_value['N'])
    if 'BOOL' in dynamo_value:
        return dynamo_value['BOOL']
    if 'NULL' in dynamo_value:
        return None
    return dynamo_value
