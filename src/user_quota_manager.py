"""
ユーザークォータ管理機能
"""
import os
from datetime import datetime
from typing import Dict, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import boto3


class QuotaType(Enum):
    """クォータの種類"""
    DOCUMENTS = "documents"
    VECTORS = "vectors"
    STORAGE_SIZE = "storage_size"
    MONTHLY_QUERIES = "monthly_queries"
    DAILY_UPLOADS = "daily_uploads"


@dataclass
class UserQuota:
    """ユーザークォータ設定"""
    user_id: str
    plan_type: str = "free"  # free, basic, premium
    max_documents: int = 100
    max_vectors: int = 10000
    max_storage_size_mb: int = 100  # MB
    max_monthly_queries: int = 1000
    max_daily_uploads: int = 10
    created_at: str = None
    updated_at: str = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        self.updated_at = datetime.utcnow().isoformat()


@dataclass
class QuotaUsage:
    """ユーザークォータ使用状況"""
    user_id: str
    current_documents: int = 0
    current_vectors: int = 0
    current_storage_size_mb: float = 0.0
    monthly_queries: int = 0
    daily_uploads: int = 0
    last_query_date: str = None
    last_upload_date: str = None
    month_year: str = None  # YYYY-MM形式
    upload_date: str = None  # YYYY-MM-DD形式

    def __post_init__(self):
        today = datetime.utcnow()
        if not self.month_year:
            self.month_year = today.strftime("%Y-%m")
        if not self.upload_date:
            self.upload_date = today.strftime("%Y-%m-%d")


