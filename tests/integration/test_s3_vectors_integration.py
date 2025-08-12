"""S3VectorsClientの統合テスト"""
import pytest
from unittest.mock import patch, Mock
from src.s3_vectors_client import S3VectorsClient


class TestS3VectorsClientIntegration:
    """S3VectorsClientの統合テストクラス"""

    def test_full_document_workflow(
        self, 
        test_environment, 
        mock_s3vectors_client, 
        mock_embedding_model,
        sample_document
    ):
        """ドキュメント追加から検索まで全体フローのテスト"""
        
        # S3VectorsClientのモックを設定
        with patch('boto3.client') as mock_boto3:
            with patch('src.s3_vectors_client.BedrockEmbeddings') as mock_bedrock:
                
                # モックの設定
                mock_boto3.return_value = mock_s3vectors_client
                mock_bedrock.return_value = mock_embedding_model
                
                # クライアント初期化
                client = S3VectorsClient()
                client.s3vectors_client = mock_s3vectors_client
                client.embedding_model = mock_embedding_model
                
                # 1. ドキュメントを追加
                vector_count = client.add_document(
                    vector_bucket_name=test_environment["VECTOR_BUCKET_NAME"],
                    index_name=test_environment["VECTOR_INDEX_NAME"],
                    text=sample_document["text"],
                    title=sample_document["title"]
                )
                
                # ベクトルが作成されたことを確認
                assert vector_count > 0
                assert mock_embedding_model.embed_query.call_count > 0
                mock_s3vectors_client.put_vectors.assert_called_once()
                
                # put_vectorsの引数を確認
                call_args = mock_s3vectors_client.put_vectors.call_args
                assert call_args[1]['vectorBucketName'] == test_environment["VECTOR_BUCKET_NAME"]
                assert call_args[1]['indexName'] == test_environment["VECTOR_INDEX_NAME"]
                assert len(call_args[1]['vectors']) == vector_count
                
                # 2. 質問でベクトル検索を実行
                question = "リコについて教えて"
                results = client.query_vectors(
                    vector_bucket_name=test_environment["VECTOR_BUCKET_NAME"],
                    index_name=test_environment["VECTOR_INDEX_NAME"],
                    question=question,
                    top_k=3
                )
                
                # 検索結果を確認
                assert len(results) > 0
                assert all('metadata' in result for result in results)
                assert all('text' in result['metadata'] for result in results)
                
                # クエリの呼び出しを確認
                mock_s3vectors_client.query_vectors.assert_called_once()
                query_call_args = mock_s3vectors_client.query_vectors.call_args
                assert query_call_args[1]['vectorBucketName'] == test_environment["VECTOR_BUCKET_NAME"]
                assert query_call_args[1]['indexName'] == test_environment["VECTOR_INDEX_NAME"]
                assert query_call_args[1]['topK'] == 3

    def test_multiple_documents_integration(
        self, 
        test_environment, 
        mock_s3vectors_client, 
        mock_embedding_model
    ):
        """複数ドキュメントの統合テスト"""
        
        with patch('boto3.client') as mock_boto3:
            with patch('src.s3_vectors_client.BedrockEmbeddings') as mock_bedrock:
                
                mock_boto3.return_value = mock_s3vectors_client
                mock_bedrock.return_value = mock_embedding_model
                
                client = S3VectorsClient()
                client.s3vectors_client = mock_s3vectors_client
                client.embedding_model = mock_embedding_model
                
                documents = [
                    {"text": "リコは主人公の少女探窟家です。", "title": "キャラクター1"},
                    {"text": "レグはロボットの少年です。", "title": "キャラクター2"},
                    {"text": "ナナチは成れ果てです。", "title": "キャラクター3"}
                ]
                
                total_vectors = 0
                for doc in documents:
                    vector_count = client.add_document(
                        vector_bucket_name=test_environment["VECTOR_BUCKET_NAME"],
                        index_name=test_environment["VECTOR_INDEX_NAME"],
                        text=doc["text"],
                        title=doc["title"]
                    )
                    total_vectors += vector_count
                
                # 全てのドキュメントが追加されたことを確認
                assert total_vectors > 0
                assert mock_s3vectors_client.put_vectors.call_count == len(documents)

    def test_error_handling_integration(
        self, 
        test_environment, 
        mock_embedding_model
    ):
        """エラーハンドリングの統合テスト"""
        
        with patch('boto3.client') as mock_boto3:
            with patch('src.s3_vectors_client.BedrockEmbeddings') as mock_bedrock:
                
                # S3Vectorsクライアントでエラーを発生させる
                mock_s3vectors = Mock()
                mock_s3vectors.put_vectors.side_effect = Exception("S3 Vectors connection error")
                mock_s3vectors.query_vectors.side_effect = Exception("S3 Vectors query error")
                
                mock_boto3.return_value = mock_s3vectors
                mock_bedrock.return_value = mock_embedding_model
                
                client = S3VectorsClient()
                client.s3vectors_client = mock_s3vectors
                client.embedding_model = mock_embedding_model
                
                # put_vectorsエラーのテスト
                vectors = [{"key": "test", "data": {"float32": [0.1, 0.2]}, "metadata": {"text": "test"}}]
                with pytest.raises(Exception, match="S3 Vectors connection error"):
                    client.put_vectors(
                        test_environment["VECTOR_BUCKET_NAME"],
                        test_environment["VECTOR_INDEX_NAME"],
                        vectors
                    )
                
                # query_vectorsエラーのテスト  
                with pytest.raises(Exception, match="S3 Vectors query error"):
                    client.query_vectors(
                        test_environment["VECTOR_BUCKET_NAME"],
                        test_environment["VECTOR_INDEX_NAME"],
                        "test question"
                    )

    def test_embedding_model_integration(
        self, 
        test_environment,
        mock_s3vectors_client
    ):
        """埋め込みモデルとの統合テスト"""
        
        with patch('boto3.client') as mock_boto3:
            with patch('src.s3_vectors_client.BedrockEmbeddings') as mock_bedrock:
                
                # 実際のEmbedding処理をシミュレート
                mock_embedding = Mock()
                # 呼び出し回数に応じて異なる埋め込みベクトルを返す
                mock_embedding.embed_query.side_effect = [
                    [0.1, 0.2, 0.3] * 512,  # ドキュメント用
                    [0.4, 0.5, 0.6] * 512   # 質問用
                ]
                
                mock_boto3.return_value = mock_s3vectors_client
                mock_bedrock.return_value = mock_embedding
                
                client = S3VectorsClient()
                client.s3vectors_client = mock_s3vectors_client
                client.embedding_model = mock_embedding
                
                # ドキュメント追加（embedding呼び出し1回目）
                client.add_document(
                    test_environment["VECTOR_BUCKET_NAME"],
                    test_environment["VECTOR_INDEX_NAME"],
                    "テストドキュメント",
                    "テストタイトル"
                )
                
                # 質問検索（embedding呼び出し2回目）
                client.query_vectors(
                    test_environment["VECTOR_BUCKET_NAME"],
                    test_environment["VECTOR_INDEX_NAME"],
                    "テスト質問"
                )
                
                # Embeddingが適切に呼び出されたことを確認
                assert mock_embedding.embed_query.call_count >= 2
                call_args_list = mock_embedding.embed_query.call_args_list
                assert "テストドキュメント" in str(call_args_list)
                assert "テスト質問" in str(call_args_list)