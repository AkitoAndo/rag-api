"""
画像管理用Lambdaハンドラー関数群
"""
import json
import base64
import uuid
from typing import Dict, Any
from datetime import datetime

from PIL import Image
import io
from dotenv import load_dotenv

from multi_tenant_handlers import (
    extract_user_id_from_cognito,
    create_cors_response
)
from image_storage_client import ImageStorageClient
from ocr_vision_processor import OCRVisionProcessor
from image_knowledge_manager import ImageKnowledgeManager
from user_quota_manager import UserQuotaManager

# .envファイルを読み込み（ローカル開発時用）
load_dotenv()


def validate_image_file(file_content: bytes, filename: str) -> tuple[bool, str]:
    """画像ファイルの検証"""
    # サイズチェック（10MB制限）
    max_size = 10 * 1024 * 1024  # 10MB
    if len(file_content) > max_size:
        return False, "ファイルサイズは10MB以下にしてください"
    
    # 形式チェック
    try:
        image = Image.open(io.BytesIO(file_content))
        format_lower = image.format.lower() if image.format else ""
        
        allowed_formats = ['jpeg', 'jpg', 'png', 'gif', 'webp']
        if format_lower not in allowed_formats:
            return False, "JPEG、PNG、GIF、WebP形式のみ対応しています"
        
        return True, "OK"
        
    except Exception as e:
        return False, f"無効な画像ファイルです: {str(e)}"


def parse_multipart_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """マルチパートデータのパース"""
    try:
        # API Gateway経由の場合
        body = event.get("body", "")
        if event.get("isBase64Encoded", False):
            body = base64.b64decode(body)
        
        # 簡易的なマルチパートパーサー（実際の実装では専用ライブラリを使用推奨）
        content_type = event.get("headers", {}).get("content-type", "")
        
        if "multipart/form-data" not in content_type:
            raise ValueError("multipart/form-data形式である必要があります")
        
        # boundary抽出
        boundary = None
        for part in content_type.split(";"):
            if "boundary=" in part:
                boundary = part.split("boundary=")[1].strip()
                break
        
        if not boundary:
            raise ValueError("multipart boundary が見つかりません")
        
        # 実際の実装では、python-multipartなどのライブラリを使用
        # ここでは簡易版として基本的な解析のみ実装
        
        return {
            "image": body,  # 画像データ
            "title": "テスト画像",  # 実際はフォームから抽出
            "description": "",
            "tags": [],
            "extract_text": True,
            "create_knowledge": True
        }
        
    except Exception as e:
        raise ValueError(f"マルチパートデータの解析に失敗: {str(e)}")


def image_upload_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """画像アップロードハンドラー"""
    try:
        # ユーザーIDを抽出
        user_id = extract_user_id_from_cognito(event)
        
        # クォータチェック
        quota_manager = UserQuotaManager()
        can_upload, quota_message = quota_manager.check_image_quota_before_upload(user_id)
        if not can_upload:
            return create_cors_response(400, {
                "error": f"画像アップロード制限に達しています: {quota_message}",
                "code": "IMAGE_QUOTA_EXCEEDED"
            })
        
        # マルチパートデータをパース
        form_data = parse_multipart_data(event)
        image_data = form_data["image"]
        title = form_data["title"].strip()
        description = form_data.get("description", "").strip()
        tags = form_data.get("tags", [])
        extract_text = form_data.get("extract_text", True)
        create_knowledge = form_data.get("create_knowledge", True)
        
        if not title:
            raise ValueError("画像タイトルは必須です")
        
        # 画像ファイル検証
        is_valid, validation_message = validate_image_file(image_data, title)
        if not is_valid:
            return create_cors_response(400, {
                "error": validation_message,
                "code": "INVALID_FILE_FORMAT" if "形式" in validation_message else "FILE_SIZE_EXCEEDED"
            })
        
        # 画像ID生成
        image_id = f"img_{uuid.uuid4().hex[:12]}"
        
        # 画像ストレージクライアント初期化
        storage_client = ImageStorageClient()
        
        # S3に画像保存
        image_url, thumbnail_url = storage_client.save_image(
            user_id=user_id,
            image_id=image_id,
            image_data=image_data,
            filename=f"{title}.jpg"  # 統一形式で保存
        )
        
        # OCR・Vision分析実行
        analysis_results = {}
        ocr_text = ""
        
        if extract_text:
            ocr_processor = OCRVisionProcessor()
            
            # OCR実行
            ocr_result = ocr_processor.extract_text_from_image(image_data)
            ocr_text = ocr_result.get("text", "")
            
            # Vision分析実行
            vision_result = ocr_processor.analyze_image_content(image_data)
            
            analysis_results = {
                "vision_description": vision_result.get("description", ""),
                "confidence": vision_result.get("confidence", 0.0)
            }
        
        # ナレッジベース統合
        knowledge_vectors_created = 0
        if create_knowledge and ocr_text:
            knowledge_manager = ImageKnowledgeManager()
            knowledge_vectors_created = knowledge_manager.create_knowledge_from_image(
                user_id=user_id,
                image_id=image_id,
                image_title=title,
                ocr_text=ocr_text,
                vision_description=analysis_results.get("vision_description", ""),
                additional_context=description
            )
        
        # 画像メタデータをDynamoDBに保存
        image_metadata = {
            "id": image_id,
            "user_id": user_id,
            "title": title,
            "filename": f"{title}.jpg",
            "url": image_url,
            "thumbnail_url": thumbnail_url,
            "upload_date": datetime.utcnow().isoformat(),
            "size": len(image_data),
            "tags": tags,
            "ocr_text": ocr_text,
            "analysis_results": analysis_results,
            "knowledge_vectors_created": knowledge_vectors_created,
            "processing_status": "completed"
        }
        
        storage_client.save_image_metadata(image_metadata)
        
        # クォータ使用量更新
        quota_manager.update_image_usage_after_upload(
            user_id, 
            image_size_mb=len(image_data) / (1024 * 1024),
            vector_count=knowledge_vectors_created
        )
        
        # レスポンス作成（フロントエンド仕様準拠）
        response_body = {
            "id": image_id,
            "title": title,
            "filename": f"{title}.jpg",
            "url": image_url,
            "thumbnail_url": thumbnail_url,
            "upload_date": datetime.utcnow().isoformat(),
            "size": len(image_data),
            "tags": tags,
            "processing_status": "completed",
            "ocr_text": ocr_text,
            "knowledge_vectors_created": knowledge_vectors_created,
            "analysis_results": analysis_results
        }
        
        return create_cors_response(200, response_body)
        
    except ValueError as e:
        return create_cors_response(400, {
            "error": str(e),
            "code": "INVALID_REQUEST"
        })
    except Exception as e:
        print(f"Error in image_upload_handler: {str(e)}")
        return create_cors_response(500, {
            "error": "サーバー内部エラーが発生しました",
            "code": "INTERNAL_SERVER_ERROR"
        })


