"""
画像ストレージ管理クライアント
S3での画像保存とDynamoDBでのメタデータ管理
"""
import os
import boto3
import json
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
from PIL import Image
import io


class ImageStorageClient:
    """画像ストレージ管理クラス"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.dynamodb = boto3.resource('dynamodb')
        
        # 環境変数から設定を取得
        self.image_bucket_name = os.getenv('IMAGE_BUCKET_NAME', 'rag-images-bucket')
        self.image_table_name = os.getenv('IMAGE_TABLE_NAME', 'rag-image-metadata')
        
        try:
            self.image_table = self.dynamodb.Table(self.image_table_name)
        except Exception:
            self.image_table = None
    
    def generate_s3_key(self, user_id: str, image_id: str, filename: str, is_thumbnail: bool = False) -> str:
        """S3オブジェクトキーを生成"""
        prefix = "thumbnails" if is_thumbnail else "images"
        sanitized_user_id = user_id.replace("/", "_").replace("\\", "_")
        return f"{prefix}/{sanitized_user_id}/{image_id}/{filename}"
    
    def create_thumbnail(self, image_data: bytes, max_size: Tuple[int, int] = (200, 200)) -> bytes:
        """サムネイル画像を作成"""
        try:
            image = Image.open(io.BytesIO(image_data))
            
            # アスペクト比を保持してリサイズ
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # JPEG形式で保存
            output = io.BytesIO()
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            image.save(output, format="JPEG", quality=85)
            
            return output.getvalue()
            
        except Exception as e:
            print(f"Error creating thumbnail: {str(e)}")
            return image_data  # 失敗した場合は元画像を返す
    
    def save_image(self, user_id: str, image_id: str, image_data: bytes, filename: str) -> Tuple[str, str]:
        """S3に画像を保存し、URLを返す"""
        try:
            # 元画像を保存
            image_key = self.generate_s3_key(user_id, image_id, filename)
            self.s3_client.put_object(
                Bucket=self.image_bucket_name,
                Key=image_key,
                Body=image_data,
                ContentType='image/jpeg'
            )
            
            # サムネイル作成・保存
            thumbnail_data = self.create_thumbnail(image_data)
            thumbnail_filename = f"thumb_{filename}"
            thumbnail_key = self.generate_s3_key(user_id, image_id, thumbnail_filename, is_thumbnail=True)
            
            self.s3_client.put_object(
                Bucket=self.image_bucket_name,
                Key=thumbnail_key,
                Body=thumbnail_data,
                ContentType='image/jpeg'
            )
            
            # 署名付きURLを生成（24時間有効）
            image_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.image_bucket_name, 'Key': image_key},
                ExpiresIn=86400  # 24時間
            )
            
            thumbnail_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.image_bucket_name, 'Key': thumbnail_key},
                ExpiresIn=86400  # 24時間
            )
            
            return image_url, thumbnail_url
            
        except Exception as e:
            print(f"Error saving image to S3: {str(e)}")
            raise Exception(f"画像の保存に失敗しました: {str(e)}")
    
    def save_image_metadata(self, metadata: Dict[str, Any]) -> bool:
        """DynamoDBに画像メタデータを保存"""
        if not self.image_table:
            print("DynamoDB table not available, skipping metadata save")
            return False
        
        try:
            # DynamoDB用にデータを準備
            item = {
                'image_id': metadata['id'],
                'user_id': metadata['user_id'],
                'title': metadata['title'],
                'filename': metadata['filename'],
                'upload_date': metadata['upload_date'],
                'size': metadata['size'],
                'tags': metadata.get('tags', []),
                'ocr_text': metadata.get('ocr_text', ''),
                'analysis_results': json.dumps(metadata.get('analysis_results', {})),
                'knowledge_vectors_created': metadata.get('knowledge_vectors_created', 0),
                'processing_status': metadata.get('processing_status', 'completed'),
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }
            
            self.image_table.put_item(Item=item)
            return True
            
        except Exception as e:
            print(f"Error saving image metadata: {str(e)}")
            return False
    
    def get_image_info(self, user_id: str, image_id: str) -> Optional[Dict[str, Any]]:
        """画像情報を取得"""
        if not self.image_table:
            return None
        
        try:
            response = self.image_table.get_item(
                Key={
                    'image_id': image_id,
                    'user_id': user_id
                }
            )
            
            if 'Item' not in response:
                return None
            
            item = response['Item']
            
            # S3署名付きURL再生成
            image_key = self.generate_s3_key(user_id, image_id, item['filename'])
            thumbnail_key = self.generate_s3_key(user_id, image_id, f"thumb_{item['filename']}", is_thumbnail=True)
            
            image_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.image_bucket_name, 'Key': image_key},
                ExpiresIn=86400
            )
            
            thumbnail_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.image_bucket_name, 'Key': thumbnail_key},
                ExpiresIn=86400
            )
            
            # レスポンス形式を整える
            return {
                'id': item['image_id'],
                'title': item['title'],
                'filename': item['filename'],
                'url': image_url,
                'thumbnail_url': thumbnail_url,
                'upload_date': item['upload_date'],
                'size': int(item['size']),
                'tags': item.get('tags', []),
                'ocr_text': item.get('ocr_text', ''),
                'analysis_results': json.loads(item.get('analysis_results', '{}')),
                'knowledge_vectors_created': int(item.get('knowledge_vectors_created', 0)),
                'processing_status': item.get('processing_status', 'completed')
            }
            
        except Exception as e:
            print(f"Error getting image info: {str(e)}")
            return None
    
    def list_user_images(
        self, 
        user_id: str, 
        limit: int = 20, 
        offset: int = 0,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """ユーザーの画像一覧を取得"""
        if not self.image_table:
            return [], 0
        
        try:
            # DynamoDBクエリでユーザーの全画像を取得
            response = self.image_table.query(
                IndexName='user_id-upload_date-index',  # GSIが必要
                KeyConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={
                    ':user_id': user_id
                },
                ScanIndexForward=False  # 新しい順
            )
            
            items = response.get('Items', [])
            
            # フィルタリング適用
            filtered_items = []
            for item in items:
                # タグフィルタ
                if tags:
                    item_tags = item.get('tags', [])
                    if not any(tag in item_tags for tag in tags):
                        continue
                
                # 検索フィルタ
                if search:
                    title = item.get('title', '').lower()
                    if search.lower() not in title:
                        continue
                
                filtered_items.append(item)
            
            total_count = len(filtered_items)
            
            # ページネーション適用
            paginated_items = filtered_items[offset:offset + limit]
            
            # レスポンス形式に変換
            result_images = []
            for item in paginated_items:
                # S3署名付きURL再生成
                image_key = self.generate_s3_key(user_id, item['image_id'], item['filename'])
                thumbnail_key = self.generate_s3_key(user_id, item['image_id'], f"thumb_{item['filename']}", is_thumbnail=True)
                
                try:
                    image_url = self.s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': self.image_bucket_name, 'Key': image_key},
                        ExpiresIn=86400
                    )
                    
                    thumbnail_url = self.s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': self.image_bucket_name, 'Key': thumbnail_key},
                        ExpiresIn=86400
                    )
                except Exception:
                    # URL生成に失敗した場合はスキップ
                    continue
                
                result_images.append({
                    'id': item['image_id'],
                    'title': item['title'],
                    'filename': item['filename'],
                    'url': image_url,
                    'thumbnail_url': thumbnail_url,
                    'upload_date': item['upload_date'],
                    'size': int(item['size']),
                    'tags': item.get('tags', []),
                    'ocr_text': item.get('ocr_text', ''),
                    'analysis_results': json.loads(item.get('analysis_results', '{}'))
                })
            
            return result_images, total_count
            
        except Exception as e:
            print(f"Error listing user images: {str(e)}")
            return [], 0
    
    def delete_image(self, user_id: str, image_id: str) -> bool:
        """画像とメタデータを削除"""
        try:
            # まず画像情報を取得
            image_info = self.get_image_info(user_id, image_id)
            if not image_info:
                return False
            
            filename = image_info['filename']
            
            # S3から画像とサムネイルを削除
            image_key = self.generate_s3_key(user_id, image_id, filename)
            thumbnail_key = self.generate_s3_key(user_id, image_id, f"thumb_{filename}", is_thumbnail=True)
            
            try:
                self.s3_client.delete_object(Bucket=self.image_bucket_name, Key=image_key)
                self.s3_client.delete_object(Bucket=self.image_bucket_name, Key=thumbnail_key)
            except Exception:
                pass  # S3削除失敗は継続
            
            # DynamoDBからメタデータを削除
            if self.image_table:
                self.image_table.delete_item(
                    Key={
                        'image_id': image_id,
                        'user_id': user_id
                    }
                )
            
            return True
            
        except Exception as e:
            print(f"Error deleting image: {str(e)}")
            return False
    
    def get_user_image_statistics(self, user_id: str) -> Dict[str, Any]:
        """ユーザーの画像関連統計を取得"""
        if not self.image_table:
            return {
                'user_id': user_id,
                'total_images': 0,
                'total_storage_mb': 0.0,
                'total_image_vectors': 0,
                'analysis_count': {'ocr': 0, 'vision': 0},
                'tag_distribution': {},
                'upload_trend': []
            }
        
        try:
            # ユーザーの全画像を取得
            response = self.image_table.query(
                IndexName='user_id-upload_date-index',
                KeyConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={
                    ':user_id': user_id
                }
            )
            
            items = response.get('Items', [])
            
            # 統計計算
            total_images = len(items)
            total_storage_bytes = sum(int(item.get('size', 0)) for item in items)
            total_storage_mb = total_storage_bytes / (1024 * 1024)
            total_vectors = sum(int(item.get('knowledge_vectors_created', 0)) for item in items)
            
            # 分析実行回数
            ocr_count = sum(1 for item in items if item.get('ocr_text', ''))
            vision_count = sum(1 for item in items if item.get('analysis_results', '{}') != '{}')
            
            # タグ分布
            tag_distribution = {}
            for item in items:
                tags = item.get('tags', [])
                for tag in tags:
                    tag_distribution[tag] = tag_distribution.get(tag, 0) + 1
            
            # アップロード傾向（過去30日）
            upload_trend = []
            today = datetime.utcnow()
            for i in range(30):
                date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
                count = sum(1 for item in items if item.get('upload_date', '').startswith(date))
                upload_trend.append({
                    'date': date,
                    'count': count
                })
            
            upload_trend.reverse()  # 古い順に並び替え
            
            return {
                'user_id': user_id,
                'total_images': total_images,
                'total_storage_mb': round(total_storage_mb, 2),
                'total_image_vectors': total_vectors,
                'analysis_count': {
                    'ocr': ocr_count,
                    'vision': vision_count
                },
                'tag_distribution': tag_distribution,
                'upload_trend': upload_trend
            }
            
        except Exception as e:
            print(f"Error getting image statistics: {str(e)}")
            return {
                'user_id': user_id,
                'total_images': 0,
                'total_storage_mb': 0.0,
                'total_image_vectors': 0,
                'analysis_count': {'ocr': 0, 'vision': 0},
                'tag_distribution': {},
                'upload_trend': []
            }