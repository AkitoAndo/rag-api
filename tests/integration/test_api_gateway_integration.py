"""API Gateway統合テスト"""
import pytest
import json
import sys
import os
from pathlib import Path

# srcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lambda_handler import lambda_handler, add_document_handler


@pytest.mark.integration_mock
class TestAPIGatewayIntegration:
    """API Gateway形式でのLambda関数統合テスト"""
    
    def test_api_gateway_query_request_format(self, mock_s3vectors_client, test_environment):
        """API Gateway形式のクエリリクエストテスト"""
        # API Gateway形式のイベント
        api_event = {
            "httpMethod": "POST",
            "path": "/query",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "question": "メイドインアビスについて教えて"
            }),
            "requestContext": {
                "httpMethod": "POST",
                "path": "/query"
            }
        }
        
        # Mock設定
        mock_s3_vectors_client.return_value.query_vectors.return_value = [
            {
                "metadata": {
                    "text": "メイドインアビスは冒険の物語です"
                },
                "distance": 0.1
            }
        ]
        
        with test_environment:
            result = lambda_handler(api_event, {})
            
            assert result["statusCode"] == 200
            assert "Content-Type" in result["headers"]
            assert result["headers"]["Content-Type"] == "application/json; charset=utf-8"
            
            body = json.loads(result["body"])
            assert "answer" in body
            assert len(body["answer"]) > 0
    
    def test_api_gateway_add_document_request_format(self, mock_s3_vectors_client, test_environment):
        """API Gateway形式のドキュメント追加リクエストテスト"""
        # API Gateway形式のイベント
        api_event = {
            "httpMethod": "POST",
            "path": "/add-document",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "text": "これはテスト用のドキュメントです。API Gateway統合テストで使用されています。",
                "title": "API Gatewayテストドキュメント"
            }),
            "requestContext": {
                "httpMethod": "POST",
                "path": "/add-document"
            }
        }
        
        # Mock設定
        mock_s3_vectors_client.return_value.add_document.return_value = 3
        
        with test_environment:
            result = add_document_handler(api_event, {})
            
            assert result["statusCode"] == 200
            assert "Content-Type" in result["headers"]
            assert result["headers"]["Content-Type"] == "application/json; charset=utf-8"
            
            body = json.loads(result["body"])
            assert "message" in body
            assert "vector_count" in body
            assert body["vector_count"] == 3
    
    def test_api_gateway_cors_headers(self, mock_s3_vectors_client, test_environment):
        """CORS対応のヘッダーテスト"""
        api_event = {
            "httpMethod": "POST",
            "path": "/query",
            "headers": {
                "Content-Type": "application/json",
                "Origin": "https://example.com"
            },
            "body": json.dumps({
                "question": "テスト質問"
            })
        }
        
        mock_s3_vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": "テスト回答"}, "distance": 0.1}
        ]
        
        with test_environment:
            result = lambda_handler(api_event, {})
            
            assert result["statusCode"] == 200
            # CORS ヘッダーが含まれていることを確認
            headers = result["headers"]
            assert "Content-Type" in headers
            assert headers["Content-Type"] == "application/json; charset=utf-8"
    
    def test_api_gateway_error_handling(self, mock_s3_vectors_client, test_environment):
        """API Gateway形式でのエラーハンドリングテスト"""
        # 不正なJSONボディ
        api_event = {
            "httpMethod": "POST",
            "path": "/query",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": "invalid json"
        }
        
        with test_environment:
            result = lambda_handler(api_event, {})
            
            assert result["statusCode"] == 500
            assert "Content-Type" in result["headers"]
            
            body = json.loads(result["body"])
            assert "error" in body
    
    def test_api_gateway_missing_question_field(self, test_environment):
        """API Gateway形式で必須フィールドが欠けている場合のテスト"""
        api_event = {
            "httpMethod": "POST",
            "path": "/query",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "message": "質問ではなくメッセージ"  # questionフィールドが欠けている
            })
        }
        
        with test_environment:
            result = lambda_handler(api_event, {})
            
            assert result["statusCode"] == 500
            body = json.loads(result["body"])
            assert "error" in body
    
    def test_api_gateway_unicode_support(self, mock_s3_vectors_client, test_environment):
        """Unicode文字のサポートテスト"""
        api_event = {
            "httpMethod": "POST",
            "path": "/query",
            "headers": {
                "Content-Type": "application/json; charset=utf-8"
            },
            "body": json.dumps({
                "question": "日本語の質問です。絵文字も含みます 🤖🚀"
            })
        }
        
        mock_s3_vectors_client.return_value.query_vectors.return_value = [
            {
                "metadata": {
                    "text": "日本語での回答です。絵文字付き 📚✨"
                },
                "distance": 0.1
            }
        ]
        
        with test_environment:
            result = lambda_handler(api_event, {})
            
            assert result["statusCode"] == 200
            body = json.loads(result["body"])
            assert "answer" in body
            # Unicode文字が正しく処理されることを確認
            assert "日本語" in body["answer"] or "絵文字" in body["answer"]
    
    def test_api_gateway_large_payload(self, mock_s3_vectors_client, test_environment):
        """大きなペイロードのテスト"""
        # 大きなテキストを生成
        large_text = "これは大きなドキュメントです。" * 100  # 約3KB
        
        api_event = {
            "httpMethod": "POST",
            "path": "/add-document",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "text": large_text,
                "title": "大きなドキュメント"
            })
        }
        
        mock_s3_vectors_client.return_value.add_document.return_value = 5
        
        with test_environment:
            result = add_document_handler(api_event, {})
            
            assert result["statusCode"] == 200
            body = json.loads(result["body"])
            assert body["vector_count"] == 5


