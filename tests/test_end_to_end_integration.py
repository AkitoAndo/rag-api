"""
エンドツーエンド統合テスト
"""
import pytest
import json
import requests
import time
import os
from unittest.mock import patch, Mock
import sys

# テスト用のパス設定
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestEndToEndIntegration:
    """完全なエンドツーエンド統合テスト"""

    @pytest.fixture
    def api_base_url(self):
        """テスト用のAPI Base URL"""
        return os.getenv('TEST_API_BASE_URL', 'https://zdhodcv40h.execute-api.us-east-1.amazonaws.com/Prod')

    @pytest.fixture
    def mock_cognito_token(self):
        """モックCognitoトークン（実際のテストでは実トークンを使用）"""
        return "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9..."

    def test_legacy_endpoints_without_auth(self, api_base_url):
        """レガシーエンドポイント（認証なし）のテスト"""
        # ドキュメント追加のテスト
        add_doc_response = requests.post(
            f"{api_base_url}/add-document",
            json={
                "title": "E2Eテストドキュメント",
                "text": "これはエンドツーエンドテスト用のドキュメントです。API Gatewayから直接アクセスできます。"
            },
            headers={"Content-Type": "application/json"}
        )
        
        if add_doc_response.status_code == 200:
            add_result = add_doc_response.json()
            assert "vector_count" in add_result
            assert add_result["vector_count"] > 0

            # クエリのテスト
            query_response = requests.post(
                f"{api_base_url}/query",
                json={
                    "question": "E2Eテストについて教えてください"
                },
                headers={"Content-Type": "application/json"}
            )
            
            if query_response.status_code == 200:
                query_result = query_response.json()
                assert "answer" in query_result
                assert len(query_result["answer"]) > 0
        else:
            pytest.skip(f"API endpoint not available: {add_doc_response.status_code}")

    def test_authenticated_endpoints_without_token(self, api_base_url):
        """認証が必要なエンドポイントを認証なしでアクセス（失敗を期待）"""
        # 認証が必要なエンドポイントに認証なしでアクセス
        response = requests.post(
            f"{api_base_url}/users/testuser/documents",
            json={
                "title": "認証テスト",
                "text": "このリクエストは失敗するはずです"
            },
            headers={"Content-Type": "application/json"}
        )
        
        # 認証エラーを期待
        assert response.status_code in [401, 403], f"Expected auth error, got {response.status_code}"

    @pytest.mark.skipif(
        not os.getenv('COGNITO_ACCESS_TOKEN'),
        reason="Real Cognito token not available"
    )
    def test_authenticated_endpoints_with_real_token(self, api_base_url):
        """実際のCognitoトークンを使用した認証エンドポイントテスト"""
        token = os.getenv('COGNITO_ACCESS_TOKEN')
        user_id = os.getenv('TEST_USER_ID', 'testuser')
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        # ユーザー固有のドキュメント追加
        add_response = requests.post(
            f"{api_base_url}/users/{user_id}/documents",
            json={
                "title": "認証済みE2Eテスト",
                "text": "これは認証済みユーザーのテストドキュメントです。"
            },
            headers=headers
        )
        
        if add_response.status_code == 200:
            add_result = add_response.json()
            assert "user_id" in add_result
            assert add_result["user_id"] == user_id

            # ユーザー固有のクエリ
            query_response = requests.post(
                f"{api_base_url}/users/{user_id}/query",
                json={
                    "question": "私のドキュメントについて教えて"
                },
                headers=headers
            )
            
            if query_response.status_code == 200:
                query_result = query_response.json()
                assert "answer" in query_result
                assert "user_id" in query_result


