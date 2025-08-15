"""API クライアントテスト"""
import pytest
import json
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch

# toolsディレクトリをパスに追加
sys.path.append(str(Path(__file__).parent.parent / "tools"))

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

def api_add_document(base_url: str, text: str, title: str) -> bool:
    """文書追加APIテスト"""
    try:
        response = requests.post(
            f"{base_url}/add-document",
            json={"text": text, "title": title},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        return response.status_code == 200
    except Exception:
        return False

def api_query(base_url: str, question: str) -> bool:
    """質問応答APIテスト"""
    try:
        response = requests.post(
            f"{base_url}/query",
            json={"question": question},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        return response.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests library not available")
@pytest.mark.unit
class TestAPIClient:
    """API クライアントの単体テスト"""
    
    @patch('requests.post')
    def test_add_document_success(self, mock_post):
        """ドキュメント追加成功テスト"""
        # モックレスポンス設定
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Successfully added 3 vectors",
            "vector_count": 3
        }
        mock_post.return_value = mock_response
        
        # テスト実行
        result = api_add_document(
            base_url="https://test-api.example.com",
            text="テストドキュメント",
            title="テストタイトル"
        )
        
        # 結果確認
        assert result is True
        mock_post.assert_called_once()
        
        # 呼び出し引数確認
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://test-api.example.com/add-document"
        assert call_args[1]["json"]["text"] == "テストドキュメント"
        assert call_args[1]["json"]["title"] == "テストタイトル"
    
    @patch('requests.post')
    def test_add_document_error(self, mock_post):
        """ドキュメント追加エラーテスト"""
        # モックレスポンス設定（エラー）
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = '{"error": "Internal server error"}'
        mock_post.return_value = mock_response
        
        # テスト実行
        result = api_add_document(
            base_url="https://test-api.example.com",
            text="テストドキュメント",
            title="テストタイトル"
        )
        
        # 結果確認
        assert result is False
    
    @patch('requests.post')
    def test_query_success(self, mock_post):
        """質問応答成功テスト"""
        # モックレスポンス設定
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": "これはテスト回答です"
        }
        mock_post.return_value = mock_response
        
        # テスト実行
        result = api_query(
            base_url="https://test-api.example.com",
            question="テスト質問"
        )
        
        # 結果確認
        assert result is True
        mock_post.assert_called_once()
        
        # 呼び出し引数確認
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://test-api.example.com/query"
        assert call_args[1]["json"]["question"] == "テスト質問"
    
    @patch('requests.post')
    def test_query_error(self, mock_post):
        """質問応答エラーテスト"""
        # モックレスポンス設定（エラー）
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = '{"error": "Query failed"}'
        mock_post.return_value = mock_response
        
        # テスト実行
        result = api_query(
            base_url="https://test-api.example.com",
            question="テスト質問"
        )
        
        # 結果確認
        assert result is False
    
    @patch('requests.post')
    def test_connection_error(self, mock_post):
        """接続エラーテスト"""
        # 接続エラーをシミュレート
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        # テスト実行
        result = api_add_document(
            base_url="https://unreachable-api.example.com",
            text="テストドキュメント",
            title="テストタイトル"
        )
        
        # 結果確認
        assert result is False
    
    @patch('requests.post')
    def test_timeout_error(self, mock_post):
        """タイムアウトエラーテスト"""
        # タイムアウトエラーをシミュレート
        mock_post.side_effect = requests.exceptions.Timeout("Request timeout")
        
        # テスト実行
        result = api_query(
            base_url="https://slow-api.example.com",
            question="テスト質問"
        )
        
        # 結果確認
        assert result is False
    
    @patch('requests.post')
    def test_unicode_handling(self, mock_post):
        """Unicode文字処理テスト"""
        # モックレスポンス設定
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": "日本語での回答です 🤖"
        }
        mock_post.return_value = mock_response
        
        # Unicode文字を含むテスト実行
        result = api_query(
            base_url="https://test-api.example.com",
            question="日本語の質問です 🚀"
        )
        
        # 結果確認
        assert result is True
        
        # Unicode文字が正しく送信されることを確認
        call_args = mock_post.call_args
        assert call_args[1]["json"]["question"] == "日本語の質問です 🚀"


@pytest.mark.unit
class TestAPIClientValidation:
    """API クライアント入力検証テスト"""
    
    def test_empty_base_url(self):
        """空のベースURL処理テスト"""
        with pytest.raises(Exception):
            # 空のURLでの呼び出しは例外を発生させるべき
            api_query("", "テスト質問")
    
    def test_invalid_base_url_format(self):
        """不正なURL形式テスト"""
        # 不正なURL形式でも関数は実行されるが、requests内でエラーになる
        result = api_query("invalid-url", "テスト質問")
        assert result is False
    
    def test_empty_question(self):
        """空の質問処理テスト"""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"answer": "Empty question response"}
            mock_post.return_value = mock_response
            
            result = api_query("https://test-api.example.com", "")
            
            # 空の質問でも送信されることを確認
            assert result is True
            call_args = mock_post.call_args
            assert call_args[1]["json"]["question"] == ""
    
    def test_empty_document_text(self):
        """空のドキュメントテキスト処理テスト"""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": "Empty document processed",
                "vector_count": 0
            }
            mock_post.return_value = mock_response
            
            result = api_add_document(
                "https://test-api.example.com",
                "",  # 空のテキスト
                "Empty Document"
            )
            
            assert result is True
            call_args = mock_post.call_args
            assert call_args[1]["json"]["text"] == ""


@pytest.mark.unit
class TestAPIResponseParsing:
    """API レスポンス解析テスト"""
    
    @patch('requests.post')
    def test_malformed_json_response(self, mock_post):
        """不正なJSONレスポンス処理テスト"""
        # 不正なJSONレスポンス
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.text = "Invalid JSON response"
        mock_post.return_value = mock_response
        
        result = api_query("https://test-api.example.com", "テスト質問")
        
        # JSONパースエラーでもFalseを返すことを確認
        assert result is False
    
    @patch('requests.post')
    def test_missing_expected_fields(self, mock_post):
        """期待するフィールドが欠けているレスポンステスト"""
        # answerフィールドが欠けているレスポンス
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Success but no answer field"
        }
        mock_post.return_value = mock_response
        
        result = api_query("https://test-api.example.com", "テスト質問")
        
        # 必要なフィールドが欠けていてもTrueを返す（フィールド存在チェックはAPI側の責任）
        assert result is True


if __name__ == "__main__":
    # 直接実行時のテスト
    pytest.main([__file__, "-v"])

