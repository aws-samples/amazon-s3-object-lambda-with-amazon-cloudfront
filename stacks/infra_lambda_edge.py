# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from constructs import Construct
from aws_cdk import (
    Stack,
    aws_cloudfront as cloudfront,
    aws_lambda,
    aws_iam as iam,
)
from aws_cdk.aws_ssm import StringParameter


class LambdaEdge(Stack):
    def __init__(self, scope: Construct, construct_id: str, deploy_region, **kwargs) -> None:
        super().__init__(
            scope,
            construct_id,
            env={
                'region': 'us-east-1'
            },
            **kwargs
        )

        # Stack info
        stack_name = Stack.of(self).stack_name
        base_stack_name = stack_name.replace('-lambda-edge', '')
        storage_stack_name = f"{base_stack_name}-storage"
        account_id = Stack.of(self).account

        # Lambda@Edge Origin Request Function
        # Note: L@E does not support environment variables
        fn_le_origin_req = cloudfront.experimental.EdgeFunction(
            self,
            "edge-function",
            runtime=aws_lambda.Runtime.PYTHON_3_9,
            handler='edge_signer.lambda_handler',
            code=aws_lambda.Code.from_asset('lambda/edge_signer'),
        )

        # Allow the L@E function to invoke S3 Object Lambda
        # The resource is the ARN of the Lambda function used by S3OL, defined in infra_storage
        fn_le_origin_req.add_to_role_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[
                    f'arn:aws:lambda:{deploy_region}:{account_id}:function:{storage_stack_name}-lambdaexiffn*'
                ],
            )
        )

        # Allow the L@E function to read S3 objects from the supporting S3 access point and bucket
        fn_le_origin_req.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[
                    f"arn:aws:s3:::{storage_stack_name}-bucket*/*",
                    f"arn:aws:s3:{deploy_region}:{account_id}:accesspoint/{storage_stack_name}-s3ol-supporting-ap/object/*",
                ],
            )
        )

        # Allow L@E function to get objects from the S3 Object Lambda access point
        # The resource is the ARN of the S3OL access point, defined in infra_storage (s3ol_ap_name)
        fn_le_origin_req.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3-object-lambda:GetObject"],
                resources=[
                    f'arn:aws:s3-object-lambda:{deploy_region}:{account_id}:accesspoint/{storage_stack_name}-s3ol-ap'
                ],
            )
        )

        # Write the Lambda@Edge version ARN to SSM so other regions may consume it
        # This will be used by the cdn stack as the Lambda@Edge origin request configuration
        StringParameter(
            self,
            "edge-origin-request-fn-version-arn",
            parameter_name=f'/{base_stack_name}/Edge-Origin-Request-Fn-Version-Arn',
            string_value=fn_le_origin_req.edge_arn,
            description="Lambda@Edge origin request lambda version arn",
        )