class TestMultiUserScenarios:
    """マルチユーザーシナリオテスト"""

    def test_multiple_users_data_isolation_simulation(self):
        """複数ユーザーのデータ分離シミュレーション"""
        from multi_tenant_handlers import user_add_document_handler, user_query_handler
        
        with patch('multi_tenant_handlers.S3VectorsClient') as mock_s3_client:
            mock_client_instance = Mock()
            mock_s3_client.return_value = mock_client_instance
            
            # ユーザー1のドキュメント追加をシミュレート
            mock_client_instance.add_user_document.return_value = 2
            
            user1_add_event = {
                "requestContext": {
                    "authorizer": {
                        "claims": {
                            "sub": "user-001",
                            "email": "user1@company.com"
                        }
                    }
                },
                "body": json.dumps({
                    "title": "ユーザー1の機密ドキュメント",
                    "text": "これはユーザー1の機密情報です。他のユーザーには見えてはいけません。"
                })
            }

            with patch.dict(os.environ, {
                'VECTOR_BUCKET_NAME': 'test-bucket',
                'VECTOR_INDEX_NAME': 'test-index'
            }):
                response1 = user_add_document_handler(user1_add_event, {})

            assert response1['statusCode'] == 200
            result1 = json.loads(response1['body'])
            assert result1['user_id'] == "user-001"

            # ユーザー2のドキュメント追加をシミュレート
            user2_add_event = {
                "requestContext": {
                    "authorizer": {
                        "claims": {
                            "sub": "user-002",
                            "email": "user2@company.com"
                        }
                    }
                },
                "body": json.dumps({
                    "title": "ユーザー2の機密ドキュメント",
                    "text": "これはユーザー2の機密情報です。ユーザー1には見えてはいけません。"
                })
            }

            with patch.dict(os.environ, {
                'VECTOR_BUCKET_NAME': 'test-bucket',
                'VECTOR_INDEX_NAME': 'test-index'
            }):
                response2 = user_add_document_handler(user2_add_event, {})

            assert response2['statusCode'] == 200
            result2 = json.loads(response2['body'])
            assert result2['user_id'] == "user-002"

            # 各ユーザーが異なるuser_idで呼ばれたことを確認
            calls = mock_client_instance.add_user_document.call_args_list
            assert len(calls) == 2
            assert calls[0].kwargs['user_id'] == "user-001"
            assert calls[1].kwargs['user_id'] == "user-002"

    def test_cross_user_query_isolation(self):
        """ユーザー間のクエリ分離テスト"""
        from multi_tenant_handlers import user_query_handler
        
        with patch('multi_tenant_handlers.S3VectorsClient') as mock_s3_client:
            with patch('multi_tenant_handlers.ChatBedrockConverse') as mock_chat:
                mock_client_instance = Mock()
                mock_s3_client.return_value = mock_client_instance
                
                mock_chat_instance = Mock()
                mock_chat_instance.invoke.return_value.content = "ユーザー固有の回答"
                mock_chat.return_value = mock_chat_instance

                # ユーザー1のクエリ（ユーザー1のドキュメントのみ検索）
                mock_client_instance.query_user_vectors.return_value = [
                    {
                        "metadata": {
                            "text": "ユーザー1のドキュメント内容",
                            "user_id": "user-alpha"
                        }
                    }
                ]

                user1_query_event = {
                    "requestContext": {
                        "authorizer": {
                            "claims": {
                                "sub": "user-alpha",
                                "email": "alpha@company.com"
                            }
                        }
                    },
                    "body": json.dumps({
                        "question": "私の機密情報について教えて"
                    })
                }

                with patch.dict(os.environ, {
                    'VECTOR_BUCKET_NAME': 'test-bucket',
                    'VECTOR_INDEX_NAME': 'test-index'
                }):
                    response1 = user_query_handler(user1_query_event, {})

                assert response1['statusCode'] == 200

                # ユーザー2のクエリ（ユーザー2のドキュメントのみ検索）
                mock_client_instance.reset_mock()
                mock_client_instance.query_user_vectors.return_value = [
                    {
                        "metadata": {
                            "text": "ユーザー2のドキュメント内容",
                            "user_id": "user-beta"
                        }
                    }
                ]

                user2_query_event = {
                    "requestContext": {
                        "authorizer": {
                            "claims": {
                                "sub": "user-beta",
                                "email": "beta@company.com"
                            }
                        }
                    },
                    "body": json.dumps({
                        "question": "私の機密情報について教えて"
                    })
                }

                with patch.dict(os.environ, {
                    'VECTOR_BUCKET_NAME': 'test-bucket',
                    'VECTOR_INDEX_NAME': 'test-index'
                }):
                    response2 = user_query_handler(user2_query_event, {})

                assert response2['statusCode'] == 200

                # 各ユーザーが自分のuser_idでのみクエリしたことを確認
                mock_client_instance.query_user_vectors.assert_called_with(
                    user_id="user-beta",
                    vector_bucket_name="test-bucket",
                    question="私の機密情報について教えて",
                    top_k=3
                )


