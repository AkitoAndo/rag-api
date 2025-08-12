import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


@pytest.mark.unit
class TestUserSpecificQuery:
    """ユーザー固有クエリシステムのテスト"""

    @pytest.fixture
    def query_processor(self):
        """UserQueryProcessor（新しいクラス想定）のインスタンス"""
        with patch('src.user_query_processor.S3VectorsClient'), \
             patch('src.user_query_processor.ChatBedrockConverse'):
            from src.user_query_processor import UserQueryProcessor
            return UserQueryProcessor()

    @pytest.fixture
    def user_preferences(self):
        """ユーザー設定のサンプル"""
        return {
            "language": "ja",
            "max_results": 5,
            "temperature": 0.7,
            "chatbot_persona": "あなたは私の個人アシスタントです。親しみやすく、詳細な回答をしてください。",
            "include_sources": True,
            "response_format": "structured"
        }

    @pytest.fixture
    def mock_search_results(self):
        """モック検索結果"""
        return [
            {
                "distance": 0.15,
                "metadata": {
                    "user_id": "user123",
                    "document_id": "doc_1",
                    "title": "プロジェクト計画書",
                    "text": "プロジェクトの第一段階では、要件定義と基本設計を行います。",
                    "category": "business",
                    "created_at": "2025-01-10T09:00:00Z"
                }
            },
            {
                "distance": 0.22,
                "metadata": {
                    "user_id": "user123",
                    "document_id": "doc_2",
                    "title": "進捗レポート",
                    "text": "現在の進捗は予定通りで、来週には設計フェーズに入る予定です。",
                    "category": "status",
                    "created_at": "2025-01-12T14:30:00Z"
                }
            }
        ]

    def test_user_query_with_preferences_applied(
        self, query_processor, user_preferences, mock_search_results
    ):
        """ユーザー設定が適用されたクエリ処理テスト"""
        user_id = "user123"
        question = "プロジェクトの進捗はどうですか？"
        
        with patch.object(query_processor, '_search_user_documents') as mock_search, \
             patch.object(query_processor, '_generate_response') as mock_generate:
            
            mock_search.return_value = mock_search_results
            mock_generate.return_value = {
                "answer": "プロジェクトは順調に進んでいます。要件定義が完了し、来週から設計フェーズに入る予定です。",
                "sources": mock_search_results,
                "confidence": 0.92
            }
            
            result = query_processor.process_user_query(
                user_id=user_id,
                question=question,
                preferences=user_preferences
            )
            
            # ユーザー設定が検索に適用されることを確認
            search_call_args = mock_search.call_args
            assert search_call_args[1]['top_k'] == user_preferences['max_results']
            
            # LLM生成に設定が適用されることを確認
            generate_call_args = mock_generate.call_args
            assert generate_call_args[1]['temperature'] == user_preferences['temperature']
            assert user_preferences['chatbot_persona'] in generate_call_args[1]['system_prompt']
            
            # レスポンス形式が正しいことを確認
            assert 'answer' in result
            assert 'sources' in result
            assert result['confidence'] == 0.92

    def test_personalized_system_prompt_generation(self, query_processor, user_preferences):
        """個人化されたシステムプロンプト生成テスト"""
        user_context = {
            "user_id": "user456",
            "name": "田中太郎",
            "preferences": user_preferences,
            "document_categories": ["business", "personal", "learning"],
            "recent_topics": ["プロジェクト管理", "Python学習", "健康管理"]
        }
        
        with patch.object(query_processor, '_build_system_prompt') as mock_prompt:
            mock_prompt.return_value = (
                f"あなたは{user_context['name']}さんの個人アシスタントです。"
                f"田中さんの過去の文書（{', '.join(user_context['document_categories'])}）"
                f"に基づいて回答してください。"
            )
            
            prompt = query_processor._build_system_prompt(user_context)
            
            assert user_context['name'] in prompt
            assert user_preferences['chatbot_persona'] in prompt or "個人アシスタント" in prompt
            assert any(cat in prompt for cat in user_context['document_categories'])

    def test_query_result_ranking_with_user_context(
        self, query_processor, mock_search_results
    ):
        """ユーザーコンテキストを考慮した検索結果ランキングテスト"""
        user_id = "user789"
        question = "最近の作業について"
        
        # ユーザーの過去のクエリ履歴をシミュレート
        user_history = {
            "frequent_topics": ["プロジェクト", "作業", "進捗"],
            "preferred_categories": ["business", "status"],
            "recent_queries": [
                {"query": "作業進捗", "timestamp": "2025-01-14T10:00:00Z"},
                {"query": "プロジェクト状況", "timestamp": "2025-01-13T15:30:00Z"}
            ]
        }
        
        with patch.object(query_processor, '_rerank_with_user_context') as mock_rerank:
            # ユーザーコンテキストを考慮して結果を再ランク
            reranked_results = [
                mock_search_results[1],  # 進捗レポート（より関連性が高い）
                mock_search_results[0]   # プロジェクト計画書
            ]
            mock_rerank.return_value = reranked_results
            
            results = query_processor._rerank_with_user_context(
                results=mock_search_results,
                user_history=user_history,
                question=question
            )
            
            # より関連性の高い結果が上位に来ることを確認
            assert results[0]['metadata']['title'] == "進捗レポート"
            assert results[1]['metadata']['title'] == "プロジェクト計画書"

    def test_query_with_temporal_context(self, query_processor):
        """時間的コンテキストを考慮したクエリテスト"""
        user_id = "user_temporal"
        question = "今週の予定を教えて"
        
        # 時間に関連する検索結果
        temporal_results = [
            {
                "metadata": {
                    "title": "今週のスケジュール",
                    "text": "今週は月曜日に会議、水曜日にレビューがあります。",
                    "created_at": "2025-01-15T08:00:00Z",  # 最新
                    "category": "schedule"
                }
            },
            {
                "metadata": {
                    "title": "先週のスケジュール",
                    "text": "先週は火曜日に会議がありました。",
                    "created_at": "2025-01-08T08:00:00Z",  # 古い
                    "category": "schedule"
                }
            }
        ]
        
        with patch.object(query_processor, '_apply_temporal_boost') as mock_temporal:
            mock_temporal.return_value = [temporal_results[0]]  # 新しいものを優先
            
            results = query_processor._apply_temporal_boost(
                results=temporal_results,
                question=question,
                current_time="2025-01-15T10:00:00Z"
            )
            
            # 時間的に関連性の高い結果が選ばれることを確認
            assert len(results) == 1
            assert "今週" in results[0]['metadata']['title']

    def test_query_response_with_confidence_scoring(self, query_processor, mock_search_results):
        """信頼度スコア付きクエリレスポンステスト"""
        user_id = "user_confidence"
        question = "プロジェクトの状況は？"
        
        with patch.object(query_processor, '_calculate_confidence') as mock_confidence:
            mock_confidence.return_value = {
                "overall_confidence": 0.85,
                "source_quality": 0.90,
                "question_match": 0.80,
                "recency_factor": 0.85,
                "explanation": "複数の関連文書から一貫した情報が得られました。"
            }
            
            confidence_info = query_processor._calculate_confidence(
                question=question,
                search_results=mock_search_results,
                generated_answer="プロジェクトは順調に進んでいます。"
            )
            
            assert confidence_info["overall_confidence"] > 0.8
            assert "explanation" in confidence_info
            assert confidence_info["source_quality"] > confidence_info["question_match"]

    def test_query_with_follow_up_context(self, query_processor):
        """フォローアップクエリのコンテキスト管理テスト"""
        user_id = "user_followup"
        
        # 初回クエリ
        initial_query = {
            "question": "プロジェクトの進捗はどうですか？",
            "session_id": "session_123",
            "timestamp": "2025-01-15T10:00:00Z"
        }
        
        # フォローアップクエリ
        followup_query = {
            "question": "それはいつ完了予定ですか？",
            "session_id": "session_123",
            "timestamp": "2025-01-15T10:02:00Z"
        }
        
        with patch.object(query_processor, '_get_session_context') as mock_session:
            mock_session.return_value = {
                "previous_questions": [initial_query["question"]],
                "previous_answers": ["プロジェクトは順調に進んでいます。"],
                "context_topics": ["プロジェクト", "進捗"],
                "active_documents": ["doc_1", "doc_2"]
            }
            
            session_context = query_processor._get_session_context(
                user_id=user_id,
                session_id=followup_query["session_id"]
            )
            
            # セッションコンテキストが適切に取得されることを確認
            assert len(session_context["previous_questions"]) == 1
            assert "プロジェクト" in session_context["context_topics"]

    def test_query_error_handling_with_fallback(self, query_processor):
        """クエリエラーハンドリングとフォールバック処理テスト"""
        user_id = "user_error"
        question = "テスト質問"
        
        # S3 Vectorsエラーのシミュレート
        with patch.object(query_processor, '_search_user_documents') as mock_search:
            mock_search.side_effect = Exception("Vector search failed")
            
            # フォールバック処理のモック
            with patch.object(query_processor, '_fallback_response') as mock_fallback:
                mock_fallback.return_value = {
                    "answer": "申し訳ありませんが、現在検索機能に問題が発生しています。しばらく後に再度お試しください。",
                    "sources": [],
                    "confidence": 0.0,
                    "fallback_used": True,
                    "error_type": "search_unavailable"
                }
                
                result = query_processor.process_user_query_with_fallback(
                    user_id=user_id,
                    question=question
                )
                
                assert result["fallback_used"] is True
                assert result["confidence"] == 0.0
                assert "申し訳ありません" in result["answer"]

    def test_query_caching_for_performance(self, query_processor):
        """パフォーマンス向上のためのクエリキャッシュテスト"""
        user_id = "user_cache"
        question = "よく聞かれる質問"
        
        # キャッシュからの取得をシミュレート
        with patch.object(query_processor, '_get_cached_response') as mock_cache_get, \
             patch.object(query_processor, '_set_cached_response') as mock_cache_set:
            
            # 初回クエリ（キャッシュなし）
            mock_cache_get.return_value = None
            
            with patch.object(query_processor, '_search_user_documents') as mock_search:
                mock_search.return_value = []
                
                result1 = query_processor.process_user_query_cached(
                    user_id=user_id,
                    question=question,
                    cache_ttl=300  # 5分
                )
                
                # キャッシュに保存されることを確認
                mock_cache_set.assert_called_once()
            
            # 2回目のクエリ（キャッシュあり）
            cached_response = {
                "answer": "キャッシュされた回答",
                "sources": [],
                "confidence": 0.95,
                "cached": True
            }
            mock_cache_get.return_value = cached_response
            
            result2 = query_processor.process_user_query_cached(
                user_id=user_id,
                question=question
            )
            
            assert result2["cached"] is True
            assert result2["answer"] == "キャッシュされた回答"


