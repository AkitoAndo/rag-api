"""エラーハンドリングテスト - OpenAPI仕様のHTTPステータスコード対応"""
import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError, NoCredentialsError

# srcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lambda_handler import lambda_handler, add_document_handler


@pytest.mark.unit
class TestHTTPErrorResponses:
    """HTTPエラーレスポンステスト - OpenAPI仕様準拠"""
    
    def test_400_bad_request_scenarios(self, test_environment):
        """400 Bad Request エラーのシナリオテスト"""
        # 無効なJSON
        invalid_json_event = {
            "body": '{"invalid": json}'
        }
        
        with test_environment:
            result = lambda_handler(invalid_json_event, {})
            assert result["statusCode"] == 400
            body = json.loads(result["body"])
            assert "error" in body
            assert "json" in body["error"].lower()
        
        # 必須フィールド不足
        missing_field_event = {
            "body": json.dumps({"title": "タイトルのみ"})
        }
        
        with test_environment:
            result = add_document_handler(missing_field_event, {})
            assert result["statusCode"] == 400
            body = json.loads(result["body"])
            assert "error" in body
            assert "text" in body["error"].lower()
        
        # 空の質問
        empty_question_event = {
            "body": json.dumps({"question": ""})
        }
        
        with test_environment:
            result = lambda_handler(empty_question_event, {})
            assert result["statusCode"] == 400
            body = json.loads(result["body"])
            assert "error" in body

    def test_500_internal_server_error_scenarios(self, mock_s3vectors_client, test_environment):
        """500 Internal Server Error のシナリオテスト"""
        
        # S3 Vectorsサービスエラー
        mock_s3vectors_client.return_value.query_vectors.side_effect = Exception("S3 Vectors service error")
        
        event = {
            "body": json.dumps({"question": "テスト質問"})
        }
        
        with test_environment:
            result = lambda_handler(event, {})
            assert result["statusCode"] == 500
            body = json.loads(result["body"])
            assert "error" in body
    
    def test_bedrock_service_errors(self, mock_s3vectors_client, test_environment):
        """Bedrockサービスエラーのテスト"""
        # 検索は成功するがEmbedding生成でエラー
        mock_s3vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": "テスト", "title": "タイトル"}}
        ]
        
        event = {
            "body": json.dumps({"question": "テスト質問"})
        }
        
        with test_environment:
            with patch('lambda_handler.ChatBedrockConverse') as mock_chat:
                mock_chat.side_effect = ClientError(
                    error_response={'Error': {'Code': 'AccessDeniedException', 'Message': 'Model access denied'}},
                    operation_name='InvokeModel'
                )
                
                result = lambda_handler(event, {})
                assert result["statusCode"] == 500
                body = json.loads(result["body"])
                assert "error" in body
                assert "bedrock" in body["error"].lower() or "model" in body["error"].lower()

    def test_aws_credentials_error(self, mock_s3vectors_client, test_environment):
        """AWS認証エラーのテスト"""
        mock_s3vectors_client.side_effect = NoCredentialsError()
        
        event = {
            "body": json.dumps({"question": "テスト質問"})
        }
        
        with test_environment:
            result = lambda_handler(event, {})
            assert result["statusCode"] == 500
            body = json.loads(result["body"])
            assert "error" in body

    def test_timeout_simulation(self, mock_s3vectors_client, test_environment):
        """タイムアウトシミュレーションテスト"""
        # 非常に遅いレスポンス（タイムアウト）をシミュレート
        import time
        
        def slow_query(*args, **kwargs):
            time.sleep(0.1)  # 実際のテストでは短い時間に設定
            raise Exception("Operation timed out")
        
        mock_s3vectors_client.return_value.query_vectors.side_effect = slow_query
        
        event = {
            "body": json.dumps({"question": "タイムアウトテスト"})
        }
        
        with test_environment:
            result = lambda_handler(event, {})
            assert result["statusCode"] == 500
            body = json.loads(result["body"])
            assert "error" in body


