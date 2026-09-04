
import boto3

from botocore.exceptions import ClientError

from app.config.config import settings

from typing import Optional

import os

import json

import logging

 

logger = logging.getLogger(__name__)

 

class S3Service:

    def __init__(self):

        client_config = {'region_name': settings.aws_region}

       

        if settings.is_local:

            client_config['aws_access_key_id'] = settings.aws_access_key_id

            client_config['aws_secret_access_key'] = settings.aws_secret_access_key

            client_config['endpoint_url'] = settings.aws_endpoint_url

       

        self.s3_client = boto3.client('s3', **client_config)

 

   

    def upload_file(self, file_content: bytes, file_name: str, bucket: str, folder: str = "audio") -> Optional[str]:

        try:

            s3_key = f"{folder}/{file_name}"

           

            self.s3_client.put_object(

                Bucket=bucket,

                Key=s3_key,

                Body=file_content

            )

            s3_url = f"s3://{bucket}/{s3_key}"

            return s3_url

        except ClientError as e:

            print(f"Error uploading file to S3: {e}")

            return None

   

    def stream_upload(self, file_stream, file_name: str, bucket: str, folder: str = "audio") -> Optional[str]:

        s3_key = f"{folder}/{file_name}"

        try:

            self.s3_client.upload_fileobj(

                file_stream,

                bucket,

                s3_key

            )

            return f"s3://{bucket}/{s3_key}"

        except ClientError as e:

            print(f"Error in stream upload: {e}")

            return None

   

    def download_file(self, bucket: str, s3_key: str) -> Optional[bytes]:

        try:

            response = self.s3_client.get_object(Bucket=bucket, Key=s3_key)

            return response['Body'].read()

        except ClientError as e:

            print(f"Error downloading file from S3: {e}")

            return None

   

    def get_presigned_url(self, bucket: str, s3_key: str, expiration: int = 3600) -> Optional[str]:

        try:

            url = self.s3_client.generate_presigned_url(

                'get_object',

                Params={'Bucket': bucket, 'Key': s3_key},

                ExpiresIn=expiration

            )

            return url

        except ClientError as e:

            print(f"Error generating presigned URL: {e}")

            return None

   

    def read_json_file(self, bucket: str, s3_key: str) -> Optional[bytes]:

        try:

            response = self.s3_client.get_object(Bucket=bucket, Key=s3_key)

            content = response['Body'].read()

            return content

        except ClientError as e:

            logger.error(f"Error reading file from S3 - Bucket: {bucket}, Key: {s3_key}, Error: {str(e)}", exc_info=True)

            return None

        except Exception as e:

            logger.error(f"Unexpected error reading file - Bucket: {bucket}, Key: {s3_key}, Error: {str(e)}", exc_info=True)

            return None

 

s3_service = S3Service()