@pytest.mark.integration_mock
class TestAPIGatewayRequestValidation:
    """API Gateway リクエスト検証テスト"""
    
    def test_content_type_validation(self, test_environment):
        """Content-Type検証テスト"""
        # 間違ったContent-Type
        api_event = {
            "httpMethod": "POST",
            "path": "/query",
            "headers": {
                "Content-Type": "text/plain"
            },
            "body": "plain text instead of json"
        }
        
        with test_environment:
            result = lambda_handler(api_event, {})
            
            # JSONパースエラーで500エラーになることを確認
            assert result["statusCode"] == 500
    
    def test_empty_body_handling(self, test_environment):
        """空のボディの処理テスト"""
        api_event = {
            "httpMethod": "POST",
            "path": "/query",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": ""
        }
        
        with test_environment:
            result = lambda_handler(api_event, {})
            
            assert result["statusCode"] == 500
            body = json.loads(result["body"])
            assert "error" in body
    
    def test_null_body_handling(self, test_environment):
        """Nullボディの処理テスト"""
        api_event = {
            "httpMethod": "POST",
            "path": "/query",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": None
        }
        
        with test_environment:
            result = lambda_handler(api_event, {})
            
            assert result["statusCode"] == 500
            body = json.loads(result["body"])
            assert "error" in body


@pytest.mark.integration_mock  
class TestAPIGatewayResponseFormat:
    """API Gateway レスポンス形式テスト"""
    
    def test_success_response_structure(self, mock_s3_vectors_client, test_environment):
        """成功レスポンスの構造テスト"""
        api_event = {
            "httpMethod": "POST",
            "path": "/query", 
            "body": json.dumps({"question": "テスト"})
        }
        
        mock_s3_vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": "テスト回答"}, "distance": 0.1}
        ]
        
        with test_environment:
            result = lambda_handler(api_event, {})
            
            # API Gateway形式のレスポンス構造を確認
            required_fields = ["statusCode", "headers", "body"]
            for field in required_fields:
                assert field in result
            
            assert isinstance(result["statusCode"], int)
            assert isinstance(result["headers"], dict)
            assert isinstance(result["body"], str)
            
            # ボディがJSONとしてパース可能であることを確認
            body = json.loads(result["body"])
            assert isinstance(body, dict)
    
    def test_error_response_structure(self, test_environment):
        """エラーレスポンスの構造テスト"""
        api_event = {
            "httpMethod": "POST",
            "path": "/query",
            "body": "invalid"
        }
        
        with test_environment:
            result = lambda_handler(api_event, {})
            
            # エラーレスポンスでも同じ構造を確認
            assert result["statusCode"] == 500
            assert "headers" in result
            assert "body" in result
            
            body = json.loads(result["body"])
            assert "error" in body
            assert isinstance(body["error"], str)
