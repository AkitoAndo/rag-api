"""
マルチテナント機能の統合テスト
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import uuid

# テスト用のパス設定
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# モジュールインポート
from multi_tenant_handlers import (
    user_query_handler, 
    user_add_document_handler,
    user_document_list_handler,
    user_document_delete_handler
)
from s3_vectors_client import S3VectorsClient


class TestMultiTenantDataIsolation:
    """マルチテナント機能のデータ分離テスト"""

    @patch('multi_tenant_handlers.S3VectorsClient')
    @patch('multi_tenant_handlers.ChatBedrockConverse')
    def test_user_data_isolation_in_queries(self, mock_chat, mock_s3_client):
        """ユーザー間のデータ分離をテスト"""
        # S3VectorsClientのモックを設定
        mock_client_instance = Mock()
        mock_s3_client.return_value = mock_client_instance
        
        # Bedrockのモック設定
        mock_chat_instance = Mock()
        mock_chat_instance.invoke.return_value.content = "ユーザー固有の回答"
        mock_chat.return_value = mock_chat_instance

        # ユーザー1のクエリ
        user1_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "user-001",
                        "email": "user1@example.com"
                    }
                }
            },
            "body": json.dumps({
                "question": "私のドキュメントについて教えて"
            })
        }

        # ユーザー1のドキュメントを返すモック
        mock_client_instance.query_user_vectors.return_value = [
            {
                "metadata": {
                    "text": "ユーザー1のドキュメント",
                    "title": "User1 Doc",
                    "user_id": "user-001"
                }
            }
        ]

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_query_handler(user1_event, {})

        assert response['statusCode'] == 200
        
        # ユーザー1のインデックスが使用されたことを確認
        mock_client_instance.query_user_vectors.assert_called_with(
            user_id="user-001",
            vector_bucket_name="test-bucket",
            question="私のドキュメントについて教えて",
            top_k=3
        )

        # ユーザー2のクエリでリセット
        mock_client_instance.reset_mock()
        
        user2_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "user-002",
                        "email": "user2@example.com"
                    }
                }
            },
            "body": json.dumps({
                "question": "私のドキュメントについて教えて"
            })
        }

        # ユーザー2のドキュメントを返すモック
        mock_client_instance.query_user_vectors.return_value = [
            {
                "metadata": {
                    "text": "ユーザー2のドキュメント",
                    "title": "User2 Doc", 
                    "user_id": "user-002"
                }
            }
        ]

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_query_handler(user2_event, {})

        assert response['statusCode'] == 200
        
        # ユーザー2のインデックスが使用されたことを確認
        mock_client_instance.query_user_vectors.assert_called_with(
            user_id="user-002",
            vector_bucket_name="test-bucket",
            question="私のドキュメントについて教えて",
            top_k=3
        )

    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_document_addition_with_user_isolation(self, mock_s3_client):
        """ドキュメント追加時のユーザー分離"""
        mock_client_instance = Mock()
        mock_client_instance.add_user_document.return_value = 3
        mock_s3_client.return_value = mock_client_instance

        # ユーザー1のドキュメント追加
        user1_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "user-alpha",
                        "cognito:username": "alpha"
                    }
                }
            },
            "body": json.dumps({
                "title": "ユーザーAlphaのドキュメント",
                "text": "これはユーザーAlpha専用のコンテンツです。"
            })
        }

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_add_document_handler(user1_event, {})

        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['user_id'] == "user-alpha"
        assert response_body['vector_count'] == 3

        # ユーザーAlpha専用でドキュメントが追加されたことを確認
        mock_client_instance.add_user_document.assert_called_with(
            user_id="user-alpha",
            vector_bucket_name="test-bucket",
            text="これはユーザーAlpha専用のコンテンツです。",
            title="ユーザーAlphaのドキュメント"
        )

    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_document_list_user_isolation(self, mock_s3_client):
        """ドキュメント一覧のユーザー分離"""
        mock_client_instance = Mock()
        mock_client_instance.list_user_documents.return_value = [
            {
                "document_id": "doc1",
                "title": "ユーザーベータ文書1",
                "created_at": "2024-01-01T00:00:00Z",
                "user_id": "user-beta"
            },
            {
                "document_id": "doc2", 
                "title": "ユーザーベータ文書2",
                "created_at": "2024-01-02T00:00:00Z",
                "user_id": "user-beta"
            }
        ]
        mock_s3_client.return_value = mock_client_instance

        user_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "user-beta",
                        "email": "beta@example.com"
                    }
                }
            }
        }

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_document_list_handler(user_event, {})

        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['user_id'] == "user-beta"
        assert len(response_body['documents']) == 2
        
        # 全てのドキュメントがuser-betaのものであることを確認
        for doc in response_body['documents']:
            assert doc['user_id'] == "user-beta"

        mock_client_instance.list_user_documents.assert_called_with(
            user_id="user-beta",
            vector_bucket_name="test-bucket",
            limit=50
        )


class TestMultiTenantSecurityBoundaries:
    """マルチテナントセキュリティ境界のテスト"""

    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_prevent_cross_tenant_access(self, mock_s3_client):
        """クロステナントアクセス防止"""
        mock_client_instance = Mock()
        mock_s3_client.return_value = mock_client_instance

        # ユーザーAがユーザーBのドキュメントを削除しようとする
        # （実際のパスパラメータではなく、JWTトークンからユーザーIDを取得するため、
        #  異なるユーザーのドキュメントIDを指定しても自分のユーザーIDでアクセスされる）
        
        user_a_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "user-a",
                        "email": "usera@example.com"
                    }
                }
            },
            "pathParameters": {
                "document_id": "user-b-document-123"  # 他のユーザーのドキュメントID
            }
        }

        # ユーザーAのコンテキストでドキュメント削除が試行される
        mock_client_instance.delete_user_document.return_value = True

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_document_delete_handler(user_a_event, {})

        # ユーザーAのコンテキストでのみ削除が実行されることを確認
        mock_client_instance.delete_user_document.assert_called_with(
            user_id="user-a",  # JWTから抽出されたユーザーID
            vector_bucket_name="test-bucket",
            document_id="user-b-document-123"
        )

    def test_user_id_extraction_consistency(self):
        """異なるハンドラー間でのユーザーID抽出の一貫性"""
        from multi_tenant_handlers import extract_user_id_from_cognito
        
        cognito_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "consistent-user-id",
                        "cognito:username": "consistentuser",
                        "email": "consistent@example.com"
                    }
                }
            }
        }

        # 複数回呼び出して一貫性を確認
        user_id_1 = extract_user_id_from_cognito(cognito_event)
        user_id_2 = extract_user_id_from_cognito(cognito_event)
        user_id_3 = extract_user_id_from_cognito(cognito_event)

        assert user_id_1 == user_id_2 == user_id_3 == "consistent-user-id"


class TestMultiTenantPerformance:
    """マルチテナント機能のパフォーマンステスト"""

    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_concurrent_user_operations(self, mock_s3_client):
        """同時ユーザー操作のシミュレーション"""
        import concurrent.futures
        import threading
        
        mock_client_instance = Mock()
        mock_client_instance.add_user_document.return_value = 1
        mock_s3_client.return_value = mock_client_instance
        
        # スレッドローカルな呼び出し回数を追跡
        call_counts = {}
        call_lock = threading.Lock()

        def mock_add_document(*args, **kwargs):
            user_id = kwargs.get('user_id') or args[0]
            with call_lock:
                call_counts[user_id] = call_counts.get(user_id, 0) + 1
            return 1

        mock_client_instance.add_user_document.side_effect = mock_add_document

        def simulate_user_request(user_id):
            """ユーザーリクエストをシミュレート"""
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
                    "title": f"{user_id}のドキュメント",
                    "text": f"これは{user_id}のテストドキュメントです。"
                })
            }

            with patch.dict(os.environ, {
                'VECTOR_BUCKET_NAME': 'test-bucket',
                'VECTOR_INDEX_NAME': 'test-index'
            }):
                return user_add_document_handler(event, {})

        # 10人のユーザーが同時にドキュメントを追加
        user_ids = [f"user-{i:03d}" for i in range(10)]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(simulate_user_request, user_id) for user_id in user_ids]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        # 全てのリクエストが成功したことを確認
        for result in results:
            assert result['statusCode'] == 200

        # 各ユーザーのドキュメントが正確に1回ずつ追加されたことを確認
        assert len(call_counts) == 10
        for user_id in user_ids:
            assert call_counts[user_id] == 1


class TestMultiTenantEdgeCases:
    """マルチテナント機能のエッジケーステスト"""

    def test_user_id_sanitization(self):
        """ユーザーIDのサニタイゼーション"""
        client = S3VectorsClient()
        
        # 正常なユーザーID
        normal_user_id = "user123"
        assert client.get_user_index_name(normal_user_id) == "user-user123-knowledge-base"
        
        # 特殊文字を含むユーザーID
        special_user_id = "user@#$%^&*()123"
        sanitized_index = client.get_user_index_name(special_user_id)
        assert "user123" in sanitized_index
        assert "@#$%^&*()" not in sanitized_index

    def test_empty_user_id_handling(self):
        """空のユーザーIDの処理"""
        client = S3VectorsClient()
        
        with pytest.raises(ValueError, match="User ID cannot be empty"):
            client.get_user_index_name("")
            
        with pytest.raises(ValueError, match="User ID cannot be empty"):
            client.get_user_index_name("   ")

    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_large_document_multi_user(self, mock_s3_client):
        """大きなドキュメントの複数ユーザー処理"""
        mock_client_instance = Mock()
        mock_client_instance.add_user_document.return_value = 50  # 大きなドキュメント = 多くのチャンク
        mock_s3_client.return_value = mock_client_instance

        large_text = "これは非常に長いドキュメントです。" * 1000  # 約50,000文字

        event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "user-large-doc",
                        "email": "largedoc@example.com"
                    }
                }
            },
            "body": json.dumps({
                "title": "大きなドキュメント",
                "text": large_text
            })
        }

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_add_document_handler(event, {})

        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['vector_count'] == 50
        assert response_body['user_id'] == "user-large-doc"


class TestMultiTenantMetadata:
    """マルチテナントメタデータ管理テスト"""

    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_user_context_in_document_metadata(self, mock_s3_client):
        """ドキュメントメタデータにユーザーコンテキストが含まれることを確認"""
        mock_client_instance = Mock()
        mock_s3_client.return_value = mock_client_instance

        # メタデータ確認用のモック
        def verify_metadata(*args, **kwargs):
            # add_user_documentの引数を確認
            assert 'user_id' in kwargs
            assert kwargs['user_id'] == "metadata-user"
            return 3

        mock_client_instance.add_user_document.side_effect = verify_metadata

        event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "metadata-user",
                        "email": "metadata@example.com",
                        "given_name": "Meta",
                        "family_name": "User"
                    }
                }
            },
            "body": json.dumps({
                "title": "メタデータテストドキュメント",
                "text": "これはメタデータテスト用のドキュメントです。"
            })
        }

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_add_document_handler(event, {})

        assert response['statusCode'] == 200
        
        # モック関数が呼ばれたことで、メタデータが正しく設定されたことを確認
        mock_client_instance.add_user_document.assert_called_once()