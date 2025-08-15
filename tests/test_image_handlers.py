"""
画像ハンドラー関数のテストケース
"""
import json
import pytest
import boto3
from moto import mock_s3, mock_dynamodb, mock_textract, mock_rekognition
from unittest.mock import patch, MagicMock
import base64
from io import BytesIO
from PIL import Image

# テスト対象のモジュールをインポート
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from image_handlers import (
    image_upload_handler,
    image_list_handler,
    image_detail_handler,
    image_delete_handler,
    image_query_handler,
    image_statistics_handler
)


class TestImageHandlers:
    """画像ハンドラーのテストクラス"""
    
    @pytest.fixture
    def sample_image_data(self):
        """サンプル画像データを作成"""
        # 小さなテスト用JPEG画像を作成
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG')
        return img_bytes.getvalue()
    
    @pytest.fixture
    def cognito_event_base(self):
        """Cognito認証情報を含むベースイベント"""
        return {
            "requestContext": {
                "authorizer": {
                    "claims": {
                        "sub": "test-user-123",
                        "email": "test@example.com"
                    }
                }
            },
            "headers": {
                "Content-Type": "multipart/form-data; boundary=----WebKitFormBoundary"
            }
        }
    
    @pytest.fixture
    def mock_environment(self):
        """環境変数のモック"""
        with patch.dict(os.environ, {
            'IMAGE_BUCKET_NAME': 'test-image-bucket',
            'IMAGE_TABLE_NAME': 'test-image-table',
            'VECTOR_BUCKET_NAME': 'test-vector-bucket',
            'USER_QUOTA_TABLE': 'test-quota-table',
            'USER_USAGE_TABLE': 'test-usage-table',
            'AWS_REGION': 'us-east-1'
        }):
            yield

    @mock_s3
    @mock_dynamodb
    def test_image_upload_success(self, sample_image_data, cognito_event_base, mock_environment):
        """画像アップロード成功テスト"""
        # DynamoDBテーブルを作成
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        
        # 画像メタデータテーブル
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
        
        # クォータテーブル
        dynamodb.create_table(
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
        dynamodb.create_table(
            TableName='test-usage-table',
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # S3バケットを作成
        s3_client = boto3.client('s3', region_name='us-east-1')
        s3_client.create_bucket(Bucket='test-image-bucket')
        
        # マルチパートデータを作成
        boundary = "----WebKitFormBoundary"
        image_b64 = base64.b64encode(sample_image_data).decode('utf-8')
        body = f"""------WebKitFormBoundary\r
Content-Disposition: form-data; name="image"; filename="test.jpg"\r
Content-Type: image/jpeg\r
\r
{image_b64}\r
------WebKitFormBoundary\r
Content-Disposition: form-data; name="title"\r
\r
Test Image\r
------WebKitFormBoundary--"""
        
        # イベントを構築
        event = {
            **cognito_event_base,
            "body": body,
            "headers": {
                "Content-Type": f"multipart/form-data; boundary={boundary}"
            }
        }
        
        # OCR・Vision処理をモック
        with patch('image_handlers.OCRVisionProcessor') as mock_processor:
            mock_instance = mock_processor.return_value
            mock_instance.extract_text_from_image.return_value = {
                'text': 'Sample OCR text',
                'confidence': 0.95
            }
            mock_instance.analyze_image_content.return_value = {
                'description': 'A test image',
                'confidence': 0.90,
                'labels': [{'name': 'Test', 'confidence': 0.9}]
            }
            
            # ナレッジ管理をモック
            with patch('image_handlers.ImageKnowledgeManager') as mock_knowledge:
                mock_knowledge_instance = mock_knowledge.return_value
                mock_knowledge_instance.create_knowledge_from_image.return_value = 5
                
                # ハンドラーを実行
                response = image_upload_handler(event, None)
        
        # レスポンスを検証
        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert 'image_id' in response_body
        assert response_body['message'] == '画像が正常にアップロードされました'
        assert response_body['analysis']['ocr']['confidence'] == 0.95
        assert response_body['analysis']['vision']['confidence'] == 0.90
    
    @mock_dynamodb
    def test_image_list_success(self, cognito_event_base, mock_environment):
        """画像一覧取得成功テスト"""
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
        table.put_item(Item={
            'user_id': 'test-user-123',
            'image_id': 'img-001',
            'title': 'Test Image 1',
            'filename': 'test1.jpg',
            'created_at': '2024-01-01T00:00:00Z',
            'size_mb': 1.5,
            'tags': ['test', 'sample']
        })
        
        # イベントを構築
        event = {
            **cognito_event_base,
            "queryStringParameters": {
                "limit": "20",
                "offset": "0"
            }
        }
        
        # ハンドラーを実行
        response = image_list_handler(event, None)
        
        # レスポンスを検証
        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert len(response_body['images']) == 1
        assert response_body['images'][0]['image_id'] == 'img-001'
        assert response_body['images'][0]['title'] == 'Test Image 1'
        assert response_body['total'] == 1
        assert not response_body['has_more']
    
    @mock_s3
    @mock_dynamodb
    def test_image_detail_success(self, cognito_event_base, mock_environment):
        """画像詳細取得成功テスト"""
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
        table.put_item(Item={
            'user_id': 'test-user-123',
            'image_id': 'img-001',
            'title': 'Test Image',
            'filename': 'test.jpg',
            'created_at': '2024-01-01T00:00:00Z',
            'size_mb': 1.5,
            'ocr_result': {
                'text': 'Sample OCR text',
                'confidence': 0.95
            },
            'vision_result': {
                'description': 'A test image',
                'confidence': 0.90
            }
        })
        
        # S3バケットとオブジェクトを作成
        s3_client = boto3.client('s3', region_name='us-east-1')
        s3_client.create_bucket(Bucket='test-image-bucket')
        
        # イベントを構築
        event = {
            **cognito_event_base,
            "pathParameters": {
                "image_id": "img-001"
            }
        }
        
        # ハンドラーを実行
        response = image_detail_handler(event, None)
        
        # レスポンスを検証
        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['image_id'] == 'img-001'
        assert response_body['title'] == 'Test Image'
        assert response_body['ocr_result']['text'] == 'Sample OCR text'
        assert response_body['vision_result']['description'] == 'A test image'
        assert 'image_url' in response_body
    
    @mock_s3
    @mock_dynamodb
    def test_image_delete_success(self, cognito_event_base, mock_environment):
        """画像削除成功テスト"""
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
        
        # 使用量テーブルを作成
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
        
        # テストデータを挿入
        table.put_item(Item={
            'user_id': 'test-user-123',
            'image_id': 'img-001',
            'title': 'Test Image',
            'filename': 'test.jpg',
            'size_mb': 1.5,
            'vector_count': 5
        })
        
        # S3バケットを作成
        s3_client = boto3.client('s3', region_name='us-east-1')
        s3_client.create_bucket(Bucket='test-image-bucket')
        
        # イベントを構築
        event = {
            **cognito_event_base,
            "pathParameters": {
                "image_id": "img-001"
            }
        }
        
        # ナレッジ管理をモック
        with patch('image_handlers.ImageKnowledgeManager') as mock_knowledge:
            mock_knowledge_instance = mock_knowledge.return_value
            mock_knowledge_instance.delete_knowledge_by_image.return_value = True
            
            # ハンドラーを実行
            response = image_delete_handler(event, None)
        
        # レスポンスを検証
        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['message'] == '画像が正常に削除されました'
        assert response_body['deleted_vectors'] == 5
        
        # DynamoDBから削除されたことを確認
        with pytest.raises(dynamodb.meta.client.exceptions.ResourceNotFoundException):
            table.get_item(Key={'user_id': 'test-user-123', 'image_id': 'img-001'})
    
    def test_image_query_success(self, cognito_event_base, mock_environment):
        """画像クエリ成功テスト"""
        # イベントを構築
        event = {
            **cognito_event_base,
            "body": json.dumps({
                "question": "テスト画像について教えて",
                "search_scope": "all",
                "max_results": 5
            })
        }
        
        # ナレッジ管理をモック
        with patch('image_handlers.ImageKnowledgeManager') as mock_knowledge:
            mock_knowledge_instance = mock_knowledge.return_value
            mock_knowledge_instance.query_image_knowledge.return_value = {
                "answer": "テスト画像に関する回答です",
                "image_sources": [
                    {
                        "id": "img-001",
                        "title": "テスト画像",
                        "relevance_score": 0.95,
                        "snippet": "サンプルテキスト"
                    }
                ],
                "confidence": 0.9
            }
            
            # ハンドラーを実行
            response = image_query_handler(event, None)
        
        # レスポンスを検証
        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['answer'] == 'テスト画像に関する回答です'
        assert len(response_body['image_sources']) == 1
        assert response_body['confidence'] == 0.9
    
    @mock_dynamodb
    def test_image_statistics_success(self, cognito_event_base, mock_environment):
        """画像統計取得成功テスト"""
        # DynamoDBテーブルを作成
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        image_table = dynamodb.create_table(
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
        
        # テストデータを挿入
        image_table.put_item(Item={
            'user_id': 'test-user-123',
            'image_id': 'img-001',
            'size_mb': 1.5,
            'created_at': '2024-01-01T00:00:00Z'
        })
        
        image_table.put_item(Item={
            'user_id': 'test-user-123',
            'image_id': 'img-002',
            'size_mb': 2.0,
            'created_at': '2024-01-02T00:00:00Z'
        })
        
        usage_table.put_item(Item={
            'user_id': 'test-user-123',
            'current_images': 2,
            'current_image_storage_mb': 3.5,
            'monthly_image_analyses': 10
        })
        
        # イベントを構築
        event = {
            **cognito_event_base,
            "queryStringParameters": {}
        }
        
        # ハンドラーを実行
        response = image_statistics_handler(event, None)
        
        # レスポンスを検証
        assert response['statusCode'] == 200
        response_body = json.loads(response['body'])
        assert response_body['total_images'] == 2
        assert response_body['total_storage_mb'] == 3.5
        assert response_body['monthly_analyses'] == 10
    
    def test_invalid_user_id(self, mock_environment):
        """無効なユーザーIDのテスト"""
        # Cognitoクレームが欠如したイベント
        event = {
            "requestContext": {},
            "body": json.dumps({"title": "Test"})
        }
        
        response = image_upload_handler(event, None)
        
        assert response['statusCode'] == 400
        response_body = json.loads(response['body'])
        assert 'error' in response_body
    
    def test_quota_exceeded(self, cognito_event_base, mock_environment):
        """クォータ超過テスト"""
        with patch('image_handlers.UserQuotaManager') as mock_quota:
            mock_quota_instance = mock_quota.return_value
            mock_quota_instance.check_image_quota_before_upload.return_value = (
                False, "画像数制限に達しています"
            )
            
            event = {
                **cognito_event_base,
                "body": "test-multipart-data"
            }
            
            response = image_upload_handler(event, None)
            
            assert response['statusCode'] == 429  # Too Many Requests
            response_body = json.loads(response['body'])
            assert 'quota limit exceeded' in response_body['error']
    
    def test_image_not_found(self, cognito_event_base, mock_environment):
        """画像が見つからない場合のテスト"""
        with mock_dynamodb():
            # 空のDynamoDBテーブルを作成
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
            
            event = {
                **cognito_event_base,
                "pathParameters": {
                    "image_id": "non-existent-image"
                }
            }
            
            response = image_detail_handler(event, None)
            
            assert response['statusCode'] == 404
            response_body = json.loads(response['body'])
            assert response_body['error'] == '画像が見つかりません'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])