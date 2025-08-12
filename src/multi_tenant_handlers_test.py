"""
マルチテナント対応のLambdaハンドラー関数（テスト用）
"""
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

from s3_vectors_client import S3VectorsClient

# .envファイルを読み込み（ローカル開発時用）
load_dotenv()


def extract_user_id_from_path(event: Dict[str, Any]) -> str:
    """パスパラメータからユーザーIDを安全に抽出"""
    path_params = event.get("pathParameters", {})
    if not path_params:
        raise ValueError("Path parameters are missing")
    
    user_id = path_params.get("user_id")
    if not user_id:
        raise ValueError("User ID is required")
    
    return user_id.strip()


def extract_request_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """リクエストボディを安全に抽出・パース"""
    body = event.get("body", "")
    if not body:
        raise ValueError("Request body is empty")
    
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON format")


def create_cors_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """CORS対応のレスポンスを作成"""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
        },
        "body": json.dumps(body, ensure_ascii=False)
    }


def create_personalized_system_prompt(user_preferences: Optional[Dict[str, Any]] = None) -> str:
    """ユーザー設定に基づく個人化されたシステムプロンプト"""
    base_prompt = "あなたは親切で知識豊富な個人アシスタントです。"
    
    if user_preferences:
        persona = user_preferences.get("chatbot_persona")
        if persona:
            base_prompt = persona
    
    return f"{base_prompt}\n参考となるドキュメントに記載されている内容に基づいて回答を生成してください。"


def invoke_bedrock_with_retry(model, messages: list, max_retries: int = 3) -> str:
    """Bedrock呼び出しをリトライ機能付きで実行"""
    for attempt in range(max_retries):
        try:
            response = model.invoke(messages)
            return response.content
        except Exception as e:
            if 'ThrottlingException' in str(e) or 'TooManyRequestsException' in str(e):
                if attempt < max_retries - 1:
                    delay = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(delay)
                    continue
            raise e
    
    raise Exception("Max retries exceeded")


