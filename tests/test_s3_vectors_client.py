import pytest
from unittest.mock import Mock, patch, MagicMock
from src.s3_vectors_client import S3VectorsClient


class TestS3VectorsClient:
    """S3VectorsClientのテストクラス"""
    
    @patch('boto3.client')
    @patch('src.s3_vectors_client.BedrockEmbeddings')
    def test_init(self, mock_bedrock_embeddings, mock_boto3_client):
        """初期化のテスト"""
        client = S3VectorsClient(region="us-west-2")
        
        assert client.region == "us-west-2"
        assert mock_boto3_client.call_count == 2  # bedrock-runtime and s3vectors
        mock_bedrock_embeddings.assert_called_once()
    
    @patch('boto3.client')
    @patch('src.s3_vectors_client.BedrockEmbeddings')
    def test_create_vectors_from_text(self, mock_bedrock_embeddings, mock_boto3_client):
        """テキストからベクトル作成のテスト"""
        # モックの設定
        mock_embedding = Mock()
        mock_embedding.embed_query.return_value = [0.1, 0.2, 0.3]
        mock_bedrock_embeddings.return_value = mock_embedding
        
        client = S3VectorsClient()
        
        # テストデータ
        text = "これはテストテキストです。" * 50  # 長いテキストを作成
        title = "テストタイトル"
        
        vectors = client.create_vectors_from_text(text, title, chunk_size=500)
        
        # アサーション
        assert len(vectors) > 0
        assert all('key' in vector for vector in vectors)
        assert all('data' in vector for vector in vectors)
        assert all('metadata' in vector for vector in vectors)
        
        # メタデータの確認
        for vector in vectors:
            assert vector['metadata']['title'] == title
            assert 'text' in vector['metadata']
    
    @patch('boto3.client')
    @patch('src.s3_vectors_client.BedrockEmbeddings')
    def test_put_vectors(self, mock_bedrock_embeddings, mock_boto3_client):
        """ベクトル格納のテスト"""
        mock_s3vectors = Mock()
        mock_boto3_client.return_value = mock_s3vectors
        
        client = S3VectorsClient()
        client.s3vectors_client = mock_s3vectors
        
        vectors = [
            {
                "key": "test-key",
                "data": {"float32": [0.1, 0.2, 0.3]},
                "metadata": {"text": "test", "title": "test"}
            }
        ]
        
        client.put_vectors("test-bucket", "test-index", vectors)
        
        mock_s3vectors.put_vectors.assert_called_once_with(
            vectorBucketName="test-bucket",
            indexName="test-index",
            vectors=vectors
        )
    
    @patch('boto3.client')
    @patch('src.s3_vectors_client.BedrockEmbeddings')
    def test_query_vectors(self, mock_bedrock_embeddings, mock_boto3_client):
        """ベクトル検索のテスト"""
        # モックの設定
        mock_embedding = Mock()
        mock_embedding.embed_query.return_value = [0.1, 0.2, 0.3]
        mock_bedrock_embeddings.return_value = mock_embedding
        
        mock_s3vectors = Mock()
        mock_s3vectors.query_vectors.return_value = {
            "vectors": [
                {
                    "key": "test-key",
                    "metadata": {"text": "test text", "title": "test title"},
                    "distance": 0.5
                }
            ]
        }
        mock_boto3_client.return_value = mock_s3vectors
        
        client = S3VectorsClient()
        client.s3vectors_client = mock_s3vectors
        client.embedding_model = mock_embedding
        
        result = client.query_vectors("test-bucket", "test-index", "test question", top_k=5)
        
        # アサーション
        mock_embedding.embed_query.assert_called_with("test question")
        mock_s3vectors.query_vectors.assert_called_once_with(
            vectorBucketName="test-bucket",
            indexName="test-index",
            queryVector={"float32": [0.1, 0.2, 0.3]},
            topK=5,
            returnMetadata=True,
            returnDistance=True
        )
        assert len(result) == 1
        assert result[0]["key"] == "test-key"
    
    @patch('boto3.client')
    @patch('src.s3_vectors_client.BedrockEmbeddings')
    def test_add_document(self, mock_bedrock_embeddings, mock_boto3_client):
        """ドキュメント追加のテスト"""
        mock_embedding = Mock()
        mock_embedding.embed_query.return_value = [0.1, 0.2, 0.3]
        mock_bedrock_embeddings.return_value = mock_embedding
        
        mock_s3vectors = Mock()
        mock_boto3_client.return_value = mock_s3vectors
        
        client = S3VectorsClient()
        client.s3vectors_client = mock_s3vectors
        client.embedding_model = mock_embedding
        
        with patch.object(client, 'create_vectors_from_text') as mock_create:
            with patch.object(client, 'put_vectors') as mock_put:
                mock_create.return_value = [{"test": "vector1"}, {"test": "vector2"}]
                
                result = client.add_document("test-bucket", "test-index", "test text", "test title")
                
                mock_create.assert_called_once_with("test text", "test title")
                mock_put.assert_called_once_with("test-bucket", "test-index", [{"test": "vector1"}, {"test": "vector2"}])
                assert result == 2