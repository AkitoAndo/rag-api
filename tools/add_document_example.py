#!/usr/bin/env python3
"""
S3 Vectorsにドキュメントを追加する例
使用方法: python tools/add_document_example.py -f document.txt -t "ドキュメントタイトル"
"""

import argparse
import os
import sys
from pathlib import Path

# srcディレクトリをパスに追加
sys.path.append(str(Path(__file__).parent.parent / "src"))

from s3_vectors_client import S3VectorsClient


def main():
    parser = argparse.ArgumentParser(description='S3 Vectorsにドキュメントを追加する')
    parser.add_argument('-f', '--file', required=True, help='追加するテキストファイルのパス')
    parser.add_argument('-t', '--title', required=True, help='ドキュメントのタイトル')
    parser.add_argument('--bucket', default=os.getenv('VECTOR_BUCKET_NAME', '20250811-rag'), help='ベクトルバケット名')
    parser.add_argument('--index', default=os.getenv('VECTOR_INDEX_NAME', '20250811-rag-vector-index'), help='ベクトルインデックス名')
    parser.add_argument('--chunk-size', type=int, default=1000, help='チャンクサイズ')
    
    args = parser.parse_args()
    
    # ファイルを読み込む
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"エラー: ファイル {args.file} が見つかりません")
        return
        
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    print(f"ファイル: {args.file}")
    print(f"タイトル: {args.title}")
    print(f"文字数: {len(text)}")
    print("=" * 50)
    
    # S3 Vectorsクライアントを初期化
    client = S3VectorsClient()
    
    try:
        # ドキュメントを追加
        vector_count = client.add_document(
            vector_bucket_name=args.bucket,
            index_name=args.index,
            text=text,
            title=args.title
        )
        
        print(f"成功: {vector_count}個のベクトルを追加しました")
        
    except Exception as e:
        print(f"エラー: {e}")


if __name__ == "__main__":
    main()