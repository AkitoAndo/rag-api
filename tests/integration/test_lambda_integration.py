"""Lambda関数の統合テスト"""
import json
import pytest
from unittest.mock import patch, Mock
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lambda_handler import lambda_handler, add_document_handler


class TestLambdaIntegration:
    """Lambda関数の統合テストクラス"""

    def test_full_query_workflow_integration(
        self,
        test_environment,
        sample_lambda_event,
        mock_s3vectors_client,
        mock_embedding_model,
        mock_chat_response
    ):
        """クエリ処理の全体フローの統合テスト"""
        
        with patch('src.lambda_handler.S3VectorsClient') as mock_s3vectors_class:
            with patch('src.lambda_handler.ChatBedrockConverse') as mock_chat_class:
                with patch('boto3.client') as mock_boto3:
                    
                    # S3VectorsClientのモック設定
                    mock_s3vectors = Mock()
                    mock_s3vectors.query_vectors.return_value = [
                        {
                            "key": "vector-1",
                            "metadata": {
                                "text": "リコは『メイドインアビス』の主人公で、アビスの探窟を目指す少女探窟家です。",
                                "title": "キャラクター紹介"
                            },
                            "distance": 0.1
                        },
                        {
                            "key": "vector-2",
                            "metadata": {
                                "text": "母親のライザを探すためにアビスの深層を目指しています。",
                                "title": "ストーリー"
                            },
                            "distance": 0.2
                        }
                    ]
                    mock_s3vectors_class.return_value = mock_s3vectors
                    
                    # ChatBedrockConverseのモック設定
                    mock_chat_model = Mock()
                    mock_chat_model.invoke.return_value = mock_chat_response
                    mock_chat_class.return_value = mock_chat_model
                    
                    # Lambda関数を実行
                    result = lambda_handler(sample_lambda_event, {})
                    
                    # レスポンスの検証
                    assert result["statusCode"] == 200
                    assert "Content-Type" in result["headers"]
                    
                    response_body = json.loads(result["body"])
                    assert "answer" in response_body
                    assert response_body["answer"] == mock_chat_response.content
                    
                    # 各コンポーネントの呼び出しを確認
                    mock_s3vectors.query_vectors.assert_called_once()
                    mock_chat_model.invoke.assert_called_once()
                    
                    # S3Vectors呼び出しの引数確認
                    query_args = mock_s3vectors.query_vectors.call_args
                    assert query_args[1]["vector_bucket_name"] == test_environment["VECTOR_BUCKET_NAME"]
                    assert query_args[1]["index_name"] == test_environment["VECTOR_INDEX_NAME"]
                    assert query_args[1]["question"] == "リコとは誰ですか？"
                    assert query_args[1]["top_k"] == 3

    def test_full_add_document_workflow_integration(
        self,
        test_environment,
        sample_add_document_event,
        mock_s3vectors_client,
        mock_embedding_model
    ):
        """ドキュメント追加処理の全体フローの統合テスト"""
        
        with patch('src.lambda_handler.S3VectorsClient') as mock_s3vectors_class:
            
            # S3VectorsClientのモック設定
            mock_s3vectors = Mock()
            mock_s3vectors.add_document.return_value = 3  # 3つのベクトルが作成されたとする
            mock_s3vectors_class.return_value = mock_s3vectors
            
            # Lambda関数を実行
            result = add_document_handler(sample_add_document_event, {})
            
            # レスポンスの検証
            assert result["statusCode"] == 200
            assert "Content-Type" in result["headers"]
            
            response_body = json.loads(result["body"])
            assert response_body["message"] == "Successfully added 3 vectors"
            assert response_body["vector_count"] == 3
            
            # S3VectorsClientの呼び出しを確認
            mock_s3vectors.add_document.assert_called_once()
            add_args = mock_s3vectors.add_document.call_args
            assert add_args[1]["vector_bucket_name"] == test_environment["VECTOR_BUCKET_NAME"]
            assert add_args[1]["index_name"] == test_environment["VECTOR_INDEX_NAME"]
            assert add_args[1]["text"] == "これはテスト用の新しいドキュメントです。"
            assert add_args[1]["title"] == "テスト追加ドキュメント"

    def test_lambda_error_propagation_integration(
        self,
        test_environment,
        sample_lambda_event
    ):
        """Lambda関数でのエラー伝播の統合テスト"""
        
        with patch('src.lambda_handler.S3VectorsClient') as mock_s3vectors_class:
            
            # S3VectorsClientでエラーを発生させる
            mock_s3vectors = Mock()
            mock_s3vectors.query_vectors.side_effect = Exception("Vector database connection failed")
            mock_s3vectors_class.return_value = mock_s3vectors
            
            # Lambda関数を実行
            result = lambda_handler(sample_lambda_event, {})
            
            # エラーレスポンスの検証
            assert result["statusCode"] == 500
            assert "Content-Type" in result["headers"]
            
            response_body = json.loads(result["body"])
            assert "error" in response_body
            assert "Vector database connection failed" in response_body["error"]

    def test_xml_generation_integration(
        self,
        test_environment,
        sample_lambda_event,
        mock_chat_response
    ):
        """XML生成処理の統合テスト"""
        
        with patch('src.lambda_handler.S3VectorsClient') as mock_s3vectors_class:
            with patch('src.lambda_handler.ChatBedrockConverse') as mock_chat_class:
                with patch('boto3.client'):
                    
                    # 複数のベクトル結果を返すようにモック設定
                    mock_s3vectors = Mock()
                    mock_s3vectors.query_vectors.return_value = [
                        {
                            "metadata": {
                                "text": "第一のドキュメント内容",
                                "title": "ドキュメント1"
                            }
                        },
                        {
                            "metadata": {
                                "text": "第二のドキュメント内容",
                                "title": "ドキュメント2"
                            }
                        }
                    ]
                    mock_s3vectors_class.return_value = mock_s3vectors
                    
                    # ChatModelのモック設定（XML入力をキャプチャするため）
                    mock_chat_model = Mock()
                    mock_chat_model.invoke.return_value = mock_chat_response
                    mock_chat_class.return_value = mock_chat_model
                    
                    # Lambda関数を実行
                    result = lambda_handler(sample_lambda_event, {})
                    
                    # 成功を確認
                    assert result["statusCode"] == 200
                    
                    # ChatModelに渡されたメッセージを確認
                    invoke_args = mock_chat_model.invoke.call_args[0][0]
                    human_message = invoke_args[1].content
                    
                    # XMLが適切に生成されているか確認
                    assert "第一のドキュメント内容" in human_message
                    assert "第二のドキュメント内容" in human_message
                    assert "<documents>" in human_message
                    assert "<document>" in human_message
                    assert "リコとは誰ですか？" in human_message

    def test_environment_variable_integration(self, mock_s3vectors_client):
        """環境変数の統合テスト"""
        
        # 環境変数を設定してテスト
        custom_env = {
            "VECTOR_BUCKET_NAME": "custom-bucket",
            "VECTOR_INDEX_NAME": "custom-index",
            "AWS_REGION": "us-west-2",
            "CHAT_MODEL_ID": "custom-model-id"
        }
        
        with patch.dict('os.environ', custom_env):
            with patch('src.lambda_handler.S3VectorsClient') as mock_s3vectors_class:
                with patch('src.lambda_handler.ChatBedrockConverse') as mock_chat_class:
                    with patch('boto3.client') as mock_boto3:
                        
                        mock_s3vectors = Mock()
                        mock_s3vectors.query_vectors.return_value = []
                        mock_s3vectors_class.return_value = mock_s3vectors
                        
                        mock_chat = Mock()
                        mock_response = Mock()
                        mock_response.content = "test response"
                        mock_chat.invoke.return_value = mock_response
                        mock_chat_class.return_value = mock_chat
                        
                        event = {
                            "body": json.dumps({"question": "test question"})
                        }
                        
                        result = lambda_handler(event, {})
                        
                        # 環境変数が正しく使われているか確認
                        query_args = mock_s3vectors.query_vectors.call_args
                        assert query_args[1]["vector_bucket_name"] == "custom-bucket"
                        assert query_args[1]["index_name"] == "custom-index"
                        
                        # Bedrockクライアントが正しいリージョンで初期化されているか確認
                        bedrock_call_args = mock_boto3.call_args_list
                        bedrock_call = next(call for call in bedrock_call_args if call[0][0] == "bedrock-runtime")
                        assert bedrock_call[0][1] == "us-west-2"
                        
                        # ChatModelが正しいモデルIDで初期化されているか確認
                        chat_init_args = mock_chat_class.call_args
                        assert chat_init_args[1]["model"] == "custom-model-id"