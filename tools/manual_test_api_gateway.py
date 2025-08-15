"""
🚀 **API Gateway テスト実行ツール**
SAM Local または実際のAPI Gatewayエンドポイントをテストします。

使用方法:
    python manual_test_api_gateway.py <base_url>

例:
    # SAM Local テスト
    python manual_test_api_gateway.py http://127.0.0.1:3000
    
    # 実際のAPI Gateway テスト
    python manual_test_api_gateway.py https://your-api-id.execute-api.region.amazonaws.com/Prod
"""

def test_add_document(base_url: str, text: str, title: str) -> bool:
    """文書追加エンドポイントをテスト"""
    import requests
    import json
    
    print(f"📝 文書追加テスト: {base_url}/add-document")
    print(f"📄 タイトル: {title}")
    print(f"📝 テキスト長: {len(text)}文字")
    
    try:
        response = requests.post(
            f"{base_url}/add-document",
            headers={
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "title": title
            },
            timeout=30
        )
        
        print(f"📊 ステータス: {response.status_code}")
        print(f"📋 レスポンス: {response.text}")
        
        if response.status_code == 200:
            print("✅ 文書追加成功!")
            return True
        else:
            print("❌ 文書追加失敗!")
            return False
            
    except Exception as e:
        print(f"❌ 接続エラー: {str(e)}")
        return False

def test_query(base_url: str, question: str) -> bool:
    """質問応答エンドポイントをテスト"""
    import requests
    import json
    
    print(f"\n🔍 質問応答テスト: {base_url}/query")
    print(f"❓ 質問: {question}")
    
    try:
        response = requests.post(
            f"{base_url}/query",
            headers={
                "Content-Type": "application/json",
            },
            json={
                "question": question
            },
            timeout=30
        )
        
        print(f"📊 ステータス: {response.status_code}")
        print(f"📋 レスポンス: {response.text}")
        
        if response.status_code == 200:
            print("✅ 質問応答成功!")
            return True
        else:
            print("❌ 質問応答失敗!")
            return False
            
    except Exception as e:
        print(f"❌ 接続エラー: {str(e)}")
        return False

def main():
    """メイン実行関数"""
    import sys
    
    if len(sys.argv) != 2:
        print(__doc__)
        return
    
    base_url = sys.argv[1].rstrip('/')
    
    print("🚀 **API Gateway テスト開始**")
    print(f"🌐 ベースURL: {base_url}")
    print("="*50)
    
    # テストデータ
    test_text = """
    これはテスト用の文書です。
    RAG（Retrieval-Augmented Generation）システムの動作確認のために作成されました。
    この文書には以下の情報が含まれています：
    
    1. システムの基本概念
    2. 実装詳細
    3. テスト方法
    
    質問応答システムが正しく動作するかどうかを確認できます。
    """
    
    test_title = "テスト文書"
    test_question = "このシステムの主な機能は何ですか？"
    
    # テスト実行
    doc_success = test_add_document(base_url, test_text, test_title)
    query_success = test_query(base_url, test_question)
    
    print("\n" + "="*50)
    print("📋 **テスト結果サマリー**")
    print(f"📝 文書追加: {'✅ 成功' if doc_success else '❌ 失敗'}")
    print(f"🔍 質問応答: {'✅ 成功' if query_success else '❌ 失敗'}")
    
    if doc_success and query_success:
        print("🎉 全テスト成功! APIは正常に動作しています。")
    else:
        print("⚠️  一部テストが失敗しました。ログを確認してください。")

if __name__ == "__main__":
    main()