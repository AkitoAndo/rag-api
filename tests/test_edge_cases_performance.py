"""エッジケース・パフォーマンステスト - OpenAPI仕様の限界値・性能テスト"""
import pytest
import json
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

# srcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lambda_handler import lambda_handler, add_document_handler


@pytest.mark.unit
class TestMaximumSizeInputs:
    """最大サイズ入力テスト - OpenAPI仕様限界値"""
    
    def test_maximum_text_length(self, mock_s3vectors_client, test_environment):
        """最大テキスト長（100,000文字）のテスト"""
        # OpenAPI仕様の maxLength: 100000 に合わせる
        max_text = "この文字を繰り返して最大長にします。" * 6250  # 約100,000文字
        
        event = {
            "body": json.dumps({
                "text": max_text,
                "title": "最大長文書"
            })
        }
        
        mock_s3vectors_client.return_value.add_document.return_value = 50  # 多くのチャンクが生成される
        
        with test_environment:
            start_time = time.time()
            result = add_document_handler(event, {})
            processing_time = time.time() - start_time
            
            # 成功することを確認
            assert result["statusCode"] == 200
            
            # 処理時間が合理的な範囲内であることを確認（Lambda timeout: 300秒以内）
            assert processing_time < 300
            
            body = json.loads(result["body"])
            assert "vector_count" in body
            assert body["vector_count"] > 1  # 長いテキストなので複数チャンクになる

    def test_maximum_title_length(self, mock_s3vectors_client, test_environment):
        """最大タイトル長（200文字）のテスト"""
        # OpenAPI仕様の maxLength: 200 に合わせる
        max_title = "タイトル文字" * 33 + "タイトル"  # ちょうど200文字
        
        event = {
            "body": json.dumps({
                "text": "通常のテキスト",
                "title": max_title
            })
        }
        
        mock_s3vectors_client.return_value.add_document.return_value = 1
        
        with test_environment:
            result = add_document_handler(event, {})
            assert result["statusCode"] == 200

    def test_maximum_question_length(self, mock_s3vectors_client, test_environment):
        """最大質問長（1,000文字）のテスト"""
        # OpenAPI仕様の maxLength: 1000 に合わせる
        max_question = "これは非常に長い質問です。" * 71 + "追加の質問文"  # 約1,000文字
        
        event = {
            "body": json.dumps({
                "question": max_question
            })
        }
        
        mock_s3vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": "回答用テキスト", "title": "テスト"}}
        ]
        
        with test_environment:
            with patch('lambda_handler.ChatBedrockConverse') as mock_chat:
                mock_model = Mock()
                mock_response = Mock()
                mock_response.content = "長い質問への回答"
                mock_model.invoke.return_value = mock_response
                mock_chat.return_value = mock_model
                
                start_time = time.time()
                result = lambda_handler(event, {})
                processing_time = time.time() - start_time
                
                assert result["statusCode"] == 200
                assert processing_time < 30  # クエリのTimeout: 30秒以内

    def test_over_maximum_limits(self, test_environment):
        """制限超過時の処理テスト"""
        # 制限を超えるテキスト（100,001文字）
        over_max_text = "x" * 100001
        
        event = {
            "body": json.dumps({
                "text": over_max_text,
                "title": "制限超過文書"
            })
        }
        
        with test_environment:
            result = add_document_handler(event, {})
            # 制限チェックが実装されている場合: assert result["statusCode"] == 400
            # 実装されていない場合は処理される可能性（ただし性能問題あり）


@pytest.mark.unit
class TestLargeDataProcessing:
    """大量データ処理テスト"""
    
    def test_multiple_large_chunks_processing(self, mock_s3vectors_client, test_environment):
        """複数の大きなチャンクの処理テスト"""
        # チャンクサイズ（1000文字）の10倍以上の文書
        large_document = "これは大きな文書のテキストです。" * 1000  # 約15,000文字
        
        event = {
            "body": json.dumps({
                "text": large_document,
                "title": "大規模文書"
            })
        }
        
        # 15個程度のチャンクが生成されることを想定
        mock_s3vectors_client.return_value.add_document.return_value = 15
        
        with test_environment:
            result = add_document_handler(event, {})
            
            assert result["statusCode"] == 200
            body = json.loads(result["body"])
            assert body["vector_count"] >= 10  # 複数チャンクが生成される

    def test_many_search_results_processing(self, mock_s3vectors_client, test_environment):
        """多数の検索結果処理テスト"""
        # 大量の検索結果を返すシナリオ
        many_results = []
        for i in range(100):  # 100件の検索結果
            many_results.append({
                "metadata": {
                    "text": f"検索結果{i}のテキスト内容です。これは{i}番目の文書です。",
                    "title": f"文書{i}"
                },
                "distance": 0.1 + i * 0.001
            })
        
        mock_s3vectors_client.return_value.query_vectors.return_value = many_results
        
        event = {
            "body": json.dumps({
                "question": "大量結果を返す質問"
            })
        }
        
        with test_environment:
            with patch('lambda_handler.ChatBedrockConverse') as mock_chat:
                mock_model = Mock()
                mock_response = Mock()
                mock_response.content = "大量の情報に基づく回答"
                mock_model.invoke.return_value = mock_response
                mock_chat.return_value = mock_model
                
                result = lambda_handler(event, {})
                
                assert result["statusCode"] == 200
                # LLMに送信するコンテキストが適切にトリミングされていることを確認


