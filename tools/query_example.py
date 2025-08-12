#!/usr/bin/env python3
"""
S3 Vectorsを使ったローカルでのクエリ例
使用方法: python tools/query_example.py -q "質問内容"
"""

import argparse
import os
import sys
from pathlib import Path

# srcディレクトリをパスに追加
sys.path.append(str(Path(__file__).parent.parent / "src"))

from s3_vectors_client import S3VectorsClient


def main():
    parser = argparse.ArgumentParser(description='S3 Vectorsに対してクエリを実行する')
    parser.add_argument('-q', '--question', required=True, help='質問内容')
    parser.add_argument('--bucket', default=os.getenv('VECTOR_BUCKET_NAME', '20250811-rag'), help='ベクトルバケット名')
    parser.add_argument('--index', default=os.getenv('VECTOR_INDEX_NAME', '20250811-rag-vector-index'), help='ベクトルインデックス名')
    parser.add_argument('--top-k', type=int, default=3, help='取得する上位結果数')
    
    args = parser.parse_args()
    
    # S3 Vectorsクライアントを初期化
    client = S3VectorsClient()
    
    print(f"質問: {args.question}")
    print("=" * 50)
    
    try:
        # ベクトル検索を実行
        vectors = client.query_vectors(
            vector_bucket_name=args.bucket,
            index_name=args.index,
            question=args.question,
            top_k=args.top_k
        )
        
        # 結果を表示
        for i, vector in enumerate(vectors, 1):
            print(f"\n--- 結果 {i} ---")
            print(f"距離: {vector.get('distance', 'N/A')}")
            print(f"タイトル: {vector['metadata'].get('title', 'N/A')}")
            print(f"テキスト: {vector['metadata'].get('text', 'N/A')[:200]}...")
            
    except Exception as e:
        print(f"エラー: {e}")


if __name__ == "__main__":
    main()