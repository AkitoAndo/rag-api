"""
OCR・Vision分析処理クラス
Amazon TextractとRekognitionを使用
"""
import boto3
from typing import Dict, Any
from botocore.exceptions import ClientError


class OCRVisionProcessor:
    """OCR・Vision分析処理クラス"""
    
    def __init__(self):
        self.textract_client = boto3.client('textract')
        self.rekognition_client = boto3.client('rekognition')
    
    def extract_text_from_image(self, image_data: bytes) -> Dict[str, Any]:
        """Amazon Textractを使用してテキストを抽出"""
        try:
            # Textract呼び出し
            response = self.textract_client.detect_document_text(
                Document={
                    'Bytes': image_data
                }
            )
            
            # テキストブロックからテキストを結合
            extracted_text = ""
            confidence_scores = []
            
            for block in response.get('Blocks', []):
                if block['BlockType'] == 'LINE':
                    text = block.get('Text', '')
                    confidence = block.get('Confidence', 0.0)
                    
                    if text.strip():
                        extracted_text += text + "\n"
                        confidence_scores.append(confidence)
            
            # 平均信頼度を計算
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            
            return {
                'text': extracted_text.strip(),
                'confidence': avg_confidence / 100.0,  # 0-1の範囲に正規化
                'language': 'mixed',  # Textractは言語検出機能が限定的
                'word_count': len(extracted_text.split()),
                'character_count': len(extracted_text)
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'InvalidImageFormatException':
                return {
                    'text': '',
                    'confidence': 0.0,
                    'error': '画像形式が無効です'
                }
            elif error_code == 'ImageTooLargeException':
                return {
                    'text': '',
                    'confidence': 0.0,
                    'error': '画像サイズが大きすぎます'
                }
            else:
                print(f"Textract error: {error_code} - {str(e)}")
                return {
                    'text': '',
                    'confidence': 0.0,
                    'error': f'OCR処理エラー: {error_code}'
                }
                
        except Exception as e:
            print(f"OCR processing error: {str(e)}")
            return {
                'text': '',
                'confidence': 0.0,
                'error': f'OCR処理中にエラーが発生しました: {str(e)}'
            }
    
    def analyze_image_content(self, image_data: bytes) -> Dict[str, Any]:
        """Amazon Rekognitionを使用して画像内容を分析"""
        try:
            # ラベル検出
            labels_response = self.rekognition_client.detect_labels(
                Image={
                    'Bytes': image_data
                },
                MaxLabels=10,
                MinConfidence=70.0
            )
            
            # テキスト検出（Rekognitionでもテキスト検出可能）
            try:
                text_response = self.rekognition_client.detect_text(
                    Image={
                        'Bytes': image_data
                    }
                )
            except Exception:
                text_response = {'TextDetections': []}
            
            # ラベル情報を処理
            labels = []
            for label in labels_response.get('Labels', []):
                labels.append({
                    'name': label['Name'],
                    'confidence': label['Confidence'] / 100.0,
                    'categories': [parent['Name'] for parent in label.get('Parents', [])]
                })
            
            # 検出されたテキスト（Rekognition版）
            detected_texts = []
            for text_detection in text_response.get('TextDetections', []):
                if text_detection['Type'] == 'LINE':
                    detected_texts.append({
                        'text': text_detection['DetectedText'],
                        'confidence': text_detection['Confidence'] / 100.0
                    })
            
            # 画像の説明文を生成
            description_parts = []
            
            # 主要なオブジェクト・概念を抽出
            high_confidence_labels = [label for label in labels if label['confidence'] > 0.8]
            if high_confidence_labels:
                objects = [label['name'] for label in high_confidence_labels[:5]]
                if len(objects) == 1:
                    description_parts.append(f"{objects[0]}が写っています")
                elif len(objects) == 2:
                    description_parts.append(f"{objects[0]}と{objects[1]}が写っています")
                else:
                    description_parts.append(f"{', '.join(objects[:-1])}、{objects[-1]}などが写っています")
            
            # テキストが検出された場合
            if detected_texts:
                description_parts.append("画像内にテキストが含まれています")
            
            # カテゴリ情報を追加
            categories = set()
            for label in labels:
                categories.update(label['categories'])
            
            if 'Document' in categories:
                description_parts.append("文書や資料の画像のようです")
            elif 'Chart' in categories or 'Graph' in categories:
                description_parts.append("図表やグラフの画像のようです")
            elif 'Screenshot' in categories:
                description_parts.append("スクリーンショットの画像のようです")
            
            description = "。".join(description_parts) if description_parts else "画像の内容を分析しました"
            
            # 全体の信頼度を計算
            if labels:
                overall_confidence = sum(label['confidence'] for label in labels) / len(labels)
            else:
                overall_confidence = 0.5  # デフォルト値
            
            return {
                'description': description,
                'confidence': overall_confidence,
                'labels': labels,
                'detected_texts': detected_texts,
                'categories': list(categories),
                'analysis_type': 'rekognition'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'InvalidImageFormatException':
                return {
                    'description': '',
                    'confidence': 0.0,
                    'error': '画像形式が無効です'
                }
            elif error_code == 'ImageTooLargeException':
                return {
                    'description': '',
                    'confidence': 0.0,
                    'error': '画像サイズが大きすぎます'
                }
            else:
                print(f"Rekognition error: {error_code} - {str(e)}")
                return {
                    'description': '',
                    'confidence': 0.0,
                    'error': f'Vision分析エラー: {error_code}'
                }
                
        except Exception as e:
            print(f"Vision analysis error: {str(e)}")
            return {
                'description': '',
                'confidence': 0.0,
                'error': f'Vision分析中にエラーが発生しました: {str(e)}'
            }
    
    def analyze_document_structure(self, image_data: bytes) -> Dict[str, Any]:
        """Textractを使用して文書構造を分析（表、フォームなど）"""
        try:
            # 表とフォームの分析
            response = self.textract_client.analyze_document(
                Document={
                    'Bytes': image_data
                },
                FeatureTypes=['TABLES', 'FORMS']
            )
            
            # 表の抽出
            tables = []
            table_blocks = [block for block in response.get('Blocks', []) if block['BlockType'] == 'TABLE']
            
            for table_block in table_blocks:
                table_info = {
                    'id': table_block['Id'],
                    'confidence': table_block.get('Confidence', 0.0) / 100.0,
                    'row_count': 0,
                    'column_count': 0
                }
                
                # セル数から行・列数を推定
                cell_blocks = [block for block in response.get('Blocks', []) 
                              if block['BlockType'] == 'CELL' and 
                              any(rel['Id'] == table_block['Id'] for rel in block.get('Relationships', []))]
                
                if cell_blocks:
                    max_row = max(cell.get('RowIndex', 0) for cell in cell_blocks)
                    max_col = max(cell.get('ColumnIndex', 0) for cell in cell_blocks)
                    table_info['row_count'] = max_row
                    table_info['column_count'] = max_col
                
                tables.append(table_info)
            
            # フォームフィールドの抽出
            form_fields = []
            key_blocks = [block for block in response.get('Blocks', []) if block['BlockType'] == 'KEY_VALUE_SET']
            
            for key_block in key_blocks:
                if key_block.get('EntityTypes', [None])[0] == 'KEY':
                    field_info = {
                        'key': '',
                        'value': '',
                        'confidence': key_block.get('Confidence', 0.0) / 100.0
                    }
                    
                    # キーと値のテキストを抽出（簡略化）
                    form_fields.append(field_info)
            
            return {
                'document_type': 'structured' if tables or form_fields else 'unstructured',
                'tables': tables,
                'form_fields': form_fields,
                'confidence': 0.8,  # 構造分析の全体信頼度
                'analysis_type': 'textract_structure'
            }
            
        except Exception as e:
            print(f"Document structure analysis error: {str(e)}")
            return {
                'document_type': 'unknown',
                'tables': [],
                'form_fields': [],
                'confidence': 0.0,
                'error': str(e)
            }
    
    def get_comprehensive_analysis(self, image_data: bytes) -> Dict[str, Any]:
        """OCR・Vision・構造分析の統合分析"""
        try:
            # 各分析を並行実行
            ocr_result = self.extract_text_from_image(image_data)
            vision_result = self.analyze_image_content(image_data)
            structure_result = self.analyze_document_structure(image_data)
            
            # 統合結果を作成
            return {
                'ocr': ocr_result,
                'vision': vision_result,
                'structure': structure_result,
                'summary': {
                    'has_text': bool(ocr_result.get('text', '').strip()),
                    'has_objects': len(vision_result.get('labels', [])) > 0,
                    'has_structure': structure_result.get('document_type') == 'structured',
                    'overall_confidence': (
                        ocr_result.get('confidence', 0) + 
                        vision_result.get('confidence', 0) + 
                        structure_result.get('confidence', 0)
                    ) / 3.0
                },
                'processing_time': None,  # 実装時に追加
                'analysis_version': '1.0'
            }
            
        except Exception as e:
            print(f"Comprehensive analysis error: {str(e)}")
            return {
                'ocr': {'text': '', 'confidence': 0.0, 'error': str(e)},
                'vision': {'description': '', 'confidence': 0.0, 'error': str(e)},
                'structure': {'document_type': 'unknown', 'confidence': 0.0, 'error': str(e)},
                'summary': {
                    'has_text': False,
                    'has_objects': False,
                    'has_structure': False,
                    'overall_confidence': 0.0
                },
                'error': f'包括分析エラー: {str(e)}'
            }