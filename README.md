# Modify images cached in Amazon CloudFront using Amazon S3 Object Lambda

This solution lets you dynamically modify images cached in [Amazon CloudFront](https://aws.amazon.com/cloudfront/) via [S3 Object Lambda](https://aws.amazon.com/s3/features/object-lambda/) using [Lambda@Edge](https://aws.amazon.com/lambda/edge/). S3 Object Lambda eliminates the need to create and store derivative copies of your data or to run expensive proxies, all with no changes required to your applications. Amazon CloudFront caches the transformed copies at the edge, enabling low-latency delivery to users.

After deploying the [AWS Cloud Development Kit (CDK)](https://aws.amazon.com/cdk/) application in this repository, you will be able to store images in a private bucket and retrieve images with their EXIF data stripped using a public URL. To further demonstrate the capabilities of this solution, you can specify a query string in the public URL to retrieve only the EXIF data instead of the image.

- [Solution Architecture](#solution-architecture)
- [CDK Architecture](#cdk-architecture)
  - [Stacks](#stacks)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Setup](#setup)
  - [Bootstrap](#bootstrap)
  - [Deployment](#deployment)
- [Usage](#usage)
- [Uninstall](#uninstall)
- [References](#references)
- [Security](#security)
- [License](#license)

## Solution Architecture

![Architecture Diagram](/images/ArchitectureDiagram.png)

1. The user makes a request for an object via a public URL.
2. The request arrives at the nearest Amazon CloudFront edge location.
3. If the object is *not* in the edge cache, CloudFront would typically send an _origin request_ to the object origin in order to retrieve, return and cache the object. In this case we have configured CloudFront to route the origin request through Lambda@Edge.
4. The Lambda@Edge function uses its execution role to sign the origin request, giving the request an authentication principal. The request is returned to CloudFront.
5. CloudFront sends the updated, signed request to the S3 Object Lambda Access Point in order to retrieve the transformed object.
6. The S3 Object Lambda Access Point requires all access be made by authenticated principals. It receives our modified, signed request.
7. Upon validating that our principal has S3 Object Lambda access permissions, S3 Object Lambda invokes its Lambda function.
8. The Lambda function uses the supporting S3 Access Point to read the original file from S3 and transforms the file.
9. The Lambda function writes the result back to S3 Object Lambda.
10. CloudFront returns the object to the consumer and caches the object at the edge. Subsequent requests for this object will return the cached version instead of invoking S3 Object Lambda. By default objects are cached for 24 hours.

## CDK Architecture

While Lambda@Edge functions are replicated to edge locations, their source region must be in us-east-1. We do not want to limit our S3 bucket to the same region. As such, this CDK application creates multiple stacks, where the LambdaEdge stack will always be deployed in us-east-1.

Because we can't natively share resource outputs between regions, we use SSM parameters to store the Lambda@Edge function version ARN, to be consumed by the Cdn stack possibly in another region. For example, the Storage and Cdn stacks can be deployed in us-west-2, while the LambdaEdge stack remains in us-east-1. The Cdn stack will use a custom resource to read the SSM parameters from us-east-1 for the Lambda@Edge function version ARN (Lambda@Edge origin request config) and S3 Object Lambda Access Point (origin domain name).

![CDK Diagram](/images/CDKDiagram.png)

### Stacks

#### Storage

-   Private S3 bucket
-   Lambda function with EXIF tools for S3 Object Lambda
-   Supporting access point for S3 Object Lambda
-   S3 Object Lambda access point

#### LambdaEdge

-   Lambda Edge function in us-east-1
-   SSM parameters in us-east-1:
    -   \<base stack name>/Edge-Origin-Request-Version-Arn

#### Cdn

-   CloudFront distribution with:
    -   Default origin: S3 Object Lambda access point (read from SSM)
    -   Cache policy: cache "showExif" query string and enable compression
    -   Origin request policy: "showExif" query string only
    -   Lambda@Edge origin request (created in LambdaEdge stack, version ARN read from SSM)

## Installation

### Prerequisites

-   [Python 3.x](https://www.python.org/downloads/)
-   [git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
-   [Docker](https://www.docker.com/get-started/)
-   An AWS account
-   [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
-   AWS CLI [configured](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html#cli-configure-quickstart-config)
-   [AWS CDK](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html)

Note: you can use [AWS Cloud9](https://aws.amazon.com/cloud9/) which fulfills all of the prerequisites above. You may have to update AWS CDK by running `npm install -g aws-cdk --force`.

### Setup

First, clone the repository to a local working directory:

```bash
git clone https://github.com/aws-samples/amazon-s3-object-lambda-with-amazon-cloudfront
```

Navigate into the project directory:

```bash
cd amazon-s3-object-lambda-with-amazon-cloudfront
```

This project is set up like a standard Python project. The initialization
process also creates a virtualenv within this project, stored under the `.venv`
directory. To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package. If for any reason the automatic creation of the virtualenv fails,
you can create the virtualenv manually.

To manually create a virtualenv on MacOS and Linux:

```
python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
.venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
pip install -r requirements.txt
```

### Bootstrap
Deploying AWS CDK apps into an AWS environment (a combination of an AWS account and region) requires that you provision resources the AWS CDK needs to perform the deployment. These resources include an Amazon S3 bucket for storing files and IAM roles that grant permissions needed to perform deployments. The process of provisioning these initial resources is called bootstrapping.

The LambdaEdge stack is required to be deployed in us-east-1 while the other stacks may be deployed in other regions. All regions where you plan to deploy this solution will need to be bootstrapped. If you have already done this or have deployed CDK apps in the target regions already, please move on to the next section.

To bootstrap your environment, run the following:

```
cdk bootstrap
```

Possible customizations include:

```
cdk bootstrap --profile <profile_name> aws://<account id>/<region 1> aws://<account id>/<region 2>
```

More information on bootstrapping can be [found here](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html).

### Deployment

This solution is made up of 3 stacks within a single CDK application. This requires the `--all` flag during CDK operations to interact with all stacks at once.

To deploy the CDK app with the default profile and region, run the following:

```
cdk deploy --all
```

To customize the AWS CLI profile or region, use the following:

```
cdk deploy --profile <profile_name> --region <region_name> --all
```

**Note**: the lambda-edge stack will **always** be deployed in the us-east-1 region.

## Usage

To use the solution:

-   Upload test images to the private storage bucket. Some test images have been provided in the images directory of this project. See below for instructions on finding the S3 bucket name.
-   Navigate to the CloudFront URL with the file name attached, e.g. https://a1b2c3d4e5f6g7.cloudfront.net/test.jpg
    -   This will return the image _without_ any EXIF data.
-   Append the query string ?showExif=true to the URL, e.g. https://a1b2c3d4e5f6g7.cloudfront.net/test.jpg?showExif=true
    -   This will return the image's EXIF data in JSON format

**S3 Bucket**

-   The bucket name will be displayed after CDK deploy is complete:
    ```
    Outputs:
    anon-s3ol-storage.s3bucket = anon-s3ol-storage-storagebucketa1b2c3d4-a1b2c3d4e5f6
    ```
-   Alternatively, you can go to the console for [AWS CloudFormation](https://console.aws.amazon.com/cloudformation).
    -   Select "anon-s3ol-storage"
    -   Select the "Outputs" tab
    -   The S3 Bucket name will be listed in the outputs list with t he _s3bucket_ key

**CloudFront URL**

-   The public-facing URL will be displayed in your terminal after CDK deploy is complete:
    ```
    Outputs:
    anon-s3ol-cdn.cf-domain = **a1b2c3d4e5f6g7.cloudfront.net**
    ```
-   Alternatively, you can go to the console for [AWS CloudFormation](https://console.aws.amazon.com/cloudformation).
    -   Select "anon-s3ol-cdn"
    -   Select the "Outputs" tab
    -   The S3 Bucket name will be listed in the outputs list with the _cf-domain_ key

## Uninstall

CloudFront replicates Lambda@Edge functions at the edge. These Lambda functions can only be deleted when all of the replicas have been deleted.

Prior to destroying the stack, the Lambda@Edge function must be disassociated from the CloudFront distribution:

1. Sign into the AWS Management Console and open the [CloudFront console](https://us-east-1.console.aws.amazon.com/cloudfront).
2. Select the distribution created by this app. Its description will mention anonymous S3 Object Lambda access.
3. Select the **Behaviors** tab.
4. Select the default behavior and choose **Edit**.
5. Scroll to the **Function associations** section and for **Origin request**, select **No association.**
6. Select **Save changes.**

Replicas are typically deleted within a few hours.

To remove all stacks in this app, run the following in the project directory:

`cdk destroy --all`

If you did not disassociate the Lambda@Edge function from the CloudFront distribution prior to running this command, the delete will fail when attempting to delete the `lambda-edge` stack. However, the CloudFront distribution (`cdn` stack) will have been deleted at this point. Simply wait for the Lambda@Edge function replicates to be removed from edge locations (up to a few hours), then run the delete command again.

## References

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.