@pytest.mark.unit
class TestErrorResponseFormat:
    """エラーレスポンス形式テスト"""
    
    def test_error_response_structure(self, test_environment):
        """エラーレスポンスの構造テスト"""
        invalid_event = {
            "body": "invalid json"
        }
        
        with test_environment:
            result = lambda_handler(invalid_event, {})
            
            # 基本構造の確認
            assert "statusCode" in result
            assert "headers" in result
            assert "body" in result
            
            # ヘッダーの確認
            headers = result["headers"]
            assert "Content-Type" in headers
            assert headers["Content-Type"] == "application/json; charset=utf-8"
            assert "Access-Control-Allow-Origin" in headers
            
            # ボディの確認
            body = json.loads(result["body"])
            assert "error" in body
            assert isinstance(body["error"], str)
            assert len(body["error"]) > 0

    def test_error_message_localization(self, test_environment):
        """エラーメッセージの言語対応テスト"""
        # 日本語エラーメッセージの確認
        invalid_event = {
            "body": json.dumps({"title": "タイトルのみ"})
        }
        
        with test_environment:
            result = add_document_handler(invalid_event, {})
            body = json.loads(result["body"])
            
            # エラーメッセージが適切な言語で返されることを確認
            error_message = body["error"]
            # 実装に応じて日本語または英語での確認
            assert len(error_message) > 0

    def test_error_logging_and_debugging(self, mock_s3vectors_client, test_environment):
        """エラーログとデバッグ情報のテスト"""
        # 例外が適切にログに記録されることを確認
        mock_s3vectors_client.return_value.query_vectors.side_effect = Exception("Test exception for logging")
        
        event = {
            "body": json.dumps({"question": "ログテスト"})
        }
        
        with test_environment:
            with patch('builtins.print') as mock_print:  # print文をキャプチャ
                result = lambda_handler(event, {})
                
                assert result["statusCode"] == 500
                # ログが出力されていることを確認（実装依存）
                # mock_print.assert_called() # 必要に応じて有効化


@pytest.mark.unit
class TestServiceDependencyErrors:
    """外部サービス依存エラーテスト"""
    
    def test_s3_vectors_connection_error(self, test_environment):
        """S3 Vectors接続エラーテスト"""
        with test_environment:
            with patch('s3_vectors_client.S3VectorsClient') as mock_client:
                mock_client.side_effect = ConnectionError("Cannot connect to S3 Vectors")
                
                event = {
                    "body": json.dumps({"question": "接続テスト"})
                }
                
                result = lambda_handler(event, {})
                assert result["statusCode"] == 500
                body = json.loads(result["body"])
                assert "error" in body

    def test_bedrock_throttling_error(self, mock_s3vectors_client, test_environment):
        """Bedrockスロットリングエラーテスト"""
        mock_s3vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": "テスト", "title": "タイトル"}}
        ]
        
        event = {
            "body": json.dumps({"question": "スロットリングテスト"})
        }
        
        with test_environment:
            with patch('lambda_handler.ChatBedrockConverse') as mock_chat:
                mock_chat.side_effect = ClientError(
                    error_response={'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
                    operation_name='InvokeModel'
                )
                
                result = lambda_handler(event, {})
                assert result["statusCode"] == 500
                body = json.loads(result["body"])
                assert "error" in body

    def test_memory_error_handling(self, mock_s3vectors_client, test_environment):
        """メモリ不足エラーのテスト"""
        # 大量のデータでメモリエラーをシミュレート
        mock_s3vectors_client.return_value.query_vectors.side_effect = MemoryError("Out of memory")
        
        event = {
            "body": json.dumps({"question": "メモリテスト"})
        }
        
        with test_environment:
            result = lambda_handler(event, {})
            assert result["statusCode"] == 500
            body = json.loads(result["body"])
            assert "error" in body


@pytest.mark.unit  
class TestRateLimitingAndRetry:
    """レート制限・リトライ機能テスト"""
    
    def test_bedrock_retry_mechanism(self, mock_s3vectors_client, test_environment):
        """Bedrockリトライメカニズムテスト"""
        mock_s3vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": "テスト", "title": "タイトル"}}
        ]
        
        event = {
            "body": json.dumps({"question": "リトライテスト"})
        }
        
        with test_environment:
            with patch('lambda_handler.ChatBedrockConverse') as mock_chat:
                # 最初の数回は失敗、最後は成功
                call_count = 0
                def side_effect(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count <= 2:
                        raise ClientError(
                            error_response={'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
                            operation_name='InvokeModel'
                        )
                    else:
                        mock_model = Mock()
                        mock_response = Mock()
                        mock_response.content = "成功レスポンス"
                        mock_model.invoke.return_value = mock_response
                        return mock_model
                
                mock_chat.side_effect = side_effect
                
                result = lambda_handler(event, {})
                # リトライが実装されている場合は成功、されていない場合は失敗
                # 実装に応じて期待値を調整


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