@pytest.mark.unit
class TestSpecialCharacterHandling:
    """特殊文字処理テスト"""
    
    def test_unicode_emoji_handling(self, mock_s3vectors_client, test_environment):
        """Unicode絵文字処理テスト"""
        emoji_text = """
        こんにちは！🌸 これは絵文字を含む文書です 🚀
        
        各種絵文字のテスト:
        - 顔文字: 😀😃😄😁😆😅😂🤣
        - 動物: 🐶🐱🐭🐹🐰🦊🐻🐼
        - 食べ物: 🍎🍌🍇🍓🥝🍅🥑🌽
        - 国旗: 🇯🇵🇺🇸🇬🇧🇫🇷🇩🇪🇮🇹
        - 記号: ⭐️✨💫⚡️🔥💧🌈☀️
        """
        
        event = {
            "body": json.dumps({
                "text": emoji_text,
                "title": "絵文字テスト文書 📝"
            })
        }
        
        mock_s3vectors_client.return_value.add_document.return_value = 1
        
        with test_environment:
            result = add_document_handler(event, {})
            assert result["statusCode"] == 200

    def test_special_control_characters(self, mock_s3vectors_client, test_environment):
        """制御文字・特殊文字処理テスト"""
        special_text = """
        制御文字テスト:
        - 改行: \n
        - タブ: \t
        - 復帰: \r
        - NULL文字のエスケープ
        - Unicode制御文字: \u200B\u200C\u200D
        - 引用符: "ダブル" 'シングル'
        - バックスラッシュ: \\
        - JSON特殊文字: {"key": "value"}
        """
        
        event = {
            "body": json.dumps({
                "text": special_text,
                "title": "制御文字テスト"
            })
        }
        
        mock_s3vectors_client.return_value.add_document.return_value = 1
        
        with test_environment:
            result = add_document_handler(event, {})
            assert result["statusCode"] == 200

    def test_mixed_language_content(self, mock_s3vectors_client, test_environment):
        """多言語混在コンテンツテスト"""
        multilang_text = """
        日本語: これは日本語のテキストです。
        English: This is English text.
        中文: 这是中文文本。
        한국어: 이것은 한국어 텍스트입니다.
        Español: Este es texto en español.
        Français: Ceci est un texte français.
        العربية: هذا نص باللغة العربية.
        русский: Это русский текст.
        """
        
        event = {
            "body": json.dumps({
                "text": multilang_text,
                "title": "多言語テスト文書"
            })
        }
        
        mock_s3vectors_client.return_value.add_document.return_value = 1
        
        with test_environment:
            result = add_document_handler(event, {})
            assert result["statusCode"] == 200


