# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# This Lambda is intended to be used as an Origin Request Lambda@Edge function
# It expects a CloudFront origin request input, e.g. some origin and an URI
# The S3 Object Lambda Access Point should already be the intended origin
# The function will sign the request using its execution credentials
# This allows for anonymous access to S3 Object Lambda

# Both items below are taken care of by the CDK aws_cloudfront.experimental.EdgeFunction construct:
#   - Lambda execution role needs to have additional CloudWatch permissions for Lambda@Edge
#   - Lambda execution role needs to have edgelambda.amazonaws.com as an additional principal

import logging
import hashlib
import datetime
import hmac
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Copied from http://docs.aws.amazon.com/general/latest/gr/signature-v4-examples.html#signature-v4-examples-python


def sign(key, msg):
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()


def getSignatureKey(key, dateStamp, regionName, serviceName):
    kDate = sign(('AWS4' + key).encode('utf-8'), dateStamp)
    kRegion = sign(kDate, regionName)
    kService = sign(kRegion, serviceName)
    kSigning = sign(kService, 'aws4_request')
    return kSigning


def lambda_handler(event, context):
    logger.debug("Event JSON: {}".format(event))
    logger.debug("Context JSON: {}".format(context))

    request = event['Records'][0]['cf']['request']
    headers = request['headers']
    cf_request_id = event['Records'][0]['cf']['config']['requestId']

    if not request['method'] == 'GET':
        logger.debug(
            "Method {} doesn't qualify for S3 object Lambda. Returning original request.".format(
                request['method']
            )
        )
        return request

    # If the origin is not S3 Object Lambda, return the original request
    try:
        domain_name = request['origin']['custom']['domainName']
        if not 's3-object-lambda' in domain_name:
            raise Exception(
                "S3 Object Lambda expected in origin domain name. Got {}".format(domain_name))
    except Exception as e:
        logger.error(e)
        return request

    # full_url = 'https://' + domain_name + request['uri']

    # Use Lambda execution role credentials
    access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    session_token = os.environ.get('AWS_SESSION_TOKEN')
    service = 's3-object-lambda'
    region = domain_name.split(
        '.')[domain_name.split('.').index("amazonaws") - 1]
    payload_hash = "UNSIGNED-PAYLOAD"

    # Lowercase the header name (they appear to be already lowercased, but just in case)
    # L@E header object {} example:
    # "user-agent": [
    #   {
    #       "key": "User-Agent",
    #       "value": "Amazon CloudFront"
    #      }
    #   ],
    lower_headers = {}
    for header, value in headers.items():
        if header.lower().startswith('x-amz') or header.lower() == 'host':
            lower_headers[header.lower()] = value
        else:
            lower_headers[header] = value
    request['headers'] = lower_headers

    # Start building header/signature
    t = datetime.datetime.utcnow()
    # Format date as YYYYMMDD'T'HHMMSS'Z'
    amzdate = t.strftime('%Y%m%dT%H%M%SZ')
    datestamp = t.strftime('%Y%m%d')  # Date w/o time, used in credential scope

    # The steps below follow the example here:
    # https://docs.aws.amazon.com/general/latest/gr/sigv4-signed-request-examples.html#sig-v4-examples-get-auth-header

    # step 1 - define verb - this should be 'GET' and checked above
    method = request['method']
    logger.debug("Step 1 (method): {}".format(method))

    # step 2: canonical URI from CF
    canonical_uri = request['uri']
    logger.debug("Step 2 (canonical_uri): {}".format(canonical_uri))

    # Step 3: canonical query string from CF. This should be an empty string
    canonical_querystring = request['querystring']
    logger.debug("Step 3 (canonical_querystring): {}".format(
        canonical_querystring))

    # Step 4: Create the canonical headers and signed headers.
    aws_headers = {}
    aws_headers.update(
        {
            'host': [{'key': 'host', 'value': domain_name}],
            'x-amz-date': [{'key': 'x-amz-date', 'value': amzdate}],
            'x-amz-content-sha256': [{'key': 'x-amz-content-sha256', 'value': payload_hash}],
            'x-amz-security-token': [{'key': 'x-amz-security-token', 'value': session_token}],
        }
    )
    request['headers'].update(aws_headers)

    # All x-amz headers must be signed - add blacklisted (CF auto-added) headers
    # x-amz-cf-id is added by CloudFront automatically in the origin request
    aws_headers.update(
        {
            'x-amz-cf-id': [{'key': 'x-amz-cf-id', 'value': cf_request_id}],
        }
    )

    canonical_headers = (
        '\n'.join(["%s:%s" % (header, aws_headers[header][0]['value'])
                  for header in sorted(aws_headers.keys())])
        + '\n'
    )
    logger.debug("Step 4 (canonical_headers): {}".format(canonical_headers))

    # Step 5: Create the list of signed headers.
    signed_headers = ';'.join([h.lower() for h in sorted(aws_headers.keys())])
    logger.debug("Step 5 (signed_headers): {}".format(signed_headers))

    # Step 6: Create payload hash. For our S3 purpose this is 'UNSIGNED-PAYLOAD' defined above
    logger.debug("Step 6 (payload_hash): {}".format(payload_hash))

    # Step 7: Combine elements to create canonical request
    canonical_request = (
        method
        + '\n'
        + canonical_uri
        + '\n'
        + canonical_querystring
        + '\n'
        + canonical_headers
        + '\n'
        + signed_headers
        + '\n'
        + payload_hash
    )
    logger.debug("Step 7 (canonical_request): {}".format(canonical_request))

    # Task 2: create the string to sign
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = datestamp + '/' + region + \
        '/' + service + '/' + 'aws4_request'
    string_to_sign = (
        algorithm
        + '\n'
        + amzdate
        + '\n'
        + credential_scope
        + '\n'
        + hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
    )
    logger.debug("Task 2 (string_to_sign): {}".format(string_to_sign))

    # Task 3: calculate the signature
    signing_key = getSignatureKey(secret_key, datestamp, region, service)
    string_to_sign_utf8 = string_to_sign.encode('utf-8')
    signature = hmac.new(signing_key, string_to_sign_utf8,
                         hashlib.sha256).hexdigest()
    logger.debug("Task 3 (signature): {}".format(signature))

    # Task 4: add signing information to the request
    authorization_header = (
        algorithm
        + ' '
        + 'Credential='
        + access_key
        + '/'
        + credential_scope
        + ', '
        + 'SignedHeaders='
        + signed_headers
        + ', '
        + 'Signature='
        + signature
    )
    logger.debug("Task 4 (authorization_header): {}".format(
        authorization_header))

    auth_header = {}
    auth_header['Authorization'] = [
        {'key': 'Authorization', 'value': authorization_header}]

    logger.debug("AWS headers: {}".format(auth_header))

    # Update headers
    request['headers'].update(auth_header)
    logger.debug("Request headers: {}".format(request['headers']))

    logger.debug("Request: {}".format(request, indent=4))

    # Return the signed request
    return request