def image_list_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """画像一覧取得ハンドラー"""
    try:
        # ユーザーIDを抽出
        user_id = extract_user_id_from_cognito(event)
        
        # クエリパラメータを取得
        query_params = event.get("queryStringParameters", {}) or {}
        limit = min(int(query_params.get("limit", 20)), 100)
        offset = max(int(query_params.get("offset", 0)), 0)
        tags_filter = query_params.get("tags", "").strip()
        search = query_params.get("search", "").strip()
        
        # タグフィルターを配列に変換
        tag_list = [tag.strip() for tag in tags_filter.split(",") if tag.strip()] if tags_filter else []
        
        # 画像ストレージクライアント初期化
        storage_client = ImageStorageClient()
        
        # 画像一覧を取得
        images, total_count = storage_client.list_user_images(
            user_id=user_id,
            limit=limit,
            offset=offset,
            tags=tag_list,
            search=search
        )
        
        has_more = (offset + len(images)) < total_count
        
        # フロントエンド仕様準拠のレスポンス
        response_body = {
            "images": images,
            "total": total_count,
            "has_more": has_more
        }
        
        return create_cors_response(200, response_body)
        
    except ValueError as e:
        return create_cors_response(400, {
            "error": str(e),
            "code": "INVALID_REQUEST"
        })
    except Exception as e:
        print(f"Error in image_list_handler: {str(e)}")
        return create_cors_response(500, {
            "error": "サーバー内部エラーが発生しました",
            "code": "INTERNAL_SERVER_ERROR"
        })


def image_detail_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """画像詳細取得ハンドラー"""
    try:
        # ユーザーIDを抽出
        user_id = extract_user_id_from_cognito(event)
        
        # パスパラメータから画像IDを抽出
        path_params = event.get("pathParameters", {})
        image_id = path_params.get("image_id")
        if not image_id:
            raise ValueError("画像IDが必要です")
        
        # 画像ストレージクライアント初期化
        storage_client = ImageStorageClient()
        
        # 画像詳細を取得
        image_info = storage_client.get_image_info(user_id, image_id)
        
        if not image_info:
            return create_cors_response(404, {
                "error": "画像が見つかりません",
                "code": "IMAGE_NOT_FOUND"
            })
        
        return create_cors_response(200, image_info)
        
    except ValueError as e:
        return create_cors_response(400, {
            "error": str(e),
            "code": "INVALID_REQUEST"
        })
    except Exception as e:
        print(f"Error in image_detail_handler: {str(e)}")
        return create_cors_response(500, {
            "error": "サーバー内部エラーが発生しました",
            "code": "INTERNAL_SERVER_ERROR"
        })


