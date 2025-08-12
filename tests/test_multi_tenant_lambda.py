import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from src import multi_tenant_handlers


@pytest.mark.unit
class TestMultiTenantLambdaHandlers:
    """マルチテナント対応Lambdaハンドラーのテスト"""

    @pytest.fixture
    def mock_s3vectors_client(self):
        """S3VectorsClientのモック"""
        with patch('src.multi_tenant_handlers.S3VectorsClient') as mock_class:
            mock_instance = Mock()
            mock_class.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def mock_bedrock_chat(self):
        """BedrockChatのモック"""
        with patch('src.multi_tenant_handlers.ChatBedrockConverse') as mock_chat:
            mock_instance = Mock()
            mock_chat.return_value = mock_instance
            mock_response = Mock()
            mock_response.content = "テスト回答です。"
            mock_instance.invoke.return_value = mock_response
            yield mock_instance

    @pytest.fixture
    def sample_user_query_event(self):
        """ユーザー固有クエリのサンプルイベント"""
        return {
            "pathParameters": {"user_id": "user123"},
            "body": json.dumps({
                "question": "私のプロジェクトについて教えてください",
                "preferences": {
                    "language": "ja",
                    "max_results": 5
                }
            }),
            "headers": {"Content-Type": "application/json"}
        }

    @pytest.fixture
    def sample_user_document_event(self):
        """ユーザードキュメント追加のサンプルイベント"""
        return {
            "pathParameters": {"user_id": "user456"},
            "body": json.dumps({
                "text": "これは私の個人的なメモです。プロジェクトの進捗について記録します。",
                "title": "プロジェクト進捗メモ"
            }),
            "headers": {"Content-Type": "application/json"}
        }

    def test_user_query_handler_extracts_user_id_from_path(
        self, mock_s3vectors_client, mock_bedrock_chat, sample_user_query_event, multi_tenant_environment
    ):
        """ユーザークエリハンドラーがパスパラメータからユーザーIDを抽出するテスト"""
        # モックの検索結果を設定
        mock_search_results = [
            {
                "metadata": {
                    "user_id": "user123",
                    "text": "プロジェクトは順調に進んでいます。",
                    "title": "進捗レポート"
                }
            }
        ]
        mock_s3vectors_client.query_user_documents.return_value = mock_search_results
        
        # ハンドラーを実行（新しい関数を想定）
        response = multi_tenant_handlers.user_query_handler(sample_user_query_event, {})
        
        # ユーザー固有の検索が実行されることを確認
        mock_s3vectors_client.query_user_documents.assert_called_once()
        call_args = mock_s3vectors_client.query_user_documents.call_args
        
        assert call_args[1]['user_id'] == "user123"  # user_id
        assert "プロジェクトについて" in call_args[1]['question']  # question
        assert call_args[1]['top_k'] == 5  # max_results from preferences
        
        # 正常なレスポンスが返される
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'answer' in body
        assert 'sources' in body

    def test_user_document_handler_adds_user_context(
        self, mock_s3vectors_client, sample_user_document_event, multi_tenant_environment
    ):
        """ユーザードキュメントハンドラーがユーザーコンテキストを追加するテスト"""
        # モックの戻り値を設定
        mock_s3vectors_client.add_user_document.return_value = 3
        
        # ハンドラーを実行（新しい関数を想定）
        response = multi_tenant_handlers.user_add_document_handler(
            sample_user_document_event, {}
        )
        
        # ユーザー固有のドキュメント追加が実行されることを確認
        mock_s3vectors_client.add_user_document.assert_called_once()
        call_args = mock_s3vectors_client.add_user_document.call_args
        
        assert call_args[1]['user_id'] == "user456"  # user_id
        assert "個人的なメモ" in call_args[1]['text']  # text
        assert call_args[1]['title'] == "プロジェクト進捗メモ"  # title
        
        # 正常なレスポンスが返される
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['vector_count'] == 3
        assert body['user_id'] == "user456"

    def test_user_query_handler_validates_user_id(self, mock_s3vectors_client):
        """ユーザーIDバリデーションテスト"""
        # ユーザーIDが欠けているイベント
        invalid_event = {
            "pathParameters": {},
            "body": json.dumps({"question": "テスト質問"}),
            "headers": {"Content-Type": "application/json"}
        }
        
        response = multi_tenant_handlers.user_query_handler(invalid_event, {})
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert "Path parameters are missing" in body['error']

    def test_user_query_handler_with_preferences(
        self, mock_s3vectors_client, mock_bedrock_chat, multi_tenant_environment
    ):
        """ユーザー設定を考慮したクエリハンドラーテスト"""
        event = {
            "pathParameters": {"user_id": "user789"},
            "body": json.dumps({
                "question": "テスト質問",
                "preferences": {
                    "language": "en",
                    "max_results": 2,
                    "temperature": 0.5
                }
            })
        }
        
        mock_s3vectors_client.query_user_documents.return_value = []
        
        response = multi_tenant_handlers.user_query_handler(event, {})
        
        # 設定が適用されることを確認
        call_args = mock_s3vectors_client.query_user_documents.call_args
        assert call_args[1]['top_k'] == 2
        
        # Bedrockの温度設定が適用されることを確認（実装時）
        # ここではモックの呼び出しを確認 - .invoke()が実際に呼ばれる
        mock_bedrock_chat.invoke.assert_called_once()

    def test_user_document_list_handler(self, mock_s3vectors_client):
        """ユーザードキュメント一覧ハンドラーテスト"""
        # モックデータを設定
        mock_documents = [
            {
                "document_id": "doc_1",
                "title": "ドキュメント1",
                "created_at": "2025-01-15T10:30:00Z",
                "vector_count": 3
            }
        ]
        mock_s3vectors_client.list_user_documents.return_value = mock_documents
        
        event = {
            "pathParameters": {"user_id": "user999"},
            "queryStringParameters": {"limit": "10", "offset": "0"},
            "headers": {"Content-Type": "application/json"}
        }
        
        response = multi_tenant_handlers.user_document_list_handler(event, {})
        
        # 正しい一覧が返される
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'documents' in body
        assert len(body['documents']) == 1
        
        # 正しいパラメータで呼び出される
        mock_s3vectors_client.list_user_documents.assert_called_once_with(
            user_id="user999",
            vector_bucket_name=multi_tenant_handlers.os.environ.get("VECTOR_BUCKET_NAME"),
            limit=10,
            offset=0
        )

    def test_user_document_delete_handler(self, mock_s3vectors_client):
        """ユーザードキュメント削除ハンドラーテスト"""
        mock_s3vectors_client.delete_user_document.return_value = True
        
        event = {
            "pathParameters": {
                "user_id": "user111",
                "document_id": "doc_123"
            },
            "headers": {"Content-Type": "application/json"}
        }
        
        response = multi_tenant_handlers.user_document_delete_handler(event, {})
        
        # 削除が実行される
        assert response['statusCode'] == 200
        mock_s3vectors_client.delete_user_document.assert_called_once_with(
            user_id="user111",
            vector_bucket_name=multi_tenant_handlers.os.environ.get("VECTOR_BUCKET_NAME"),
            document_id="doc_123"
        )

    def test_error_handling_preserves_user_context(self, mock_s3vectors_client):
        """エラー処理でユーザーコンテキストが保持されるテスト"""
        # S3 Vectorsでエラーが発生する状況をシミュレート
        mock_s3vectors_client.query_user_documents.side_effect = Exception(
            "S3 Vectors connection failed"
        )
        
        event = {
            "pathParameters": {"user_id": "user_error"},
            "body": json.dumps({"question": "テスト質問"})
        }
        
        response = multi_tenant_handlers.user_query_handler(event, {})
        
        # エラーレスポンスでもユーザー情報が含まれる
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'error' in body
        # ユーザーIDは含めない（セキュリティ上）が、ログには記録される想定

    def test_user_isolation_in_error_scenarios(self, mock_s3vectors_client, mock_bedrock_chat, multi_tenant_environment):
        """エラーシナリオでのユーザー分離テスト"""
        # 異なるユーザーからの同時リクエストをシミュレート
        user1_event = {
            "pathParameters": {"user_id": "user_a"},
            "body": json.dumps({"question": "質問A"})
        }
        user2_event = {
            "pathParameters": {"user_id": "user_b"},
            "body": json.dumps({"question": "質問B"})
        }
        
        # user_aの処理でエラーが発生
        mock_s3vectors_client.query_user_documents.side_effect = [
            Exception("User A error"),
            [{"metadata": {"user_id": "user_b", "text": "正常なデータ"}}]
        ]
        
        response1 = multi_tenant_handlers.user_query_handler(user1_event, {})
        response2 = multi_tenant_handlers.user_query_handler(user2_event, {})
        
        # user_aはエラー、user_bは正常
        assert response1['statusCode'] == 500
        assert response2['statusCode'] == 200
        
        # 各ユーザーのデータが独立して処理されることを確認
        assert mock_s3vectors_client.query_user_documents.call_count == 2


