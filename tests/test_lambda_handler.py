import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lambda_handler import lambda_handler, add_document_handler


class TestLambdaHandler:
    """lambda_handlerのテストクラス"""
    
    @patch.dict('os.environ', {
        'VECTOR_BUCKET_NAME': 'test-bucket',
        'VECTOR_INDEX_NAME': 'test-index'
    })
    @patch('src.lambda_handler.S3VectorsClient')
    @patch('lambda_handler.ChatBedrockConverse')
    @patch('boto3.client')
    def test_lambda_handler_success(self, mock_boto3_client, mock_chat_bedrock, mock_s3_vectors_class):
        """lambda_handlerの正常系テスト"""
        # モックの設定
        mock_s3_vectors = Mock()
        mock_s3_vectors.query_vectors.return_value = [
            {
                "metadata": {
                    "text": "テストテキスト1",
                    "title": "テストタイトル1"
                }
            },
            {
                "metadata": {
                    "text": "テストテキスト2", 
                    "title": "テストタイトル2"
                }
            }
        ]
        mock_s3_vectors_class.return_value = mock_s3_vectors
        
        mock_model = Mock()
        mock_response = Mock()
        mock_response.content = "テスト回答"
        mock_model.invoke.return_value = mock_response
        mock_chat_bedrock.return_value = mock_model
        
        # テストイベント
        event = {
            "body": json.dumps({"question": "テスト質問"})
        }
        context = {}
        
        result = lambda_handler(event, context)
        
        # アサーション
        assert result["statusCode"] == 200
        response_body = json.loads(result["body"])
        assert "answer" in response_body
        assert response_body["answer"] == "テスト回答"
        
        # モックの呼び出し確認
        mock_s3_vectors.query_vectors.assert_called_once_with(
            vector_bucket_name="test-bucket",
            index_name="test-index",
            question="テスト質問",
            top_k=3
        )
    
    def test_lambda_handler_invalid_json(self):
        """不正なJSONの場合のテスト"""
        event = {
            "body": "invalid json"
        }
        context = {}
        
        result = lambda_handler(event, context)
        
        assert result["statusCode"] == 500
        response_body = json.loads(result["body"])
        assert "error" in response_body
    
    @patch.dict('os.environ', {
        'VECTOR_BUCKET_NAME': 'test-bucket',
        'VECTOR_INDEX_NAME': 'test-index'
    })
    @patch('src.lambda_handler.S3VectorsClient')
    def test_lambda_handler_s3vectors_error(self, mock_s3_vectors_class):
        """S3Vectorsエラーの場合のテスト"""
        mock_s3_vectors = Mock()
        mock_s3_vectors.query_vectors.side_effect = Exception("S3Vectors Error")
        mock_s3_vectors_class.return_value = mock_s3_vectors
        
        event = {
            "body": json.dumps({"question": "テスト質問"})
        }
        context = {}
        
        result = lambda_handler(event, context)
        
        assert result["statusCode"] == 500
        response_body = json.loads(result["body"])
        assert "error" in response_body


class TestAddDocumentHandler:
    """add_document_handlerのテストクラス"""
    
    @patch.dict('os.environ', {
        'VECTOR_BUCKET_NAME': 'test-bucket',
        'VECTOR_INDEX_NAME': 'test-index'
    })
    @patch('src.lambda_handler.S3VectorsClient')
    def test_add_document_handler_success(self, mock_s3_vectors_class):
        """add_document_handlerの正常系テスト"""
        # モックの設定
        mock_s3_vectors = Mock()
        mock_s3_vectors.add_document.return_value = 5
        mock_s3_vectors_class.return_value = mock_s3_vectors
        
        # テストイベント
        event = {
            "body": json.dumps({
                "text": "テストドキュメント",
                "title": "テストタイトル"
            })
        }
        context = {}
        
        result = add_document_handler(event, context)
        
        # アサーション
        assert result["statusCode"] == 200
        response_body = json.loads(result["body"])
        assert response_body["message"] == "Successfully added 5 vectors"
        assert response_body["vector_count"] == 5
        
        # モックの呼び出し確認
        mock_s3_vectors.add_document.assert_called_once_with(
            vector_bucket_name="test-bucket",
            index_name="test-index",
            text="テストドキュメント",
            title="テストタイトル"
        )
    
    def test_add_document_handler_invalid_json(self):
        """不正なJSONの場合のテスト"""
        event = {
            "body": "invalid json"
        }
        context = {}
        
        result = add_document_handler(event, context)
        
        assert result["statusCode"] == 500
        response_body = json.loads(result["body"])
        assert "error" in response_body
    
    @patch.dict('os.environ', {
        'VECTOR_BUCKET_NAME': 'test-bucket',
        'VECTOR_INDEX_NAME': 'test-index'
    })
    @patch('src.lambda_handler.S3VectorsClient')
    def test_add_document_handler_s3vectors_error(self, mock_s3_vectors_class):
        """S3Vectorsエラーの場合のテスト"""
        mock_s3_vectors = Mock()
        mock_s3_vectors.add_document.side_effect = Exception("S3Vectors Error")
        mock_s3_vectors_class.return_value = mock_s3_vectors
        
        event = {
            "body": json.dumps({
                "text": "テストドキュメント",
                "title": "テストタイトル"
            })
        }
        context = {}
        
        result = add_document_handler(event, context)
        
        assert result["statusCode"] == 500
        response_body = json.loads(result["body"])
        assert "error" in response_body