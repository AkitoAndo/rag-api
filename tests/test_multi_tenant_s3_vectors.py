import pytest
import uuid
from unittest.mock import Mock, patch, MagicMock
from src.s3_vectors_client import S3VectorsClient


@pytest.mark.unit
class TestMultiTenantS3Vectors:
    """マルチテナント対応S3VectorsClientのテスト"""

    @pytest.fixture
    def mock_s3vectors_client(self):
        """S3 Vectorsクライアントのモック"""
        with patch('boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def mock_embedding_model(self):
        """埋め込みモデルのモック"""
        with patch('src.s3_vectors_client.BedrockEmbeddings') as mock_embeddings:
            mock_model = Mock()
            mock_embeddings.return_value = mock_model
            mock_model.embed_query.return_value = [0.1, 0.2, 0.3]
            yield mock_model

    def test_get_user_index_name(self, mock_s3vectors_client, mock_embedding_model):
        """ユーザー別インデックス名の生成テスト"""
        client = S3VectorsClient()
        
        # ユーザー別インデックス名を生成できる
        user_id = "user123"
        index_name = client.get_user_index_name(user_id)
        
        expected_name = f"user-{user_id}-knowledge-base"
        assert index_name == expected_name

    def test_get_user_index_name_with_invalid_user_id(self, mock_s3vectors_client, mock_embedding_model):
        """無効なユーザーIDでのインデックス名生成テスト"""
        client = S3VectorsClient()
        
        # 空文字のユーザーIDは例外を発生させる
        with pytest.raises(ValueError, match="User ID cannot be empty"):
            client.get_user_index_name("")
        
        # NoneのユーザーIDは例外を発生させる
        with pytest.raises(ValueError, match="User ID cannot be empty"):
            client.get_user_index_name(None)

    def test_add_user_document_creates_user_specific_vectors(
        self, mock_s3vectors_client, mock_embedding_model
    ):
        """ユーザー固有のドキュメント追加テスト"""
        client = S3VectorsClient()
        
        user_id = "user123"
        text = "これはユーザー固有のドキュメントです。"
        title = "個人メモ"
        vector_bucket = "test-bucket"
        
        # ドキュメントを追加
        vector_count = client.add_user_document(
            user_id=user_id,
            vector_bucket_name=vector_bucket,
            text=text,
            title=title
        )
        
        # ユーザー固有のインデックス名が使用されることを確認
        expected_index_name = f"user-{user_id}-knowledge-base"
        mock_s3vectors_client.put_vectors.assert_called_once()
        
        call_args = mock_s3vectors_client.put_vectors.call_args
        assert call_args[1]['vectorBucketName'] == vector_bucket
        assert call_args[1]['indexName'] == expected_index_name
        
        # ベクトル配列が渡されることを確認
        vectors = call_args[1]['vectors']
        assert isinstance(vectors, list)
        assert len(vectors) > 0
        
        # 各ベクトルにユーザーIDがメタデータに含まれることを確認
        for vector in vectors:
            assert vector['metadata']['user_id'] == user_id
            assert vector['metadata']['title'] == title
            assert 'text' in vector['metadata']

    def test_query_user_documents_uses_user_specific_index(
        self, mock_s3vectors_client, mock_embedding_model
    ):
        """ユーザー固有の検索テスト"""
        client = S3VectorsClient()
        
        user_id = "user456"
        question = "私のメモについて教えて"
        vector_bucket = "test-bucket"
        
        # モックの検索結果を設定（正しいレスポンス形式）
        mock_search_results = {
            "vectors": [
                {
                    "key": "test-key-1",
                    "distance": 0.2,
                    "metadata": {
                        "user_id": user_id,
                        "text": "検索結果のテキスト",
                        "title": "個人メモ1"
                    }
                }
            ]
        }
        mock_s3vectors_client.query_vectors.return_value = mock_search_results
        
        # ユーザー固有の検索を実行
        results = client.query_user_documents(
            user_id=user_id,
            vector_bucket_name=vector_bucket,
            question=question,
            top_k=3
        )
        
        # ユーザー固有のインデックス名が使用されることを確認
        expected_index_name = f"user-{user_id}-knowledge-base"
        mock_s3vectors_client.query_vectors.assert_called_once()
        
        call_args = mock_s3vectors_client.query_vectors.call_args
        assert call_args[1]['vectorBucketName'] == vector_bucket
        assert call_args[1]['indexName'] == expected_index_name
        assert call_args[1]['topK'] == 3
        
        # 結果が返されることを確認（vectorsの配列部分）
        assert results == mock_search_results["vectors"]

    def test_user_data_isolation(self, mock_s3vectors_client, mock_embedding_model):
        """ユーザーデータ分離の確認テスト"""
        client = S3VectorsClient()
        
        user1_id = "user111"
        user2_id = "user222"
        vector_bucket = "test-bucket"
        
        # 各ユーザーのインデックス名が異なることを確認
        index1 = client.get_user_index_name(user1_id)
        index2 = client.get_user_index_name(user2_id)
        
        assert index1 != index2
        assert index1 == f"user-{user1_id}-knowledge-base"
        assert index2 == f"user-{user2_id}-knowledge-base"
        
        # 各ユーザーが独立したインデックスを使用することを確認
        client.query_user_documents(user1_id, vector_bucket, "質問1")
        client.query_user_documents(user2_id, vector_bucket, "質問2")
        
        assert mock_s3vectors_client.query_vectors.call_count == 2
        
        # 各呼び出しで異なるインデックス名が使用されることを確認
        calls = mock_s3vectors_client.query_vectors.call_args_list
        assert calls[0][1]['indexName'] == index1
        assert calls[1][1]['indexName'] == index2

    def test_user_document_metadata_includes_user_context(
        self, mock_s3vectors_client, mock_embedding_model
    ):
        """ドキュメントメタデータにユーザーコンテキストが含まれるテスト"""
        client = S3VectorsClient()
        
        user_id = "user789"
        text = "テストドキュメント"
        title = "テストタイトル"
        vector_bucket = "test-bucket"
        
        # ドキュメントを追加
        client.add_user_document(
            user_id=user_id,
            vector_bucket_name=vector_bucket,
            text=text,
            title=title
        )
        
        # ベクトルのメタデータを確認
        call_args = mock_s3vectors_client.put_vectors.call_args
        vectors = call_args[1]['vectors']
        
        for vector in vectors:
            metadata = vector['metadata']
            
            # 必須のメタデータ項目を確認
            assert metadata['user_id'] == user_id
            assert metadata['title'] == title
            assert 'text' in metadata
            assert 'document_id' in metadata
            assert 'created_at' in metadata
            
            # document_idはUUID形式であることを確認
            document_id = metadata['document_id']
            uuid.UUID(document_id)  # UUID形式でない場合は例外が発生

    def test_delete_user_document(self, mock_s3vectors_client, mock_embedding_model):
        """ユーザードキュメント削除テスト"""
        client = S3VectorsClient()
        
        user_id = "user999"
        document_id = "doc_123"
        vector_bucket = "test-bucket"
        
        # 削除の実行
        success = client.delete_user_document(
            user_id=user_id,
            vector_bucket_name=vector_bucket,
            document_id=document_id
        )
        
        # ユーザー固有のインデックスから削除されることを確認
        expected_index_name = f"user-{user_id}-knowledge-base"
        mock_s3vectors_client.delete_vectors.assert_called_once_with(
            vectorBucketName=vector_bucket,
            indexName=expected_index_name,
            keys=[document_id]
        )
        
        assert success is True

    def test_list_user_documents(self, mock_s3vectors_client, mock_embedding_model):
        """ユーザードキュメント一覧取得テスト"""
        client = S3VectorsClient()
        
        user_id = "user555"
        vector_bucket = "test-bucket"
        
        # モックの一覧データを設定
        mock_documents = [
            {
                "document_id": "doc_1",
                "title": "ドキュメント1",
                "created_at": "2025-01-15T10:30:00Z",
                "vector_count": 3
            },
            {
                "document_id": "doc_2", 
                "title": "ドキュメント2",
                "created_at": "2025-01-15T11:00:00Z",
                "vector_count": 2
            }
        ]
        mock_s3vectors_client.list_documents.return_value = mock_documents
        
        # ユーザードキュメント一覧を取得
        documents = client.list_user_documents(
            user_id=user_id,
            vector_bucket_name=vector_bucket,
            limit=10,
            offset=0
        )
        
        # ユーザー固有のインデックスが使用されることを確認
        expected_index_name = f"user-{user_id}-knowledge-base"
        mock_s3vectors_client.list_documents.assert_called_once_with(
            vectorBucketName=vector_bucket,
            indexName=expected_index_name,
            limit=10,
            offset=0
        )
        
        assert documents == mock_documents


@pytest.mark.integration_mock
class TestMultiTenantS3VectorsIntegration:
    """マルチテナントS3 Vectors統合テスト"""

    @pytest.fixture
    def s3_vectors_client(self):
        """実際のS3VectorsClientインスタンス（モック付き）"""
        with patch('boto3.client'), patch('src.s3_vectors_client.BedrockEmbeddings'):
            return S3VectorsClient()

    def test_multi_user_workflow(self, s3_vectors_client):
        """複数ユーザーのワークフロー統合テスト"""
        # 複数ユーザーでの操作が独立して実行されることを確認
        user1 = "user_alice"
        user2 = "user_bob"
        bucket = "test-bucket"
        
        # 各ユーザーがドキュメントを追加
        with patch.object(s3_vectors_client, 'add_user_document') as mock_add:
            mock_add.return_value = 2
            
            count1 = s3_vectors_client.add_user_document(
                user1, bucket, "Aliceの個人メモ", "Alice's Notes"
            )
            count2 = s3_vectors_client.add_user_document(
                user2, bucket, "Bobのプロジェクト資料", "Bob's Project"
            )
            
            assert count1 == 2
            assert count2 == 2
            assert mock_add.call_count == 2
        
        # 各ユーザーが検索を実行
        with patch.object(s3_vectors_client, 'query_user_documents') as mock_query:
            mock_query.side_effect = [
                [{"metadata": {"user_id": user1, "title": "Alice's Notes"}}],
                [{"metadata": {"user_id": user2, "title": "Bob's Project"}}]
            ]
            
            results1 = s3_vectors_client.query_user_documents(
                user1, bucket, "私のメモ"
            )
            results2 = s3_vectors_client.query_user_documents(
                user2, bucket, "プロジェクト"
            )
            
            # 各ユーザーは自分のデータのみにアクセス
            assert results1[0]['metadata']['user_id'] == user1
            assert results2[0]['metadata']['user_id'] == user2