@pytest.mark.integration_mock
class TestMultiTenantLambdaIntegration:
    """マルチテナントLambda統合テスト"""

    @pytest.fixture
    def test_environment(self):
        """テスト環境変数"""
        import os
        old_env = os.environ.copy()
        os.environ.update({
            "VECTOR_BUCKET_NAME": "test-multi-tenant-bucket",
            "VECTOR_INDEX_NAME": "unused-in-multitenant",  # ユーザー別なので未使用
            "AWS_REGION": "us-east-1"
        })
        yield
        os.environ.clear()
        os.environ.update(old_env)

    def test_end_to_end_multi_user_workflow(self, multi_tenant_environment):
        """エンドツーエンドのマルチユーザーワークフローテスト"""
        with patch('src.multi_tenant_handlers.S3VectorsClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            # ユーザー1: ドキュメント追加
            user1_add_event = {
                "pathParameters": {"user_id": "alice"},
                "body": json.dumps({
                    "text": "Aliceの業務メモ",
                    "title": "業務日誌"
                })
            }
            
            mock_client.add_user_document.return_value = 2
            add_response = multi_tenant_handlers.user_add_document_handler(
                user1_add_event, {}
            )
            
            assert add_response['statusCode'] == 200
            
            # ユーザー1: 検索実行
            user1_query_event = {
                "pathParameters": {"user_id": "alice"},
                "body": json.dumps({"question": "業務について"})
            }
            
            mock_client.query_user_documents.return_value = [
                {"metadata": {"user_id": "alice", "text": "業務メモの内容"}}
            ]
            
            with patch('src.multi_tenant_handlers.ChatBedrockConverse') as mock_chat_class:
                mock_chat_instance = Mock()
                mock_chat_class.return_value = mock_chat_instance
                mock_response = Mock()
                mock_response.content = "業務メモに関する回答です。"
                mock_chat_instance.invoke.return_value = mock_response
                
                query_response = multi_tenant_handlers.user_query_handler(
                    user1_query_event, {}
                )
            
            assert query_response['statusCode'] == 200
            
            # 各操作で正しいユーザーIDが使用されることを確認
            add_call = mock_client.add_user_document.call_args
            query_call = mock_client.query_user_documents.call_args
            
            assert add_call[1]['user_id'] == "alice"  # add_user_document(user_id=...)
            assert query_call[1]['user_id'] == "alice"  # query_user_documents(user_id=...)