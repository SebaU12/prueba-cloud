"""Utilidades compartidas para los scripts de seed."""
import time
import boto3


def batch_write(dynamodb_client, table_name, items):
    """
    Escribe items en DynamoDB en lotes de 25 con reintento exponencial
    para los UnprocessedItems.
    """
    for i in range(0, len(items), 25):
        batch    = items[i:i + 25]
        retries  = 0
        requests = [{'PutRequest': {'Item': item}} for item in batch]

        while requests:
            response     = dynamodb_client.batch_write_item(RequestItems={table_name: requests})
            unprocessed  = response.get('UnprocessedItems', {}).get(table_name, [])
            requests     = unprocessed

            if requests:
                retries += 1
                time.sleep(min(0.1 * (2 ** retries), 5))


def print_progress(current, total, label=''):
    pct = int(current / total * 100)
    bar = '█' * (pct // 5) + '░' * (20 - pct // 5)
    print(f'\r  {label} [{bar}] {current}/{total} ({pct}%)', end='', flush=True)
