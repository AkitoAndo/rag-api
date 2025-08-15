"""マルチリージョンBedrock クライアント"""
import boto3
import random
from typing import List, Optional
from botocore.exceptions import ClientError
import time

class MultiRegionBedrockClient:
    """複数リージョンでBedrockリクエストを分散"""
    
    def __init__(self, regions: Optional[List[str]] = None):
        self.regions = regions or [
            'us-east-1',
            'us-west-2', 
            'eu-west-1'
        ]
        
        # 各リージョンのクライアントを作成
        self.clients = {}
        self.region_status = {}
        
        for region in self.regions:
            try:
                self.clients[region] = boto3.client('bedrock-runtime', region_name=region)
                self.region_status[region] = 'healthy'
                print(f"✓ Bedrock client initialized for {region}")
            except Exception as e:
                print(f"✗ Failed to initialize {region}: {e}")
                self.region_status[region] = 'unhealthy'
    
    def get_healthy_regions(self) -> List[str]:
        """健全なリージョンのリストを取得"""
        return [region for region, status in self.region_status.items() 
                if status == 'healthy']
    
    def invoke_model_with_fallback(self, model_id: str, body: str, 
                                 max_retries: int = 3) -> dict:
        """複数リージョンでフォールバック付きモデル呼び出し"""
        
        healthy_regions = self.get_healthy_regions()
        if not healthy_regions:
            raise Exception("No healthy regions available")
        
        # リージョンをランダムにシャッフルして負荷分散
        regions_to_try = healthy_regions.copy()
        random.shuffle(regions_to_try)
        
        last_error = None
        
        for region in regions_to_try:
            client = self.clients[region]
            
            for attempt in range(max_retries):
                try:
                    print(f"Attempting {region} (attempt {attempt + 1})")
                    
                    response = client.invoke_model(
                        body=body,
                        modelId=model_id,
                        accept='application/json',
                        contentType='application/json'
                    )
                    
                    print(f"✓ Success in {region}")
                    return response
                    
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    last_error = e
                    
                    if error_code in ['ThrottlingException', 'TooManyRequestsException']:
                        print(f"Rate limit hit in {region}, trying next region...")
                        self.region_status[region] = 'throttled'
                        break  # 次のリージョンを試す
                    
                    elif attempt < max_retries - 1:
                        # 指数バックオフでリトライ
                        delay = (2 ** attempt) + random.uniform(0, 1)
                        print(f"Retrying {region} in {delay:.1f}s...")
                        time.sleep(delay)
                    
                except Exception as e:
                    print(f"Unexpected error in {region}: {e}")
                    last_error = e
                    break
        
        # すべてのリージョンで失敗
        raise last_error or Exception("All regions failed")
    
    def health_check(self):
        """すべてのリージョンのヘルスチェック"""
        print("=== Multi-Region Health Check ===")
        
        for region in self.regions:
            if region not in self.clients:
                print(f"{region}: Not initialized")
                continue
                
            try:
                # 簡単なテスト呼び出し
                bedrock = boto3.client('bedrock', region_name=region)
                
                # モデル一覧取得でテスト
                models = bedrock.list_foundation_models()
                self.region_status[region] = 'healthy'
                
                print(f"✓ {region}: Healthy ({len(models['modelSummaries'])} models)")
                
            except Exception as e:
                self.region_status[region] = 'unhealthy'
                print(f"✗ {region}: {str(e)[:50]}...")
    
    def get_status_summary(self) -> dict:
        """ステータスサマリーを取得"""
        healthy = sum(1 for status in self.region_status.values() if status == 'healthy')
        throttled = sum(1 for status in self.region_status.values() if status == 'throttled')
        unhealthy = sum(1 for status in self.region_status.values() if status == 'unhealthy')
        
        return {
            'total_regions': len(self.regions),
            'healthy': healthy,
            'throttled': throttled, 
            'unhealthy': unhealthy,
            'region_status': self.region_status.copy()
        }

# 使用例
if __name__ == "__main__":
    # マルチリージョンクライアントの初期化
    client = MultiRegionBedrockClient()
    
    # ヘルスチェック実行
    client.health_check()
    
    # ステータス表示
    status = client.get_status_summary()
    print(f"\nStatus: {status['healthy']}/{status['total_regions']} regions healthy")