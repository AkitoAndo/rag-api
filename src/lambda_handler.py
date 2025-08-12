import json
import os
import time
import random
from typing import Dict, Any, Optional

import boto3
import xmltodict
from langchain_aws.chat_models import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv

from .s3_vectors_client import S3VectorsClient

# .envファイルを読み込み（ローカル開発時用）
load_dotenv()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda関数のメインハンドラー"""
    try:
        request = json.loads(event["body"])
        question = request["question"]

        vector_bucket_name = os.environ["VECTOR_BUCKET_NAME"]
        vector_index_name = os.environ["VECTOR_INDEX_NAME"]

        # S3 Vectorsクライアントを初期化
        s3_vectors = S3VectorsClient()

        # ベクトル検索を実行
        vectors = s3_vectors.query_vectors(
            vector_bucket_name=vector_bucket_name,
            index_name=vector_index_name,
            question=question,
            top_k=3,
        )

        # 検索結果をXML形式に変換
        xml_docs = xmltodict.unparse(
            {
                "documents": {
                    "document": [
                        {
                            "text": vector["metadata"]["text"],
                        }
                        for vector in vectors
                    ]
                }
            },
            full_document=False,
            pretty=True,
        )

        # ChatBedrockConverseを使用してRAG回答を生成
        bedrock_client = boto3.client(
            "bedrock-runtime", os.getenv("AWS_REGION", "us-east-1")
        )
        messages = [
            SystemMessage(
                (
                    "あなたはメイドインアビスと呼ばれる作品に関する質問に回答するチャットボットです。\n"
                    "参考となるドキュメントに記載されている内容に基づいて回答を生成してください"
                )
            ),
            HumanMessage((f"# 参考ドキュメント\n{xml_docs}\n# 質問\n{question}")),
        ]

        model = ChatBedrockConverse(
            client=bedrock_client,
            model=os.getenv(
                "CHAT_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"
            ),
        )
        
        # レート制限対応のリトライ機能
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = model.invoke(messages)
                break
            except Exception as e:
                if 'ThrottlingException' in str(e) or 'TooManyRequestsException' in str(e):
                    if attempt < max_retries - 1:
                        delay = (2 ** attempt) + random.uniform(0, 1)
                        time.sleep(delay)
                        continue
                raise e
        answer = response.content

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps({"answer": answer}, ensure_ascii=False),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps({"error": str(e)}, ensure_ascii=False),
        }


def add_document_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """ドキュメント追加用のLambda関数"""
    try:
        request = json.loads(event["body"])
        text = request["text"]
        title = request["title"]

        vector_bucket_name = os.environ["VECTOR_BUCKET_NAME"]
        vector_index_name = os.environ["VECTOR_INDEX_NAME"]

        # S3 Vectorsクライアントを初期化
        s3_vectors = S3VectorsClient()

        # ドキュメントを追加
        vector_count = s3_vectors.add_document(
            vector_bucket_name=vector_bucket_name,
            index_name=vector_index_name,
            text=text,
            title=title,
        )

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps(
                {
                    "message": f"Successfully added {vector_count} vectors",
                    "vector_count": vector_count,
                },
                ensure_ascii=False,
            ),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps({"error": str(e)}, ensure_ascii=False),
        }
