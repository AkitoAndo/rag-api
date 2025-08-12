# 🎨 フロントエンド実装ガイド

## 📋 **実装に必要な追加情報**

### **🔐 認証設定詳細**

#### **Cognito設定**
```javascript
// AWS Cognito設定例
const cognitoConfig = {
  userPoolId: 'ap-northeast-1_xxxxxxxxx',    // 要確認
  userPoolWebClientId: 'xxxxxxxxxxxxxxxx',   // 要確認
  region: 'ap-northeast-1',                  // 要確認
  authenticationFlowType: 'USER_SRP_AUTH'
};
```

#### **JWT取得・管理**
```javascript
// JWT取得例
import { Auth } from 'aws-amplify';

// ログイン後のトークン取得
const session = await Auth.currentSession();
const jwtToken = session.getIdToken().getJwtToken();

// APIリクエスト時のヘッダー設定
const headers = {
  'Authorization': `Bearer ${jwtToken}`,
  'Content-Type': 'application/json'
};
```

### **🌐 エンドポイント設定**

```javascript
// 環境別API基本URL（要確認）
const API_ENDPOINTS = {
  development: 'https://dev-api.your-domain.com',
  staging: 'https://staging-api.your-domain.com', 
  production: 'https://api.your-domain.com'
};

const API_BASE_URL = API_ENDPOINTS[process.env.NODE_ENV] || API_ENDPOINTS.development;
```

---

## 💻 **実装例・コードサンプル**

### **1. 画像アップロード機能**

