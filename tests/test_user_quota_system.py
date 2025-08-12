"""
ユーザークォータシステムのテスト
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# テスト用のパス設定
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from user_quota_manager import (
    UserQuotaManager, 
    UserQuota, 
    QuotaUsage, 
    QuotaType,
    estimate_vector_count,
    get_document_size_mb
)
from multi_tenant_handlers import (
    user_query_handler,
    user_add_document_handler,
    user_quota_status_handler,
    user_plan_update_handler
)


class TestUserQuotaManager:
    """ユーザークォータマネージャーのテスト"""

    @pytest.fixture
    def mock_quota_manager(self):
        """DynamoDBなしでテストできるモックマネージャー"""
        with patch('user_quota_manager.boto3'):
            manager = UserQuotaManager()
            manager.quota_table = None
            manager.usage_table = None
            return manager

    def test_plan_defaults(self, mock_quota_manager):
        """プラン別デフォルト設定の確認"""
        plans = ["free", "basic", "premium"]
        
        for plan in plans:
            quota = mock_quota_manager.get_user_quota("test-user", plan)
            assert quota.plan_type == plan
            assert quota.user_id == "test-user"
            assert quota.max_documents > 0
            assert quota.max_vectors > 0
            assert quota.max_storage_size_mb > 0

    def test_free_plan_limits(self, mock_quota_manager):
        """フリープランの制限確認"""
        quota = mock_quota_manager.get_user_quota("free-user", "free")
        
        assert quota.max_documents == 50
        assert quota.max_vectors == 5000
        assert quota.max_storage_size_mb == 50
        assert quota.max_monthly_queries == 500
        assert quota.max_daily_uploads == 5

    def test_premium_plan_limits(self, mock_quota_manager):
        """プレミアムプランの制限確認"""
        quota = mock_quota_manager.get_user_quota("premium-user", "premium")
        
        assert quota.max_documents == 1000
        assert quota.max_vectors == 100000
        assert quota.max_storage_size_mb == 1000
        assert quota.max_monthly_queries == 10000
        assert quota.max_daily_uploads == 100

    def test_estimate_vector_count(self):
        """ベクトル数推定の確認"""
        # 短いテキスト
        short_text = "これは短いテキストです。"
        assert estimate_vector_count(short_text) >= 1
        
        # 長いテキスト（約2000文字）
        long_text = "これは長いテキストです。" * 100
        estimated = estimate_vector_count(long_text)
        assert estimated >= 2  # 少なくとも2つのチャンクに分割される
        
        # 空のテキスト
        assert estimate_vector_count("") == 0

    def test_document_size_calculation(self):
        """ドキュメントサイズ計算の確認"""
        # 英語テキスト
        english_text = "Hello World"
        size_mb = get_document_size_mb(english_text)
        assert size_mb > 0
        assert size_mb < 0.001  # 非常に小さいサイズ
        
        # 日本語テキスト（UTF-8で大きくなる）
        japanese_text = "こんにちは世界" * 1000
        size_mb = get_document_size_mb(japanese_text)
        assert size_mb > 0.01  # より大きなサイズ

    def test_quota_check_before_upload(self, mock_quota_manager):
        """アップロード前のクォータチェック"""
        user_id = "quota-test-user"
        
        # 通常サイズのドキュメント
        normal_text = "これは通常サイズのドキュメントです。" * 10
        estimated_vectors = estimate_vector_count(normal_text)
        
        can_upload, message = mock_quota_manager.check_quota_before_upload(
            user_id, normal_text, estimated_vectors
        )
        assert can_upload == True
        assert message == "OK"

    def test_quota_check_before_query(self, mock_quota_manager):
        """クエリ前のクォータチェック"""
        user_id = "query-test-user"
        
        can_query, message = mock_quota_manager.check_quota_before_query(user_id)
        assert can_query == True
        assert message == "OK"


class TestQuotaIntegrationWithHandlers:
    """ハンドラーとクォータ機能の統合テスト"""

    @pytest.fixture
    def mock_cognito_event(self):
        """Cognitoイベントのモック"""
        return {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "quota-test-user-123",
                        "email": "quotatest@example.com"
                    }
                }
            }
        }

    @patch('multi_tenant_handlers.UserQuotaManager')
    @patch('multi_tenant_handlers.S3VectorsClient')
    @patch('multi_tenant_handlers.ChatBedrockConverse')
    def test_query_handler_with_quota_exceeded(self, mock_chat, mock_s3, mock_quota_manager_class, mock_cognito_event):
        """クォータ超過時のクエリハンドラーテスト"""
        # クォータマネージャーのモック設定
        mock_quota_manager = Mock()
        mock_quota_manager_class.return_value = mock_quota_manager
        
        # クォータ超過をシミュレート
        mock_quota_manager.check_quota_before_query.return_value = (False, "Monthly query limit exceeded (1000/1000)")
        mock_quota_manager.get_quota_status.return_value = {
            "user_id": "quota-test-user-123",
            "plan_type": "free",
            "quotas": {
                "monthly_queries": {
                    "current": 1000,
                    "max": 1000,
                    "percentage": 100.0
                }
            }
        }

        # イベント設定
        event = mock_cognito_event.copy()
        event["body"] = json.dumps({
            "question": "この質問はクォータ制限でブロックされるはずです"
        })

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_query_handler(event, {})

        assert response['statusCode'] == 429  # Too Many Requests
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert 'quota_status' in response_body
        assert "Monthly query limit exceeded" in response_body['error']

        # S3VectorsClientが呼ばれていないことを確認（クォータでブロック）
        mock_s3.assert_not_called()

    @patch('multi_tenant_handlers.UserQuotaManager')
    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_add_document_handler_with_quota_exceeded(self, mock_s3, mock_quota_manager_class, mock_cognito_event):
        """クォータ超過時のドキュメント追加ハンドラーテスト"""
        # クォータマネージャーのモック設定
        mock_quota_manager = Mock()
        mock_quota_manager_class.return_value = mock_quota_manager
        
        # クォータ超過をシミュレート
        mock_quota_manager.check_quota_before_upload.return_value = (False, "Document limit exceeded (50/50)")
        mock_quota_manager.get_quota_status.return_value = {
            "user_id": "quota-test-user-123",
            "plan_type": "free",
            "quotas": {
                "documents": {
                    "current": 50,
                    "max": 50,
                    "percentage": 100.0
                }
            }
        }

        # イベント設定
        event = mock_cognito_event.copy()
        event["body"] = json.dumps({
            "title": "クォータ制限テスト",
            "text": "このドキュメント追加はクォータ制限でブロックされるはずです。"
        })

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_add_document_handler(event, {})

        assert response['statusCode'] == 429  # Too Many Requests
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert 'quota_status' in response_body
        assert 'estimated_vectors' in response_body
        assert 'document_size_mb' in response_body
        assert "Document limit exceeded" in response_body['error']

        # S3VectorsClientが呼ばれていないことを確認（クォータでブロック）
        mock_s3.assert_not_called()

    @patch('multi_tenant_handlers.UserQuotaManager')
    @patch('multi_tenant_handlers.S3VectorsClient')
    def test_successful_upload_with_quota_update(self, mock_s3, mock_quota_manager_class, mock_cognito_event):
        """成功時のアップロードとクォータ更新テスト"""
        # クォータマネージャーのモック設定
        mock_quota_manager = Mock()
        mock_quota_manager_class.return_value = mock_quota_manager
        
        # クォータOKをシミュレート
        mock_quota_manager.check_quota_before_upload.return_value = (True, "OK")
        mock_quota_manager.get_quota_status.return_value = {
            "user_id": "quota-test-user-123",
            "plan_type": "free",
            "quotas": {
                "documents": {
                    "current": 1,  # アップロード後
                    "max": 50,
                    "percentage": 2.0
                }
            }
        }

        # S3VectorsClientのモック設定
        mock_s3_client_instance = Mock()
        mock_s3_client_instance.add_user_document.return_value = 3
        mock_s3.return_value = mock_s3_client_instance

        # イベント設定
        event = mock_cognito_event.copy()
        event["body"] = json.dumps({
            "title": "成功テストドキュメント",
            "text": "このドキュメント追加は成功するはずです。"
        })

        with patch.dict(os.environ, {
            'VECTOR_BUCKET_NAME': 'test-bucket',
            'VECTOR_INDEX_NAME': 'test-index'
        }):
            response = user_add_document_handler(event, {})

        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['vector_count'] == 3
        assert response_body['user_id'] == "quota-test-user-123"
        assert 'quota_status' in response_body

        # クォータ更新が呼ばれたことを確認
        mock_quota_manager.update_usage_after_upload.assert_called_once()

    @patch('multi_tenant_handlers.UserQuotaManager')
    def test_quota_status_handler(self, mock_quota_manager_class, mock_cognito_event):
        """クォータ状況取得ハンドラーのテスト"""
        # クォータマネージャーのモック設定
        mock_quota_manager = Mock()
        mock_quota_manager_class.return_value = mock_quota_manager
        
        mock_quota_status = {
            "user_id": "quota-test-user-123",
            "plan_type": "basic",
            "quotas": {
                "documents": {
                    "current": 25,
                    "max": 200,
                    "percentage": 12.5
                },
                "vectors": {
                    "current": 2500,
                    "max": 20000,
                    "percentage": 12.5
                },
                "monthly_queries": {
                    "current": 150,
                    "max": 2000,
                    "percentage": 7.5
                }
            }
        }
        mock_quota_manager.get_quota_status.return_value = mock_quota_status

        response = user_quota_status_handler(mock_cognito_event, {})

        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['user_id'] == "quota-test-user-123"
        assert response_body['plan_type'] == "basic"
        assert 'quotas' in response_body

    @patch('multi_tenant_handlers.UserQuotaManager')
    def test_plan_update_handler(self, mock_quota_manager_class, mock_cognito_event):
        """プラン変更ハンドラーのテスト"""
        # クォータマネージャーのモック設定
        mock_quota_manager = Mock()
        mock_quota_manager_class.return_value = mock_quota_manager
        
        mock_quota_manager.set_user_plan.return_value = True
        mock_quota_manager.get_quota_status.return_value = {
            "user_id": "quota-test-user-123",
            "plan_type": "premium",
            "quotas": {
                "documents": {
                    "current": 25,
                    "max": 1000,
                    "percentage": 2.5
                }
            }
        }

        # イベント設定
        event = mock_cognito_event.copy()
        event["body"] = json.dumps({
            "plan_type": "premium"
        })

        response = user_plan_update_handler(event, {})

        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert "successfully updated" in response_body['message']
        assert 'quota_status' in response_body

        # プラン変更が呼ばれたことを確認
        mock_quota_manager.set_user_plan.assert_called_once_with("quota-test-user-123", "premium")

    @patch('multi_tenant_handlers.UserQuotaManager')
    def test_invalid_plan_update(self, mock_quota_manager_class, mock_cognito_event):
        """無効なプラン変更のテスト"""
        # イベント設定
        event = mock_cognito_event.copy()
        event["body"] = json.dumps({
            "plan_type": "invalid_plan"
        })

        response = user_plan_update_handler(event, {})

        assert response['statusCode'] == 400
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert "Invalid plan type" in response_body['error']


class TestQuotaEnforcement:
    """クォータ強制実行の詳細テスト"""

    def test_daily_upload_limit_reset(self):
        """日次アップロード制限のリセット"""
        manager = UserQuotaManager()
        manager.usage_table = None  # DynamoDBなしでテスト
        
        # 今日のアップロード制限をテスト
        usage = manager.get_user_usage("daily-test-user")
        usage.daily_uploads = 5  # 制限に達している
        usage.upload_date = "2024-01-01"  # 昨日の日付
        
        # 新しい日でのアップロードをシミュレート
        can_upload, message = manager.check_quota_before_upload(
            "daily-test-user", "test text", 1
        )
        # 新しい日なので、日次カウンターがリセットされてアップロード可能
        assert can_upload == True

    def test_monthly_query_limit_reset(self):
        """月間クエリ制限のリセット"""
        manager = UserQuotaManager()
        manager.usage_table = None  # DynamoDBなしでテスト
        
        # 先月のクエリ制限をテスト
        usage = manager.get_user_usage("monthly-test-user")
        usage.monthly_queries = 1000  # 制限に達している
        usage.month_year = "2024-01"  # 先月
        
        # 新しい月でのクエリをシミュレート
        can_query, message = manager.check_quota_before_query("monthly-test-user")
        # 新しい月なので、月次カウンターがリセットされてクエリ可能
        assert can_query == True

    def test_storage_size_limit(self):
        """ストレージサイズ制限のテスト"""
        manager = UserQuotaManager()
        manager.usage_table = None
        
        # 大きなドキュメント（50MB制限に近い）
        large_text = "あ" * (45 * 1024 * 1024)  # 約45MB（UTF-8で3バイト×文字数）
        estimated_vectors = estimate_vector_count(large_text)
        
        # 現在の使用量を45MBに設定
        usage = manager.get_user_usage("storage-test-user")
        usage.current_storage_size_mb = 45.0
        
        can_upload, message = manager.check_quota_before_upload(
            "storage-test-user", large_text, estimated_vectors
        )
        # ストレージ制限を超えるためアップロード不可
        assert can_upload == False
        assert "Storage limit" in message

    def test_vector_count_limit(self):
        """ベクトル数制限のテスト"""
        manager = UserQuotaManager()
        manager.usage_table = None
        
        # 現在4900ベクトル使用中、制限は5000
        usage = manager.get_user_usage("vector-test-user")
        usage.current_vectors = 4900
        
        # 200ベクトルのドキュメントをアップロードしようとする
        large_document = "テスト" * 50000  # 大きなドキュメント
        estimated_vectors = 200
        
        can_upload, message = manager.check_quota_before_upload(
            "vector-test-user", large_document, estimated_vectors
        )
        # ベクトル制限を超えるためアップロード不可
        assert can_upload == False
        assert "Vector limit" in message


class TestQuotaPlanHierarchy:
    """プラン階層テスト"""

    def test_plan_upgrade_benefits(self):
        """プランアップグレードの利益確認"""
        manager = UserQuotaManager()
        
        # フリープランからベーシックプランへのアップグレード
        free_quota = manager.get_user_quota("upgrade-user", "free")
        basic_quota = manager.get_user_quota("upgrade-user", "basic")
        
        assert basic_quota.max_documents > free_quota.max_documents
        assert basic_quota.max_vectors > free_quota.max_vectors
        assert basic_quota.max_storage_size_mb > free_quota.max_storage_size_mb
        assert basic_quota.max_monthly_queries > free_quota.max_monthly_queries
        assert basic_quota.max_daily_uploads > free_quota.max_daily_uploads

    def test_premium_plan_generous_limits(self):
        """プレミアムプランの寛大な制限確認"""
        manager = UserQuotaManager()
        premium_quota = manager.get_user_quota("premium-user", "premium")
        
        # プレミアムプランは非常に寛大な制限
        assert premium_quota.max_documents >= 1000
        assert premium_quota.max_vectors >= 100000
        assert premium_quota.max_storage_size_mb >= 1000
        assert premium_quota.max_monthly_queries >= 10000
        assert premium_quota.max_daily_uploads >= 100