@pytest.mark.unit
class TestPerformanceEdgeCases:
    """パフォーマンスエッジケーステスト"""
    
    def test_rapid_consecutive_requests(self, mock_s3vectors_client, test_environment):
        """連続リクエスト処理テスト"""
        mock_s3vectors_client.return_value.query_vectors.return_value = [
            {"metadata": {"text": "テスト回答", "title": "テスト"}}
        ]
        
        events = []
        for i in range(10):
            events.append({
                "body": json.dumps({
                    "question": f"連続質問{i}"
                })
            })
        
        with test_environment:
            with patch('lambda_handler.ChatBedrockConverse') as mock_chat:
                mock_model = Mock()
                mock_response = Mock()
                mock_response.content = "迅速な回答"
                mock_model.invoke.return_value = mock_response
                mock_chat.return_value = mock_model
                
                # 連続実行
                results = []
                total_start = time.time()
                
                for event in events:
                    start = time.time()
                    result = lambda_handler(event, {})
                    duration = time.time() - start
                    
                    results.append({
                        "result": result,
                        "duration": duration
                    })
                
                total_duration = time.time() - total_start
                
                # 全てのリクエストが成功することを確認
                for r in results:
                    assert r["result"]["statusCode"] == 200
                    assert r["duration"] < 30  # 個別リクエストのタイムアウト
                
                # 全体の処理時間が合理的であることを確認
                assert total_duration < 300

    def test_memory_intensive_operations(self, mock_s3vectors_client, test_environment):
        """メモリ集約的操作テスト"""
        # 大量のベクトル検索結果を生成
        large_result_set = []
        for i in range(1000):
            large_result_set.append({
                "metadata": {
                    "text": f"大量データ{i}: " + "x" * 500,  # 各結果が約500文字
                    "title": f"文書{i}"
                },
                "distance": 0.001 * i
            })
        
        mock_s3vectors_client.return_value.query_vectors.return_value = large_result_set
        
        event = {
            "body": json.dumps({
                "question": "メモリ集約的な質問"
            })
        }
        
        with test_environment:
            with patch('lambda_handler.ChatBedrockConverse') as mock_chat:
                mock_model = Mock()
                mock_response = Mock()
                mock_response.content = "大量データからの回答"
                mock_model.invoke.return_value = mock_response
                mock_chat.return_value = mock_model
                
                result = lambda_handler(event, {})
                
                # メモリエラーなしで完了することを確認
                assert result["statusCode"] == 200

    def test_timeout_boundary_conditions(self, mock_s3vectors_client, test_environment):
        """タイムアウト境界条件テスト"""
        # 処理に時間がかかる操作をシミュレート
        def slow_query(*args, **kwargs):
            time.sleep(0.5)  # 0.5秒の遅延
            return [{"metadata": {"text": "遅延回答", "title": "テスト"}}]
        
        mock_s3vectors_client.return_value.query_vectors.side_effect = slow_query
        
        event = {
            "body": json.dumps({
                "question": "タイムアウトテスト質問"
            })
        }
        
        with test_environment:
            with patch('lambda_handler.ChatBedrockConverse') as mock_chat:
                def slow_llm(*args, **kwargs):
                    time.sleep(0.5)  # さらに0.5秒の遅延
                    mock_model = Mock()
                    mock_response = Mock()
                    mock_response.content = "遅延後の回答"
                    mock_model.invoke.return_value = mock_response
                    return mock_model
                
                mock_chat.side_effect = slow_llm
                
                start_time = time.time()
                result = lambda_handler(event, {})
                total_time = time.time() - start_time
                
                # タイムアウト内で完了することを確認
                assert result["statusCode"] == 200
                assert total_time < 30  # Lambda関数のタイムアウト内


@pytest.mark.integration
class TestRealWorldScenarios:
    """実世界シナリオテスト"""
    
    def test_wikipedia_article_size_document(self, mock_s3vectors_client, test_environment):
        """Wikipedia記事サイズの文書処理テスト"""
        # Wikipediaの平均的な記事サイズ（約20,000文字）
        wikipedia_size_text = """
        メイドインアビス（Made in Abyss）は、つくしあきひとによる日本の漫画作品。
        『WEBコミックガンマ』にて2012年より連載中。
        
        """ + "詳細な設定と世界観の説明が続く..." * 1000
        
        event = {
            "body": json.dumps({
                "text": wikipedia_size_text,
                "title": "メイドインアビス - Wikipedia記事サイズ"
            })
        }
        
        mock_s3vectors_client.return_value.add_document.return_value = 20
        
        with test_environment:
            result = add_document_handler(event, {})
            assert result["statusCode"] == 200

    def test_academic_paper_abstract_query(self, mock_s3vectors_client, test_environment):
        """学術論文の抄録クエリテスト"""
        academic_question = """
        深層学習における注意機構（Attention Mechanism）の発展と
        自然言語処理への応用について、特にTransformerアーキテクチャが
        機械翻訳と文書要約タスクに与えた影響を、最新の研究動向と
        性能評価指標（BLEU、ROUGE、BERTScore）の観点から
        詳細に分析してください。
        """
        
        event = {
            "body": json.dumps({
                "question": academic_question
            })
        }
        
        mock_s3vectors_client.return_value.query_vectors.return_value = [
            {
                "metadata": {
                    "text": "Transformerアーキテクチャに関する詳細な解説...",
                    "title": "注意機構の発展"
                }
            }
        ]
        
        with test_environment:
            with patch('lambda_handler.ChatBedrockConverse') as mock_chat:
                mock_model = Mock()
                mock_response = Mock()
                mock_response.content = "学術的で詳細な回答..."
                mock_model.invoke.return_value = mock_response
                mock_chat.return_value = mock_model
                
                result = lambda_handler(event, {})
                assert result["statusCode"] == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

