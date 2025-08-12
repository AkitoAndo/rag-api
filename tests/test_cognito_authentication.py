"""
Cognito認証機能のテスト
"""
import pytest
import json
from unittest.mock import Mock, patch
import sys
import os

# テスト用のパス設定
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# モジュールインポート
from multi_tenant_handlers import extract_user_id_from_cognito, extract_user_id_from_path


class TestCognitoAuthentication:
    """Cognito認証機能のテスト"""

    def test_extract_user_id_from_cognito_with_sub(self):
        """Cognito subからユーザーIDを正常に抽出"""
        event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "user123-uuid-4567",
                        "cognito:username": "testuser",
                        "email": "test@example.com"
                    }
                }
            }
        }
        
        user_id = extract_user_id_from_cognito(event)
        assert user_id == "user123-uuid-4567"

    def test_extract_user_id_from_cognito_fallback_to_username(self):
        """subがない場合usernameにフォールバック"""
        event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "cognito:username": "testuser",
                        "email": "test@example.com"
                    }
                }
            }
        }
        
        user_id = extract_user_id_from_cognito(event)
        assert user_id == "testuser"

    def test_extract_user_id_from_cognito_fallback_to_email(self):
        """subとusernameがない場合emailにフォールバック"""
        event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "email": "test@example.com"
                    }
                }
            }
        }
        
        user_id = extract_user_id_from_cognito(event)
        assert user_id == "test@example.com"

    def test_extract_user_id_from_cognito_missing_request_context(self):
        """requestContextがない場合のエラーハンドリング"""
        event = {}
        
        with pytest.raises(ValueError, match="User ID not found in JWT token"):
            extract_user_id_from_cognito(event)

    def test_extract_user_id_from_cognito_missing_authorizer(self):
        """authorizerがない場合のエラーハンドリング"""
        event = {
            "requestContext": {}
        }
        
        with pytest.raises(ValueError, match="User ID not found in JWT token"):
            extract_user_id_from_cognito(event)

    def test_extract_user_id_from_cognito_missing_claims(self):
        """claimsがない場合のエラーハンドリング"""
        event = {
            "requestContext": {
                "authorizer": {}
            }
        }
        
        with pytest.raises(ValueError, match="User ID not found in JWT token"):
            extract_user_id_from_cognito(event)

    def test_extract_user_id_from_cognito_empty_claims(self):
        """claimsが空の場合のエラーハンドリング"""
        event = {
            "requestContext": {
                "authorizer": {
                    "claims": {}
                }
            }
        }
        
        with pytest.raises(ValueError, match="User ID not found in JWT token"):
            extract_user_id_from_cognito(event)

    def test_extract_user_id_from_cognito_whitespace_handling(self):
        """空白文字の適切な処理"""
        event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "  user123  "
                    }
                }
            }
        }
        
        user_id = extract_user_id_from_cognito(event)
        assert user_id == "user123"

    def test_extract_user_id_from_cognito_real_cognito_structure(self):
        """実際のCognito JWTクレーム構造をテスト"""
        event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "a1b2c3d4-e5f6-7890-abcd-1234567890ab",
                        "aud": "client-id-123",
                        "cognito:groups": ["admin"],
                        "email_verified": "true",
                        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXXXXXXX",
                        "cognito:username": "testuser@example.com",
                        "given_name": "Test",
                        "family_name": "User",
                        "aud": "7example23140923",
                        "event_id": "01234567-0123-0123-0123-012345678901",
                        "token_use": "id",
                        "auth_time": "1234567890",
                        "exp": "1234567890",
                        "custom:tenant_id": "tenant123",
                        "iat": "1234567890",
                        "email": "testuser@example.com"
                    }
                }
            }
        }
        
        user_id = extract_user_id_from_cognito(event)
        assert user_id == "a1b2c3d4-e5f6-7890-abcd-1234567890ab"


