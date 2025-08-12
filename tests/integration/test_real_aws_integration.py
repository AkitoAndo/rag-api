"""実際のAWSサービスとの統合テスト（手動実行用）"""
import pytest
import os
import boto3
from src.s3_vectors_client import S3VectorsClient
from src.lambda_handler import lambda_handler, add_document_handler
import json


@pytest.mark.integration_real
@pytest.mark.skipif(
    not all([
        os.getenv("VECTOR_BUCKET_NAME"),
        os.getenv("VECTOR_INDEX_NAME"), 
        os.getenv("AWS_ACCESS_KEY_ID")
    ]),
    reason="実際のAWS統合テストには環境変数が必要"
)
class TestRealAWSIntegration:
    """実際のAWSサービスとの統合テスト
    
    注意: このテストは実際のAWSリソースを使用し、料金が発生します。
    実行前に以下の環境変数を設定してください:
    - VECTOR_BUCKET_NAME
    - VECTOR_INDEX_NAME  
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - AWS_REGION
    """
    
    @pytest.fixture(autouse=True)
    def check_aws_connectivity(self):
        """AWS接続確認"""
        try:
            # S3 Vectorsクライアント接続テスト
            s3vectors = boto3.client('s3vectors', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            
            # Bedrockクライアント接続テスト
            bedrock = boto3.client('bedrock-runtime', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            
            yield
            
        except Exception as e:
            pytest.skip(f"AWS接続に失敗: {str(e)}")
    
    def test_real_s3_vectors_document_workflow(self):
        """実際のS3 Vectorsを使用したドキュメント追加テスト"""
        client = S3VectorsClient()
        
        test_text = """
        これは統合テスト用のドキュメントです。
        実際のAmazon S3 Vectorsサービスに保存され、検索されます。
        テスト完了後は適切にクリーンアップしてください。
        """
        
        try:
            # ドキュメント追加
            vector_count = client.add_document(
                vector_bucket_name=os.getenv("VECTOR_BUCKET_NAME"),
                index_name=os.getenv("VECTOR_INDEX_NAME"),
                text=test_text,
                title="統合テストドキュメント"
            )
            
            assert vector_count > 0
            print(f"Document addition completed: {vector_count} vectors created")
            
            # 検索テスト
            results = client.query_vectors(
                vector_bucket_name=os.getenv("VECTOR_BUCKET_NAME"),
                index_name=os.getenv("VECTOR_INDEX_NAME"), 
                question="統合テストについて教えて",
                top_k=3
            )
            
            assert len(results) > 0
            assert any("統合テスト" in result.get("metadata", {}).get("text", "") for result in results)
            print(f"Search completed: {len(results)} results retrieved")
            
        except Exception as e:
            pytest.fail(f"実際のS3 Vectors統合テストに失敗: {str(e)}")
    
    def test_real_bedrock_embedding_integration(self):
        """実際のBedrock埋め込みモデルとの統合テスト"""
        client = S3VectorsClient()
        
        try:
            # 埋め込み生成テスト
            test_texts = [
                "機械学習とは何ですか？",
                "人工知能の応用例を教えてください",
                "データサイエンスの基礎知識"
            ]
            
            embeddings = []
            for text in test_texts:
                embedding = client.embedding_model.embed_query(text)
                embeddings.append(embedding)
                
                # 埋め込みベクトルの妥当性チェック
                assert isinstance(embedding, list)
                assert len(embedding) > 1000  # Titan Embed v2は通常1536次元
                assert all(isinstance(x, float) for x in embedding)
            
            # 異なるテキストで異なる埋め込みが生成されることを確認
            assert not all(emb == embeddings[0] for emb in embeddings[1:])
            print("Bedrock embedding integration test completed successfully")
            
        except Exception as e:
            pytest.fail(f"Bedrock埋め込み統合テストに失敗: {str(e)}")
    
    def test_real_end_to_end_lambda_workflow(self):
        """実際のサービスを使用したLambda関数のE2Eテスト"""
        
        # 1. ドキュメント追加のテスト
        add_event = {
            "body": json.dumps({
                "text": "Amazon S3 Vectorsは、機械学習とAI分野での検索機能を強化する新しいサービスです。",
                "title": "S3 Vectors紹介"
            })
        }
        
        try:
            # ドキュメント追加
            add_result = add_document_handler(add_event, {})
            assert add_result["statusCode"] == 200
            
            add_body = json.loads(add_result["body"])
            assert "vector_count" in add_body
            assert add_body["vector_count"] > 0
            print(f"Lambda document addition completed: {add_body['vector_count']} vectors")
            
            # 2. 質問応答のテスト  
            query_event = {
                "body": json.dumps({
                    "question": "S3 Vectorsとは何ですか？"
                })
            }
            
            query_result = lambda_handler(query_event, {})
            assert query_result["statusCode"] == 200
            
            query_body = json.loads(query_result["body"])
            assert "answer" in query_body
            assert len(query_body["answer"]) > 0
            print(f"Lambda Q&A completed: Answer generated")
            
        except Exception as e:
            pytest.fail(f"Lambda E2E統合テストに失敗: {str(e)}")
    
    def test_real_error_scenarios(self):
        """実際のサービスでのエラーシナリオテスト"""
        
        # 存在しないバケットでのテスト
        client = S3VectorsClient()
        
        with pytest.raises(Exception):
            client.query_vectors(
                vector_bucket_name="non-existent-bucket-12345",
                index_name="non-existent-index",
                question="テスト質問"
            )
        print("Error handling verification completed")


# 実行方法を示すヘルパー関数
def run_real_integration_tests():
    """実際の統合テストの実行方法
    
    使用方法:
    ```bash
    # 環境変数を設定
    export VECTOR_BUCKET_NAME="your-vector-bucket"
    export VECTOR_INDEX_NAME="your-index"
    export AWS_ACCESS_KEY_ID="your-access-key"
    export AWS_SECRET_ACCESS_KEY="your-secret-key"
    export AWS_REGION="us-east-1"
    
    # 実際の統合テストを実行
    pytest -m integration_real tests/integration/test_real_aws_integration.py -v -s
    ```
    
    注意: このテストは実際のAWSリソースを使用し、料金が発生します。
    """
    pass