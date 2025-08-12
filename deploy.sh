#!/bin/bash

# S3 Vectors RAGシステムのデプロイスクリプト

set -e

# 設定値
STACK_NAME="s3-vectors-rag-api"
REGION="us-east-1"
S3_BUCKET="sam-deployment-bucket-$(date +%s)"
VECTOR_BUCKET_NAME="20250811-rag"
VECTOR_INDEX_NAME="20250811-rag-vector-index"

echo "=== S3 Vectors RAG API デプロイスクリプト ==="

# SAMがインストールされているかチェック
if ! command -v sam &> /dev/null; then
    echo "エラー: AWS SAM CLIがインストールされていません"
    echo "インストール方法: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html"
    exit 1
fi

# AWS CLIがインストールされているかチェック  
if ! command -v aws &> /dev/null; then
    echo "エラー: AWS CLIがインストールされていません"
    exit 1
fi

# デプロイ用のS3バケットを作成（既に存在する場合はスキップ）
echo "デプロイ用S3バケットを作成中..."
aws s3 mb s3://$S3_BUCKET --region $REGION 2>/dev/null || echo "S3バケット $S3_BUCKET は既に存在します"

# SAMアプリケーションをビルド
echo "SAMアプリケーションをビルド中..."
sam build

# SAMアプリケーションをデプロイ
echo "SAMアプリケーションをデプロイ中..."
sam deploy \
    --stack-name $STACK_NAME \
    --s3-bucket $S3_BUCKET \
    --region $REGION \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
        VectorBucketName=$VECTOR_BUCKET_NAME \
        VectorIndexName=$VECTOR_INDEX_NAME \
    --no-confirm-changeset

echo "=== デプロイ完了 ==="
echo ""

# API Gateway エンドポイント情報を取得・表示
echo "🌐 API Gateway エンドポイント情報:"
BASE_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].Outputs[?OutputKey==`RAGApiBaseUrl`].OutputValue' --output text)
QUERY_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].Outputs[?OutputKey==`RAGQueryEndpoint`].OutputValue' --output text)
ADD_DOC_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].Outputs[?OutputKey==`AddDocumentEndpoint`].OutputValue' --output text)

echo "📍 Base URL: $BASE_URL"
echo "🔍 Query Endpoint: $QUERY_URL"
echo "📝 Add Document Endpoint: $ADD_DOC_URL"
echo ""

echo "🚀 テスト方法:"
echo "1. Python スクリプトでテスト:"
echo "   python tools/test_api_gateway.py --base-url $BASE_URL"
echo ""
echo "2. cURL でテスト:"
echo "   # ドキュメント追加"
echo "   curl -X POST \"$ADD_DOC_URL\" \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"title\": \"テスト\", \"text\": \"これはテストです\"}'"
echo ""
echo "   # 質問応答"
echo "   curl -X POST \"$QUERY_URL\" \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"question\": \"テストについて教えて\"}'"
echo ""

echo "⚠️  次のステップ:"
echo "1. S3 Vectorsバケットとインデックスが作成済みか確認"
echo "2. Bedrockモデルアクセス権限を確認"
echo "3. 上記のテストコマンドでAPIを確認"