class TestCognitoIntegration:
    """Cognito認証の統合テスト"""

    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_user_query_handler_with_cognito_auth(self, mock_s3_client):
        """Cognito認証を使用したユーザークエリハンドラーのテスト"""
        from multi_tenant_handlers import user_query_handler
        
        # S3VectorsClientのモックを設定
        mock_client_instance = Mock()
        mock_client_instance.query_user_vectors.return_value = [
            {
                "metadata": {
                    "text": "テストドキュメント",
                    "user_id": "user123"
                }
            }
        ]
        mock_s3_client.return_value = mock_client_instance

        # Cognitoイベントを作成
        event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "user123",
                        "email": "test@example.com"
                    }
                }
            },
            "body": json.dumps({
                "question": "テスト質問"
            })
        }

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            with patch('multi_tenant_handlers.ChatBedrockConverse') as mock_chat:
                # Bedrockのモックレスポンス
                mock_chat_instance = Mock()
                mock_chat_instance.invoke.return_value.content = "テスト回答"
                mock_chat.return_value = mock_chat_instance

                response = user_query_handler(event, {})

        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert 'answer' in response_body
        assert response_body['answer'] == "テスト回答"

        # S3VectorsClientが正しい引数で呼ばれたことを確認
        mock_client_instance.query_user_vectors.assert_called_once_with(
            user_id="user123",
            vector_bucket_name="test-bucket",
            question="テスト質問",
            top_k=3
        )

    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_user_add_document_handler_with_cognito_auth(self, mock_s3_client):
        """Cognito認証を使用したドキュメント追加ハンドラーのテスト"""
        from multi_tenant_handlers import user_add_document_handler
        
        # S3VectorsClientのモックを設定
        mock_client_instance = Mock()
        mock_client_instance.add_user_document.return_value = 2
        mock_s3_client.return_value = mock_client_instance

        # Cognitoイベントを作成
        event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "user456",
                        "cognito:username": "testuser456"
                    }
                }
            },
            "body": json.dumps({
                "title": "テストドキュメント",
                "text": "これはテストドキュメントです。"
            })
        }

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_add_document_handler(event, {})

        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['message'] == "Successfully added 2 vectors"
        assert response_body['vector_count'] == 2
        assert response_body['user_id'] == "user456"

        # S3VectorsClientが正しい引数で呼ばれたことを確認
        mock_client_instance.add_user_document.assert_called_once_with(
            user_id="user456",
            vector_bucket_name="test-bucket",
            text="これはテストドキュメントです。",
            title="テストドキュメント"
        )


class TestCognitoErrorHandling:
    """Cognito認証エラーハンドリングのテスト"""

    def test_user_query_handler_missing_cognito_claims(self):
        """Cognitoクレームが不正な場合のエラーハンドリング"""
        from multi_tenant_handlers import user_query_handler
        
        event = {
            "requestContext": {
                "authorizer": {}
            },
            "body": json.dumps({
                "question": "テスト質問"
            })
        }

        response = user_query_handler(event, {})
        
        assert response['statusCode'] == 500
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert "User ID not found in JWT token" in response_body['error']

    def test_user_add_document_handler_invalid_cognito_token(self):
        """無効なCognitoトークンの場合のエラーハンドリング"""
        from multi_tenant_handlers import user_add_document_handler
        
        event = {
            "requestContext": {},
            "body": json.dumps({
                "title": "テストドキュメント",
                "text": "テストテキスト"
            })
        }

        response = user_add_document_handler(event, {})
        
        assert response['statusCode'] == 500
        response_body = json.loads(response['body'])
        assert 'error' in response_body


class TestCognitoAuthenticationComparison:
    """新旧認証方式の比較テスト"""

    def test_path_vs_cognito_user_id_extraction(self):
        """パスパラメータとCognito認証の比較"""
        # パスパラメータからのユーザーID抽出
        path_event = {
            "pathParameters": {
                "user_id": "path-user-123"
            }
        }
        path_user_id = extract_user_id_from_path(path_event)
        
        # Cognito認証からのユーザーID抽出
        cognito_event = {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "cognito-user-456"
                    }
                }
            }
        }
        cognito_user_id = extract_user_id_from_cognito(cognito_event)
        
        assert path_user_id == "path-user-123"
        assert cognito_user_id == "cognito-user-456"
        assert path_user_id != cognito_user_id  # 異なるソースからの異なるID