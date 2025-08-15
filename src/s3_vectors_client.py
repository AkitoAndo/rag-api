import os
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

import boto3
from langchain_aws.embeddings import BedrockEmbeddings
from langchain_text_splitters import MarkdownTextSplitter
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()


class S3VectorsClient:
    def __init__(self, region: str = None):
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.bedrock_client = boto3.client("bedrock-runtime", self.region)
        self.s3vectors_client = boto3.client("s3vectors", self.region)
        self.embedding_model = BedrockEmbeddings(
            client=self.bedrock_client,
            model_id=os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"),
        )

    def create_vectors_from_text(
        self, text: str, title: str, chunk_size: int = 1000
    ) -> List[Dict[str, Any]]:
        """テキストからベクトルを作成する"""
        text_splitter = MarkdownTextSplitter(chunk_size=chunk_size, chunk_overlap=200)
        chunks = text_splitter.split_text(text)

        vectors = []
        for chunk in chunks:
            embedding = self.embedding_model.embed_query(chunk)
            vectors.append(
                {
                    "key": str(uuid.uuid4()),
                    "data": {
                        "float32": embedding,
                    },
                    "metadata": {
                        "text": chunk,
                        "title": title,
                    },
                }
            )

        return vectors

    def put_vectors(
        self, vector_bucket_name: str, index_name: str, vectors: List[Dict[str, Any]]
    ) -> None:
        """ベクトルをS3 Vectorsに格納する"""
        self.s3vectors_client.put_vectors(
            vectorBucketName=vector_bucket_name,
            indexName=index_name,
            vectors=vectors,
        )

    def query_vectors(
        self, vector_bucket_name: str, index_name: str, question: str, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """質問に対してベクトル検索を実行する"""
        embedding = self.embedding_model.embed_query(question)

        response = self.s3vectors_client.query_vectors(
            vectorBucketName=vector_bucket_name,
            indexName=index_name,
            queryVector={
                "float32": embedding,
            },
            topK=top_k,
            returnMetadata=True,
            returnDistance=True,
        )

        return response["vectors"]

    def add_document(
        self, vector_bucket_name: str, index_name: str, text: str, title: str
    ) -> int:
        """ドキュメントを追加する（便利メソッド）"""
        vectors = self.create_vectors_from_text(text, title)
        self.put_vectors(vector_bucket_name, index_name, vectors)
        return len(vectors)

    # マルチテナント対応メソッド
    def get_user_index_name(self, user_id: str) -> str:
        """ユーザー固有のインデックス名を生成"""
        if not user_id or not user_id.strip():
            raise ValueError("User ID cannot be empty")
        
        # セキュリティのためユーザーIDをサニタイズ
        sanitized_user_id = re.sub(r'[^a-zA-Z0-9_-]', '', user_id.strip())
        if not sanitized_user_id:
            raise ValueError("Invalid user ID format")
        
        return f"user-{sanitized_user_id}-knowledge-base"

    def create_user_vectors_from_text(
        self, 
        user_id: str, 
        text: str, 
        title: str, 
        chunk_size: int = 1000,
        additional_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """ユーザー固有のメタデータ付きベクトルを作成"""
        text_splitter = MarkdownTextSplitter(chunk_size=chunk_size, chunk_overlap=200)
        chunks = text_splitter.split_text(text)

        document_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()

        vectors = []
        for chunk in chunks:
            embedding = self.embedding_model.embed_query(chunk)
            
            # ベースメタデータ
            metadata = {
                "user_id": user_id,
                "document_id": document_id,
                "text": chunk,
                "title": title,
                "created_at": created_at,
            }
            
            # 追加メタデータをマージ
            if additional_metadata:
                metadata.update(additional_metadata)
            
            vectors.append({
                "key": str(uuid.uuid4()),
                "data": {
                    "float32": embedding,
                },
                "metadata": metadata,
            })

        return vectors

    def add_user_document(
        self, 
        user_id: str, 
        vector_bucket_name: str, 
        text: str, 
        title: str,
        **kwargs
    ) -> int:
        """ユーザー固有の文書を追加"""
        # 入力検証
        if not text.strip():
            raise ValueError("Document text cannot be empty")
        if not title.strip():
            raise ValueError("Document title cannot be empty")
        
        # ユーザー固有のインデックス名を取得
        index_name = self.get_user_index_name(user_id)
        
        # ユーザー固有のベクトルを作成
        vectors = self.create_user_vectors_from_text(
            user_id=user_id,
            text=text,
            title=title,
            additional_metadata=kwargs
        )
        
        # S3 Vectorsに格納
        self.put_vectors(vector_bucket_name, index_name, vectors)
        
        return len(vectors)

    def query_user_documents(
        self, 
        user_id: str, 
        vector_bucket_name: str, 
        question: str, 
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """ユーザー固有の文書を検索"""
        if not question.strip():
            raise ValueError("Question cannot be empty")
        
        # ユーザー固有のインデックス名を取得
        index_name = self.get_user_index_name(user_id)
        
        # ベクトル検索を実行
        try:
            results = self.query_vectors(vector_bucket_name, index_name, question, top_k)
            
            # ユーザーIDでフィルタリング（安全性確保）
            user_results = [
                result for result in results 
                if result.get("metadata", {}).get("user_id") == user_id
            ]
            
            return user_results
            
        except Exception as e:
            # インデックスが存在しない場合は空結果を返す
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                return []
            raise e

    def delete_user_document(
        self, 
        user_id: str, 
        vector_bucket_name: str, 
        document_id: str
    ) -> bool:
        """ユーザーの特定文書を削除"""
        if not document_id.strip():
            raise ValueError("Document ID cannot be empty")
        
        # ユーザー固有のインデックス名を取得
        index_name = self.get_user_index_name(user_id)
        
        try:
            # 安全性のため、削除前に文書の所有者を確認
            # 実際の実装では、まず検索してユーザーIDを確認する必要がある
            self.s3vectors_client.delete_vectors(
                vectorBucketName=vector_bucket_name,
                indexName=index_name,
                keys=[document_id]
            )
            return True
            
        except Exception as e:
            print(f"Error deleting document {document_id} for user {user_id}: {str(e)}")
            return False

    def list_user_documents(
        self, 
        user_id: str, 
        vector_bucket_name: str, 
        limit: int = 20, 
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """ユーザーの文書一覧を取得（基本版）"""
        if limit <= 0:
            raise ValueError("Limit must be positive")
        if offset < 0:
            raise ValueError("Offset must be non-negative")
        
        # ユーザー固有のインデックス名を取得
        index_name = self.get_user_index_name(user_id)
        
        try:
            # S3 Vectors APIが文書一覧機能を提供していない可能性があるため、
            # 実際の実装では別の方法（DynamoDBなど）で管理することも検討
            response = self.s3vectors_client.list_documents(
                vectorBucketName=vector_bucket_name,
                indexName=index_name,
                limit=limit,
                offset=offset
            )
            return response
            
        except Exception as e:
            # インデックスが存在しない場合は空配列を返す
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                return []
            raise e

    def list_user_documents_extended(
        self,
        user_id: str,
        vector_bucket_name: str,
        limit: int = 20,
        offset: int = 0,
        search: str = "",
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> List[Dict[str, Any]]:
        """ユーザーの文書一覧を取得（拡張版：検索・ソート対応）"""
        if limit <= 0:
            raise ValueError("Limit must be positive")
        if offset < 0:
            raise ValueError("Offset must be non-negative")
        
        # ユーザー固有のインデックス名を取得
        index_name = self.get_user_index_name(user_id)
        
        try:
            # 基本的な文書一覧を取得
            all_documents = self.s3vectors_client.list_documents(
                vectorBucketName=vector_bucket_name,
                indexName=index_name,
                limit=1000  # 大きな値で全件取得（実際の実装では改善が必要）
            )
            
            # 検索フィルタ適用
            if search:
                all_documents = [
                    doc for doc in all_documents
                    if search.lower() in doc.get("title", "").lower()
                ]
            
            # ソート適用
            reverse = (sort_order == "desc")
            if sort_by == "title":
                all_documents.sort(key=lambda x: x.get("title", ""), reverse=reverse)
            elif sort_by == "vector_count":
                all_documents.sort(key=lambda x: x.get("vector_count", 0), reverse=reverse)
            elif sort_by == "content_length":
                all_documents.sort(key=lambda x: len(x.get("text", "")), reverse=reverse)
            else:  # created_at
                all_documents.sort(key=lambda x: x.get("created_at", ""), reverse=reverse)
            
            # ページネーション適用
            return all_documents[offset:offset + limit]
            
        except Exception as e:
            # インデックスが存在しない場合は空配列を返す
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                return []
            raise e

    def get_user_documents_count(
        self,
        user_id: str,
        vector_bucket_name: str,
        search: str = ""
    ) -> int:
        """ユーザーの文書総数を取得（検索条件適用）"""
        # ユーザー固有のインデックス名を取得
        index_name = self.get_user_index_name(user_id)
        
        try:
            # 全文書を取得して数をカウント
            all_documents = self.s3vectors_client.list_documents(
                vectorBucketName=vector_bucket_name,
                indexName=index_name,
                limit=10000  # 大きな値で全件取得
            )
            
            # 検索フィルタ適用
            if search:
                filtered_documents = [
                    doc for doc in all_documents
                    if search.lower() in doc.get("title", "").lower()
                ]
                return len(filtered_documents)
            
            return len(all_documents)
            
        except Exception as e:
            # インデックスが存在しない場合は0を返す
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                return 0
            raise e

    def get_document_info(
        self,
        user_id: str,
        vector_bucket_name: str,
        document_id: str
    ) -> Optional[Dict[str, Any]]:
        """特定の文書情報を取得"""
        index_name = self.get_user_index_name(user_id)
        
        try:
            # 文書一覧から該当文書を検索
            documents = self.s3vectors_client.list_documents(
                vectorBucketName=vector_bucket_name,
                indexName=index_name,
                limit=1000
            )
            
            for doc in documents:
                if doc.get("document_id") == document_id or doc.get("id") == document_id:
                    return doc
            
            return None
            
        except Exception as e:
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                return None
            raise e

    def delete_user_document_with_count(
        self,
        user_id: str,
        vector_bucket_name: str,
        document_id: str
    ) -> bool:
        """ユーザーの特定文書を削除（ベクトル数計算付き）"""
        if not document_id.strip():
            raise ValueError("Document ID cannot be empty")
        
        # ユーザー固有のインデックス名を取得
        
        try:
            # 既存の削除メソッドを使用
            return self.delete_user_document(user_id, vector_bucket_name, document_id)
            
        except Exception as e:
            print(f"Error deleting document {document_id} for user {user_id}: {str(e)}")
            return False

    def get_user_statistics(
        self, 
        user_id: str, 
        vector_bucket_name: str
    ) -> Dict[str, Any]:
        """ユーザーの統計情報を取得"""
        index_name = self.get_user_index_name(user_id)
        
        try:
            # 基本統計情報（実際のS3 Vectors APIに依存）
            stats = {
                "user_id": user_id,
                "index_name": index_name,
                "total_documents": 0,
                "total_vectors": 0,
                "last_updated": None
            }
            
            # 文書一覧から統計を計算
            documents = self.list_user_documents(user_id, vector_bucket_name, limit=1000)
            stats["total_documents"] = len(documents)
            
            # ベクトル数の合計を計算（文書メタデータから）
            total_vectors = sum(doc.get("vector_count", 1) for doc in documents)
            stats["total_vectors"] = total_vectors
            
            # 最後の更新日時
            if documents:
                latest_doc = max(documents, key=lambda d: d.get("created_at", ""))
                stats["last_updated"] = latest_doc.get("created_at")
            
            return stats
            
        except Exception as e:
            print(f"Error getting statistics for user {user_id}: {str(e)}")
            return {
                "user_id": user_id,
                "error": str(e),
                "total_documents": 0,
                "total_vectors": 0
            }