@pytest.mark.integration_mock
class TestUserSpecificQueryIntegration:
    """ユーザー固有クエリ統合テスト"""

    def test_end_to_end_personalized_query_flow(self):
        """エンドツーエンドの個人化クエリフロー統合テスト"""
        user_id = "user_e2e"
        
        with patch('src.user_query_processor.S3VectorsClient') as mock_s3, \
             patch('src.user_query_processor.ChatBedrockConverse') as mock_chat:
            
            from src.user_query_processor import UserQueryProcessor
            processor = UserQueryProcessor()
            
            # モックの設定
            mock_s3_instance = Mock()
            mock_s3.return_value = mock_s3_instance
            
            mock_chat_instance = Mock()
            mock_chat.return_value = mock_chat_instance
            
            mock_response = Mock()
            mock_response.content = "総合的な回答: ユーザーの文書に基づく詳細な回答です。"
            mock_chat_instance.invoke.return_value = mock_response
            
            # 検索結果の設定
            mock_s3_instance.query_user_documents.return_value = [
                {
                    "distance": 0.1,
                    "metadata": {
                        "user_id": user_id,
                        "title": "個人メモ",
                        "text": "重要な情報がここに記録されています。"
                    }
                }
            ]
            
            # フローの実行
            result = processor.process_user_query(
                user_id=user_id,
                question="私の記録について教えて",
                preferences={
                    "language": "ja",
                    "max_results": 3,
                    "include_sources": True
                }
            )
            
            # 各ステップが実行されることを確認
            mock_s3_instance.query_user_documents.assert_called_once()
            mock_chat_instance.invoke.assert_called_once()
            
            # 結果の構造を確認
            assert 'answer' in result
            assert 'sources' in result
            assert len(result['sources']) > 0