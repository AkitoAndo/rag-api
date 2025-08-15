"""
画像ナレッジマネージャーのテストケース
"""
import pytest
from unittest.mock import patch, MagicMock, Mock
import uuid
import json
from datetime import datetime

# テスト対象のモジュールをインポート
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from image_knowledge_manager import ImageKnowledgeManager


class TestImageKnowledgeManager:
    """画像ナレッジマネージャーのテストクラス"""
    
    @pytest.fixture
    def manager(self):
        """マネージャーインスタンス"""
        with patch.dict(os.environ, {
            'AWS_REGION': 'us-east-1',
            'VECTOR_BUCKET_NAME': 'test-vector-bucket',
            'EMBEDDING_MODEL_ID': 'amazon.titan-embed-text-v2:0',
            'CHAT_MODEL_ID': 'us.anthropic.claude-sonnet-4-20250514-v1:0'
        }):
            return ImageKnowledgeManager()
    
    @pytest.fixture
    def sample_image_data(self):
        """サンプル画像データ"""
        return {
            'user_id': 'test-user-123',
            'image_id': 'img-001',
            'image_title': 'テスト用文書画像',
            'ocr_text': 'これは重要な文書です。\n会議の議事録として保管します。',
            'vision_description': 'ビジネス文書が写っている画像。テキストとグラフが含まれている。',
            'additional_context': 'プロジェクトX関連資料'
        }
    
    def test_create_integrated_content(self, manager, sample_image_data):
        """統合コンテンツ作成テスト"""
        integrated_content = manager._create_integrated_content(
            image_title=sample_image_data['image_title'],
            ocr_text=sample_image_data['ocr_text'],
            vision_description=sample_image_data['vision_description'],
            additional_context=sample_image_data['additional_context']
        )
        
        # 各要素が含まれていることを確認
        assert sample_image_data['image_title'] in integrated_content
        assert sample_image_data['ocr_text'] in integrated_content
        assert sample_image_data['vision_description'] in integrated_content
        assert sample_image_data['additional_context'] in integrated_content
        
        # 構造化されていることを確認
        assert '画像タイトル:' in integrated_content
        assert '画像内容:' in integrated_content
        assert '抽出されたテキスト:' in integrated_content
        assert '補足情報:' in integrated_content
    
    def test_create_integrated_content_partial(self, manager):
        """部分的なデータでの統合コンテンツ作成テスト"""
        # OCRテキストのみの場合
        content_ocr_only = manager._create_integrated_content(
            image_title="テスト画像",
            ocr_text="テキストのみ",
            vision_description="",
            additional_context=""
        )
        
        assert "画像タイトル: テスト画像" in content_ocr_only
        assert "抽出されたテキスト:\nテキストのみ" in content_ocr_only
        assert "画像内容:" not in content_ocr_only
        
        # Visionのみの場合
        content_vision_only = manager._create_integrated_content(
            image_title="",
            ocr_text="",
            vision_description="画像の説明のみ",
            additional_context=""
        )
        
        assert "画像内容: 画像の説明のみ" in content_vision_only
        assert "抽出されたテキスト:" not in content_vision_only
    
    def test_create_knowledge_from_image_success(self, manager, sample_image_data):
        """画像からのナレッジ作成成功テスト"""
        # 必要なモジュールをモック
        with patch.object(manager, 'text_splitter') as mock_splitter, \
             patch.object(manager, 'embedding_model') as mock_embedding, \
             patch.object(manager, 's3_vectors_client') as mock_s3_client:
            
            # テキスト分割のモック
            mock_splitter.split_text.return_value = [
                "画像タイトル: テスト用文書画像\n\n画像内容: ビジネス文書が写っている画像",
                "抽出されたテキスト:\nこれは重要な文書です。\n会議の議事録として保管します。",
                "補足情報: プロジェクトX関連資料"
            ]
            
            # 埋め込みベクトル生成のモック
            mock_embedding.embed_query.return_value = [0.1] * 1024  # ダミーベクトル
            
            # S3 Vectorsクライアントのモック
            mock_s3_client.get_user_index_name.return_value = "user-test-user-123-index"
            mock_s3_client.put_vectors.return_value = None
            
            # ナレッジ作成を実行
            vector_count = manager.create_knowledge_from_image(**sample_image_data)
            
            # 結果を検証
            assert vector_count == 3  # 3つのチャンクが作成された
            
            # 各メソッドが正しく呼ばれたことを確認
            mock_splitter.split_text.assert_called_once()
            assert mock_embedding.embed_query.call_count == 3
            assert mock_s3_client.put_vectors.call_count == 3
    
    def test_create_knowledge_from_image_empty_content(self, manager):
        """空のコンテンツでのナレッジ作成テスト"""
        vector_count = manager.create_knowledge_from_image(
            user_id="test-user",
            image_id="img-001",
            image_title="",
            ocr_text="",
            vision_description="",
            additional_context=""
        )
        
        # 空のコンテンツではナレッジが作成されない
        assert vector_count == 0
    
    def test_create_knowledge_from_image_error_handling(self, manager, sample_image_data):
        """ナレッジ作成エラーハンドリングテスト"""
        with patch.object(manager, 'text_splitter') as mock_splitter:
            # 例外を発生させる
            mock_splitter.split_text.side_effect = Exception("Splitting error")
            
            vector_count = manager.create_knowledge_from_image(**sample_image_data)
            
            # エラーが発生した場合は0を返す
            assert vector_count == 0
    
    def test_query_image_knowledge_success(self, manager):
        """画像ナレッジクエリ成功テスト"""
        with patch.object(manager, 's3_vectors_client') as mock_s3_client, \
             patch.object(manager, '_generate_answer_from_image_context') as mock_generate:
            
            # S3 Vectorsクエリ結果のモック
            mock_search_results = [
                {
                    'metadata': {
                        'source_type': 'image',
                        'image_id': 'img-001',
                        'image_title': 'テスト文書',
                        'text': '画像内容: ビジネス文書の画像です'
                    },
                    'distance': 0.1  # 高い関連度
                },
                {
                    'metadata': {
                        'source_type': 'image',
                        'image_id': 'img-002',
                        'image_title': '別の文書',
                        'text': '抽出されたテキスト:\n重要な情報が含まれています'
                    },
                    'distance': 0.3  # 中程度の関連度
                }
            ]
            
            mock_s3_client.query_user_documents.return_value = mock_search_results
            mock_generate.return_value = "画像から抽出された情報に基づく回答です"
            
            # クエリを実行
            result = manager.query_image_knowledge(
                user_id="test-user",
                question="文書について教えて",
                search_scope="all",
                max_results=5
            )
            
            # 結果を検証
            assert result['answer'] == "画像から抽出された情報に基づく回答です"
            assert len(result['image_sources']) == 2
            
            # 最初のソース情報を検証
            first_source = result['image_sources'][0]
            assert first_source['id'] == 'img-001'
            assert first_source['title'] == 'テスト文書'
            assert first_source['relevance_score'] == 0.9  # 1.0 - 0.1
            assert first_source['source_type'] == 'vision_analysis'
            
            assert 0 < result['confidence'] <= 1.0
    
    def test_query_image_knowledge_scope_filtering(self, manager):
        """検索スコープフィルタリングテスト"""
        with patch.object(manager, 's3_vectors_client') as mock_s3_client, \
             patch.object(manager, '_generate_answer_from_image_context') as mock_generate:
            
            # OCRとVisionの両方を含む結果
            mock_search_results = [
                {
                    'metadata': {
                        'source_type': 'image',
                        'image_id': 'img-001',
                        'text': '画像内容: Visionの分析結果'
                    },
                    'distance': 0.1
                },
                {
                    'metadata': {
                        'source_type': 'image',
                        'image_id': 'img-002',
                        'text': '抽出されたテキスト:\nOCRの結果'
                    },
                    'distance': 0.2
                }
            ]
            
            mock_s3_client.query_user_documents.return_value = mock_search_results
            mock_generate.return_value = "フィルタされた結果"
            
            # Vision分析のみを検索
            result_vision = manager.query_image_knowledge(
                user_id="test-user",
                question="テスト",
                search_scope="vision_only"
            )
            
            # OCRを含む結果は除外される
            assert len(result_vision['image_sources']) == 1
    
    def test_query_image_knowledge_no_results(self, manager):
        """検索結果なしのテスト"""
        with patch.object(manager, 's3_vectors_client') as mock_s3_client:
            # 空の検索結果
            mock_s3_client.query_user_documents.return_value = []
            
            result = manager.query_image_knowledge(
                user_id="test-user",
                question="存在しない内容",
                max_results=5
            )
            
            assert result['answer'] == "関連する画像情報が見つかりませんでした。"
            assert len(result['image_sources']) == 0
            assert result['confidence'] == 0.0
    
    def test_query_image_knowledge_error_handling(self, manager):
        """クエリエラーハンドリングテスト"""
        with patch.object(manager, 's3_vectors_client') as mock_s3_client:
            # S3 Vectors呼び出しで例外発生
            mock_s3_client.query_user_documents.side_effect = Exception("Vector query failed")
            
            result = manager.query_image_knowledge(
                user_id="test-user",
                question="エラーテスト"
            )
            
            assert "エラーが発生しました" in result['answer']
            assert len(result['image_sources']) == 0
            assert result['confidence'] == 0.0
            assert 'error' in result
    
    def test_generate_answer_from_image_context(self, manager):
        """画像コンテキストからの回答生成テスト"""
        # 検索結果のモックデータ
        search_results = [
            {
                'metadata': {
                    'image_title': '会議資料',
                    'text': 'これは重要な会議の議事録です。プロジェクトXの進捗について記載されています。'
                }
            },
            {
                'metadata': {
                    'image_title': '予算表',
                    'text': '予算の内訳が表として整理されています。総額は100万円です。'
                }
            }
        ]
        
        # ChatModelをモック
        with patch.object(manager, 'chat_model') as mock_chat:
            mock_response = Mock()
            mock_response.content = "会議資料と予算表から、プロジェクトXに関する詳細な回答です"
            mock_chat.invoke.return_value = mock_response
            
            answer = manager._generate_answer_from_image_context(
                question="プロジェクトXについて教えて",
                search_results=search_results
            )
            
            # 回答が生成されることを確認
            assert "プロジェクトX" in answer
            
            # ChatModelが正しく呼ばれることを確認
            mock_chat.invoke.assert_called_once()
            
            # プロンプトに画像情報が含まれることを確認
            call_args = mock_chat.invoke.call_args[0][0]
            messages_text = str(call_args)
            assert '会議資料' in messages_text
            assert '予算表' in messages_text
    
    def test_generate_answer_no_context(self, manager):
        """コンテキストなしでの回答生成テスト"""
        answer = manager._generate_answer_from_image_context(
            question="何かについて",
            search_results=[]
        )
        
        assert answer == "関連する画像情報が見つかりませんでした。"
    
    def test_generate_answer_error_handling(self, manager):
        """回答生成エラーハンドリングテスト"""
        search_results = [
            {
                'metadata': {
                    'image_title': 'テスト',
                    'text': 'テストデータ'
                }
            }
        ]
        
        with patch.object(manager, 'chat_model') as mock_chat:
            # Chat model呼び出しで例外発生
            mock_chat.invoke.side_effect = Exception("Chat model error")
            
            answer = manager._generate_answer_from_image_context(
                question="テスト質問",
                search_results=search_results
            )
            
            assert "エラーが発生しました" in answer
    
    def test_delete_knowledge_by_image(self, manager):
        """画像によるナレッジ削除テスト"""
        with patch.object(manager, 's3_vectors_client') as mock_s3_client:
            mock_s3_client.get_user_index_name.return_value = "user-test-index"
            
            success = manager.delete_knowledge_by_image("test-user", "img-001")
            
            # 削除処理が呼ばれることを確認
            assert success is True
            mock_s3_client.get_user_index_name.assert_called_with("test-user")
    
    def test_delete_knowledge_by_image_error(self, manager):
        """ナレッジ削除エラーテスト"""
        with patch.object(manager, 's3_vectors_client') as mock_s3_client:
            # 例外を発生させる
            mock_s3_client.get_user_index_name.side_effect = Exception("Delete error")
            
            success = manager.delete_knowledge_by_image("test-user", "img-001")
            
            assert success is False
    
    def test_update_image_knowledge(self, manager):
        """画像ナレッジ更新テスト"""
        with patch.object(manager, 'delete_knowledge_by_image') as mock_delete:
            mock_delete.return_value = True
            
            success = manager.update_image_knowledge(
                user_id="test-user",
                image_id="img-001",
                new_title="新しいタイトル",
                new_description="新しい説明",
                new_tags=["新タグ"]
            )
            
            # 削除→再作成の流れを確認
            assert success is True
            mock_delete.assert_called_once_with("test-user", "img-001")
    
    def test_update_image_knowledge_error(self, manager):
        """ナレッジ更新エラーテスト"""
        with patch.object(manager, 'delete_knowledge_by_image') as mock_delete:
            # 削除で例外発生
            mock_delete.side_effect = Exception("Update error")
            
            success = manager.update_image_knowledge(
                user_id="test-user",
                image_id="img-001"
            )
            
            assert success is False
    
    def test_vector_metadata_structure(self, manager, sample_image_data):
        """ベクトルメタデータ構造のテスト"""
        with patch.object(manager, 'text_splitter') as mock_splitter, \
             patch.object(manager, 'embedding_model') as mock_embedding, \
             patch.object(manager, 's3_vectors_client') as mock_s3_client:
            
            mock_splitter.split_text.return_value = ["チャンク1"]
            mock_embedding.embed_query.return_value = [0.1] * 1024
            mock_s3_client.get_user_index_name.return_value = "test-index"
            
            # put_vectors呼び出しをキャプチャ
            put_vectors_calls = []
            def capture_put_vectors(vector_bucket_name, index_name, vectors):
                put_vectors_calls.append(vectors[0])  # 最初のベクトルをキャプチャ
            
            mock_s3_client.put_vectors.side_effect = capture_put_vectors
            
            # ナレッジを作成
            manager.create_knowledge_from_image(**sample_image_data)
            
            # メタデータ構造を検証
            assert len(put_vectors_calls) == 1
            vector_data = put_vectors_calls[0]
            
            assert 'key' in vector_data
            assert 'data' in vector_data
            assert 'metadata' in vector_data
            
            metadata = vector_data['metadata']
            assert metadata['user_id'] == sample_image_data['user_id']
            assert metadata['source_type'] == 'image'
            assert metadata['image_id'] == sample_image_data['image_id']
            assert metadata['image_title'] == sample_image_data['image_title']
            assert metadata['chunk_index'] == 0
            assert metadata['total_chunks'] == 1
            assert metadata['content_type'] == 'image_knowledge'
            assert 'created_at' in metadata


if __name__ == '__main__':
    pytest.main([__file__, '-v'])