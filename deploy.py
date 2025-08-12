#!/usr/bin/env python3
"""
SAMテンプレートをCloudFormationでデプロイするスクリプト
"""
import os
import sys
import time
import zipfile
import boto3
from botocore.exceptions import ClientError
import tempfile

def create_deployment_package():
    """デプロイ用のZipファイルを作成"""
    print("Creating deployment package...")
    
    # 一時ファイルを作成
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    temp_file.close()
    
    with zipfile.ZipFile(temp_file.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # srcディレクトリの全ファイルを追加
        src_dir = 'src'
        for root, dirs, files in os.walk(src_dir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, src_dir)
                    zipf.write(file_path, arcname)
                    print(f"Added {file_path} as {arcname}")
    
    print(f"Deployment package created: {temp_file.name}")
    return temp_file.name

def upload_to_s3(zip_file_path, bucket_name, key):
    """デプロイパッケージをS3にアップロード"""
    s3 = boto3.client('s3', region_name='us-east-1')
    
    try:
        print(f"Uploading {zip_file_path} to s3://{bucket_name}/{key}")
        s3.upload_file(zip_file_path, bucket_name, key)
        return f"s3://{bucket_name}/{key}"
    except ClientError as e:
        print(f"Error uploading to S3: {e}")
        return None

def deploy_cloudformation_stack(template_file, stack_name, parameters=None):
    """CloudFormationスタックをデプロイ"""
    cf = boto3.client('cloudformation', region_name='us-east-1')
    
    # テンプレートを読み込み
    with open(template_file, 'r', encoding='utf-8') as f:
        template_body = f.read()
    
    # パラメータを準備
    cf_parameters = []
    if parameters:
        for key, value in parameters.items():
            cf_parameters.append({
                'ParameterKey': key,
                'ParameterValue': value
            })
    
    try:
        # スタックが存在するかチェック
        try:
            cf.describe_stacks(StackName=stack_name)
            stack_exists = True
        except ClientError as e:
            if 'does not exist' in str(e):
                stack_exists = False
            else:
                raise e
        
        # スタックの作成または更新
        if stack_exists:
            print(f"Updating existing stack: {stack_name}")
            operation = cf.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=cf_parameters,
                Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND']
            )
            operation_type = 'UPDATE'
        else:
            print(f"Creating new stack: {stack_name}")
            operation = cf.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=cf_parameters,
                Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND']
            )
            operation_type = 'CREATE'
        
        # デプロイの進行状況を監視
        print(f"Stack {operation_type} initiated. Monitoring progress...")
        waiter_name = 'stack_create_complete' if operation_type == 'CREATE' else 'stack_update_complete'
        waiter = cf.get_waiter(waiter_name)
        
        try:
            waiter.wait(
                StackName=stack_name,
                WaiterConfig={
                    'Delay': 10,
                    'MaxAttempts': 120  # 最大20分待機
                }
            )
            print(f"Stack {operation_type} completed successfully!")
            
            # スタックの出力を表示
            show_stack_outputs(cf, stack_name)
            return True
            
        except Exception as e:
            print(f"Stack {operation_type} failed or timed out: {e}")
            show_stack_events(cf, stack_name)
            return False
    
    except ClientError as e:
        print(f"Error during stack operation: {e}")
        return False

def show_stack_outputs(cf, stack_name):
    """スタックの出力を表示"""
    try:
        response = cf.describe_stacks(StackName=stack_name)
        stack = response['Stacks'][0]
        
        if 'Outputs' in stack:
            print("\n=== Stack Outputs ===")
            for output in stack['Outputs']:
                print(f"{output['OutputKey']}: {output['OutputValue']}")
                if 'Description' in output:
                    print(f"  Description: {output['Description']}")
        else:
            print("No outputs found for this stack.")
    except Exception as e:
        print(f"Error retrieving stack outputs: {e}")

def show_stack_events(cf, stack_name, max_events=20):
    """スタックイベントを表示"""
    try:
        response = cf.describe_stack_events(StackName=stack_name)
        events = response['StackEvents'][:max_events]
        
        print(f"\n=== Recent Stack Events (last {len(events)}) ===")
        for event in events:
            timestamp = event['Timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            logical_id = event['LogicalResourceId']
            status = event['ResourceStatus']
            reason = event.get('ResourceStatusReason', '')
            
            print(f"{timestamp} | {logical_id} | {status}")
            if reason:
                print(f"  Reason: {reason}")
    except Exception as e:
        print(f"Error retrieving stack events: {e}")

def main():
    """メイン関数"""
    stack_name = "rag-api-stack"
    template_file = "template.yaml"
    
    # 環境変数をチェック
    required_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION']
    for var in required_vars:
        if not os.getenv(var):
            print(f"Error: Environment variable {var} is not set")
            return False
    
    print("=== RAG API Cognito Authentication Update ===")
    print(f"Stack Name: {stack_name}")
    print(f"Template: {template_file}")
    print(f"Region: {os.getenv('AWS_REGION')}")
    
    # テンプレートファイルの存在をチェック
    if not os.path.exists(template_file):
        print(f"Error: Template file {template_file} not found")
        return False
    
    # パラメータを設定
    parameters = {
        'VectorBucketName': '20250811-rag',
        'VectorIndexName': '20250811-rag-vector-index'
    }
    
    print(f"Parameters: {parameters}")
    
    # CloudFormationでデプロイ
    success = deploy_cloudformation_stack(template_file, stack_name, parameters)
    
    if success:
        print("\nDeployment completed successfully!")
        return True
    else:
        print("\nDeployment failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)