
import boto3

import json

from botocore.exceptions import ClientError

from app.config.config import settings

from typing import Optional

 

class SQSService:

    def __init__(self):

        client_config = {

            'region_name': settings.aws_region

        }

       

        if settings.is_local and settings.aws_endpoint_url:

            client_config['endpoint_url'] = settings.aws_endpoint_url

            client_config['aws_access_key_id'] = settings.aws_access_key_id

            client_config['aws_secret_access_key'] = settings.aws_secret_access_key

       

        self.sqs_client = boto3.client('sqs', **client_config)

        self.queue_url = settings.sqs_queue_url

   

    def send_message(self, message_body: dict) -> Optional[str]:

        try:

            response = self.sqs_client.send_message(

                QueueUrl=self.queue_url,

                MessageBody=json.dumps(message_body)

            )

            return response.get('MessageId')

        except ClientError as e:

            print(f"Error sending message to SQS: {e}")

            return None

 

sqs_service = SQSService()

 

 