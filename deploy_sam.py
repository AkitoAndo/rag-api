#!/usr/bin/env python3
"""
SAM CLIを使用してデプロイするスクリプト
"""
import os
import sys
import subprocess

def run_command(command, description):
    """コマンドを実行して結果を表示"""
    print(f"\n=== {description} ===")
    print(f"Running: {command}")
    
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
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
    
    print("=== SAM Deployment for Cognito Authentication ===")
    
    # SAM buildを実行
    if not run_command("sam build", "Building SAM application"):
        return False
    
    # SAM deployを実行
    deploy_cmd = """sam deploy --stack-name rag-api-stack --capabilities CAPABILITY_IAM --parameter-overrides "VectorBucketName=20250811-rag VectorIndexName=20250811-rag-vector-index" --resolve-s3 --confirm-changeset"""
    
    if not run_command(deploy_cmd, "Deploying SAM application"):
        return False
    
    print("\n🎉 Deployment completed successfully!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)