#### **React + TypeScript例**
```tsx
import React, { useState } from 'react';

interface ImageUploadProps {
  onUploadSuccess: (result: any) => void;
}

const ImageUpload: React.FC<ImageUploadProps> = ({ onUploadSuccess }) => {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (selectedFile) {
      // ファイルサイズチェック（10MB制限例）
      if (selectedFile.size > 10 * 1024 * 1024) {
        alert('ファイルサイズは10MB以下にしてください');
        return;
      }
      
      // 対応形式チェック
      const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
      if (!allowedTypes.includes(selectedFile.type)) {
        alert('JPEG、PNG、GIF、WebP形式のみ対応しています');
        return;
      }
      
      setFile(selectedFile);
    }
  };

  const uploadImage = async () => {
    if (!file) return;

    setUploading(true);
    setProgress(0);

    try {
      const formData = new FormData();
      formData.append('image', file);
      formData.append('title', document.getElementById('title')?.value || '');
      formData.append('description', document.getElementById('description')?.value || '');
      formData.append('extract_text', 'true');
      formData.append('create_knowledge', 'true');

      const response = await fetch(`${API_BASE_URL}/images`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${await getJwtToken()}` // JWT取得関数
        },
        body: formData,
        // プログレス監視
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          setProgress(percentCompleted);
        }
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'アップロードに失敗しました');
      }

      const result = await response.json();
      onUploadSuccess(result);
      
    } catch (error) {
      console.error('Upload error:', error);
      alert(`アップロードエラー: ${error.message}`);
    } finally {
      setUploading(false);
      setProgress(0);
    }
  };

  return (
    <div className="image-upload">
      <div className="file-input">
        <input
          type="file"
          accept="image/jpeg,image/png,image/gif,image/webp"
          onChange={handleFileSelect}
          disabled={uploading}
        />
      </div>
      
      {file && (
        <div className="file-info">
          <p>選択ファイル: {file.name}</p>
          <p>サイズ: {(file.size / 1024 / 1024).toFixed(2)} MB</p>
        </div>
      )}

      <div className="form-fields">
        <input id="title" placeholder="画像タイトル" required />
        <textarea id="description" placeholder="画像の説明（オプション）" />
      </div>

      <button 
        onClick={uploadImage} 
        disabled={!file || uploading}
        className="upload-button"
      >
        {uploading ? `アップロード中... ${progress}%` : '画像をアップロード'}
      </button>

      {uploading && (
        <div className="progress-bar">
          <div 
            className="progress-fill" 
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </div>
  );
};
```

### **2. 画像ベースクエリ機能**

```tsx
import React, { useState } from 'react';

interface QueryResult {
  answer: string;
  sources: Array<{
    image_id: string;
    title: string;
    relevance_score: number;
    snippet: string;
    thumbnail_url: string;
  }>;
  confidence: number;
}

const ImageQuery: React.FC = () => {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);

  const executeQuery = async () => {
    if (!question.trim()) return;

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/images/query`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${await getJwtToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          question: question,
          search_scope: 'all',
          max_results: 3
        })
      });

      if (!response.ok) {
        const error = await response.json();
        if (response.status === 429) {
          throw new Error('クエリ制限に達しました。しばらく待ってから再試行してください。');
        }
        throw new Error(error.error || 'クエリの実行に失敗しました');
      }

      const result = await response.json();
      setResult(result);
      
    } catch (error) {
      console.error('Query error:', error);
      alert(`エラー: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="image-query">
      <div className="query-input">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="画像に関する質問を入力してください..."
          rows={3}
        />
        <button 
          onClick={executeQuery}
          disabled={loading || !question.trim()}
        >
          {loading ? '検索中...' : '質問する'}
        </button>
      </div>

      {result && (
        <div className="query-result">
          <div className="answer-section">
            <h3>回答</h3>
            <p>{result.answer}</p>
            <div className="confidence">
              信頼度: {(result.confidence * 100).toFixed(1)}%
            </div>
          </div>

          <div className="sources-section">
            <h3>参照画像</h3>
            {result.sources.map((source, index) => (
              <div key={source.image_id} className="source-item">
                <img 
                  src={source.thumbnail_url} 
                  alt={source.title}
                  className="source-thumbnail"
                />
                <div className="source-info">
                  <h4>{source.title}</h4>
                  <p>{source.snippet}</p>
                  <span className="relevance">
                    関連度: {(source.relevance_score * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
```

### **3. エラーハンドリング統一管理**

```typescript
// エラーハンドリングユーティリティ
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public details?: any
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export const handleApiError = (error: ApiError): string => {
  switch (error.status) {
    case 400:
      return 'リクエストが無効です。入力内容を確認してください。';
    case 401:
      return 'ログインが必要です。再度ログインしてください。';
    case 403:
      return 'このアクションを実行する権限がありません。';
    case 404:
      return '指定されたリソースが見つかりません。';
    case 429:
      return 'リクエスト制限に達しました。しばらく待ってから再試行してください。';
    case 500:
      return 'サーバーエラーが発生しました。しばらく待ってから再試行してください。';
    default:
      return error.message || '予期しないエラーが発生しました。';
  }
};

// API呼び出し共通関数
export const apiCall = async (url: string, options: RequestInit = {}) => {
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Authorization': `Bearer ${await getJwtToken()}`,
        'Content-Type': 'application/json',
        ...options.headers
      }
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.error || 'API呼び出しエラー',
        response.status,
        errorData.code,
        errorData
      );
    }

    return response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError('ネットワークエラー', 0);
  }
};
```

---

## 📊 **クォータ管理UI例**

```tsx
const QuotaDisplay: React.FC = () => {
  const [quotaStatus, setQuotaStatus] = useState(null);

  useEffect(() => {
    fetchQuotaStatus();
  }, []);

  const fetchQuotaStatus = async () => {
    try {
      const status = await apiCall('/quota/status');
      setQuotaStatus(status);
    } catch (error) {
      console.error('Failed to fetch quota status:', error);
    }
  };

  if (!quotaStatus) return <div>読み込み中...</div>;

  return (
    <div className="quota-display">
      <h3>使用状況</h3>
      
      <div className="quota-item">
        <label>画像数</label>
        <div className="quota-bar">
          <div 
            className="quota-fill"
            style={{ 
              width: `${quotaStatus.quotas.images.percentage}%`,
              backgroundColor: quotaStatus.quotas.images.percentage > 80 ? '#ff4d4f' : '#52c41a'
            }}
          />
        </div>
        <span>{quotaStatus.quotas.images.current} / {quotaStatus.quotas.images.max}</span>
      </div>

      <div className="quota-item">
        <label>ストレージ</label>
        <div className="quota-bar">
          <div 
            className="quota-fill"
            style={{ width: `${quotaStatus.quotas.storage.percentage}%` }}
          />
        </div>
        <span>{quotaStatus.quotas.storage.current_mb}MB / {quotaStatus.quotas.storage.max_mb}MB</span>
      </div>

      {quotaStatus.quotas.images.percentage > 80 && (
        <div className="quota-warning">
          <p>⚠️ 画像制限の{quotaStatus.quotas.images.percentage}%に達しています</p>
          <button>プランをアップグレード</button>
        </div>
      )}
    </div>
  );
};
```

---

## 🎯 **実装チェックリスト**

### **認証関連**
- [ ] Cognito設定値の確認・取得
- [ ] JWT自動リフレッシュ機能
- [ ] ログアウト時のトークンクリア
- [ ] 認証エラー時の自動リダイレクト

### **ファイル処理**
- [ ] ドラッグ&ドロップ対応
- [ ] ファイルサイズ・形式バリデーション
- [ ] アップロードプログレス表示
- [ ] 画像プレビュー機能

### **エラーハンドリング**
- [ ] 統一エラーメッセージ表示
- [ ] ネットワークエラー対応
- [ ] クォータ制限エラーの適切な案内
- [ ] リトライ機能

### **UX/UI**
- [ ] ローディング状態表示
- [ ] 成功・エラー通知
- [ ] レスポンシブ対応
- [ ] アクセシビリティ対応

---

## 📞 **開発時のサポート**

### **必要な追加情報**
1. **実際のCognito設定値** (userPoolId, clientId等)
2. **本番API Gateway URL**
3. **画像サイズ制限の最終仕様**
4. **サポートする画像形式の詳細**

### **テスト用データ**
- サンプル画像ファイル
- テスト用Cognitoアカウント
- 開発環境エンドポイント

この実装ガイドがあれば、フロントエンドチームは効率的に実装を進められると思います！