class UserQuotaManager:
    """ユーザークォータ管理クラス"""

    # プラン別デフォルト設定（画像機能拡張版）
    PLAN_DEFAULTS = {
        "free": {
            "max_documents": 50,
            "max_vectors": 5000,
            "max_storage_size_mb": 50,
            "max_monthly_queries": 500,
            "max_daily_uploads": 5,
            # 画像関連制限
            "max_images": 20,
            "max_image_storage_mb": 100,
            "max_image_vectors": 1000,
            "max_monthly_image_analyses": 50
        },
        "basic": {
            "max_documents": 200,
            "max_vectors": 20000,
            "max_storage_size_mb": 200,
            "max_monthly_queries": 2000,
            "max_daily_uploads": 20,
            # 画像関連制限
            "max_images": 100,
            "max_image_storage_mb": 500,
            "max_image_vectors": 5000,
            "max_monthly_image_analyses": 200
        },
        "premium": {
            "max_documents": 1000,
            "max_vectors": 100000,
            "max_storage_size_mb": 1000,
            "max_monthly_queries": 10000,
            "max_daily_uploads": 100,
            # 画像関連制限
            "max_images": 500,
            "max_image_storage_mb": 2000,
            "max_image_vectors": 20000,
            "max_monthly_image_analyses": 1000
        }
    }

    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.quota_table_name = os.getenv('USER_QUOTA_TABLE', 'rag-user-quotas')
        self.usage_table_name = os.getenv('USER_USAGE_TABLE', 'rag-user-usage')
        
        try:
            self.quota_table = self.dynamodb.Table(self.quota_table_name)
            self.usage_table = self.dynamodb.Table(self.usage_table_name)
        except Exception:
            # テーブルが存在しない場合は None に設定
            self.quota_table = None
            self.usage_table = None

    def get_user_quota(self, user_id: str, plan_type: str = "free") -> UserQuota:
        """ユーザーのクォータ設定を取得"""
        if not self.quota_table:
            # DynamoDBが利用できない場合はデフォルト値を返す
            defaults = self.PLAN_DEFAULTS.get(plan_type, self.PLAN_DEFAULTS["free"])
            return UserQuota(user_id=user_id, plan_type=plan_type, **defaults)

        try:
            response = self.quota_table.get_item(Key={'user_id': user_id})
            if 'Item' in response:
                item = response['Item']
                return UserQuota(
                    user_id=item['user_id'],
                    plan_type=item.get('plan_type', plan_type),
                    max_documents=int(item.get('max_documents', self.PLAN_DEFAULTS[plan_type]['max_documents'])),
                    max_vectors=int(item.get('max_vectors', self.PLAN_DEFAULTS[plan_type]['max_vectors'])),
                    max_storage_size_mb=int(item.get('max_storage_size_mb', self.PLAN_DEFAULTS[plan_type]['max_storage_size_mb'])),
                    max_monthly_queries=int(item.get('max_monthly_queries', self.PLAN_DEFAULTS[plan_type]['max_monthly_queries'])),
                    max_daily_uploads=int(item.get('max_daily_uploads', self.PLAN_DEFAULTS[plan_type]['max_daily_uploads'])),
                    created_at=item.get('created_at'),
                    updated_at=item.get('updated_at')
                )
            else:
                # ユーザーのクォータ設定が見つからない場合はデフォルトを作成
                defaults = self.PLAN_DEFAULTS.get(plan_type, self.PLAN_DEFAULTS["free"])
                return UserQuota(user_id=user_id, plan_type=plan_type, **defaults)
        except Exception as e:
            print(f"Error getting user quota: {e}")
            defaults = self.PLAN_DEFAULTS.get(plan_type, self.PLAN_DEFAULTS["free"])
            return UserQuota(user_id=user_id, plan_type=plan_type, **defaults)

    def get_user_usage(self, user_id: str) -> QuotaUsage:
        """ユーザーの使用状況を取得"""
        if not self.usage_table:
            return QuotaUsage(user_id=user_id)

        try:
            response = self.usage_table.get_item(Key={'user_id': user_id})
            if 'Item' in response:
                item = response['Item']
                return QuotaUsage(
                    user_id=item['user_id'],
                    current_documents=int(item.get('current_documents', 0)),
                    current_vectors=int(item.get('current_vectors', 0)),
                    current_storage_size_mb=float(item.get('current_storage_size_mb', 0.0)),
                    monthly_queries=int(item.get('monthly_queries', 0)),
                    daily_uploads=int(item.get('daily_uploads', 0)),
                    last_query_date=item.get('last_query_date'),
                    last_upload_date=item.get('last_upload_date'),
                    month_year=item.get('month_year'),
                    upload_date=item.get('upload_date')
                )
            else:
                return QuotaUsage(user_id=user_id)
        except Exception as e:
            print(f"Error getting user usage: {e}")
            return QuotaUsage(user_id=user_id)

    def check_quota_before_upload(self, user_id: str, document_text: str, estimated_vectors: int) -> Tuple[bool, str]:
        """ドキュメントアップロード前のクォータチェック"""
        quota = self.get_user_quota(user_id)
        usage = self.get_user_usage(user_id)
        
        # 現在の日付をチェック
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if usage.upload_date != today:
            # 新しい日の場合、日次アップロード数をリセット
            usage.daily_uploads = 0
            usage.upload_date = today

        # 各制限をチェック
        if usage.current_documents >= quota.max_documents:
            return False, f"Document limit exceeded ({usage.current_documents}/{quota.max_documents})"

        if usage.current_vectors + estimated_vectors > quota.max_vectors:
            return False, f"Vector limit would be exceeded ({usage.current_vectors + estimated_vectors}/{quota.max_vectors})"

        document_size_mb = len(document_text.encode('utf-8')) / (1024 * 1024)
        if usage.current_storage_size_mb + document_size_mb > quota.max_storage_size_mb:
            return False, f"Storage limit would be exceeded ({usage.current_storage_size_mb + document_size_mb:.2f}/{quota.max_storage_size_mb} MB)"

        if usage.daily_uploads >= quota.max_daily_uploads:
            return False, f"Daily upload limit exceeded ({usage.daily_uploads}/{quota.max_daily_uploads})"

        return True, "OK"

    def check_quota_before_query(self, user_id: str) -> Tuple[bool, str]:
        """クエリ実行前のクォータチェック"""
        quota = self.get_user_quota(user_id)
        usage = self.get_user_usage(user_id)
        
        # 現在の月をチェック
        current_month = datetime.utcnow().strftime("%Y-%m")
        if usage.month_year != current_month:
            # 新しい月の場合、月間クエリ数をリセット
            usage.monthly_queries = 0
            usage.month_year = current_month

        if usage.monthly_queries >= quota.max_monthly_queries:
            return False, f"Monthly query limit exceeded ({usage.monthly_queries}/{quota.max_monthly_queries})"

        return True, "OK"

    def update_usage_after_upload(self, user_id: str, vector_count: int, document_size_mb: float):
        """ドキュメントアップロード後の使用状況更新"""
        if not self.usage_table:
            return

        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            
            self.usage_table.update_item(
                Key={'user_id': user_id},
                UpdateExpression="""
                    ADD current_documents :doc_inc, 
                        current_vectors :vec_inc, 
                        current_storage_size_mb :size_inc,
                        daily_uploads :upload_inc
                    SET upload_date = :upload_date,
                        last_upload_date = :last_upload_date
                """,
                ExpressionAttributeValues={
                    ':doc_inc': 1,
                    ':vec_inc': vector_count,
                    ':size_inc': document_size_mb,
                    ':upload_inc': 1,
                    ':upload_date': today,
                    ':last_upload_date': datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            print(f"Error updating usage after upload: {e}")

    def update_usage_after_query(self, user_id: str):
        """クエリ実行後の使用状況更新"""
        if not self.usage_table:
            return

        try:
            current_month = datetime.utcnow().strftime("%Y-%m")
            
            self.usage_table.update_item(
                Key={'user_id': user_id},
                UpdateExpression="""
                    ADD monthly_queries :query_inc
                    SET month_year = :month_year,
                        last_query_date = :last_query_date
                """,
                ExpressionAttributeValues={
                    ':query_inc': 1,
                    ':month_year': current_month,
                    ':last_query_date': datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            print(f"Error updating usage after query: {e}")

    def get_quota_status(self, user_id: str) -> Dict[str, Any]:
        """ユーザーのクォータ状況を取得"""
        quota = self.get_user_quota(user_id)
        usage = self.get_user_usage(user_id)
        
        # パーセンテージ計算
        def safe_percentage(current: float, maximum: float) -> float:
            return (current / maximum * 100) if maximum > 0 else 0.0

        return {
            "user_id": user_id,
            "plan_type": quota.plan_type,
            "quotas": {
                "documents": {
                    "current": usage.current_documents,
                    "max": quota.max_documents,
                    "percentage": safe_percentage(usage.current_documents, quota.max_documents)
                },
                "vectors": {
                    "current": usage.current_vectors,
                    "max": quota.max_vectors,
                    "percentage": safe_percentage(usage.current_vectors, quota.max_vectors)
                },
                "storage": {
                    "current_mb": usage.current_storage_size_mb,
                    "max_mb": quota.max_storage_size_mb,
                    "percentage": safe_percentage(usage.current_storage_size_mb, quota.max_storage_size_mb)
                },
                "monthly_queries": {
                    "current": usage.monthly_queries,
                    "max": quota.max_monthly_queries,
                    "percentage": safe_percentage(usage.monthly_queries, quota.max_monthly_queries),
                    "month": usage.month_year
                },
                "daily_uploads": {
                    "current": usage.daily_uploads,
                    "max": quota.max_daily_uploads,
                    "percentage": safe_percentage(usage.daily_uploads, quota.max_daily_uploads),
                    "date": usage.upload_date
                }
            },
            "last_updated": usage.last_query_date or usage.last_upload_date
        }

    def set_user_plan(self, user_id: str, plan_type: str) -> bool:
        """ユーザーのプランを設定"""
        if plan_type not in self.PLAN_DEFAULTS:
            raise ValueError(f"Invalid plan type: {plan_type}")

        if not self.quota_table:
            return False

        try:
            defaults = self.PLAN_DEFAULTS[plan_type]
            quota = UserQuota(user_id=user_id, plan_type=plan_type, **defaults)
            
            self.quota_table.put_item(Item=asdict(quota))
            return True
        except Exception as e:
            print(f"Error setting user plan: {e}")
            return False

    def reset_monthly_usage(self, user_id: str):
        """月間使用量をリセット（月初めに実行）"""
        if not self.usage_table:
            return

        try:
            current_month = datetime.utcnow().strftime("%Y-%m")
            
            self.usage_table.update_item(
                Key={'user_id': user_id},
                UpdateExpression="SET monthly_queries = :zero, month_year = :month",
                ExpressionAttributeValues={
                    ':zero': 0,
                    ':month': current_month
                }
            )
        except Exception as e:
            print(f"Error resetting monthly usage: {e}")

    def reset_daily_usage(self, user_id: str):
        """日次使用量をリセット（日初めに実行）"""
        if not self.usage_table:
            return

        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            
            self.usage_table.update_item(
                Key={'user_id': user_id},
                UpdateExpression="SET daily_uploads = :zero, upload_date = :date",
                ExpressionAttributeValues={
                    ':zero': 0,
                    ':date': today
                }
            )
        except Exception as e:
            print(f"Error resetting daily usage: {e}")

    # 画像関連クォータ管理メソッド
    def check_image_quota_before_upload(self, user_id: str) -> Tuple[bool, str]:
        """画像アップロード前のクォータチェック"""
        quota = self.get_user_quota(user_id)
        usage = self.get_user_usage(user_id)
        
        # 画像数制限チェック
        current_images = getattr(usage, 'current_images', 0)
        max_images = getattr(quota, 'max_images', self.PLAN_DEFAULTS[quota.plan_type]['max_images'])
        
        if current_images >= max_images:
            return False, f"画像数制限に達しています ({current_images}/{max_images})"
        
        # 画像ストレージ制限は個別ファイルでチェック
        return True, "OK"
    
    def check_image_storage_quota(self, user_id: str, new_image_size_mb: float) -> Tuple[bool, str]:
        """画像ストレージクォータチェック"""
        quota = self.get_user_quota(user_id)
        usage = self.get_user_usage(user_id)
        
        current_image_storage = getattr(usage, 'current_image_storage_mb', 0.0)
        max_image_storage = getattr(quota, 'max_image_storage_mb', self.PLAN_DEFAULTS[quota.plan_type]['max_image_storage_mb'])
        
        if current_image_storage + new_image_size_mb > max_image_storage:
            return False, f"画像ストレージ制限を超過します ({current_image_storage + new_image_size_mb:.2f}/{max_image_storage} MB)"
        
        return True, "OK"
    
    def check_image_analysis_quota(self, user_id: str) -> Tuple[bool, str]:
        """画像分析実行クォータチェック"""
        quota = self.get_user_quota(user_id)
        usage = self.get_user_usage(user_id)
        
        # 現在の月をチェック
        current_month = datetime.utcnow().strftime("%Y-%m")
        usage_month = getattr(usage, 'analysis_month_year', current_month)
        
        # 月が変わった場合はリセット
        monthly_analyses = getattr(usage, 'monthly_image_analyses', 0)
        if usage_month != current_month:
            monthly_analyses = 0
        
        max_analyses = getattr(quota, 'max_monthly_image_analyses', self.PLAN_DEFAULTS[quota.plan_type]['max_monthly_image_analyses'])
        
        if monthly_analyses >= max_analyses:
            return False, f"月間画像分析制限に達しています ({monthly_analyses}/{max_analyses})"
        
        return True, "OK"
    
    def update_image_usage_after_upload(self, user_id: str, image_size_mb: float, vector_count: int):
        """画像アップロード後の使用量更新"""
        if not self.usage_table:
            return
        
        try:
            current_month = datetime.utcnow().strftime("%Y-%m")
            
            self.usage_table.update_item(
                Key={'user_id': user_id},
                UpdateExpression="""
                    ADD current_images :img_inc,
                        current_image_storage_mb :storage_inc,
                        current_image_vectors :vec_inc,
                        monthly_image_analyses :analysis_inc
                    SET analysis_month_year = :month_year,
                        last_image_upload_date = :upload_date
                """,
                ExpressionAttributeValues={
                    ':img_inc': 1,
                    ':storage_inc': image_size_mb,
                    ':vec_inc': vector_count,
                    ':analysis_inc': 1,  # OCR/Vision分析実行としてカウント
                    ':month_year': current_month,
                    ':upload_date': datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            print(f"Error updating image usage after upload: {e}")
    
    def update_image_usage_after_delete(self, user_id: str, image_size_mb: float, vector_count: int):
        """画像削除後の使用量更新"""
        if not self.usage_table:
            return
        
        try:
            self.usage_table.update_item(
                Key={'user_id': user_id},
                UpdateExpression="""
                    ADD current_images :img_dec,
                        current_image_storage_mb :storage_dec,
                        current_image_vectors :vec_dec
                    SET last_image_delete_date = :delete_date
                """,
                ExpressionAttributeValues={
                    ':img_dec': -1,
                    ':storage_dec': -image_size_mb,
                    ':vec_dec': -vector_count,
                    ':delete_date': datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            print(f"Error updating image usage after delete: {e}")
    
    def get_extended_quota_status(self, user_id: str) -> Dict[str, Any]:
        """画像関連を含む拡張クォータ状況を取得"""
        base_status = self.get_quota_status(user_id)
        quota = self.get_user_quota(user_id)
        usage = self.get_user_usage(user_id)
        
        # 画像関連クォータを追加
        def safe_percentage(current: float, maximum: float) -> float:
            return (current / maximum * 100) if maximum > 0 else 0.0
        
        # 画像関連の使用状況を取得
        current_images = getattr(usage, 'current_images', 0)
        current_image_storage = getattr(usage, 'current_image_storage_mb', 0.0)
        current_image_vectors = getattr(usage, 'current_image_vectors', 0)
        monthly_image_analyses = getattr(usage, 'monthly_image_analyses', 0)
        
        # 制限値を取得
        max_images = getattr(quota, 'max_images', self.PLAN_DEFAULTS[quota.plan_type]['max_images'])
        max_image_storage = getattr(quota, 'max_image_storage_mb', self.PLAN_DEFAULTS[quota.plan_type]['max_image_storage_mb'])
        max_image_vectors = getattr(quota, 'max_image_vectors', self.PLAN_DEFAULTS[quota.plan_type]['max_image_vectors'])
        max_analyses = getattr(quota, 'max_monthly_image_analyses', self.PLAN_DEFAULTS[quota.plan_type]['max_monthly_image_analyses'])
        
        # 画像関連クォータを追加
        base_status["quotas"]["images"] = {
            "count": current_images,
            "limit": max_images,
            "usage_percentage": safe_percentage(current_images, max_images)
        }
        
        base_status["quotas"]["image_storage"] = {
            "used_mb": current_image_storage,
            "limit_mb": max_image_storage,
            "usage_percentage": safe_percentage(current_image_storage, max_image_storage)
        }
        
        base_status["quotas"]["image_vectors"] = {
            "count": current_image_vectors,
            "limit": max_image_vectors,
            "usage_percentage": safe_percentage(current_image_vectors, max_image_vectors)
        }
        
        base_status["quotas"]["monthly_image_analyses"] = {
            "count": monthly_image_analyses,
            "limit": max_analyses,
            "usage_percentage": safe_percentage(monthly_image_analyses, max_analyses),
            "month": getattr(usage, 'analysis_month_year', datetime.utcnow().strftime("%Y-%m"))
        }
        
        return base_status


# 便利な関数
def estimate_vector_count(text: str, chunk_size: int = 1000) -> int:
    """テキストから推定ベクトル数を計算"""
    if not text:
        return 0
    
    # 概算: chunk_size文字ごとに1つのベクトル
    # 実際にはオーバーラップがあるため、少し多めに見積もる
    estimated_chunks = len(text) // chunk_size
    if len(text) % chunk_size > 0:
        estimated_chunks += 1
    
    # オーバーラップを考慮して20%増し
    return int(estimated_chunks * 1.2)


def get_document_size_mb(text: str) -> float:
    """ドキュメントのサイズをMBで取得"""
    return len(text.encode('utf-8')) / (1024 * 1024)