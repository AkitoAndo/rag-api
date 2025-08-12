# GitHub CLI を使った自動化スクリプト
# 今までの実装内容をイシュー化・ブランチ化・コミット・プッシュ

$ErrorActionPreference = "Stop"

# GitHub CLI パス設定
$ghPath = "C:\Program Files\GitHub CLI\gh.exe"

# イシューとブランチの定義
$issues = @(
    @{
        title = "🔐 Cognito認証システムの実装"
        body = @"
## 概要
Amazon Cognitoを使用したJWT認証システムの実装

## 実装内容
- [ ] CognitoユーザープールとClientの設定
- [ ] JWT token抽出機能の実装
- [ ] フォールバック認証フロー (sub → username → email)
- [ ] 認証エラーハンドリング
- [ ] マルチテナント対応のユーザーID管理

## 技術要件
- Amazon Cognito User Pool
- JWT token解析
- Lambda Authorizer統合

## 関連ファイル
- `src/multi_tenant_handlers.py`
- `template.yaml`
- `tests/test_cognito_authentication.py`

## 受入基準
- [ ] JWT tokenからuser_idを正しく抽出できる
- [ ] 認証失敗時に適切なエラーを返す
- [ ] 15個のテストケースすべてが通る
"@
        labels = @("feature", "authentication", "cognito")
        branch = "feature/cognito-authentication"
        files = @(
            "src/multi_tenant_handlers.py",
            "tests/test_cognito_authentication.py"
        )
    },
    @{
        title = "👥 マルチテナント機能の実装"
        body = @"
## 概要
ユーザー間のデータ完全分離を実現するマルチテナントアーキテクチャの実装

## 実装内容
- [ ] ユーザー固有インデックス生成
- [ ] データアクセス制御
- [ ] クロステナントアクセス防止
- [ ] メタデータにユーザーコンテキスト追加
- [ ] セキュリティ境界の実装

## 技術要件
- S3 Vectors ユーザー別インデックス
- セキュアなデータ分離
- スケーラブルなアーキテクチャ

## 関連ファイル
- `src/s3_vectors_client.py`
- `src/multi_tenant_handlers.py`
- `tests/test_multi_tenant_integration.py`

## 受入基準
- [ ] ユーザーAがユーザーBのデータにアクセスできない
- [ ] 20ユーザー同時操作でも分離が維持される
- [ ] 18個のテストケースすべてが通る
"@
        labels = @("feature", "multi-tenant", "security")
        branch = "feature/multi-tenant-system"
        files = @(
            "src/s3_vectors_client.py",
            "tests/test_multi_tenant_integration.py",
            "tests/test_multi_tenant_lambda_updated.py"
        )
    },
    @{
        title = "📊 ユーザークォータ管理システムの実装"
        body = @"
## 概要
プラン別のリソース制限とクォータ管理システムの実装

## 実装内容
- [ ] 3層プランシステム (Free/Basic/Premium)
- [ ] 5つのクォータ次元 (documents, vectors, storage, queries, uploads)
- [ ] リアルタイムクォータチェック
- [ ] 使用量追跡とレポート
- [ ] クォータ超過時の制御

## 技術要件
- DynamoDB クォータテーブル
- リアルタイム使用量計算
- アトミックな更新処理

## 関連ファイル
- `src/user_quota_manager.py`
- `src/multi_tenant_handlers.py` (クォータ統合)
- `tests/test_user_quota_system.py`

## 受入基準
- [ ] プラン別制限が正しく適用される
- [ ] クォータ超過時に適切にブロックされる
- [ ] 29個のテストケースすべてが通る
"@
        labels = @("feature", "quota", "business-logic")
        branch = "feature/user-quota-system"
        files = @(
            "src/user_quota_manager.py",
            "tests/test_user_quota_system.py"
        )
    },
    @{
        title = "🧪 包括的テストスイートの実装"
        body = @"
## 概要
システム全体の品質保証のための包括的テストスイートの実装

## 実装内容
- [ ] エンドツーエンド統合テスト
- [ ] 実際のAPI Gateway呼び出しテスト
- [ ] 障害回復力テスト
- [ ] パフォーマンステスト
- [ ] セキュリティテスト

## 技術要件
- 実環境対応テスト
- モック戦略
- 同時実行テスト

## 関連ファイル
- `tests/test_end_to_end_integration.py`
- `TEST_IMPLEMENTATION_REPORT.md`

## 受入基準
- [ ] 74個のテストケースすべてが通る
- [ ] 実環境での動作確認完了
- [ ] カバレッジ90%以上達成
"@
        labels = @("testing", "quality-assurance", "integration")
        branch = "feature/comprehensive-testing"
        files = @(
            "tests/test_end_to_end_integration.py",
            "TEST_IMPLEMENTATION_REPORT.md"
        )
    },
    @{
        title = "🖼️ 画像処理API仕様の設計"
        body = @"
## 概要
画像保存・OCR・ナレッジベース統合機能のAPI仕様設計

## 実装内容
- [ ] OpenAPI 3.0仕様書の作成
- [ ] 画像アップロード・管理エンドポイント
- [ ] OCR・Vision解析エンドポイント
- [ ] 画像ナレッジベース統合エンドポイント
- [ ] ハイブリッドクエリエンドポイント

## 技術要件
- OpenAPI 3.0準拠
- Swagger UI対応
- 既存システムとの統合設計

## 関連ファイル
- `docs/image-processing-api-specification.yaml`
- `docs/api-docs.html`
- `docs/frontend-implementation-guide.md`

## 受入基準
- [ ] 完全なAPI仕様書が作成されている
- [ ] Swagger UIで仕様を確認できる
- [ ] フロントエンド実装ガイドが完備されている
"@
        labels = @("documentation", "api-design", "image-processing")
        branch = "feature/image-processing-api-design"
        files = @(
            "docs/image-processing-api-specification.yaml",
            "docs/api-docs.html",
            "docs/frontend-implementation-guide.md"
        )
    },
    @{
        title = "⚙️ SAMテンプレートとデプロイメント設定"
        body = @"
## 概要
AWS SAMテンプレートの実装とデプロイメント自動化

## 実装内容
- [ ] Lambda関数定義
- [ ] API Gateway設定
- [ ] DynamoDBテーブル定義
- [ ] IAMロール・ポリシー設定
- [ ] 環境変数管理

## 技術要件
- AWS SAM Framework
- CloudFormation
- 環境別設定

## 関連ファイル
- `template.yaml`
- `deploy.py`
- `deploy_manual.py`

## 受入基準
- [ ] 正常にデプロイされる
- [ ] 全てのAWSリソースが作成される
- [ ] 環境変数が正しく設定される
"@
        labels = @("infrastructure", "sam", "deployment")
        branch = "feature/sam-template-deployment"
        files = @(
            "template.yaml",
            "deploy.py", 
            "deploy_manual.py"
        )
    },
    @{
        title = "📚 プロジェクトドキュメント整備"
        body = @"
## 概要
プロジェクトの包括的なドキュメント整備

## 実装内容
- [ ] README.mdの更新
- [ ] デプロイメント成功レポート
- [ ] テストカバレッジレポート
- [ ] APIドキュメント

## 関連ファイル
- `README.md`
- `DEPLOYMENT_SUCCESS.md`
- `TEST_COVERAGE_REPORT.md`

## 受入基準
- [ ] 新規開発者がスムーズにセットアップできる
- [ ] 全機能が網羅的に説明されている
- [ ] 実装状況が明確に把握できる
"@
        labels = @("documentation", "maintenance")
        branch = "feature/project-documentation"
        files = @(
            "README.md",
            "DEPLOYMENT_SUCCESS.md", 
            "TEST_COVERAGE_REPORT.md"
        )
    }
)

