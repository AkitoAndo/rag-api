"""統合テスト用の共通設定とフィクスチャ"""
import os
import pytest
import boto3
from moto import mock_aws
# 新しいmotoバージョンではmock_awsを使用
from unittest.mock import Mock, patch


@pytest.fixture(scope="session")
def aws_credentials():
    """AWS認証情報をモック"""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def mock_s3_client(aws_credentials):
    """モックS3クライアント"""
    with mock_aws():
        yield boto3.client("s3", region_name="us-east-1")


@pytest.fixture(scope="function")
def mock_bedrock_client(aws_credentials):
    """モックBedrockクライアント"""
    # Bedrock Runtimeは手動でモック
    mock_client = Mock()
    mock_client.invoke_model.return_value = {
        'body': Mock(),
        'contentType': 'application/json'
    }
    return mock_client


@pytest.fixture
def mock_s3vectors_client():
    """モックS3Vectorsクライアント（統一命名）"""
    mock_client = Mock()
    
    # put_vectorsのモック
    mock_client.put_vectors.return_value = None
    
    # query_vectorsのモック - 正しいレスポンス形式
    mock_client.query_vectors.return_value = {
        "vectors": [
            {
                "key": "test-vector-1",
                "metadata": {
                    "text": "これはテスト用のドキュメントです。",
                    "title": "テストドキュメント"
                },
                "distance": 0.1
            },
            {
                "key": "test-vector-2", 
                "metadata": {
                    "text": "統合テストのためのサンプルテキストです。",
                    "title": "サンプル"
                },
                "distance": 0.3
            }
        ]
    }
    
    # delete_vectorsのモック（マルチテナント用）
    mock_client.delete_vectors.return_value = None
    
    # list_documentsのモック（マルチテナント用）
    mock_client.list_documents.return_value = []
    
    return mock_client


# マルチテナント対応のためのエイリアス
@pytest.fixture
def mock_s3_vectors_client():
    """モックS3Vectorsクライアント（エイリアス）"""
    return mock_s3vectors_client()


@pytest.fixture
def mock_embedding_model():
    """モック埋め込みモデル"""
    mock_model = Mock()
    mock_model.embed_query.return_value = [0.1, 0.2, 0.3, 0.4, 0.5] * 256  # 1536次元のベクトル
    return mock_model


@pytest.fixture
def test_environment():
    """テスト用環境変数"""
    env_vars = {
        "VECTOR_BUCKET_NAME": "test-vector-bucket",
        "VECTOR_INDEX_NAME": "test-index",
        "AWS_REGION": "us-east-1",
        "EMBEDDING_MODEL_ID": "amazon.titan-embed-text-v2:0",
        "CHAT_MODEL_ID": "us.anthropic.claude-sonnet-4-20250514-v1:0"
    }
    
    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest.fixture
def sample_document():
    """テスト用ドキュメント"""
    return {
        "text": """
        メイドインアビスは、つくしあきひとによる日本の漫画作品です。
        
        ## あらすじ
        巨大な縦穴「アビス」が存在する島で、少女リコが母親を探す冒険の物語です。
        アビスは深層に行くほど危険な生物が住み、上昇負荷という謎の現象があります。
        
        ## 主要キャラクター
        - リコ: 主人公の少女探窟家
        - レグ: ロボットの少年
        - ナナチ: うさぎのような見た目の成れ果て
        
        ## 世界設定
        アビスには複数の層があり、それぞれ異なる環境と生物が存在します。
        深界一層から深界七層まで知られており、さらに深い層の存在も示唆されています。
        """,
        "title": "メイドインアビス概要"
    }


@pytest.fixture
def sample_lambda_event():
    """Lambda関数テスト用のイベント"""
    return {
        "body": '{"question": "リコとは誰ですか？"}',
        "headers": {
            "Content-Type": "application/json"
        },
        "httpMethod": "POST",
        "path": "/query"
    }


@pytest.fixture
def sample_add_document_event():
    """ドキュメント追加用のLambdaイベント"""
    return {
        "body": '{"text": "これはテスト用の新しいドキュメントです。", "title": "テスト追加ドキュメント"}',
        "headers": {
            "Content-Type": "application/json"
        },
        "httpMethod": "POST",
        "path": "/add-document"
    }


@pytest.fixture
def mock_chat_response():
    """チャット応答のモック"""
    mock_response = Mock()
    mock_response.content = "リコは『メイドインアビス』の主人公で、アビスの探窟を目指す少女探窟家です。母親のライザを探すためにアビスの深層を目指しています。"
    return mock_response