def image_delete_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """画像削除ハンドラー"""
    try:
        # ユーザーIDを抽出
        user_id = extract_user_id_from_cognito(event)
        
        # パスパラメータから画像IDを抽出
        path_params = event.get("pathParameters", {})
        image_id = path_params.get("image_id")
        if not image_id:
            raise ValueError("画像IDが必要です")
        
        # 画像ストレージクライアント初期化
        storage_client = ImageStorageClient()
        
        # 削除前に画像情報を取得（ベクトル数取得用）
        image_info = storage_client.get_image_info(user_id, image_id)
        if not image_info:
            return create_cors_response(404, {
                "error": "画像が見つかりません",
                "code": "IMAGE_NOT_FOUND"
            })
        
        deleted_vectors = image_info.get("knowledge_vectors_created", 0)
        
        # 画像とメタデータを削除
        success = storage_client.delete_image(user_id, image_id)
        
        if success:
            # ナレッジベースからも削除
            if deleted_vectors > 0:
                knowledge_manager = ImageKnowledgeManager()
                knowledge_manager.delete_knowledge_by_image(user_id, image_id)
            
            # クォータ使用量更新
            quota_manager = UserQuotaManager()
            quota_manager.update_image_usage_after_delete(
                user_id,
                image_size_mb=image_info.get("size", 0) / (1024 * 1024),
                vector_count=deleted_vectors
            )
            
            response_body = {
                "message": "画像が正常に削除されました",
                "deleted_vectors": deleted_vectors
            }
            
            return create_cors_response(200, response_body)
        else:
            return create_cors_response(500, {
                "error": "画像の削除に失敗しました",
                "code": "DELETE_FAILED"
            })
        
    except ValueError as e:
        return create_cors_response(400, {
            "error": str(e),
            "code": "INVALID_REQUEST"
        })
    except Exception as e:
        print(f"Error in image_delete_handler: {str(e)}")
        return create_cors_response(500, {
            "error": "サーバー内部エラーが発生しました",
            "code": "INTERNAL_SERVER_ERROR"
        })


def image_query_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """画像ベースクエリハンドラー"""
    try:
        # ユーザーIDを抽出
        user_id = extract_user_id_from_cognito(event)
        
        # クォータチェック
        quota_manager = UserQuotaManager()
        can_query, quota_message = quota_manager.check_quota_before_query(user_id)
        if not can_query:
            return create_cors_response(429, {
                "error": f"クエリ制限に達しています: {quota_message}",
                "code": "QUERY_LIMIT_EXCEEDED"
            })
        
        # リクエストボディをパース
        request_body = event.get("body", "{}")
        if isinstance(request_body, str):
            request_body = json.loads(request_body)
        
        question = request_body.get("question", "").strip()
        search_scope = request_body.get("search_scope", "all")
        max_results = min(int(request_body.get("max_results", 5)), 20)
        image_tags = request_body.get("image_tags", [])
        
        if not question:
            raise ValueError("質問は必須です")
        
        valid_scopes = ["all", "text_only", "vision_only"]
        if search_scope not in valid_scopes:
            raise ValueError(f"search_scopeは {', '.join(valid_scopes)} のいずれかである必要があります")
        
        # 画像ナレッジマネージャー初期化
        knowledge_manager = ImageKnowledgeManager()
        
        # 画像ベースクエリ実行
        query_result = knowledge_manager.query_image_knowledge(
            user_id=user_id,
            question=question,
            search_scope=search_scope,
            max_results=max_results,
            image_tags=image_tags
        )
        
        # クエリ実行後の使用量更新
        quota_manager.update_usage_after_query(user_id)
        
        return create_cors_response(200, query_result)
        
    except ValueError as e:
        return create_cors_response(400, {
            "error": str(e),
            "code": "INVALID_REQUEST"
        })
    except Exception as e:
        print(f"Error in image_query_handler: {str(e)}")
        return create_cors_response(500, {
            "error": "サーバー内部エラーが発生しました",
            "code": "INTERNAL_SERVER_ERROR"
        })


def image_statistics_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """画像統計取得ハンドラー"""
    try:
        # ユーザーIDを抽出
        user_id = extract_user_id_from_cognito(event)
        
        # 画像ストレージクライアント初期化
        storage_client = ImageStorageClient()
        
        # 統計情報を取得
        statistics = storage_client.get_user_image_statistics(user_id)
        
        return create_cors_response(200, statistics)
        
    except ValueError as e:
        return create_cors_response(400, {
            "error": str(e),
            "code": "INVALID_REQUEST"
        })
    except Exception as e:
        print(f"Error in image_statistics_handler: {str(e)}")
        return create_cors_response(500, {
            "error": "サーバー内部エラーが発生しました",
            "code": "INTERNAL_SERVER_ERROR"
        })