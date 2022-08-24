# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk as cdk
import os

from stacks.infra_storage import Storage
from stacks.infra_lambda_edge import LambdaEdge
from stacks.infra_cdn import Cdn

app = cdk.App()

APP_PREFIX = 'anon-s3-ol'
STORAGE_STACK_NAME = f"{APP_PREFIX}-storage"
LE_STACK_NAME = f"{APP_PREFIX}-lambda-edge"
CDN_STACK_NAME = f"{APP_PREFIX}-cdn"

# Lambda@Edge functions must be deployed in us-east-1.
# If the rest of thes stack is deployed in other regions, use SSM to share values.
# Get the deployment region for the rest of the stack:
try:
    deploy_region = os.environ.get(
        "CDK_DEPLOY_REGION", os.environ["CDK_DEFAULT_REGION"])
except:
    deploy_region = 'us-east-1'

# The storage stack creates:
#   - Private S3 bucket
#   - Lambda function with exif tools for S3 Object Lambda
#   - Supporting access point for S3 Object Lambda
#   - S3 Object Lambda access point
storage_stack = Storage(app, STORAGE_STACK_NAME, deploy_region=deploy_region)

# The lambda-edge stack creates:
#   - Lambda Edge function in us-east-1
#   - SSM parameters in us-east-1:
#     - <stack>/Edge-Origin-Request-Fn-Version-Arn
lambda_edge_stack = LambdaEdge(app, LE_STACK_NAME, deploy_region=deploy_region)

# The cdn stack creates:
#  - CloudFront distribution with
#    - Default origin: S3 Object Lambda access point
#    - Cache policy: cache "showExif" query string and enable compression
#    - Origin request policy: "showExif" query string only
#    - Lambda@Edge origin request from the LambdaEdge stack
cdn_stack = Cdn(app, CDN_STACK_NAME, deploy_region=deploy_region)

# Deploy CloudFront last, as it reads SSM parameters from the Lambda@Edge stack
cdn_stack.add_dependency(storage_stack)
cdn_stack.add_dependency(lambda_edge_stack)

app.synth()
