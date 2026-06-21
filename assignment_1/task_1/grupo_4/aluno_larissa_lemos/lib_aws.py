from __future__ import annotations

import os
from typing import Optional

import boto3


def boto3_session(region: Optional[str] = None, profile: Optional[str] = None) -> boto3.session.Session:
    profile = profile or os.getenv("AWS_PROFILE")
    region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if profile:
        return boto3.session.Session(profile_name=profile, region_name=region)
    return boto3.session.Session(region_name=region)


def rds_client(*, region: Optional[str] = None, profile: Optional[str] = None):
    return boto3_session(region=region, profile=profile).client("rds")

