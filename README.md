# S3 Vectors RAG API

Amazon S3 Vectorsを使用したサーバーレスRAGシステムのサンプル実装です。

## 概要

このプロジェクトは、AWS Lambda + API Gateway + Amazon Bedrockを使用して構築された、S3 Vectorsベースの検索拡張生成（RAG）システムです。

### 主な機能

- **ドキュメント追加**: テキストをチャンクに分割し、ベクトル化してS3 Vectorsに保存
- **質問応答**: ユーザーの質問に対してベクトル検索を行い、関連ドキュメントを基にしたRAG回答を生成

## アーキテクチャ

- **Amazon S3 Vectors**: ベクトルの保存とクエリ
- **Amazon Bedrock**: 
  - Amazon Titan Embed v2 (埋め込み生成)
  - Claude Sonnet 4 (回答生成)
- **AWS Lambda**: API処理とRAGロジック
- **Amazon API Gateway**: RESTful API エンドポイント

## セットアップ

### 前提条件

- AWS CLI がインストール・設定済み
- AWS SAM CLI がインストール済み
- Python 3.11 以上

### 1. S3 Vectorsの準備

1. AWSコンソールでS3 Vectorsのプレビューが有効なリージョン（us-east-1など）に移動
2. S3 コンソールから「ベクトルバケット」を作成
3. ベクトルインデックスを作成:
   - ディメンション: 1024 (Amazon Titan Embed v2用)
   - 距離メトリック: Cosine
   - フィルタ対象外メタデータ: `text`

### 2. アプリケーションのデプロイ

```bash
# リポジトリをクローン
git clone <this-repository>
cd rag-api

# デプロイスクリプトを実行
chmod +x deploy.sh
./deploy.sh
```

または、手動でデプロイ:

```bash
# SAMアプリケーションをビルド
sam build

# デプロイ
sam deploy --guided
```

## API使用方法

### ドキュメント追加

```bash
curl -X POST "https://your-api-gateway-url/add-document" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "ここにドキュメントのテキストを入力",
    "title": "ドキュメントのタイトル"
  }'
```

### 質問応答

```bash
curl -X POST "https://your-api-gateway-url/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "あなたの質問をここに入力"
  }'
```

## プロジェクト構造

```
rag-api/
├── src/
│   ├── lambda_handler.py       # Lambda関数のハンドラー
│   ├── s3_vectors_client.py    # S3 Vectorsクライアント
│   └── requirements.txt        # Python依存関係
├── template.yaml               # SAMテンプレート
├── deploy.sh                   # デプロイスクリプト
└── README.md                   # このファイル
```

## 設定

環境変数で以下の設定が可能です:

- `VECTOR_BUCKET_NAME`: S3 Vectorsバケット名
- `VECTOR_INDEX_NAME`: S3 Vectorsインデックス名

## 料金

S3 Vectorsは以下の料金体系です:

- ベクトルストレージ: 保存されたベクトルのデータ量に基づく
- API リクエスト: PUT/QUERYリクエスト数に基づく

従来のマネージドベクトルデータベースと比較して大幅にコストを削減できます。

## 制限事項

- S3 Vectorsは現在プレビュー段階です
- 利用可能リージョンが限定されています
- CloudFormationでの作成はまだサポートされていません

## テスト

### テスト結果 ✅

統合テストの実装と実行が正常に完了しました。

- **統合テスト**: 9個のテスト ✅
- **ユニットテスト**: 11個のテスト ✅ 
- **合計**: 20個のテスト ✅
- **コードカバレッジ**: 100% ✅

### テスト実行方法

```bash
# 全テスト実行
python -m pytest tests/ -v

# 統合テストのみ実行
python -m pytest tests/integration/ -v

# カバレッジ付きで実行
python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

### 統合テスト内容

1. **S3VectorsClient統合テスト**
   - ドキュメント追加から検索まで全体フロー
   - 複数ドキュメントの処理
   - エラーハンドリング
   - 埋め込みモデルとの統合

2. **Lambda関数統合テスト**
   - クエリ処理の全体フロー
   - ドキュメント追加処理の全体フロー
   - エラー伝播とレスポンス
   - XML生成処理
   - 環境変数の検証

### テストファイル構成

```
tests/
├── integration/              # 統合テスト
│   ├── test_s3_vectors_integration.py
│   └── test_lambda_integration.py
├── test_lambda_handler.py    # ユニットテスト
├── test_s3_vectors_client.py # ユニットテスト
└── conftest.py              # テストフィクスチャ
```

## ライセンス

MIT License

## 参考リンク

- [Amazon S3 Vectors Documentation](https://docs.aws.amazon.com/s3/latest/userguide/s3-vector-storage.html)
- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)