def user_query_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """ユーザー固有の質問応答ハンドラー"""
    try:
        # パスパラメータからユーザーIDを抽出
        user_id = extract_user_id_from_path(event)
        
        # リクエストボディをパース
        request = extract_request_body(event)
        question = request.get("question", "").strip()
        if not question:
            raise ValueError("Question cannot be empty")
        
        # ユーザー設定を取得
        preferences = request.get("preferences", {})
        max_results = preferences.get("max_results", 3)
        temperature = preferences.get("temperature", 0.7)
        
        # 環境変数を取得
        vector_bucket_name = os.environ["VECTOR_BUCKET_NAME"]
        
        # S3 Vectorsクライアントを初期化
        s3_vectors = S3VectorsClient()
        
        # ユーザー固有の検索を実行
        vectors = s3_vectors.query_user_documents(
            user_id=user_id,
            vector_bucket_name=vector_bucket_name,
            question=question,
            top_k=max_results
        )
        
        # 検索結果をソース情報として構造化
        sources = []
        for vector in vectors:
            metadata = vector.get("metadata", {})
            sources.append({
                "document_id": metadata.get("document_id", "unknown"),
                "title": metadata.get("title", "Untitled"),
                "relevance_score": 1.0 - vector.get("distance", 0.0),  # 距離を関連度に変換
                "snippet": metadata.get("text", "")[:200] + "..." if len(metadata.get("text", "")) > 200 else metadata.get("text", "")
            })
        
        # XML形式でコンテキストを構造化
        xml_docs = ""
        if vectors:
            xml_docs = xmltodict.unparse(
                {
                    "documents": {
                        "document": [
                            {
                                "title": vector["metadata"].get("title", ""),
                                "text": vector["metadata"]["text"],
                            }
                            for vector in vectors
                        ]
                    }
                },
                full_document=False,
                pretty=True,
            )
        
        # LLMで回答を生成
        bedrock_client = boto3.client(
            "bedrock-runtime", os.getenv("AWS_REGION", "us-east-1")
        )
        
        system_prompt = create_personalized_system_prompt(preferences)
        messages = [
            SystemMessage(system_prompt),
            HumanMessage(f"# 参考ドキュメント\n{xml_docs}\n# 質問\n{question}")
        ]
        
        model = ChatBedrockConverse(
            client=bedrock_client,
            model=os.getenv("CHAT_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
            temperature=temperature
        )
        
        answer = invoke_bedrock_with_retry(model, messages)
        
        # レスポンスを構築
        response_body = {
            "answer": answer,
            "sources": sources,
            "user_context": {
                "user_id": user_id,
                "preferences_applied": bool(preferences)
            },
            "confidence": min(1.0, len(sources) / max_results) if max_results > 0 else 0.0
        }
        
        return create_cors_response(200, response_body)
        
    except ValueError as e:
        return create_cors_response(400, {"error": str(e)})
    except Exception as e:
        print(f"Error in user_query_handler: {str(e)}")
        return create_cors_response(500, {"error": "Internal server error"})


def user_add_document_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """ユーザー固有のドキュメント追加ハンドラー"""
    try:
        # パスパラメータからユーザーIDを抽出
        user_id = extract_user_id_from_path(event)
        
        # リクエストボディをパース
        request = extract_request_body(event)
        text = request.get("text", "").strip()
        title = request.get("title", "").strip()
        
        if not text:
            raise ValueError("Document text cannot be empty")
        if not title:
            raise ValueError("Document title cannot be empty")
        
        # 環境変数を取得
        vector_bucket_name = os.environ["VECTOR_BUCKET_NAME"]
        
        # S3 Vectorsクライアントを初期化
        s3_vectors = S3VectorsClient()
        
        # ユーザー固有のドキュメントを追加
        vector_count = s3_vectors.add_user_document(
            user_id=user_id,
            vector_bucket_name=vector_bucket_name,
            text=text,
            title=title,
            **{k: v for k, v in request.items() if k not in ['text', 'title']}  # 追加メタデータ
        )
        
        response_body = {
            "message": f"Successfully added {vector_count} vectors to user knowledge base",
            "vector_count": vector_count,
            "user_id": user_id,
            "document_title": title
        }
        
        return create_cors_response(200, response_body)
        
    except ValueError as e:
        return create_cors_response(400, {"error": str(e)})
    except Exception as e:
        print(f"Error in user_add_document_handler: {str(e)}")
        return create_cors_response(500, {"error": "Internal server error"})


def user_document_list_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """ユーザーのドキュメント一覧取得ハンドラー"""
    try:
        # パスパラメータからユーザーIDを抽出
        user_id = extract_user_id_from_path(event)
        
        # クエリパラメータを取得
        query_params = event.get("queryStringParameters", {}) or {}
        limit = min(int(query_params.get("limit", 20)), 100)  # 最大100件
        offset = max(int(query_params.get("offset", 0)), 0)
        
        # 環境変数を取得
        vector_bucket_name = os.environ["VECTOR_BUCKET_NAME"]
        
        # S3 Vectorsクライアントを初期化
        s3_vectors = S3VectorsClient()
        
        # ユーザーのドキュメント一覧を取得
        documents = s3_vectors.list_user_documents(
            user_id=user_id,
            vector_bucket_name=vector_bucket_name,
            limit=limit,
            offset=offset
        )
        
        response_body = {
            "documents": documents,
            "total": len(documents),  # 実際の実装では合計数を別途取得
            "limit": limit,
            "offset": offset,
            "user_id": user_id
        }
        
        return create_cors_response(200, response_body)
        
    except ValueError as e:
        return create_cors_response(400, {"error": str(e)})
    except Exception as e:
        print(f"Error in user_document_list_handler: {str(e)}")
        return create_cors_response(500, {"error": "Internal server error"})


def user_document_delete_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """ユーザーのドキュメント削除ハンドラー"""
    try:
        # パスパラメータからユーザーIDとドキュメントIDを抽出
        user_id = extract_user_id_from_path(event)
        
        path_params = event.get("pathParameters", {})
        document_id = path_params.get("document_id")
        if not document_id:
            raise ValueError("Document ID is required")
        
        # 環境変数を取得
        vector_bucket_name = os.environ["VECTOR_BUCKET_NAME"]
        
        # S3 Vectorsクライアントを初期化
        s3_vectors = S3VectorsClient()
        
        # ドキュメントを削除
        success = s3_vectors.delete_user_document(
            user_id=user_id,
            vector_bucket_name=vector_bucket_name,
            document_id=document_id
        )
        
        if success:
            response_body = {
                "message": "Document deleted successfully",
                "document_id": document_id,
                "user_id": user_id
            }
            return create_cors_response(200, response_body)
        else:
            return create_cors_response(404, {"error": "Document not found or could not be deleted"})
        
    except ValueError as e:
        return create_cors_response(400, {"error": str(e)})
    except Exception as e:
        print(f"Error in user_document_delete_handler: {str(e)}")
        return create_cors_response(500, {"error": "Internal server error"})


def options_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """CORS プリフライトリクエスト用のハンドラー"""
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
        },
        "body": ""
    }