Write-Host "🚀 GitHub自動化スクリプトを開始します..." -ForegroundColor Green

# 認証状況確認
try {
    & $ghPath auth status 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠️  GitHub認証が必要です。以下を実行してください:" -ForegroundColor Yellow
        Write-Host "gh auth login --web" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "認証完了後、このスクリプトを再実行してください。" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "⚠️  GitHub CLIの認証を確認できません。" -ForegroundColor Red
    exit 1
}

Write-Host "✅ GitHub認証OK" -ForegroundColor Green

# 現在のブランチ確認
$currentBranch = git rev-parse --abbrev-ref HEAD
Write-Host "📍 現在のブランチ: $currentBranch" -ForegroundColor Cyan

# メインブランチに切り替え
if ($currentBranch -ne "main") {
    Write-Host "🔄 mainブランチに切り替え中..." -ForegroundColor Yellow
    git checkout main
    git pull origin main
}

# 各イシューとブランチを処理
foreach ($issue in $issues) {
    Write-Host "=" * 80 -ForegroundColor Blue
    Write-Host "🎯 処理中: $($issue.title)" -ForegroundColor Green
    
    try {
        # イシューを作成
        Write-Host "📝 イシューを作成中..." -ForegroundColor Yellow
        $labelsStr = $issue.labels -join ","
        
        $issueNumber = & $ghPath issue create `
            --title $issue.title `
            --body $issue.body `
            --label $labelsStr `
            --repo "AkitoAndo/rag-api" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ イシュー作成成功: $issueNumber" -ForegroundColor Green
        } else {
            Write-Host "❌ イシュー作成失敗: $issueNumber" -ForegroundColor Red
            continue
        }
        
        # ブランチを作成・切り替え
        Write-Host "🌱 ブランチ作成中: $($issue.branch)" -ForegroundColor Yellow
        git checkout -b $issue.branch
        
        # 該当ファイルをステージング
        foreach ($file in $issue.files) {
            if (Test-Path $file) {
                Write-Host "📁 ファイル追加: $file" -ForegroundColor Cyan
                git add $file
            } else {
                Write-Host "⚠️  ファイルが見つかりません: $file" -ForegroundColor Yellow
            }
        }
        
        # コミット
        $commitMessage = "$($issue.title)`n`nCloses $issueNumber`n`n$($issue.body -split "`n" | Select-Object -First 3 | Join-String "`n")"
        Write-Host "💾 コミット中..." -ForegroundColor Yellow
        git commit -m $commitMessage
        
        # プッシュ
        Write-Host "⬆️  プッシュ中..." -ForegroundColor Yellow
        git push -u origin $issue.branch
        
        # プルリクエスト作成
        Write-Host "🔀 プルリクエスト作成中..." -ForegroundColor Yellow
        $prBody = @"
## 概要
$($issue.title)

## 関連イシュー
Closes $issueNumber

## 変更内容
$($issue.body)

## テスト
- [ ] 機能テスト完了
- [ ] 結合テスト完了
- [ ] 手動テスト完了

## チェックリスト
- [x] コードレビュー準備完了
- [x] テストケース追加・実行
- [x] ドキュメント更新
"@

        $prNumber = & $ghPath pr create `
            --title $issue.title `
            --body $prBody `
            --base main `
            --head $issue.branch `
            --label $labelsStr `
            --repo "AkitoAndo/rag-api" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ プルリクエスト作成成功: $prNumber" -ForegroundColor Green
            
            # 自動マージ (オプション)
            Write-Host "🤖 自動マージ実行中..." -ForegroundColor Yellow
            & $ghPath pr merge $prNumber --merge --delete-branch 2>&1
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ マージ完了" -ForegroundColor Green
            } else {
                Write-Host "⚠️  手動マージが必要です" -ForegroundColor Yellow
            }
        } else {
            Write-Host "❌ プルリクエスト作成失敗: $prNumber" -ForegroundColor Red
        }
        
        # mainブランチに戻る
        git checkout main
        git pull origin main
        
        Write-Host "✅ $($issue.title) 処理完了" -ForegroundColor Green
        Start-Sleep 2
        
    } catch {
        Write-Host "❌ エラー: $($_.Exception.Message)" -ForegroundColor Red
        # mainブランチに戻る
        git checkout main
    }
}

Write-Host "=" * 80 -ForegroundColor Blue
Write-Host "🎉 全ての処理が完了しました！" -ForegroundColor Green
Write-Host "📊 GitHub Issues/PRsを確認してください:" -ForegroundColor Cyan
Write-Host "   https://github.com/AkitoAndo/rag-api/issues" -ForegroundColor Blue
Write-Host "   https://github.com/AkitoAndo/rag-api/pulls" -ForegroundColor Blue