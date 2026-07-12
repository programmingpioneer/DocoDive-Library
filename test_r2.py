import boto3
from botocore.config import Config

client = boto3.client(
    's3',
    endpoint_url='https://9102c684f78723bec389d86e8aaad0b9.r2.cloudflarestorage.com',
    aws_access_key_id='e7387b8552186150e11fd39069cce3c4',
    aws_secret_access_key='5b82df281ef9dbab0e202453907746be0b89e4da3f5593adf5752d5aa0a5275a',
    config=Config(signature_version='s3v4'),
    region_name='auto'
)

bucket = 'docodive'
key = 'uploads/test.txt'

try:
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body='Hello, R2 works!',
        ContentType='text/plain'
    )
    print("✅ Upload successful!")
except Exception as e:
    print("❌ Upload failed:", e)