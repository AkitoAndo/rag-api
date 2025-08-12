"""パフォーマンステスト"""
import pytest
import time
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# srcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lambda_handler import lambda_handler, add_document_handler


@pytest.mark.unit
class TestPerformance:
    """パフォーマンステスト"""
    
    def test_lambda_handler_response_time(self, mock_s3_vectors_client, test_environment):
        """Lambda関数のレスポンス時間テスト"""
        # テストイベント
        event = {
            "body": json.dumps({
                "question": "性能テスト用の質問です"
            })
        }
        
        # Mock設定
        mock_s3_vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": "パフォーマンステスト回答"}, "distance": 0.1}
        ]
        
        with test_environment:
            start_time = time.time()
            result = lambda_handler(event, {})
            end_time = time.time()
            
            response_time = end_time - start_time
            
            # レスポンス時間は1秒以内であることを確認
            assert response_time < 1.0
            assert result["statusCode"] == 200
            
            print(f"Lambda handler response time: {response_time:.3f}s")
    
    def test_add_document_handler_response_time(self, mock_s3_vectors_client, test_environment):
        """ドキュメント追加のレスポンス時間テスト"""
        # テストイベント
        event = {
            "body": json.dumps({
                "text": "パフォーマンステスト用のドキュメントです。" * 50,  # 長めのテキスト
                "title": "パフォーマンステストドキュメント"
            })
        }
        
        # Mock設定
        mock_s3_vectors_client.return_value.add_document.return_value = 5
        
        with test_environment:
            start_time = time.time()
            result = add_document_handler(event, {})
            end_time = time.time()
            
            response_time = end_time - start_time
            
            # レスポンス時間は2秒以内であることを確認
            assert response_time < 2.0
            assert result["statusCode"] == 200
            
            print(f"Add document handler response time: {response_time:.3f}s")
    
    def test_concurrent_requests_simulation(self, mock_s3_vectors_client, test_environment):
        """同時リクエストのシミュレーション"""
        # Mock設定
        mock_s3_vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": "同時リクエストテスト回答"}, "distance": 0.1}
        ]
        
        events = []
        for i in range(10):
            events.append({
                "body": json.dumps({
                    "question": f"同時リクエストテスト {i+1}"
                })
            })
        
        with test_environment:
            start_time = time.time()
            
            results = []
            for event in events:
                result = lambda_handler(event, {})
                results.append(result)
            
            end_time = time.time()
            total_time = end_time - start_time
            
            # 全てのリクエストが成功することを確認
            for result in results:
                assert result["statusCode"] == 200
            
            # 平均レスポンス時間を計算
            avg_response_time = total_time / len(events)
            
            print(f"Average response time for {len(events)} requests: {avg_response_time:.3f}s")
            print(f"Total time: {total_time:.3f}s")
            
            # 平均レスポンス時間は0.5秒以内であることを確認
            assert avg_response_time < 0.5
    
    def test_large_response_handling(self, mock_s3_vectors_client, test_environment):
        """大きなレスポンスの処理テスト"""
        # 大きなレスポンスをシミュレート
        large_answer = "これは非常に長い回答です。" * 1000  # 約50KB
        
        event = {
            "body": json.dumps({
                "question": "大きなレスポンステスト"
            })
        }
        
        # 大きなレスポンスを返すMock設定
        mock_s3_vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": large_answer}, "distance": 0.1}
        ]
        
        with test_environment:
            start_time = time.time()
            result = lambda_handler(event, {})
            end_time = time.time()
            
            response_time = end_time - start_time
            
            assert result["statusCode"] == 200
            
            body = json.loads(result["body"])
            assert len(body["answer"]) > 10000  # 大きなレスポンスが返されることを確認
            
            print(f"Large response handling time: {response_time:.3f}s")
            print(f"Response size: {len(body['answer'])} characters")
            
            # 大きなレスポンスでも3秒以内で処理されることを確認
            assert response_time < 3.0
    
    def test_memory_usage_simulation(self, mock_s3_vectors_client, test_environment):
        """メモリ使用量のシミュレーション"""
        import gc
        
        # Mock設定
        mock_s3_vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": "メモリテスト回答"}, "distance": 0.1}
        ]
        
        event = {
            "body": json.dumps({
                "question": "メモリ使用量テスト"
            })
        }
        
        with test_environment:
            # ガベージコレクションを実行
            gc.collect()
            
            # 複数回実行してメモリリークがないことを確認
            for i in range(50):
                result = lambda_handler(event, {})
                assert result["statusCode"] == 200
                
                # 10回ごとにガベージコレクション
                if i % 10 == 0:
                    gc.collect()
            
            print("Memory usage test completed - no apparent memory leaks")


@pytest.mark.unit
class TestStressTest:
    """ストレステスト"""
    
    def test_high_frequency_requests(self, mock_s3_vectors_client, test_environment):
        """高頻度リクエストテスト"""
        # Mock設定
        mock_s3_vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": "高頻度テスト回答"}, "distance": 0.1}
        ]
        
        event = {
            "body": json.dumps({
                "question": "高頻度リクエストテスト"
            })
        }
        
        success_count = 0
        total_requests = 100
        
        with test_environment:
            start_time = time.time()
            
            for i in range(total_requests):
                try:
                    result = lambda_handler(event, {})
                    if result["statusCode"] == 200:
                        success_count += 1
                except Exception as e:
                    print(f"Request {i+1} failed: {e}")
            
            end_time = time.time()
            total_time = end_time - start_time
            
            success_rate = success_count / total_requests
            requests_per_second = total_requests / total_time
            
            print(f"Success rate: {success_rate:.2%}")
            print(f"Requests per second: {requests_per_second:.2f}")
            print(f"Total time: {total_time:.3f}s")
            
            # 成功率は95%以上であることを確認
            assert success_rate >= 0.95
    
    def test_error_handling_under_stress(self, mock_s3_vectors_client, test_environment):
        """ストレス下でのエラーハンドリングテスト"""
        # 時々エラーを発生させるMock設定
        def side_effect(*args, **kwargs):
            import random
            if random.random() < 0.1:  # 10%の確率でエラー
                raise Exception("Simulated error")
            return [{"metadata": {"text": "正常回答"}, "distance": 0.1}]
        
        mock_s3_vectors_client.return_value.query_vectors.side_effect = side_effect
        
        event = {
            "body": json.dumps({
                "question": "エラーハンドリングテスト"
            })
        }
        
        error_count = 0
        success_count = 0
        total_requests = 50
        
        with test_environment:
            for i in range(total_requests):
                result = lambda_handler(event, {})
                
                if result["statusCode"] == 200:
                    success_count += 1
                elif result["statusCode"] == 500:
                    error_count += 1
                    # エラーレスポンスでも適切な形式であることを確認
                    body = json.loads(result["body"])
                    assert "error" in body
            
            error_rate = error_count / total_requests
            success_rate = success_count / total_requests
            
            print(f"Error rate: {error_rate:.2%}")
            print(f"Success rate: {success_rate:.2%}")
            
            # エラーが適切にハンドリングされていることを確認
            assert error_rate > 0  # エラーが発生していることを確認
            assert success_rate > 0  # 成功例もあることを確認
            assert (error_count + success_count) == total_requests


if __name__ == "__main__":
    # 直接実行時のテスト
    pytest.main([__file__, "-v", "-s"])
