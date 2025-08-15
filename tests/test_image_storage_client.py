"""
画像ストレージクライアントのテストケース
"""
import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch, MagicMock
from io import BytesIO
from PIL import Image
import uuid
import json
from datetime import datetime

# テスト対象のモジュールをインポート
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from image_storage_client import ImageStorageClient


class TestImageStorageClient:
    """画像ストレージクライアントのテストクラス"""
    
    @pytest.fixture
    def sample_image_data(self):
        """サンプル画像データを作成"""
        img = Image.new('RGB', (200, 200), color='blue')
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG')
        return img_bytes.getvalue()
    
    @pytest.fixture
    def client(self):
        """テスト用クライアントインスタンス"""
        return ImageStorageClient()
    
    @pytest.fixture
    def mock_environment(self):
        """環境変数のモック"""
        with patch.dict(os.environ, {
            'IMAGE_BUCKET_NAME': 'test-image-bucket',
            'IMAGE_TABLE_NAME': 'test-image-table',
            'AWS_REGION': 'us-east-1'
        }):
            yield

    @mock_aws
    def test_save_image_success(self, client, sample_image_data, mock_environment):
        """画像保存成功テスト"""
        # S3バケットを作成
        s3_client = boto3.client('s3', region_name='us-east-1')
        s3_client.create_bucket(Bucket='test-image-bucket')
        
        # DynamoDBテーブルを作成
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        dynamodb.create_table(
            TableName='test-image-table',
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                {'AttributeName': 'image_id', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
                {'AttributeName': 'image_id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # 画像を保存
        user_id = "test-user-123"
        image_id = str(uuid.uuid4())
        filename = "test_image.jpg"
        
        s3_key, thumbnail_key = client.save_image(
            user_id=user_id,
            image_id=image_id,
            image_data=sample_image_data,
            filename=filename
        )
        
        # S3にアップロードされたことを確認
        assert s3_key.startswith(f"user-{user_id}-images/{image_id}/")
        assert thumbnail_key.startswith(f"user-{user_id}-images/{image_id}/thumbnail_")
        
        # S3オブジェクトの存在確認
        s3_response = s3_client.head_object(Bucket='test-image-bucket', Key=s3_key)
        assert s3_response['ContentLength'] > 0
        
        # サムネイルの存在確認
        thumbnail_response = s3_client.head_object(Bucket='test-image-bucket', Key=thumbnail_key)
        assert thumbnail_response['ContentLength'] > 0
    
    @mock_aws
    def test_save_metadata_success(self, client, mock_environment):
        """メタデータ保存成功テスト"""
        # DynamoDBテーブルを作成
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='test-image-table',
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                {'AttributeName': 'image_id', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
                {'AttributeName': 'image_id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # メタデータを保存
        user_id = "test-user-123"
        image_id = str(uuid.uuid4())
        metadata = {
            "title": "テスト画像",
            "filename": "test.jpg",
            "size_mb": 1.5,
            "s3_key": f"user-{user_id}-images/{image_id}/test.jpg",
            "thumbnail_key": f"user-{user_id}-images/{image_id}/thumbnail_test.jpg",
            "tags": ["test", "sample"],
            "ocr_result": {
                "text": "サンプルテキスト",
                "confidence": 0.95
            },
            "vision_result": {
                "description": "テスト画像の説明",
                "confidence": 0.90
            }
        }
        
        success = client.save_metadata(user_id, image_id, metadata)
        assert success
        
        # DynamoDBから取得して確認
        response = table.get_item(Key={'user_id': user_id, 'image_id': image_id})
        assert 'Item' in response
        
        item = response['Item']
        assert item['title'] == "テスト画像"
        assert item['filename'] == "test.jpg"
        assert item['size_mb'] == 1.5
        assert item['tags'] == ["test", "sample"]
        assert item['ocr_result']['text'] == "サンプルテキスト"
        assert item['vision_result']['description'] == "テスト画像の説明"
        assert 'created_at' in item
    
    @mock_aws
    def test_list_user_images_success(self, client, mock_environment):
        """ユーザー画像一覧取得成功テスト"""
        # DynamoDBテーブルを作成
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='test-image-table',
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                {'AttributeName': 'image_id', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
                {'AttributeName': 'image_id', 'AttributeType': 'S'},
                {'AttributeName': 'created_at', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'created_at-index',
                    'KeySchema': [
                        {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                }
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # テストデータを挿入
        user_id = "test-user-123"
        test_images = [
            {
                'user_id': user_id,
                'image_id': f'img-{i:03d}',
                'title': f'テスト画像{i}',
                'filename': f'test{i}.jpg',
                'size_mb': i * 0.5,
                'tags': ['test', f'sample{i}'],
                'created_at': f'2024-01-{i:02d}T00:00:00Z'
            }
            for i in range(1, 6)
        ]
        
        for img in test_images:
            table.put_item(Item=img)
        
        # 一覧を取得（デフォルト）
        images = client.list_user_images(
            user_id=user_id,
            limit=10,
            offset=0
        )
        
        assert len(images) == 5
        assert images[0]['title'] == 'テスト画像1'
        
        # ページネーション
        images_page = client.list_user_images(
            user_id=user_id,
            limit=2,
            offset=2
        )
        
        assert len(images_page) == 2
        assert images_page[0]['title'] == 'テスト画像3'
        
        # タグフィルター
        filtered_images = client.list_user_images(
            user_id=user_id,
            limit=10,
            offset=0,
            tags=['sample1']
        )
        
        assert len(filtered_images) == 1
        assert filtered_images[0]['title'] == 'テスト画像1'
    
    @mock_aws
    def test_get_image_metadata_success(self, client, mock_environment):
        """画像メタデータ取得成功テスト"""
        # DynamoDBテーブルを作成
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='test-image-table',
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                {'AttributeName': 'image_id', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
                {'AttributeName': 'image_id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # テストデータを挿入
        user_id = "test-user-123"
        image_id = "img-001"
        test_data = {
            'user_id': user_id,
            'image_id': image_id,
            'title': 'テスト画像',
            'filename': 'test.jpg',
            'size_mb': 2.0,
            's3_key': f'user-{user_id}-images/{image_id}/test.jpg',
            'thumbnail_key': f'user-{user_id}-images/{image_id}/thumbnail_test.jpg',
            'created_at': '2024-01-01T00:00:00Z',
            'ocr_result': {
                'text': 'OCRテキスト',
                'confidence': 0.88
            },
            'vision_result': {
                'description': '画像の説明',
                'confidence': 0.92
            }
        }
        
        table.put_item(Item=test_data)
        
        # メタデータを取得
        metadata = client.get_image_metadata(user_id, image_id)
        
        assert metadata is not None
        assert metadata['title'] == 'テスト画像'
        assert metadata['filename'] == 'test.jpg'
        assert metadata['size_mb'] == 2.0
        assert metadata['ocr_result']['text'] == 'OCRテキスト'
        assert metadata['vision_result']['description'] == '画像の説明'
    
    @mock_aws
    def test_generate_presigned_url_success(self, client, mock_environment):
        """署名付きURL生成成功テスト"""
        # S3バケットを作成
        s3_client = boto3.client('s3', region_name='us-east-1')
        s3_client.create_bucket(Bucket='test-image-bucket')
        
        # オブジェクトをアップロード
        s3_key = "user-test-123-images/img-001/test.jpg"
        s3_client.put_object(
            Bucket='test-image-bucket',
            Key=s3_key,
            Body=b'test image data',
            ContentType='image/jpeg'
        )
        
        # 署名付きURLを生成
        presigned_url = client.generate_presigned_url(s3_key)
        
        assert presigned_url is not None
        assert 'test-image-bucket' in presigned_url
        assert s3_key in presigned_url
        assert 'X-Amz-Signature' in presigned_url
    
    @mock_aws
    def test_delete_image_success(self, client, mock_environment):
        """画像削除成功テスト"""
        # S3バケットを作成
        s3_client = boto3.client('s3', region_name='us-east-1')
        s3_client.create_bucket(Bucket='test-image-bucket')
        
        # DynamoDBテーブルを作成
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='test-image-table',
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                {'AttributeName': 'image_id', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
                {'AttributeName': 'image_id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # テストデータを準備
        user_id = "test-user-123"
        image_id = "img-001"
        s3_key = f"user-{user_id}-images/{image_id}/test.jpg"
        thumbnail_key = f"user-{user_id}-images/{image_id}/thumbnail_test.jpg"
        
        # S3オブジェクトを作成
        s3_client.put_object(
            Bucket='test-image-bucket',
            Key=s3_key,
            Body=b'test image data'
        )
        s3_client.put_object(
            Bucket='test-image-bucket',
            Key=thumbnail_key,
            Body=b'test thumbnail data'
        )
        
        # DynamoDBにメタデータを保存
        table.put_item(Item={
            'user_id': user_id,
            'image_id': image_id,
            's3_key': s3_key,
            'thumbnail_key': thumbnail_key,
            'title': 'テスト画像'
        })
        
        # 画像を削除
        success = client.delete_image(user_id, image_id)
        assert success
        
        # S3オブジェクトが削除されたことを確認
        with pytest.raises(s3_client.exceptions.NoSuchKey):
            s3_client.head_object(Bucket='test-image-bucket', Key=s3_key)
        
        with pytest.raises(s3_client.exceptions.NoSuchKey):
            s3_client.head_object(Bucket='test-image-bucket', Key=thumbnail_key)
        
        # DynamoDBメタデータが削除されたことを確認
        response = table.get_item(Key={'user_id': user_id, 'image_id': image_id})
        assert 'Item' not in response
    
    def test_create_thumbnail(self, client, sample_image_data):
        """サムネイル作成テスト"""
        thumbnail_data = client._create_thumbnail(sample_image_data)
        
        assert thumbnail_data is not None
        assert len(thumbnail_data) > 0
        
        # サムネイルが正しいサイズであることを確認
        thumbnail_img = Image.open(BytesIO(thumbnail_data))
        assert thumbnail_img.size == (200, 200)
    
    @mock_aws
    def test_search_images_by_content(self, client, mock_environment):
        """内容による画像検索テスト"""
        # DynamoDBテーブルを作成
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='test-image-table',
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                {'AttributeName': 'image_id', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
                {'AttributeName': 'image_id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # テストデータを挿入
        user_id = "test-user-123"
        test_images = [
            {
                'user_id': user_id,
                'image_id': 'img-001',
                'title': 'ドキュメント画像',
                'ocr_result': {'text': 'これは重要な文書です'},
                'vision_result': {'description': 'ビジネス文書が写っています'}
            },
            {
                'user_id': user_id,
                'image_id': 'img-002',
                'title': '風景画像',
                'ocr_result': {'text': ''},
                'vision_result': {'description': '美しい山の風景が写っています'}
            }
        ]
        
        for img in test_images:
            table.put_item(Item=img)
        
        # 検索実行
        results = client.search_images_by_content(
            user_id=user_id,
            search_query="文書"
        )
        
        assert len(results) == 2  # タイトル・OCR・Vision全てから検索
        
        # より具体的な検索
        document_results = client.search_images_by_content(
            user_id=user_id,
            search_query="重要な文書"
        )
        
        assert len(document_results) >= 1
        assert any(r['image_id'] == 'img-001' for r in document_results)
    
    @mock_aws
    def test_get_user_image_statistics(self, client, mock_environment):
        """ユーザー画像統計取得テスト"""
        # DynamoDBテーブルを作成
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='test-image-table',
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                {'AttributeName': 'image_id', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
                {'AttributeName': 'image_id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # テストデータを挿入
        user_id = "test-user-123"
        test_images = [
            {
                'user_id': user_id,
                'image_id': f'img-{i:03d}',
                'size_mb': i * 0.5,
                'created_at': f'2024-01-{i:02d}T00:00:00Z'
            }
            for i in range(1, 6)
        ]
        
        for img in test_images:
            table.put_item(Item=img)
        
        # 統計を取得
        stats = client.get_user_image_statistics(user_id)
        
        assert stats['total_images'] == 5
        assert stats['total_storage_mb'] == 7.5  # 0.5 + 1.0 + 1.5 + 2.0 + 2.5
        assert stats['average_size_mb'] == 1.5
        assert len(stats['recent_uploads']) <= 10
    
    def test_error_handling(self, client):
        """エラーハンドリングのテスト"""
        # 存在しない画像のメタデータ取得
        metadata = client.get_image_metadata("nonexistent-user", "nonexistent-image")
        assert metadata is None
        
        # 不正なデータでのサムネイル作成
        thumbnail = client._create_thumbnail(b"invalid image data")
        assert thumbnail is None
        
        # 存在しない画像の削除
        success = client.delete_image("nonexistent-user", "nonexistent-image")
        assert not success


if __name__ == '__main__':
    pytest.main([__file__, '-v'])