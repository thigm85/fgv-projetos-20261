
import os

import boto3


def handler(event, context):
    job_name = os.environ["GLUE_JOB_NAME"]
    client = boto3.client("glue")

    response = client.start_job_run(JobName=job_name)
    run_id = response["JobRunId"]

    print(f"Started Glue job '{job_name}' with JobRunId={run_id}")
    return {"JobName": job_name, "JobRunId": run_id}
