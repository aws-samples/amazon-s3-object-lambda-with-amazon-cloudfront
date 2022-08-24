# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk.custom_resources import (
    AwsCustomResource,
    AwsCustomResourcePolicy,
    PhysicalResourceId,
    AwsSdkCall
)
from aws_cdk import Stack, aws_logs as logs
from constructs import Construct

import time

# Custom resource to read CF exports from different regions in the same account
# This will be recreated each deployment in case the SSM value changes (physical resource id)

class SsmReader(Construct):
    def __init__(self, scope: Construct, id: str, region: str, parameter_name: str, stack_name: str) -> None:
        super().__init__(scope, id)

        account_id = Stack.of(self).account

        self.cr = AwsCustomResource(
            self,
            'SsmUtil',
            policy=AwsCustomResourcePolicy.from_sdk_calls(
                resources=[
                    f'arn:aws:ssm:{region}:{account_id}:parameter/{stack_name}*']
            ),
            log_retention=logs.RetentionDays.THREE_DAYS,
            on_update=self.__read_cf_output(region, parameter_name),
            on_delete=self.__delete_parameter(region, parameter_name)
        )

    def __read_cf_output(self, region, parameter_name):
        return AwsSdkCall(
            region=region,
            physical_resource_id=PhysicalResourceId.of(str(time.time())),
            service="SSM",
            action="getParameter",
            parameters={"Name": parameter_name},
        )

    def __delete_parameter(self, region, parameter_name):
        return AwsSdkCall(
            region=region,
            service="SSM",
            action="deleteParameter",
            parameters={"Name": parameter_name},
        )

    def get_value(self):
        return self.cr.get_response_field('Parameter.Value')