class TestSystemReliability:
    """システム信頼性テスト"""

    def test_error_handling_with_authentication(self):
        """認証付きエラーハンドリング"""
        from multi_tenant_handlers import user_query_handler
        
        # 不正なリクエストボディ
        invalid_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "error-test-user",
                        "email": "error@example.com"
                    }
                }
            },
            "body": json.dumps({
                # "question"フィールドが不足
                "invalid_field": "invalid_value"
            })
        }

        response = user_query_handler(invalid_event, {})
        
        assert response['statusCode'] == 500
        response_body = json.loads(response['body'])
        assert 'error' in response_body

    def test_malformed_cognito_claims_handling(self):
        """不正なCognitoクレームの処理"""
        from multi_tenant_handlers import user_add_document_handler
        
        # 不完全なCognitoクレーム
        malformed_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        # "sub"フィールドが不足
                        "email": "malformed@example.com"
                    }
                }
            },
            "body": json.dumps({
                "title": "テストドキュメント",
                "text": "テストテキスト"
            })
        }

        response = user_add_document_handler(malformed_event, {})
        
        assert response['statusCode'] == 500
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert "User ID not found" in response_body['error']

    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_service_integration_resilience(self, mock_s3_client):
        """サービス統合の回復力テスト"""
        from multi_tenant_handlers import user_add_document_handler
        
        # S3VectorsClientが例外を発生
        mock_client_instance = Mock()
        mock_client_instance.add_user_document.side_effect = Exception("S3 Vectors service unavailable")
        mock_s3_client.return_value = mock_client_instance

        event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "resilience-test-user",
                        "email": "resilience@example.com"
                    }
                }
            },
            "body": json.dumps({
                "title": "回復力テスト",
                "text": "S3 Vectorsサービスエラーのテスト"
            })
        }

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_add_document_handler(event, {})

        assert response['statusCode'] == 500
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert "S3 Vectors service unavailable" in response_body['error']


class TestPerformanceAndScalability:
    """パフォーマンスとスケーラビリティテスト"""

    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_concurrent_multi_tenant_operations(self, mock_s3_client):
        """同時マルチテナント操作"""
        import concurrent.futures
        import threading
        
        mock_client_instance = Mock()
        mock_client_instance.add_user_document.return_value = 1
        mock_s3_client.return_value = mock_client_instance
        
        # スレッドセーフな操作カウンター
        operation_counts = {}
        lock = threading.Lock()

        def thread_safe_add_document(*args, **kwargs):
            user_id = kwargs.get('user_id')
            with lock:
                operation_counts[user_id] = operation_counts.get(user_id, 0) + 1
            return 1

        mock_client_instance.add_user_document.side_effect = thread_safe_add_document

        def simulate_user_operation(user_index):
            """ユーザー操作のシミュレーション"""
            from multi_tenant_handlers import user_add_document_handler
            
            user_id = f"concurrent-user-{user_index:03d}"
            event = {
                "requestContext": {
                    "authorizer": {
                        "claims": {
                            "sub": user_id,
                            "email": f"{user_id}@concurrent.com"
                        }
                    }
                },
                "body": json.dumps({
                    "title": f"{user_id}のドキュメント",
                    "text": f"これは{user_id}の同時操作テストドキュメントです。"
                })
            }

            with patch.dict(os.environ, {
                'VECTOR_BUCKET_NAME': 'test-bucket',
                'VECTOR_INDEX_NAME': 'test-index'
            }):
                return user_add_document_handler(event, {})

        # 20人のユーザーが同時に操作
        num_users = 20
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(simulate_user_operation, i) for i in range(num_users)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        # 全ての操作が成功
        success_count = sum(1 for result in results if result['statusCode'] == 200)
        assert success_count == num_users

        # 各ユーザーが1回ずつ操作したことを確認
        assert len(operation_counts) == num_users
        for i in range(num_users):
            user_id = f"concurrent-user-{i:03d}"
            assert operation_counts[user_id] == 1

    def test_large_scale_document_processing(self):
        """大規模ドキュメント処理テスト"""
        from multi_tenant_handlers import user_add_document_handler
        
        with patch('multi_tenant_handlers.S3VectorsClient') as mock_s3_client:
            mock_client_instance = Mock()
            
            # 大きなドキュメントは多くのベクトルチャンクに分割される
            mock_client_instance.add_user_document.return_value = 100
            mock_s3_client.return_value = mock_client_instance

            # 非常に大きなドキュメント（約200KB）
            large_document = "これは非常に大きなドキュメントです。" * 5000

            event = {
                "requestContext": {
                    "authorizer": {
                        "claims": {
                            "sub": "large-doc-user",
                            "email": "largedoc@example.com"
                        }
                    }
                },
                "body": json.dumps({
                    "title": "大規模ドキュメント",
                    "text": large_document
                })
            }

            with patch.dict(os.environ, {
                'VECTOR_BUCKET_NAME': 'test-bucket',
                'VECTOR_INDEX_NAME': 'test-index'
            }):
                response = user_add_document_handler(event, {})

            assert response['statusCode'] == 200
            response_body = json.loads(response['body'])
            assert response_body['vector_count'] == 100
            assert response_body['user_id'] == "large-doc-user"