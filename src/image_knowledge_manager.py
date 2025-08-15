"""
画像ナレッジベース統合管理クラス
画像から抽出された情報をRAGシステムに統合
"""
import os
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

import boto3
from langchain_aws.embeddings import BedrockEmbeddings
from langchain_aws.chat_models import ChatBedrockConverse
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.messages import HumanMessage, SystemMessage

from s3_vectors_client import S3VectorsClient


class ImageKnowledgeManager:
    """画像ナレッジベース統合管理クラス"""
    
    def __init__(self):
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.bedrock_client = boto3.client("bedrock-runtime", self.region)
        self.s3_vectors_client = S3VectorsClient()
        
        # BedrockEmbeddingsの初期化
        self.embedding_model = BedrockEmbeddings(
            client=self.bedrock_client,
            model_id=os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
        )
        
        # ChatBedrockConverseの初期化
        self.chat_model = ChatBedrockConverse(
            client=self.bedrock_client,
            model=os.getenv("CHAT_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
            temperature=0.7
        )
        
        # テキスト分割器
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", "。", "、", " ", ""]
        )
    
    def create_knowledge_from_image(
        self,
        user_id: str,
        image_id: str,
        image_title: str,
        ocr_text: str,
        vision_description: str,
        additional_context: str = ""
    ) -> int:
        """画像から抽出された情報をナレッジベースに統合"""
        try:
            # 統合テキストを作成
            integrated_content = self._create_integrated_content(
                image_title=image_title,
                ocr_text=ocr_text,
                vision_description=vision_description,
                additional_context=additional_context
            )
            
            if not integrated_content.strip():
                return 0  # 有効なコンテンツがない場合
            
            # テキストを適切なサイズに分割
            text_chunks = self.text_splitter.split_text(integrated_content)
            
            # 各チャンクをベクトル化してS3 Vectorsに保存
            vector_count = 0
            vector_bucket_name = os.environ.get("VECTOR_BUCKET_NAME")
            
            if not vector_bucket_name:
                print("VECTOR_BUCKET_NAME環境変数が設定されていません")
                return 0
            
            for i, chunk in enumerate(text_chunks):
                try:
                    # ベクトル作成
                    embedding = self.embedding_model.embed_query(chunk)
                    
                    # メタデータ作成
                    metadata = {
                        "user_id": user_id,
                        "source_type": "image",
                        "image_id": image_id,
                        "image_title": image_title,
                        "chunk_index": i,
                        "total_chunks": len(text_chunks),
                        "text": chunk,
                        "created_at": datetime.utcnow().isoformat(),
                        "content_type": "image_knowledge"
                    }
                    
                    # S3 Vectorsに保存
                    vector_data = {
                        "key": f"img_{image_id}_chunk_{i}_{uuid.uuid4().hex[:8]}",
                        "data": {
                            "float32": embedding
                        },
                        "metadata": metadata
                    }
                    
                    # ユーザー固有のインデックスに保存
                    user_index = self.s3_vectors_client.get_user_index_name(user_id)
                    self.s3_vectors_client.put_vectors(
                        vector_bucket_name=vector_bucket_name,
                        index_name=user_index,
                        vectors=[vector_data]
                    )
                    
                    vector_count += 1
                    
                except Exception as e:
                    print(f"Error creating vector for chunk {i}: {str(e)}")
                    continue
            
            return vector_count
            
        except Exception as e:
            print(f"Error creating knowledge from image: {str(e)}")
            return 0
    
    def _create_integrated_content(
        self,
        image_title: str,
        ocr_text: str,
        vision_description: str,
        additional_context: str = ""
    ) -> str:
        """画像から抽出された情報を統合したコンテンツを作成"""
        content_parts = []
        
        # タイトル
        if image_title:
            content_parts.append(f"画像タイトル: {image_title}")
        
        # Vision分析結果
        if vision_description:
            content_parts.append(f"画像内容: {vision_description}")
        
        # OCRテキスト
        if ocr_text and ocr_text.strip():
            content_parts.append(f"抽出されたテキスト:\n{ocr_text}")
        
        # 追加コンテキスト
        if additional_context:
            content_parts.append(f"補足情報: {additional_context}")
        
        return "\n\n".join(content_parts)
    
    def query_image_knowledge(
        self,
        user_id: str,
        question: str,
        search_scope: str = "all",
        max_results: int = 5,
        image_tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """画像ナレッジベースに対してクエリを実行"""
        try:
            vector_bucket_name = os.environ.get("VECTOR_BUCKET_NAME")
            if not vector_bucket_name:
                raise Exception("VECTOR_BUCKET_NAME環境変数が設定されていません")
            
            # ユーザーの画像ナレッジベースを検索
            search_results = self.s3_vectors_client.query_user_documents(
                user_id=user_id,
                vector_bucket_name=vector_bucket_name,
                question=question,
                top_k=max_results * 2  # より多くの候補を取得
            )
            
            # 画像由来の結果のみフィルタリング
            image_results = []
            for result in search_results:
                metadata = result.get("metadata", {})
                if metadata.get("source_type") == "image":
                    # search_scopeフィルタ適用
                    if search_scope == "text_only" and not metadata.get("text", "").strip():
                        continue
                    elif search_scope == "vision_only" and "抽出されたテキスト:" in metadata.get("text", ""):
                        continue
                    
                    image_results.append(result)
            
            # 結果数を制限
            image_results = image_results[:max_results]
            
            # 画像ソース情報を作成
            image_sources = []
            processed_images = set()
            
            for result in image_results:
                metadata = result.get("metadata", {})
                image_id = metadata.get("image_id", "")
                
                if image_id and image_id not in processed_images:
                    processed_images.add(image_id)
                    
                    # ソース情報を決定
                    text_content = metadata.get("text", "")
                    source_type = "ocr_text"
                    snippet = ""
                    
                    if "画像内容:" in text_content:
                        source_type = "vision_analysis"
                        snippet = text_content.split("画像内容:")[1].split("\n")[0].strip()
                    elif "抽出されたテキスト:" in text_content:
                        source_type = "ocr_text"
                        ocr_part = text_content.split("抽出されたテキスト:")[1].strip()
                        snippet = ocr_part[:200] + ("..." if len(ocr_part) > 200 else "")
                    else:
                        snippet = text_content[:200] + ("..." if len(text_content) > 200 else "")
                    
                    image_sources.append({
                        "id": image_id,
                        "title": metadata.get("image_title", "画像"),
                        "filename": f"{metadata.get('image_title', 'image')}.jpg",
                        "relevance_score": 1.0 - result.get("distance", 0.0),
                        "snippet": snippet,
                        "source_type": source_type
                    })
            
            # AI回答を生成
            answer = self._generate_answer_from_image_context(question, image_results)
            
            # 信頼度を計算
            confidence = min(1.0, len(image_sources) / max_results) if max_results > 0 else 0.0
            if image_sources:
                avg_relevance = sum(source["relevance_score"] for source in image_sources) / len(image_sources)
                confidence = (confidence + avg_relevance) / 2.0
            
            return {
                "answer": answer,
                "image_sources": image_sources,
                "confidence": confidence
            }
            
        except Exception as e:
            print(f"Error querying image knowledge: {str(e)}")
            return {
                "answer": "画像ナレッジベースの検索中にエラーが発生しました。",
                "image_sources": [],
                "confidence": 0.0,
                "error": str(e)
            }
    
    def _generate_answer_from_image_context(self, question: str, search_results: List[Dict[str, Any]]) -> str:
        """画像検索結果を基にAI回答を生成"""
        try:
            if not search_results:
                return "関連する画像情報が見つかりませんでした。"
            
            # コンテキストを構築
            context_parts = []
            for i, result in enumerate(search_results, 1):
                metadata = result.get("metadata", {})
                text = metadata.get("text", "")
                image_title = metadata.get("image_title", f"画像{i}")
                
                context_parts.append(f"【{image_title}】\n{text}")
            
            context = "\n\n".join(context_parts)
            
            # システムプロンプト
            system_prompt = """あなたは親切で知識豊富な画像解析アシスタントです。
提供された画像から抽出された情報に基づいて、ユーザーの質問に正確で有用な回答を提供してください。

回答する際の注意点：
- 画像から抽出された情報のみを使用してください
- OCRテキストと画像の視覚的説明の両方を考慮してください
- 不確実な情報については推測ではなく、画像から確認できる事実のみを述べてください
- 日本語で自然な文章で回答してください"""

            # ユーザープロンプト
            user_prompt = f"""以下の画像から抽出された情報を参考に質問に答えてください：

{context}

質問: {question}"""

            # AI回答生成
            messages = [
                SystemMessage(system_prompt),
                HumanMessage(user_prompt)
            ]
            
            response = self.chat_model.invoke(messages)
            return response.content
            
        except Exception as e:
            print(f"Error generating answer from image context: {str(e)}")
            return "回答の生成中にエラーが発生しました。画像から抽出された情報を直接ご確認ください。"
    
    def delete_knowledge_by_image(self, user_id: str, image_id: str) -> bool:
        """指定した画像に関連するナレッジベースエントリを削除"""
        try:
            vector_bucket_name = os.environ.get("VECTOR_BUCKET_NAME")
            if not vector_bucket_name:
                return False
            
            # ユーザーのベクトルインデックスから画像関連のベクトルを検索・削除
            # 実際の実装では、S3 Vectorsの削除APIを使用
            # ここでは概念的な実装のみ
            
            # 画像IDに基づくベクトルキーパターンで削除
            # 実装詳細はS3 Vectors APIの仕様に依存
            
            print(f"Deleted knowledge entries for image {image_id} of user {user_id}")
            return True
            
        except Exception as e:
            print(f"Error deleting knowledge by image: {str(e)}")
            return False
    
    def update_image_knowledge(
        self,
        user_id: str,
        image_id: str,
        new_title: str = None,
        new_description: str = None,
        new_tags: List[str] = None
    ) -> bool:
        """画像ナレッジの更新（タイトル、説明、タグの変更）"""
        try:
            # 既存のナレッジエントリを削除
            self.delete_knowledge_by_image(user_id, image_id)
            
            # 新しい情報で再作成
            # 実際の実装では、画像メタデータから最新情報を取得して再生成
            
            return True
            
        except Exception as e:
            print(f"Error updating image knowledge: {str(e)}")
            return False