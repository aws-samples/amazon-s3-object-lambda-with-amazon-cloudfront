# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from constructs import Construct
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_lambda,
)

from util.ssm_util import SsmReader


class Cdn(Stack):
    def __init__(self, scope: Construct, construct_id: str, deploy_region: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Stack info
        stack_name = Stack.of(self).stack_name
        base_stack_name = stack_name.replace('-cdn', '')
        storage_stack_name = f"{base_stack_name}-storage"
        account_id = Stack.of(self).account

        s3_ol_endpoint = f'{storage_stack_name}-s3ol-ap-{account_id}.s3-object-lambda.{deploy_region}.amazonaws.com'

        # Use the SsmReader custom resource to read the exif Lambda version ARN from SSM
        # This is set as the origin request ARN for the Lambda@Edge config
        edge_fn_arn_reader = SsmReader(
            self,
            id="lambda-edge-fn-arn-reader",
            region="us-east-1",
            parameter_name=f'/{base_stack_name}/Edge-Origin-Request-Fn-Version-Arn',
            stack_name=base_stack_name,
        )
        edge_fn_arn_req_arn = edge_fn_arn_reader.get_value()

        # IVersion object for the CloudFront L@E origin request
        edge_fn_arn_request_fn = aws_lambda.Version.from_version_arn(
            self,
            "edge-origin-request-fn-version-arn",
            version_arn=edge_fn_arn_req_arn,
        )

        # CloudFront Cache Policy - only cache "showExif" and allow compression
        cf_cache_policy = cloudfront.CachePolicy(
            self,
            f"{base_stack_name}-header-cache-policy",
            comment="Cache Exif Query String Only",
            query_string_behavior=cloudfront.CacheQueryStringBehavior.allow_list(
                "showExif"),
            cookie_behavior=cloudfront.CacheCookieBehavior.none(),
            header_behavior=cloudfront.CacheHeaderBehavior.none(),
            enable_accept_encoding_brotli=True,
            enable_accept_encoding_gzip=True,
        )

        # CloudFront Origin Request Policy - not needed
        # https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/controlling-origin-requests.html
        # All URL query strings, HTTP headers, and cookies that you include in the cache key (using a cache policy) are automatically included in origin requests.

        # CloudFront distribution
        # Use the S3 Object Lambda endpoint as the default origin, supporting HTTPS TLSv1.2 only
        # Set up Lambda@Edge Origin Request with the Lambda IVersion object
        cf = cloudfront.Distribution(
            self,
            "cloudfront",
            comment='CloudFront distribution for anonymous S3 Object Lambda access',
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2018,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.HttpOrigin(
                    domain_name=s3_ol_endpoint,
                    origin_ssl_protocols=[cloudfront.OriginSslPolicy.TLS_V1_2],
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
                ),
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cf_cache_policy,
                edge_lambdas=[
                    cloudfront.EdgeLambda(
                        event_type=cloudfront.LambdaEdgeEventType.ORIGIN_REQUEST,
                        function_version=edge_fn_arn_request_fn,
                        include_body=False,
                    )
                ]
            ),
        )

        CfnOutput(self, "cf-domain", value=cf.domain_name,
                  description="CloudFront Domain")
