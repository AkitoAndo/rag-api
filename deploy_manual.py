#!/usr/bin/env python3
"""
簡略化されたデプロイスクリプト - SAMテンプレートを通常のCloudFormationテンプレートに変換
"""
import json
import boto3
import sys
import os

def create_simple_template():
    """SAMテンプレートをシンプルなCloudFormationテンプレートに変換"""
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "RAG API Multi-tenant system",
        "Parameters": {
            "VectorBucketName": {
                "Type": "String",
                "Description": "S3 Vectors bucket name",
                "Default": "20250811-rag"
            },
            "VectorIndexName": {
                "Type": "String",
                "Description": "S3 Vectors index name",
                "Default": "20250811-rag-vector-index"
            }
        },
        "Resources": {
            "RagApiGateway": {
                "Type": "AWS::ApiGateway::RestApi",
                "Properties": {
                    "Name": "rag-api-multi-tenant",
                    "Description": "RAG System API Gateway",
                    "EndpointConfiguration": {
                        "Types": ["REGIONAL"]
                    }
                }
            },
            "ApiGatewayDeployment": {
                "Type": "AWS::ApiGateway::Deployment",
                "DependsOn": ["QueryMethod", "UserQueryMethod"],
                "Properties": {
                    "RestApiId": {"Ref": "RagApiGateway"},
                    "StageName": "Prod"
                }
            },
            "QueryResource": {
                "Type": "AWS::ApiGateway::Resource",
                "Properties": {
                    "RestApiId": {"Ref": "RagApiGateway"},
                    "ParentId": {"Fn::GetAtt": ["RagApiGateway", "RootResourceId"]},
                    "PathPart": "query"
                }
            },
            "QueryMethod": {
                "Type": "AWS::ApiGateway::Method",
                "Properties": {
                    "RestApiId": {"Ref": "RagApiGateway"},
                    "ResourceId": {"Ref": "QueryResource"},
                    "HttpMethod": "POST",
                    "AuthorizationType": "NONE",
                    "Integration": {
                        "Type": "AWS_PROXY",
                        "IntegrationHttpMethod": "POST",
                        "Uri": {"Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${RAGQueryFunction.Arn}/invocations"}
                    }
                }
            },
            "UsersResource": {
                "Type": "AWS::ApiGateway::Resource",
                "Properties": {
                    "RestApiId": {"Ref": "RagApiGateway"},
                    "ParentId": {"Fn::GetAtt": ["RagApiGateway", "RootResourceId"]},
                    "PathPart": "users"
                }
            },
            "UserIdResource": {
                "Type": "AWS::ApiGateway::Resource",
                "Properties": {
                    "RestApiId": {"Ref": "RagApiGateway"},
                    "ParentId": {"Ref": "UsersResource"},
                    "PathPart": "{user_id}"
                }
            },
            "UserQueryResource": {
                "Type": "AWS::ApiGateway::Resource",
                "Properties": {
                    "RestApiId": {"Ref": "RagApiGateway"},
                    "ParentId": {"Ref": "UserIdResource"},
                    "PathPart": "query"
                }
            },
            "UserQueryMethod": {
                "Type": "AWS::ApiGateway::Method",
                "Properties": {
                    "RestApiId": {"Ref": "RagApiGateway"},
                    "ResourceId": {"Ref": "UserQueryResource"},
                    "HttpMethod": "POST",
                    "AuthorizationType": "NONE",
                    "Integration": {
                        "Type": "AWS_PROXY",
                        "IntegrationHttpMethod": "POST",
                        "Uri": {"Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${UserQueryFunction.Arn}/invocations"}
                    }
                }
            },
            "LambdaRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {
                                    "Service": "lambda.amazonaws.com"
                                },
                                "Action": "sts:AssumeRole"
                            }
                        ]
                    },
                    "ManagedPolicyArns": [
                        "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
                    ],
                    "Policies": [
                        {
                            "PolicyName": "RAGApiPermissions",
                            "PolicyDocument": {
                                "Version": "2012-10-17",
                                "Statement": [
                                    {
                                        "Effect": "Allow",
                                        "Action": [
                                            "bedrock:InvokeModel",
                                            "s3vectors:GetVectors",
                                            "s3vectors:QueryVectors",
                                            "s3vectors:PutVectors",
                                            "s3vectors:DeleteVectors",
                                            "s3vectors:ListDocuments"
                                        ],
                                        "Resource": "*"
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        },
        "Outputs": {
            "ApiBaseUrl": {
                "Description": "API Gateway base URL",
                "Value": {"Fn::Sub": "https://${RagApiGateway}.execute-api.${AWS::Region}.amazonaws.com/Prod"}
            },
            "UserQueryEndpoint": {
                "Description": "User Query endpoint URL template",
                "Value": {"Fn::Sub": "https://${RagApiGateway}.execute-api.${AWS::Region}.amazonaws.com/Prod/users/{user_id}/query"}
            }
        }
    }

def deploy_stack():
    """CloudFormationスタックをデプロイ"""
    # 環境変数をチェック
    required_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION']
    for var in required_vars:
        if not os.getenv(var):
            print(f"Error: Environment variable {var} is not set")
            return False
    
    cf = boto3.client('cloudformation', region_name='us-east-1')
    stack_name = "rag-api-basic"
    
    template = create_simple_template()
    
    try:
        print("Creating basic API Gateway stack...")
        cf.create_stack(
            StackName=stack_name,
            TemplateBody=json.dumps(template),
            Parameters=[
                {'ParameterKey': 'VectorBucketName', 'ParameterValue': '20250811-rag'},
                {'ParameterKey': 'VectorIndexName', 'ParameterValue': '20250811-rag-vector-index'}
            ],
            Capabilities=['CAPABILITY_IAM']
        )
        
        # Wait for completion
        waiter = cf.get_waiter('stack_create_complete')
        print("Waiting for stack creation to complete...")
        waiter.wait(StackName=stack_name, WaiterConfig={'Delay': 10, 'MaxAttempts': 60})
        
        # Get outputs
        response = cf.describe_stacks(StackName=stack_name)
        stack = response['Stacks'][0]
        
        print("\n=== Deployment Successful! ===")
        if 'Outputs' in stack:
            for output in stack['Outputs']:
                print(f"{output['OutputKey']}: {output['OutputValue']}")
        
        return True
        
    except Exception as e:
        print(f"Deployment failed: {e}")
        return False

if __name__ == "__main__":
    success = deploy_stack()
    sys.exit(0 if success else 1)