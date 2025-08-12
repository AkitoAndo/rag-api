"""簡単なLambdaハンドラーテスト"""
import json
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# srcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lambda_handler import lambda_handler, add_document_handler


class TestLambdaHandlerSimple:
    """シンプルなLambda関数テスト"""
    
    @patch('lambda_handler.S3VectorsClient')
    @patch('lambda_handler.ChatBedrockConverse')
    @patch('lambda_handler.boto3.client')
    @patch.dict('os.environ', {
        'VECTOR_BUCKET_NAME': 'test-bucket',
        'VECTOR_INDEX_NAME': 'test-index'
    })
    def test_lambda_success_simple(self, mock_boto3, mock_chat, mock_s3_client_class):
        """簡単な成功テスト"""
        # S3VectorsClient のモック
        mock_s3_instance = Mock()
        mock_s3_instance.query_vectors.return_value = [
            {"metadata": {"text": "テスト回答"}}
        ]
        mock_s3_client_class.return_value = mock_s3_instance
        
        # ChatBedrockConverse のモック
        mock_chat_instance = Mock()
        mock_response = Mock()
        mock_response.content = "これは回答です"
        mock_chat_instance.invoke.return_value = mock_response
        mock_chat.return_value = mock_chat_instance
        
        # boto3.client のモック
        mock_boto3.return_value = Mock()
        
        # テストイベント
        event = {"body": json.dumps({"question": "テスト質問"})}
        
        # 実行
        result = lambda_handler(event, {})
        
        # 確認
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "answer" in body
    
    @patch('lambda_handler.S3VectorsClient')
    @patch.dict('os.environ', {
        'VECTOR_BUCKET_NAME': 'test-bucket',
        'VECTOR_INDEX_NAME': 'test-index'
    })
    def test_add_document_success_simple(self, mock_s3_client_class):
        """簡単なドキュメント追加成功テスト"""
        # S3VectorsClient のモック
        mock_s3_instance = Mock()
        mock_s3_instance.add_document.return_value = 3
        mock_s3_client_class.return_value = mock_s3_instance
        
        # テストイベント
        event = {
            "body": json.dumps({
                "text": "テストドキュメント",
                "title": "テストタイトル"
            })
        }
        
        # 実行
        result = add_document_handler(event, {})
        
        # 確認
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "vector_count" in body
        assert body["vector_count"] == 3
    
    def test_lambda_invalid_json(self):
        """不正JSONのテスト"""
        event = {"body": "invalid json"}
        result = lambda_handler(event, {})
        
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "error" in body
    
    def test_add_document_invalid_json(self):
        """ドキュメント追加の不正JSONテスト"""
        event = {"body": "invalid json"}
        result = add_document_handler(event, {})
        
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "error" in body
    
    def test_lambda_missing_question(self):
        """質問フィールドが欠けているテスト"""
        event = {"body": json.dumps({"message": "質問ではない"})}
        result = lambda_handler(event, {})
        
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "error" in body
    
    def test_add_document_missing_fields(self):
        """必須フィールドが欠けているテスト"""
        event = {"body": json.dumps({"title": "タイトルのみ"})}
        result = add_document_handler(event, {})
        
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "error" in body