# マルチテナント対応の追加フィクスチャ
@pytest.fixture
def multi_tenant_environment():
    """マルチテナント用テスト環境"""
    env_vars = {
        "VECTOR_BUCKET_NAME": "multi-tenant-vector-bucket",
        "AWS_REGION": "us-east-1",
        "EMBEDDING_MODEL_ID": "amazon.titan-embed-text-v2:0",
        "CHAT_MODEL_ID": "us.anthropic.claude-sonnet-4-20250514-v1:0"
        # VECTOR_INDEX_NAMEは使用しない（ユーザー別のため）
    }
    
    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest.fixture
def sample_user_contexts():
    """複数ユーザーのサンプルコンテキスト"""
    return {
        "user_alice": {
            "user_id": "user_alice",
            "name": "Alice Johnson",
            "preferences": {
                "language": "ja",
                "max_results": 5,
                "temperature": 0.7,
                "chatbot_persona": "親しみやすいアシスタント"
            },
            "documents": [
                {
                    "title": "Aliceのプロジェクト計画",
                    "text": "プロジェクトAの詳細計画です。フェーズ1は要件定義、フェーズ2は設計です。",
                    "category": "business"
                }
            ]
        },
        "user_bob": {
            "user_id": "user_bob", 
            "name": "Bob Smith",
            "preferences": {
                "language": "en",
                "max_results": 3,
                "temperature": 0.5,
                "chatbot_persona": "Professional assistant"
            },
            "documents": [
                {
                    "title": "Bob's Meeting Notes",
                    "text": "Meeting with client on project requirements and timeline discussions.",
                    "category": "notes"
                }
            ]
        }
    }


@pytest.fixture
def sample_user_lambda_events():
    """ユーザー固有のLambdaイベントサンプル"""
    return {
        "user_query": {
            "pathParameters": {"user_id": "user123"},
            "body": '{"question": "私のプロジェクトについて教えて", "preferences": {"language": "ja", "max_results": 5}}',
            "headers": {"Content-Type": "application/json"}
        },
        "user_add_document": {
            "pathParameters": {"user_id": "user123"},
            "body": '{"text": "個人的なメモです。", "title": "個人メモ"}',
            "headers": {"Content-Type": "application/json"}
        },
        "user_document_list": {
            "pathParameters": {"user_id": "user123"},
            "queryStringParameters": {"limit": "10", "offset": "0"},
            "headers": {"Content-Type": "application/json"}
        },
        "user_document_delete": {
            "pathParameters": {"user_id": "user123", "document_id": "doc_456"},
            "headers": {"Content-Type": "application/json"}
        }
    }


@pytest.fixture 
def mock_user_document_manager():
    """ユーザードキュメントマネージャーのモック"""
    mock_manager = Mock()
    
    # create_documentのモック
    mock_manager.create_document.return_value = {
        "document_id": "doc_test_123",
        "user_id": "user123",
        "title": "テスト文書",
        "vector_count": 3,
        "created_at": "2025-01-15T10:30:00Z"
    }
    
    # search_user_documentsのモック
    mock_manager.search_user_documents.return_value = [
        {
            "document_id": "doc_1",
            "title": "検索結果1",
            "relevance_score": 0.95,
            "snippet": "関連するテキストの抜粋..."
        }
    ]
    
    # list_user_documentsのモック
    mock_manager.list_user_documents.return_value = [
        {
            "document_id": "doc_1",
            "title": "ドキュメント1",
            "created_at": "2025-01-15T10:30:00Z",
            "vector_count": 3
        }
    ]
    
    # delete_documentのモック
    mock_manager.delete_document.return_value = {"success": True}
    
    return mock_manager


@pytest.fixture
def mock_user_query_processor():
    """ユーザークエリプロセッサーのモック"""
    mock_processor = Mock()
    
    # process_user_queryのモック
    mock_processor.process_user_query.return_value = {
        "answer": "ユーザーの文書に基づく個人化された回答です。",
        "sources": [
            {
                "document_id": "doc_1",
                "title": "関連文書",
                "relevance_score": 0.92,
                "snippet": "関連する内容..."
            }
        ],
        "confidence": 0.88,
        "user_context": {
            "user_id": "user123",
            "preferences_applied": True
        }
    }
    
    return mock_processor