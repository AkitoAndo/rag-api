#!/usr/bin/env python3
"""
API Gateway エンドポイントテスト用スクリプト
"""

import requests
import json
import sys
import argparse
from typing import Dict, Any

def test_add_document(base_url: str, text: str, title: str) -> bool:
    """ドキュメント追加APIをテスト"""
    endpoint = f"{base_url}/add-document"
    
    payload = {
        "text": text,
        "title": title
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        print(f"📤 ドキュメント追加テスト: {endpoint}")
        print(f"📝 タイトル: {title}")
        print(f"📄 テキスト: {text[:100]}...")
        
        response = requests.post(endpoint, json=payload, headers=headers)
        
        print(f"📊 レスポンス: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 成功: {result.get('message', '')}")
            print(f"🔢 ベクトル数: {result.get('vector_count', 0)}")
            return True
        else:
            print(f"❌ エラー: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 接続エラー: {str(e)}")
        return False

def test_query(base_url: str, question: str) -> bool:
    """質問応答APIをテスト"""
    endpoint = f"{base_url}/query"
    
    payload = {
        "question": question
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        print(f"🔍 質問応答テスト: {endpoint}")
        print(f"❓ 質問: {question}")
        
        response = requests.post(endpoint, json=payload, headers=headers)
        
        print(f"📊 レスポンス: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            answer = result.get('answer', '')
            print(f"✅ 成功")
            print(f"💬 回答: {answer}")
            return True
        else:
            print(f"❌ エラー: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 接続エラー: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description='API Gateway エンドポイントテスト')
    parser.add_argument('--base-url', required=True, 
                      help='API Gateway base URL (例: https://abc123.execute-api.us-east-1.amazonaws.com/Prod)')
    parser.add_argument('--test-add', action='store_true', 
                      help='ドキュメント追加のテスト実行')
    parser.add_argument('--test-query', action='store_true',
                      help='質問応答のテスト実行')
    parser.add_argument('--title', default='テストドキュメント',
                      help='ドキュメントのタイトル')
    parser.add_argument('--text', 
                      default='これはAPIテスト用のサンプルドキュメントです。機械学習とは、コンピュータがデータから自動的にパターンを学習する技術です。',
                      help='ドキュメントのテキスト')
    parser.add_argument('--question', 
                      default='機械学習について教えてください',
                      help='質問内容')
    
    args = parser.parse_args()
    
    # base_urlの末尾のスラッシュを除去
    base_url = args.base_url.rstrip('/')
    
    print("🚀 API Gateway エンドポイントテスト開始")
    print(f"🌐 Base URL: {base_url}")
    print("=" * 60)
    
    success_count = 0
    total_tests = 0
    
    if args.test_add or (not args.test_add and not args.test_query):
        total_tests += 1
        if test_add_document(base_url, args.text, args.title):
            success_count += 1
        print()
    
    if args.test_query or (not args.test_add and not args.test_query):
        total_tests += 1
        if test_query(base_url, args.question):
            success_count += 1
        print()
    
    print("=" * 60)
    print(f"📈 テスト結果: {success_count}/{total_tests} 成功")
    
    if success_count == total_tests:
        print("🎉 すべてのテストが成功しました！")
        return 0
    else:
        print("⚠️ 一部のテストが失敗しました")
        return 1

if __name__ == "__main__":
    sys.exit(main())

