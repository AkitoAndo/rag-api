"""
マルチテナント対応のLambdaハンドラー関数
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
from user_quota_manager import UserQuotaManager, estimate_vector_count, get_document_size_mb

# .envファイルを読み込み（ローカル開発時用）
load_dotenv()


def extract_user_id_from_cognito(event: Dict[str, Any]) -> str:
    """CognitoのJWTトークンからユーザーIDを抽出"""
    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {})
    
    # Cognito認証の場合、claimsにユーザー情報が含まれる
    claims = authorizer.get("claims", {})
    
    # CognitoのsubがユニークなユーザーID
    user_id = claims.get("sub")
    if not user_id:
        # フォールバック: usernameまたはemailを使用
        user_id = claims.get("cognito:username") or claims.get("email")
    
    if not user_id:
        raise ValueError("User ID not found in JWT token")
    
    return user_id.strip()


def extract_user_id_from_path(event: Dict[str, Any]) -> str:
    """パスパラメータからユーザーIDを安全に抽出（レガシー）"""
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
        user_id = extract_user_id_from_cognito(event)
        
        # クォータチェック
        quota_manager = UserQuotaManager()
        can_query, quota_message = quota_manager.check_quota_before_query(user_id)
        if not can_query:
            return create_cors_response(429, {  # Too Many Requests
                "error": f"Query limit exceeded: {quota_message}",
                "quota_status": quota_manager.get_quota_status(user_id)
            })
        
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
        
        # クエリ実行後の使用量更新
        quota_manager.update_usage_after_query(user_id)
        
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
        user_id = extract_user_id_from_cognito(event)
        
        # リクエストボディをパース
        request = extract_request_body(event)
        text = request.get("text", "").strip()
        title = request.get("title", "").strip()
        
        if not text:
            raise ValueError("Document text cannot be empty")
        if not title:
            raise ValueError("Document title cannot be empty")
        
        # クォータチェック
        quota_manager = UserQuotaManager()
        estimated_vectors = estimate_vector_count(text)
        can_upload, quota_message = quota_manager.check_quota_before_upload(user_id, text, estimated_vectors)
        if not can_upload:
            return create_cors_response(429, {  # Too Many Requests
                "error": f"Upload limit exceeded: {quota_message}",
                "quota_status": quota_manager.get_quota_status(user_id),
                "estimated_vectors": estimated_vectors,
                "document_size_mb": get_document_size_mb(text)
            })
        
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
        
        # ドキュメント追加後の使用量更新
        document_size_mb = get_document_size_mb(text)
        quota_manager.update_usage_after_upload(user_id, vector_count, document_size_mb)
        
        response_body = {
            "message": f"Successfully added {vector_count} vectors to user knowledge base",
            "vector_count": vector_count,
            "user_id": user_id,
            "document_title": title,
            "quota_status": quota_manager.get_quota_status(user_id)
        }
        
        return create_cors_response(200, response_body)
        
    except ValueError as e:
        return create_cors_response(400, {"error": str(e)})
    except Exception as e:
        print(f"Error in user_add_document_handler: {str(e)}")
        return create_cors_response(500, {"error": "Internal server error"})


def user_document_list_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """ユーザーのドキュメント一覧取得ハンドラー（フロントエンド要求対応版）"""
    try:
        # パスパラメータからユーザーIDを抽出
        user_id = extract_user_id_from_cognito(event)
        
        # クエリパラメータを取得（フロントエンド仕様に準拠）
        query_params = event.get("queryStringParameters", {}) or {}
        limit = min(int(query_params.get("limit", 20)), 100)  # 最大100件
        offset = max(int(query_params.get("offset", 0)), 0)
        search = query_params.get("search", "").strip()
        sort_by = query_params.get("sort_by", "created_at")
        sort_order = query_params.get("sort_order", "desc")
        
        # バリデーション
        valid_sort_fields = ["created_at", "title", "vector_count", "content_length"]
        if sort_by not in valid_sort_fields:
            raise ValueError(f"Invalid sort_by field. Must be one of: {', '.join(valid_sort_fields)}")
        
        valid_sort_orders = ["asc", "desc"]
        if sort_order not in valid_sort_orders:
            raise ValueError(f"Invalid sort_order. Must be one of: {', '.join(valid_sort_orders)}")
        
        # 環境変数を取得
        vector_bucket_name = os.environ["VECTOR_BUCKET_NAME"]
        
        # S3 Vectorsクライアントを初期化
        s3_vectors = S3VectorsClient()
        
        # ユーザーのドキュメント一覧を取得（拡張パラメータ付き）
        documents = s3_vectors.list_user_documents_extended(
            user_id=user_id,
            vector_bucket_name=vector_bucket_name,
            limit=limit,
            offset=offset,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # 総数を取得（has_more判定用）
        total_count = s3_vectors.get_user_documents_count(user_id, vector_bucket_name, search)
        has_more = (offset + len(documents)) < total_count
        
        # フロントエンド仕様に準拠したレスポンス形式
        response_body = {
            "documents": [
                {
                    "document_id": doc.get("document_id", doc.get("id")),
                    "title": doc.get("title", "Untitled"),
                    "filename": doc.get("filename", "unknown"),
                    "created_at": doc.get("created_at", doc.get("timestamp")),
                    "vector_count": doc.get("vector_count", 0),
                    "content_length": doc.get("content_length", len(doc.get("text", "")))
                }
                for doc in documents
            ],
            "total": total_count,
            "has_more": has_more
        }
        
        return create_cors_response(200, response_body)
        
    except ValueError as e:
        return create_cors_response(400, {"error": str(e)})
    except Exception as e:
        print(f"Error in user_document_list_handler: {str(e)}")
        return create_cors_response(500, {"error": "Internal server error"})


def user_document_delete_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """ユーザーのドキュメント削除ハンドラー（フロントエンド要求対応版）"""
    try:
        # パスパラメータからユーザーIDとドキュメントIDを抽出
        user_id = extract_user_id_from_cognito(event)
        
        path_params = event.get("pathParameters", {})
        document_id = path_params.get("document_id")
        if not document_id:
            raise ValueError("Document ID is required")
        
        # 環境変数を取得
        vector_bucket_name = os.environ["VECTOR_BUCKET_NAME"]
        
        # S3 Vectorsクライアントを初期化
        s3_vectors = S3VectorsClient()
        
        # 削除前にベクトル数を取得
        try:
            document_info = s3_vectors.get_document_info(user_id, vector_bucket_name, document_id)
            vector_count = document_info.get("vector_count", 0) if document_info else 0
        except Exception:
            vector_count = 0  # 情報取得に失敗した場合
        
        # ドキュメントを削除
        success = s3_vectors.delete_user_document_with_count(
            user_id=user_id,
            vector_bucket_name=vector_bucket_name,
            document_id=document_id
        )
        
        if success:
            # フロントエンド仕様に準拠したレスポンス
            response_body = {
                "message": "文書が正常に削除されました",
                "deleted_vectors": vector_count
            }
            return create_cors_response(200, response_body)
        else:
            return create_cors_response(404, {
                "error": "文書が見つからないか、削除できませんでした",
                "code": "DOCUMENT_NOT_FOUND"
            })
        
    except ValueError as e:
        return create_cors_response(400, {
            "error": str(e),
            "code": "INVALID_REQUEST"
        })
    except Exception as e:
        print(f"Error in user_document_delete_handler: {str(e)}")
        return create_cors_response(500, {
            "error": "サーバー内部エラーが発生しました",
            "code": "INTERNAL_SERVER_ERROR"
        })


def user_quota_status_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """ユーザーのクォータ状況を取得（画像関連含む拡張版）"""
    try:
        # CognitoからユーザーIDを抽出
        user_id = extract_user_id_from_cognito(event)
        
        # クォータマネージャーで拡張ステータスを取得
        quota_manager = UserQuotaManager()
        quota_status = quota_manager.get_extended_quota_status(user_id)
        
        # フロントエンド仕様に合わせてレスポンス形式を調整
        formatted_response = {
            "user_id": quota_status["user_id"],
            "documents": {
                "count": quota_status["quotas"]["documents"]["current"],
                "limit": quota_status["quotas"]["documents"]["max"],
                "usage_percentage": quota_status["quotas"]["documents"]["percentage"]
            },
            "images": {
                "count": quota_status["quotas"]["images"]["count"],
                "limit": quota_status["quotas"]["images"]["limit"],
                "usage_percentage": quota_status["quotas"]["images"]["usage_percentage"]
            },
            "storage": {
                "used_mb": quota_status["quotas"]["storage"]["current_mb"],
                "limit_mb": quota_status["quotas"]["storage"]["max_mb"],
                "usage_percentage": quota_status["quotas"]["storage"]["percentage"]
            },
            "api_calls": {
                "this_month": quota_status["quotas"]["monthly_queries"]["current"],
                "limit": quota_status["quotas"]["monthly_queries"]["max"],
                "usage_percentage": quota_status["quotas"]["monthly_queries"]["percentage"]
            },
            "vectors": {
                "count": quota_status["quotas"]["vectors"]["current"],
                "limit": quota_status["quotas"]["vectors"]["max"],
                "usage_percentage": quota_status["quotas"]["vectors"]["percentage"]
            }
        }
        
        return create_cors_response(200, formatted_response)
        
    except ValueError as e:
        return create_cors_response(400, {"error": str(e)})
    except Exception as e:
        return create_cors_response(500, {"error": str(e)})


def user_plan_update_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """ユーザーのプラン変更"""
    try:
        # CognitoからユーザーIDを抽出
        user_id = extract_user_id_from_cognito(event)
        
        # リクエストボディをパース
        request = extract_request_body(event)
        plan_type = request.get("plan_type", "").strip().lower()
        
        if plan_type not in ["free", "basic", "premium"]:
            raise ValueError("Invalid plan type. Must be 'free', 'basic', or 'premium'")
        
        # プラン変更を実行
        quota_manager = UserQuotaManager()
        success = quota_manager.set_user_plan(user_id, plan_type)
        
        if success:
            quota_status = quota_manager.get_quota_status(user_id)
            return create_cors_response(200, {
                "message": f"Plan successfully updated to {plan_type}",
                "quota_status": quota_status
            })
        else:
            return create_cors_response(500, {"error": "Failed to update plan"})
        
    except ValueError as e:
        return create_cors_response(400, {"error": str(e)})
    except Exception as e:
        return create_cors_response(500, {"error": str(e)})


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