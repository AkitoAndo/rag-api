"""Bedrockリクエストのリトライハンドラー"""
import time
import random
from botocore.exceptions import ClientError

def retry_with_backoff(func, max_retries=3, base_delay=1):
    """指数バックオフでリトライ"""
    for attempt in range(max_retries + 1):
        try:
            return func()
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code in ['ThrottlingException', 'TooManyRequestsException']:
                if attempt == max_retries:
                    raise e
                
                # 指数バックオフ + ジッター
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limit hit, retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})")
                time.sleep(delay)
            else:
                raise e
        except Exception as e:
            raise e
    
    return None