# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from platform import architecture
from constructs import Construct

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_s3 as s3,
    aws_s3objectlambda as s3ol,
    aws_iam as iam,
    aws_lambda,
    aws_lambda_nodejs as lambda_nodejs,
)

class Storage(Stack):
    def __init__(self, scope: Construct, construct_id: str, deploy_region: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Stack info
        stack_name = Stack.of(self).stack_name.lower()
        region = Stack.of(self).region
        account_id = Stack.of(self).account

        # S3 Object Lambda CfnAccessPoint does not have a method to add a policy except at creation time,
        #   so explicitly setting the access point name for the policy so a policy resource can be defined
        s3ol_supporting_ap_name = f"{stack_name}-s3ol-supporting-ap"
        s3ol_supporting_ap_arn = f"arn:aws:s3:{region}:{account_id}:accesspoint/{s3ol_supporting_ap_name}"
        # S3 Object Lambda access point name
        s3ol_ap_name = f"{stack_name}-s3ol-ap"
        # S3 Object Lambda access point ARN
        s3ol_ap_arn = f"arn:aws:s3-object-lambda:{deploy_region}:{account_id}:accesspoint/{s3ol_ap_name}"

        # S3 bucket
        storage_bucket = s3.Bucket(
            self,
            "bucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            public_read_access=False,
        )

        # Lambda function for S3 Object Lambda to remove exif data
        fn_s3ol_exif = lambda_nodejs.NodejsFunction(
            self,
            "lambda-exif-fn",
            description="Lambda Function for S3 Object Lambda",
            deps_lock_file_path="./lambda/exif_js/package-lock.json",
            entry="./lambda/exif_js/index.js",
            handler="handler",
            runtime=aws_lambda.Runtime.NODEJS_16_X,
            timeout=Duration.minutes(1),
            memory_size=512,
            bundling=lambda_nodejs.BundlingOptions(
                minify=True,
                node_modules=["@aws-sdk/client-s3",
                              "axios", "sharp", 'exif-reader']
            ),
        )

        # Allow Lambda function to write to S3 Object Lambda response
        fn_s3ol_exif.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3-object-lambda:WriteGetObjectResponse"],
                resources=[s3ol_ap_arn],
            )
        )

        # S3 supporting access point
        s3ol_supporting_ap = s3.CfnAccessPoint(
            self,
            "s3ol-supporting-ap",
            bucket=storage_bucket.bucket_name,
            name=s3ol_supporting_ap_name,
            public_access_block_configuration=s3.CfnAccessPoint.PublicAccessBlockConfigurationProperty(
                block_public_acls=True,
                block_public_policy=True,
                ignore_public_acls=True,
                restrict_public_buckets=True,
            ),
            policy=iam.PolicyDocument(
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=["s3:GetObject"],
                        principals=[fn_s3ol_exif.grant_principal],
                        resources=[f"{s3ol_supporting_ap_arn}/object/*"],
                    )
                ]
            ),
        )

        # S3 Object Lambda access point
        s3ol_ap = s3ol.CfnAccessPoint(
            self,
            "s3ol-ap",
            name=s3ol_ap_name,
            object_lambda_configuration=s3ol.CfnAccessPoint.ObjectLambdaConfigurationProperty(
                supporting_access_point=s3ol_supporting_ap_arn,
                cloud_watch_metrics_enabled=False,
                transformation_configurations=[
                    s3ol.CfnAccessPoint.TransformationConfigurationProperty(
                        actions=['GetObject'], content_transformation={'AwsLambda': {'FunctionArn': fn_s3ol_exif.function_arn}}
                    )
                ],
            ),
        )

        # Add the policy for the S3 Object Lambda AP
        s3ol_ap_policy = s3ol.CfnAccessPointPolicy(
            self,
            "s3ol-policy",
            object_lambda_access_point=s3ol_ap.name,
            policy_document=iam.PolicyDocument(
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=["s3-object-lambda:GetObject"],
                        principals=[fn_s3ol_exif.grant_principal],
                        resources=[s3ol_ap.attr_arn],
                    )
                ]
            ),
        )

        CfnOutput(self, "s3bucket", value=storage_bucket.bucket_name,
                  description="S3 Bucket Name")
