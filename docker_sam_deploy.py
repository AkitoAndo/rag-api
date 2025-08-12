#!/usr/bin/env python3
"""
Docker経由でSAM CLIを使用してデプロイするスクリプト
"""
import os
import sys
import subprocess

def run_docker_sam_command(command, description):
    """DockerでSAM CLIコマンドを実行"""
    print(f"\n=== {description} ===")
    
    # Dockerコマンドを構築
    aws_region = os.getenv('AWS_REGION', 'us-east-1')
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    
    docker_cmd = f"""docker run --rm -v "%cd%":/sam-app -w /sam-app -e AWS_DEFAULT_REGION={aws_region} -e AWS_ACCESS_KEY_ID={aws_access_key_id} -e AWS_SECRET_ACCESS_KEY={aws_secret_access_key} public.ecr.aws/sam/build-python3.11:latest {command}"""
    
    print(f"Running: {docker_cmd}")
    
    try:
        result = subprocess.run(docker_cmd, shell=True, check=True, capture_output=True, text=True)
        print("✅ Success!")
        if result.stdout:
            print("STDOUT:", result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print("❌ Failed!")
        print("STDERR:", e.stderr)
        if e.stdout:
            print("STDOUT:", e.stdout)
        return False

def main():
    """メイン関数"""
    # 環境変数をチェック
    required_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION']
    for var in required_vars:
        if not os.getenv(var):
            print(f"Error: Environment variable {var} is not set")
            return False
    
    print("=== Docker SAM Deployment for Cognito Authentication ===")
    
    # SAM buildを実行
    if not run_docker_sam_command("sam build", "Building SAM application"):
        return False
    
    # SAM deployを実行
    deploy_cmd = """sam deploy --stack-name rag-api-stack --capabilities CAPABILITY_IAM --parameter-overrides "VectorBucketName=20250811-rag VectorIndexName=20250811-rag-vector-index" --resolve-s3 --no-confirm-changeset"""
    
    if not run_docker_sam_command(deploy_cmd, "Deploying SAM application"):
        return False
    
    print("\n🎉 Deployment completed successfully!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)