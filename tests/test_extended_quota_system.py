"""
拡張クォータシステムのテストケース（画像関連含む）
"""
import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch
from datetime import datetime, timedelta

# テスト対象のモジュールをインポート
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from user_quota_manager import UserQuotaManager, UserQuota, QuotaUsage


class TestExtendedQuotaSystem:
    """拡張クォータシステムのテストクラス"""
    
    @pytest.fixture
    def mock_environment(self):
        """環境変数のモック"""
        with patch.dict(os.environ, {
            'USER_QUOTA_TABLE': 'test-quota-table',
            'USER_USAGE_TABLE': 'test-usage-table'
        }):
            yield
    
    @pytest.fixture
    def quota_manager(self, mock_environment):
        """クォータマネージャーインスタンス"""
        return UserQuotaManager()
    
    @pytest.fixture
    def setup_dynamodb_tables(self):
        """DynamoDBテーブルのセットアップ"""
        with mock_dynamodb():
            dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
            
            # クォータテーブル
            quota_table = dynamodb.create_table(
                TableName='test-quota-table',
                KeySchema=[
                    {'AttributeName': 'user_id', 'KeyType': 'HASH'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'user_id', 'AttributeType': 'S'}
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            
            # 使用量テーブル
            usage_table = dynamodb.create_table(
                TableName='test-usage-table',
                KeySchema=[
                    {'AttributeName': 'user_id', 'KeyType': 'HASH'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'user_id', 'AttributeType': 'S'}
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            
            yield quota_table, usage_table
    
    def test_plan_defaults_include_image_limits(self, quota_manager):
        """プランデフォルトに画像制限が含まれることを確認"""
        free_defaults = quota_manager.PLAN_DEFAULTS['free']
        basic_defaults = quota_manager.PLAN_DEFAULTS['basic']
        premium_defaults = quota_manager.PLAN_DEFAULTS['premium']
        
        # 画像関連の制限が存在することを確認
        for plan_defaults in [free_defaults, basic_defaults, premium_defaults]:
            assert 'max_images' in plan_defaults
            assert 'max_image_storage_mb' in plan_defaults
            assert 'max_image_vectors' in plan_defaults
            assert 'max_monthly_image_analyses' in plan_defaults
        
        # プラン別の制限値が適切に設定されていることを確認
        assert free_defaults['max_images'] == 20
        assert basic_defaults['max_images'] == 100
        assert premium_defaults['max_images'] == 500
        
        assert free_defaults['max_image_storage_mb'] == 100
        assert basic_defaults['max_image_storage_mb'] == 500
        assert premium_defaults['max_image_storage_mb'] == 2000
    
    def test_check_image_quota_before_upload(self, quota_manager, setup_dynamodb_tables):
        """画像アップロード前のクォータチェックテスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        
        # Freeプランのクォータを設定
        quota_manager.set_user_plan(user_id, "free")
        
        # 使用量を設定（制限近くまで使用）
        usage_table.put_item(Item={
            'user_id': user_id,
            'current_images': 19  # Freeプランの制限は20
        })
        
        # 1枚目はアップロード可能
        can_upload, message = quota_manager.check_image_quota_before_upload(user_id)
        assert can_upload is True
        assert message == "OK"
        
        # 制限に達した場合
        usage_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression="SET current_images = :val",
            ExpressionAttributeValues={':val': 20}
        )
        
        can_upload, message = quota_manager.check_image_quota_before_upload(user_id)
        assert can_upload is False
        assert "制限に達しています" in message
    
    def test_check_image_storage_quota(self, quota_manager, setup_dynamodb_tables):
        """画像ストレージクォータチェックテスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        
        # Basicプランを設定
        quota_manager.set_user_plan(user_id, "basic")
        
        # 現在のストレージ使用量を設定
        usage_table.put_item(Item={
            'user_id': user_id,
            'current_image_storage_mb': 450.0  # Basicプランの制限は500MB
        })
        
        # 40MBの画像アップロードをチェック（合計490MB、制限内）
        can_upload, message = quota_manager.check_image_storage_quota(user_id, 40.0)
        assert can_upload is True
        assert message == "OK"
        
        # 60MBの画像アップロードをチェック（合計510MB、制限超過）
        can_upload, message = quota_manager.check_image_storage_quota(user_id, 60.0)
        assert can_upload is False
        assert "ストレージ制限を超過" in message
    
    def test_check_image_analysis_quota(self, quota_manager, setup_dynamodb_tables):
        """画像分析実行クォータチェックテスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        current_month = datetime.utcnow().strftime("%Y-%m")
        
        # Premiumプランを設定
        quota_manager.set_user_plan(user_id, "premium")
        
        # 月間分析数を設定（制限近くまで使用）
        usage_table.put_item(Item={
            'user_id': user_id,
            'monthly_image_analyses': 999,  # Premiumプランの制限は1000
            'analysis_month_year': current_month
        })
        
        # 1回の分析は実行可能
        can_analyze, message = quota_manager.check_image_analysis_quota(user_id)
        assert can_analyze is True
        assert message == "OK"
        
        # 制限に達した場合
        usage_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression="SET monthly_image_analyses = :val",
            ExpressionAttributeValues={':val': 1000}
        )
        
        can_analyze, message = quota_manager.check_image_analysis_quota(user_id)
        assert can_analyze is False
        assert "月間画像分析制限" in message
    
    def test_image_analysis_quota_monthly_reset(self, quota_manager, setup_dynamodb_tables):
        """月間画像分析クォータのリセットテスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        last_month = (datetime.utcnow().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        current_month = datetime.utcnow().strftime("%Y-%m")
        
        # 先月のデータを設定（制限に達している）
        usage_table.put_item(Item={
            'user_id': user_id,
            'monthly_image_analyses': 50,  # 制限に達している
            'analysis_month_year': last_month  # 先月
        })
        
        # 今月のクォータチェック（リセットされているはず）
        can_analyze, message = quota_manager.check_image_analysis_quota(user_id)
        assert can_analyze is True
        assert message == "OK"
    
    def test_update_image_usage_after_upload(self, quota_manager, setup_dynamodb_tables):
        """画像アップロード後の使用量更新テスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        image_size_mb = 2.5
        vector_count = 8
        
        # 初期使用量を設定
        usage_table.put_item(Item={
            'user_id': user_id,
            'current_images': 5,
            'current_image_storage_mb': 10.0,
            'current_image_vectors': 20,
            'monthly_image_analyses': 3
        })
        
        # アップロード後の使用量更新
        quota_manager.update_image_usage_after_upload(user_id, image_size_mb, vector_count)
        
        # 更新された使用量を確認
        response = usage_table.get_item(Key={'user_id': user_id})
        updated_usage = response['Item']
        
        assert updated_usage['current_images'] == 6  # +1
        assert updated_usage['current_image_storage_mb'] == 12.5  # +2.5
        assert updated_usage['current_image_vectors'] == 28  # +8
        assert updated_usage['monthly_image_analyses'] == 4  # +1 (OCR/Vision分析)
        assert 'analysis_month_year' in updated_usage
        assert 'last_image_upload_date' in updated_usage
    
    def test_update_image_usage_after_delete(self, quota_manager, setup_dynamodb_tables):
        """画像削除後の使用量更新テスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        image_size_mb = 1.5
        vector_count = 5
        
        # 初期使用量を設定
        usage_table.put_item(Item={
            'user_id': user_id,
            'current_images': 10,
            'current_image_storage_mb': 25.0,
            'current_image_vectors': 50
        })
        
        # 削除後の使用量更新
        quota_manager.update_image_usage_after_delete(user_id, image_size_mb, vector_count)
        
        # 更新された使用量を確認
        response = usage_table.get_item(Key={'user_id': user_id})
        updated_usage = response['Item']
        
        assert updated_usage['current_images'] == 9  # -1
        assert updated_usage['current_image_storage_mb'] == 23.5  # -1.5
        assert updated_usage['current_image_vectors'] == 45  # -5
        assert 'last_image_delete_date' in updated_usage
    
    def test_get_extended_quota_status(self, quota_manager, setup_dynamodb_tables):
        """拡張クォータ状況取得テスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        current_month = datetime.utcnow().strftime("%Y-%m")
        
        # Basicプランを設定
        quota_manager.set_user_plan(user_id, "basic")
        
        # 使用量を設定
        usage_table.put_item(Item={
            'user_id': user_id,
            'current_documents': 50,
            'current_vectors': 5000,
            'current_storage_size_mb': 75.0,
            'monthly_queries': 500,
            'current_images': 25,
            'current_image_storage_mb': 150.0,
            'current_image_vectors': 1200,
            'monthly_image_analyses': 50,
            'analysis_month_year': current_month
        })
        
        # 拡張クォータ状況を取得
        status = quota_manager.get_extended_quota_status(user_id)
        
        # 基本的なクォータ情報を確認
        assert status['user_id'] == user_id
        assert status['plan_type'] == 'basic'
        assert 'quotas' in status
        
        # 画像関連クォータ情報を確認
        quotas = status['quotas']
        
        # 画像数
        assert quotas['images']['count'] == 25
        assert quotas['images']['limit'] == 100  # Basicプランの制限
        assert quotas['images']['usage_percentage'] == 25.0
        
        # 画像ストレージ
        assert quotas['image_storage']['used_mb'] == 150.0
        assert quotas['image_storage']['limit_mb'] == 500  # Basicプランの制限
        assert quotas['image_storage']['usage_percentage'] == 30.0
        
        # 画像ベクトル
        assert quotas['image_vectors']['count'] == 1200
        assert quotas['image_vectors']['limit'] == 5000  # Basicプランの制限
        assert quotas['image_vectors']['usage_percentage'] == 24.0
        
        # 月間画像分析
        assert quotas['monthly_image_analyses']['count'] == 50
        assert quotas['monthly_image_analyses']['limit'] == 200  # Basicプランの制限
        assert quotas['monthly_image_analyses']['usage_percentage'] == 25.0
        assert quotas['monthly_image_analyses']['month'] == current_month
    
    def test_quota_status_with_missing_image_data(self, quota_manager, setup_dynamodb_tables):
        """画像データが欠如している場合のクォータ状況テスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        
        # 既存のユーザー（画像関連データなし）
        quota_manager.set_user_plan(user_id, "free")
        usage_table.put_item(Item={
            'user_id': user_id,
            'current_documents': 10,
            'current_vectors': 500
        })
        
        # 拡張クォータ状況を取得
        status = quota_manager.get_extended_quota_status(user_id)
        
        # 画像関連データは0として扱われる
        quotas = status['quotas']
        assert quotas['images']['count'] == 0
        assert quotas['image_storage']['used_mb'] == 0.0
        assert quotas['image_vectors']['count'] == 0
        assert quotas['monthly_image_analyses']['count'] == 0
    
    def test_plan_upgrade_quota_expansion(self, quota_manager, setup_dynamodb_tables):
        """プラン変更による制限拡張テスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        
        # Freeプランからスタート
        quota_manager.set_user_plan(user_id, "free")
        free_status = quota_manager.get_extended_quota_status(user_id)
        
        # Premiumプランにアップグレード
        quota_manager.set_user_plan(user_id, "premium")
        premium_status = quota_manager.get_extended_quota_status(user_id)
        
        # 制限が拡張されていることを確認
        assert premium_status['quotas']['images']['limit'] > free_status['quotas']['images']['limit']
        assert premium_status['quotas']['image_storage']['limit_mb'] > free_status['quotas']['image_storage']['limit_mb']
        assert premium_status['quotas']['image_vectors']['limit'] > free_status['quotas']['image_vectors']['limit']
        assert premium_status['quotas']['monthly_image_analyses']['limit'] > free_status['quotas']['monthly_image_analyses']['limit']
    
    def test_quota_percentage_calculation(self, quota_manager, setup_dynamodb_tables):
        """使用率計算の正確性テスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        
        # テスト用の使用量を設定
        quota_manager.set_user_plan(user_id, "basic")
        usage_table.put_item(Item={
            'user_id': user_id,
            'current_images': 50,  # 100の50% = 50%
            'current_image_storage_mb': 125.0,  # 500の25% = 25%
            'current_image_vectors': 2500,  # 5000の50% = 50%
            'monthly_image_analyses': 60  # 200の30% = 30%
        })
        
        status = quota_manager.get_extended_quota_status(user_id)
        quotas = status['quotas']
        
        # 使用率が正確に計算されていることを確認
        assert abs(quotas['images']['usage_percentage'] - 50.0) < 0.1
        assert abs(quotas['image_storage']['usage_percentage'] - 25.0) < 0.1
        assert abs(quotas['image_vectors']['usage_percentage'] - 50.0) < 0.1
        assert abs(quotas['monthly_image_analyses']['usage_percentage'] - 30.0) < 0.1
    
    def test_zero_division_protection(self, quota_manager, setup_dynamodb_tables):
        """ゼロ除算保護のテスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        
        # 制限が0のカスタムクォータを設定（通常は発生しないが安全性のため）
        quota_table.put_item(Item={
            'user_id': user_id,
            'plan_type': 'custom',
            'max_images': 0,
            'max_image_storage_mb': 0
        })
        
        usage_table.put_item(Item={
            'user_id': user_id,
            'current_images': 5,
            'current_image_storage_mb': 10.0
        })
        
        # ゼロ除算エラーが発生しないことを確認
        status = quota_manager.get_extended_quota_status(user_id)
        quotas = status['quotas']
        
        # 制限が0の場合は使用率は0%として扱われる
        assert quotas['images']['usage_percentage'] == 0.0
        assert quotas['image_storage']['usage_percentage'] == 0.0
    
    def test_comprehensive_quota_integration(self, quota_manager, setup_dynamodb_tables):
        """包括的なクォータ統合テスト"""
        quota_table, usage_table = setup_dynamodb_tables
        
        user_id = "test-user-123"
        
        # 1. ユーザーを作成してFreeプランを設定
        quota_manager.set_user_plan(user_id, "free")
        
        # 2. 画像アップロード可能性をチェック
        can_upload_image, _ = quota_manager.check_image_quota_before_upload(user_id)
        assert can_upload_image is True
        
        # 3. ストレージクォータをチェック
        can_store, _ = quota_manager.check_image_storage_quota(user_id, 10.0)
        assert can_store is True
        
        # 4. 画像分析クォータをチェック
        can_analyze, _ = quota_manager.check_image_analysis_quota(user_id)
        assert can_analyze is True
        
        # 5. アップロード後の使用量更新
        quota_manager.update_image_usage_after_upload(user_id, 10.0, 5)
        
        # 6. 更新後のクォータ状況を確認
        status = quota_manager.get_extended_quota_status(user_id)
        assert status['quotas']['images']['count'] == 1
        assert status['quotas']['image_storage']['used_mb'] == 10.0
        assert status['quotas']['image_vectors']['count'] == 5
        assert status['quotas']['monthly_image_analyses']['count'] == 1
        
        # 7. Basicプランにアップグレード
        quota_manager.set_user_plan(user_id, "basic")
        
        # 8. 制限が拡張されたことを確認
        updated_status = quota_manager.get_extended_quota_status(user_id)
        assert updated_status['quotas']['images']['limit'] == 100  # Freeは20だった
        assert updated_status['quotas']['image_storage']['limit_mb'] == 500  # Freeは100だった
        
        # 9. 削除後の使用量更新テスト
        quota_manager.update_image_usage_after_delete(user_id, 10.0, 5)
        
        # 10. 削除後の状況確認
        final_status = quota_manager.get_extended_quota_status(user_id)
        assert final_status['quotas']['images']['count'] == 0
        assert final_status['quotas']['image_storage']['used_mb'] == 0.0
        assert final_status['quotas']['image_vectors']['count'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])