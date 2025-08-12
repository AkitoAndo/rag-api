import pytest
import uuid
import json
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock


@pytest.mark.unit
class TestUserDocumentManagement:
    """ユーザー文書管理機能のテスト"""

    @pytest.fixture
    def document_manager(self):
        """UserDocumentManager（新しいクラス想定）のインスタンス"""
        with patch('src.user_document_manager.S3VectorsClient'):
            from src.user_document_manager import UserDocumentManager
            return UserDocumentManager()

    @pytest.fixture
    def sample_document_data(self):
        """サンプル文書データ"""
        return {
            "user_id": "user123",
            "title": "プロジェクト計画書",
            "text": "これはプロジェクトの詳細計画です。フェーズ1では要件定義を行い、フェーズ2では設計を実施します。",
            "tags": ["project", "planning", "business"],
            "metadata": {
                "category": "business",
                "priority": "high",
                "project_id": "proj_001"
            }
        }

    def test_create_document_with_user_context(self, document_manager, sample_document_data):
        """ユーザーコンテキスト付きドキュメント作成テスト"""
        # ドキュメント作成の実行
        with patch.object(document_manager, '_generate_vectors') as mock_vectors:
            mock_vectors.return_value = [
                {"key": "vec1", "data": {"float32": [0.1, 0.2]}, "metadata": {}}
            ]
            
            document = document_manager.create_document(
                user_id=sample_document_data["user_id"],
                title=sample_document_data["title"],
                text=sample_document_data["text"],
                tags=sample_document_data["tags"],
                metadata=sample_document_data["metadata"]
            )
        
        # ドキュメントに必要な情報が含まれることを確認
        assert document["user_id"] == sample_document_data["user_id"]
        assert document["title"] == sample_document_data["title"]
        assert "document_id" in document
        assert "created_at" in document
        assert "vector_count" in document
        
        # document_idがUUID形式であることを確認
        uuid.UUID(document["document_id"])

    def test_document_metadata_enrichment(self, document_manager, sample_document_data):
        """ドキュメントメタデータ拡張テスト"""
        with patch.object(document_manager, '_generate_vectors') as mock_vectors, \
             patch.object(document_manager, '_store_vectors') as mock_store:
            
            mock_vectors.return_value = []
            mock_store.return_value = True
            
            document = document_manager.create_document(**sample_document_data)
            
            # メタデータが適切に拡張されることを確認
            call_args = mock_vectors.call_args
            enriched_metadata = call_args[1]['base_metadata']
            
            assert enriched_metadata['user_id'] == sample_document_data["user_id"]
            assert enriched_metadata['document_id'] == document['document_id']
            assert enriched_metadata['title'] == sample_document_data["title"]
            assert enriched_metadata['tags'] == sample_document_data["tags"]
            assert 'created_at' in enriched_metadata
            
            # カスタムメタデータも保持される
            assert enriched_metadata['category'] == "business"
            assert enriched_metadata['priority'] == "high"

    def test_document_search_with_filters(self, document_manager):
        """フィルター付きドキュメント検索テスト"""
        user_id = "user456"
        search_filters = {
            "tags": ["project"],
            "category": "business",
            "date_range": {
                "start": "2025-01-01",
                "end": "2025-01-31"
            }
        }
        
        with patch.object(document_manager, '_search_with_filters') as mock_search:
            mock_search.return_value = [
                {
                    "document_id": "doc_1",
                    "title": "検索結果1",
                    "relevance_score": 0.95,
                    "metadata": {"tags": ["project"], "category": "business"}
                }
            ]
            
            results = document_manager.search_user_documents(
                user_id=user_id,
                query="プロジェクト計画",
                filters=search_filters,
                top_k=5
            )
            
            # フィルターが適用された検索が実行される
            mock_search.assert_called_once()
            call_args = mock_search.call_args
            
            assert call_args[0][0] == user_id
            assert call_args[0][1] == "プロジェクト計画"
            assert call_args[1]['filters'] == search_filters
            assert call_args[1]['top_k'] == 5

    def test_document_version_management(self, document_manager):
        """ドキュメントバージョン管理テスト"""
        user_id = "user789"
        document_id = "doc_original"
        
        # 元のドキュメント
        original_doc = {
            "document_id": document_id,
            "title": "オリジナル文書",
            "text": "これは元の内容です。",
            "version": 1
        }
        
        # 更新されたドキュメント
        updated_text = "これは更新された内容です。新しい情報が追加されました。"
        
        with patch.object(document_manager, '_get_document') as mock_get, \
             patch.object(document_manager, '_create_new_version') as mock_version:
            
            mock_get.return_value = original_doc
            mock_version.return_value = {
                "document_id": document_id,
                "version": 2,
                "previous_version": 1,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            updated_doc = document_manager.update_document(
                user_id=user_id,
                document_id=document_id,
                text=updated_text,
                keep_history=True
            )
            
            # バージョン管理が正しく動作することを確認
            assert updated_doc["version"] == 2
            assert updated_doc["previous_version"] == 1
            assert "updated_at" in updated_doc

    def test_document_access_control(self, document_manager):
        """ドキュメントアクセス制御テスト"""
        user_a = "user_alice"
        user_b = "user_bob"
        document_id = "doc_alice_private"
        
        with patch.object(document_manager, '_check_access_permission') as mock_access:
            # user_aは自分のドキュメントにアクセス可能
            mock_access.return_value = True
            result_a = document_manager.get_document(user_a, document_id)
            mock_access.assert_called_with(user_a, document_id)
            
            # user_bは他人のドキュメントにアクセス不可
            mock_access.return_value = False
            with pytest.raises(PermissionError, match="Access denied"):
                document_manager.get_document(user_b, document_id)

    def test_document_bulk_operations(self, document_manager):
        """ドキュメント一括操作テスト"""
        user_id = "user_bulk"
        document_ids = ["doc_1", "doc_2", "doc_3"]
        
        with patch.object(document_manager, '_bulk_delete') as mock_bulk:
            mock_bulk.return_value = {
                "deleted_count": 3,
                "failed_ids": [],
                "success": True
            }
            
            result = document_manager.bulk_delete_documents(
                user_id=user_id,
                document_ids=document_ids
            )
            
            assert result["deleted_count"] == 3
            assert result["success"] is True
            
            # 一括削除が正しいパラメータで呼び出される
            mock_bulk.assert_called_once_with(user_id, document_ids)

    def test_document_statistics(self, document_manager):
        """ドキュメント統計情報テスト"""
        user_id = "user_stats"
        
        with patch.object(document_manager, '_calculate_user_stats') as mock_stats:
            mock_stats.return_value = {
                "total_documents": 25,
                "total_vectors": 150,
                "storage_size_mb": 12.5,
                "last_updated": "2025-01-15T10:30:00Z",
                "categories": {
                    "business": 15,
                    "personal": 10
                },
                "tags_frequency": {
                    "project": 12,
                    "meeting": 8,
                    "idea": 5
                }
            }
            
            stats = document_manager.get_user_statistics(user_id)
            
            assert stats["total_documents"] == 25
            assert stats["total_vectors"] == 150
            assert "categories" in stats
            assert "tags_frequency" in stats

    def test_document_export_import(self, document_manager):
        """ドキュメントエクスポート/インポートテスト"""
        user_id = "user_export"
        
        # エクスポートテスト
        with patch.object(document_manager, '_export_user_data') as mock_export:
            mock_export.return_value = {
                "format": "json",
                "version": "1.0",
                "user_id": user_id,
                "documents": [
                    {
                        "document_id": "doc_1",
                        "title": "文書1",
                        "text": "内容1",
                        "metadata": {"category": "test"}
                    }
                ],
                "exported_at": datetime.utcnow().isoformat()
            }
            
            export_data = document_manager.export_user_documents(
                user_id=user_id,
                format="json",
                include_vectors=False
            )
            
            assert export_data["user_id"] == user_id
            assert len(export_data["documents"]) == 1
            assert export_data["format"] == "json"

        # インポートテスト
        import_data = export_data
        
        with patch.object(document_manager, '_import_user_data') as mock_import:
            mock_import.return_value = {
                "imported_count": 1,
                "skipped_count": 0,
                "failed_count": 0,
                "success": True
            }
            
            result = document_manager.import_user_documents(
                user_id=user_id,
                data=import_data,
                merge_strategy="skip_existing"
            )
            
            assert result["imported_count"] == 1
            assert result["success"] is True


@pytest.mark.integration_mock
class TestUserDocumentManagementIntegration:
    """ユーザー文書管理統合テスト"""

    def test_document_lifecycle_workflow(self):
        """ドキュメントライフサイクルワークフロー統合テスト"""
        user_id = "user_lifecycle"
        
        with patch('src.user_document_manager.S3VectorsClient') as mock_s3:
            from src.user_document_manager import UserDocumentManager
            manager = UserDocumentManager()
            
            # 1. ドキュメント作成
            with patch.object(manager, 'create_document') as mock_create:
                mock_create.return_value = {
                    "document_id": "doc_test",
                    "user_id": user_id,
                    "title": "テスト文書",
                    "vector_count": 3,
                    "created_at": "2025-01-15T10:30:00Z"
                }
                
                doc = manager.create_document(
                    user_id=user_id,
                    title="テスト文書",
                    text="テスト内容" * 100  # 長いテキスト
                )
                
                assert doc["document_id"] == "doc_test"
            
            # 2. ドキュメント検索
            with patch.object(manager, 'search_user_documents') as mock_search:
                mock_search.return_value = [
                    {
                        "document_id": "doc_test",
                        "title": "テスト文書",
                        "relevance_score": 0.98,
                        "snippet": "テスト内容の一部..."
                    }
                ]
                
                results = manager.search_user_documents(
                    user_id=user_id,
                    query="テスト",
                    top_k=5
                )
                
                assert len(results) == 1
                assert results[0]["document_id"] == "doc_test"
            
            # 3. ドキュメント更新
            with patch.object(manager, 'update_document') as mock_update:
                mock_update.return_value = {
                    "document_id": "doc_test",
                    "version": 2,
                    "updated_at": "2025-01-15T11:00:00Z"
                }
                
                updated = manager.update_document(
                    user_id=user_id,
                    document_id="doc_test",
                    text="更新されたテスト内容"
                )
                
                assert updated["version"] == 2
            
            # 4. ドキュメント削除
            with patch.object(manager, 'delete_document') as mock_delete:
                mock_delete.return_value = {"success": True}
                
                result = manager.delete_document(
                    user_id=user_id,
                    document_id="doc_test"
                )
                
                assert result["success"] is True

    def test_multi_user_document_isolation(self):
        """マルチユーザー文書分離統合テスト"""
        user_a = "user_alice_isolation"
        user_b = "user_bob_isolation"
        
        with patch('src.user_document_manager.S3VectorsClient'):
            from src.user_document_manager import UserDocumentManager
            manager = UserDocumentManager()
            
            # 各ユーザーがドキュメントを作成
            with patch.object(manager, 'create_document') as mock_create:
                mock_create.side_effect = [
                    {"document_id": "alice_doc", "user_id": user_a},
                    {"document_id": "bob_doc", "user_id": user_b}
                ]
                
                alice_doc = manager.create_document(
                    user_id=user_a, title="Alice's Doc", text="Alice's content"
                )
                bob_doc = manager.create_document(
                    user_id=user_b, title="Bob's Doc", text="Bob's content"
                )
                
                assert alice_doc["user_id"] == user_a
                assert bob_doc["user_id"] == user_b
            
            # 各ユーザーは自分のドキュメントのみ検索可能
            with patch.object(manager, 'search_user_documents') as mock_search:
                mock_search.side_effect = [
                    [{"document_id": "alice_doc", "user_id": user_a}],
                    [{"document_id": "bob_doc", "user_id": user_b}]
                ]
                
                alice_results = manager.search_user_documents(user_a, "content")
                bob_results = manager.search_user_documents(user_b, "content")
                
                assert alice_results[0]["user_id"] == user_a
                assert bob_results[0]["user_id"] == user_b
                
                # 呼び出し回数の確認
                assert mock_search.call_count == 2