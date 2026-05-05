import boto3

glue = boto3.client('glue', region_name='us-east-1')
response = glue.start_job_run(JobName="classicmodels-star-schema-job")
print(f"Job iniciado. ID: {response['JobRunId']}")