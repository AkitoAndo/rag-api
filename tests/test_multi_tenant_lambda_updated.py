"""
マルチテナント対応Lambdaハンドラーの更新されたテスト（Cognito認証ベース）
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# テスト用のパス設定
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from multi_tenant_handlers import (
    user_query_handler,
    user_add_document_handler, 
    user_document_list_handler,
    user_document_delete_handler,
    extract_user_id_from_cognito
)


@pytest.mark.unit
class TestMultiTenantLambdaHandlersWithCognito:
    """Cognito認証ベースのマルチテナントLambdaハンドラーテスト"""

    @pytest.fixture
    def mock_s3vectors_client(self):
        """S3VectorsClientのモック"""
        with patch('multi_tenant_handlers.S3VectorsClient') as mock_class:
            mock_instance = Mock()
            mock_class.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def mock_bedrock_chat(self):
        """BedrockChatのモック"""
        with patch('multi_tenant_handlers.ChatBedrockConverse') as mock_chat:
            mock_instance = Mock()
            mock_chat.return_value = mock_instance
            mock_response = Mock()
            mock_response.content = "Cognito認証テスト回答です。"
            mock_instance.invoke.return_value = mock_response
            yield mock_instance

    @pytest.fixture
    def cognito_event_base(self):
        """基本的なCognitoイベント"""
        return {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "test-user-123",
                        "email": "testuser@example.com",
                        "cognito:username": "testuser"
                    }
                }
            }
        }

    def test_user_query_handler_extracts_user_id_from_cognito(self, mock_s3vectors_client, mock_bedrock_chat, cognito_event_base):
        """CognitoクレームからユーザーIDを正しく抽出してクエリ処理"""
        # イベントの設定
        event = cognito_event_base.copy()
        event["body"] = json.dumps({
            "question": "Cognitoテストクエリ"
        })

        # S3Vectorsクライアントのモック設定
        mock_s3vectors_client.query_user_vectors.return_value = [
            {
                "metadata": {
                    "text": "Cognitoテストドキュメント",
                    "title": "Test Doc"
                }
            }
        ]

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_query_handler(event, {})

        assert response['statusCode'] == 200
        
        # Cognitoから抽出されたユーザーIDで呼ばれたことを確認
        mock_s3vectors_client.query_user_vectors.assert_called_once_with(
            user_id="test-user-123",  # Cognitoのsubから抽出
            vector_bucket_name="test-bucket",
            question="Cognitoテストクエリ",
            top_k=3
        )

    def test_user_document_handler_adds_cognito_user_context(self, mock_s3vectors_client, cognito_event_base):
        """Cognitoユーザーコンテキストでドキュメント追加"""
        # イベントの設定
        event = cognito_event_base.copy()
        event["body"] = json.dumps({
            "title": "Cognitoユーザードキュメント",
            "text": "Cognito認証ユーザーのドキュメントです。"
        })

        # S3Vectorsクライアントのモック設定
        mock_s3vectors_client.add_user_document.return_value = 3

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_add_document_handler(event, {})

        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['user_id'] == "test-user-123"
        assert response_body['vector_count'] == 3

        # Cognitoユーザーコンテキストで呼ばれたことを確認
        mock_s3vectors_client.add_user_document.assert_called_once_with(
            user_id="test-user-123",
            vector_bucket_name="test-bucket",
            text="Cognito認証ユーザーのドキュメントです。",
            title="Cognitoユーザードキュメント"
        )

    def test_user_query_handler_validates_cognito_user_id(self, mock_s3vectors_client):
        """無効なCognitoクレームの検証"""
        # Cognitoクレームが不完全なイベント
        invalid_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        # "sub"フィールドが不足
                        "email": "incomplete@example.com"
                    }
                }
            },
            "body": json.dumps({
                "question": "不完全な認証のテスト"
            })
        }

        response = user_query_handler(invalid_event, {})
        
        assert response['statusCode'] == 500
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert "User ID not found in JWT token" in response_body['error']

        # S3Vectorsクライアントが呼ばれていないことを確認
        mock_s3vectors_client.query_user_vectors.assert_not_called()

    def test_user_document_list_handler_with_cognito(self, mock_s3vectors_client, cognito_event_base):
        """Cognito認証でのドキュメント一覧取得"""
        # ドキュメント一覧のモック
        mock_s3vectors_client.list_user_documents.return_value = [
            {
                "document_id": "doc1",
                "title": "Cognitoユーザードキュメント1",
                "created_at": "2024-01-01T00:00:00Z",
                "user_id": "test-user-123"
            },
            {
                "document_id": "doc2",
                "title": "Cognitoユーザードキュメント2", 
                "created_at": "2024-01-02T00:00:00Z",
                "user_id": "test-user-123"
            }
        ]

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_document_list_handler(cognito_event_base, {})

        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['user_id'] == "test-user-123"
        assert len(response_body['documents']) == 2

        # Cognitoユーザーでドキュメント一覧が取得されたことを確認
        mock_s3vectors_client.list_user_documents.assert_called_once_with(
            user_id="test-user-123",
            vector_bucket_name="test-bucket",
            limit=50
        )

    def test_user_document_delete_handler_with_cognito(self, mock_s3vectors_client, cognito_event_base):
        """Cognito認証でのドキュメント削除"""
        # パスパラメータの追加
        event = cognito_event_base.copy()
        event["pathParameters"] = {
            "document_id": "doc-to-delete-123"
        }

        # 削除成功のモック
        mock_s3vectors_client.delete_user_document.return_value = True

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_document_delete_handler(event, {})

        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['user_id'] == "test-user-123"
        assert response_body['document_id'] == "doc-to-delete-123"

        # Cognitoユーザーコンテキストでドキュメント削除が実行されたことを確認
        mock_s3vectors_client.delete_user_document.assert_called_once_with(
            user_id="test-user-123",  # JWTから抽出
            vector_bucket_name="test-bucket", 
            document_id="doc-to-delete-123"
        )

    def test_error_handling_preserves_cognito_user_context(self, mock_s3vectors_client, cognito_event_base):
        """エラー時もCognitoユーザーコンテキストを保持"""
        # S3Vectorsサービスエラーをシミュレート
        mock_s3vectors_client.add_user_document.side_effect = Exception("S3 Vectors error")

        event = cognito_event_base.copy()
        event["body"] = json.dumps({
            "title": "エラーテストドキュメント",
            "text": "このドキュメント追加は失敗します。"
        })

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_add_document_handler(event, {})

        assert response['statusCode'] == 500
        response_body = json.loads(response['body'])
        assert 'error' in response_body

        # エラーでもCognitoユーザーIDで呼ばれたことを確認
        mock_s3vectors_client.add_user_document.assert_called_once_with(
            user_id="test-user-123",
            vector_bucket_name="test-bucket",
            text="このドキュメント追加は失敗します。",
            title="エラーテストドキュメント"
        )

    def test_cognito_user_isolation_in_error_scenarios(self, cognito_event_base):
        """エラーシナリオでのCognitoユーザー分離"""
        # 複数ユーザーでのエラー処理テスト
        users = ["user-a", "user-b", "user-c"]
        
        for user_id in users:
            event = {
                "requestContext": {
                    "authorizer": {
                        "claims": {
                            "sub": user_id,
                            "email": f"{user_id}@example.com"
                        }
                    }
                },
                "body": json.dumps({
                    # 必須フィールド欠落
                    "invalid_field": "causes error"
                })
            }
            
            response = user_query_handler(event, {})
            
            assert response['statusCode'] == 500
            response_body = json.loads(response['body'])
            assert 'error' in response_body


@pytest.mark.integration_mock
class TestMultiTenantCognitoIntegration:
    """Cognito認証マルチテナント統合テスト"""

    @patch('multi_tenant_handlers.S3VectorsClient')
    @patch('multi_tenant_handlers.ChatBedrockConverse')
    def test_end_to_end_multi_user_cognito_workflow(self, mock_chat, mock_s3_client):
        """Cognito認証での完全なマルチユーザーワークフロー"""
        # S3VectorsClientとBedrockのモック設定
        mock_client_instance = Mock()
        mock_s3_client.return_value = mock_client_instance
        
        mock_chat_instance = Mock()
        mock_chat_instance.invoke.return_value.content = "統合テスト回答"
        mock_chat.return_value = mock_chat_instance
        
        # ユーザー1: ドキュメント追加
        user1_add_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "integration-user-1",
                        "email": "user1@integration.com",
                        "given_name": "Integration",
                        "family_name": "User1"
                    }
                }
            },
            "body": json.dumps({
                "title": "統合テストユーザー1のドキュメント",
                "text": "これはCognito認証統合テストのドキュメントです。"
            })
        }

        mock_client_instance.add_user_document.return_value = 2

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            add_response = user_add_document_handler(user1_add_event, {})

        assert add_response['statusCode'] == 200
        add_result = json.loads(add_response['body'])
        assert add_result['user_id'] == "integration-user-1"

        # ユーザー1: クエリ実行
        user1_query_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "integration-user-1",
                        "email": "user1@integration.com"
                    }
                }
            },
            "body": json.dumps({
                "question": "私のドキュメントについて教えて"
            })
        }

        mock_client_instance.query_user_vectors.return_value = [
            {
                "metadata": {
                    "text": "統合テストドキュメント内容",
                    "user_id": "integration-user-1"
                }
            }
        ]

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            query_response = user_query_handler(user1_query_event, {})

        assert query_response['statusCode'] == 200
        query_result = json.loads(query_response['body'])
        assert 'answer' in query_result

        # ドキュメント一覧取得
        mock_client_instance.list_user_documents.return_value = [
            {
                "document_id": "doc1",
                "title": "統合テストユーザー1のドキュメント",
                "created_at": "2024-01-01T00:00:00Z",
                "user_id": "integration-user-1"
            }
        ]

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            list_response = user_document_list_handler(user1_add_event, {})

        assert list_response['statusCode'] == 200
        list_result = json.loads(list_response['body'])
        assert list_result['user_id'] == "integration-user-1"
        assert len(list_result['documents']) == 1

        # 全ての操作でCognitoから同じユーザーIDが使用されたことを確認
        add_call = mock_client_instance.add_user_document.call_args
        query_call = mock_client_instance.query_user_vectors.call_args  
        list_call = mock_client_instance.list_user_documents.call_args

        assert add_call.kwargs['user_id'] == "integration-user-1"
        assert query_call.kwargs['user_id'] == "integration-user-1"
        assert list_call.kwargs['user_id'] == "integration-user-1"