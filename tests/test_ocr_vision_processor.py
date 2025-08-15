"""
OCR・Vision処理プロセッサのテストケース
"""
import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch, MagicMock
from io import BytesIO
from PIL import Image
import json

# テスト対象のモジュールをインポート
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from ocr_vision_processor import OCRVisionProcessor


class TestOCRVisionProcessor:
    """OCR・Vision処理プロセッサのテストクラス"""
    
    @pytest.fixture
    def processor(self):
        """プロセッサインスタンス"""
        return OCRVisionProcessor()
    
    @pytest.fixture
    def sample_image_data(self):
        """サンプル画像データを作成"""
        img = Image.new('RGB', (300, 200), color='white')
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG')
        return img_bytes.getvalue()
    
    @pytest.fixture
    def text_image_data(self):
        """テキストを含む画像データを作成"""
        # 実際の画像は省略し、バイトデータとして返す
        return b"fake text image data"

    @mock_aws
    def test_extract_text_success(self, processor, text_image_data):
        """OCRテキスト抽出成功テスト"""
        # Textractクライアントをモック
        with patch.object(processor, 'textract_client') as mock_textract:
            # モックレスポンスを設定
            mock_textract.detect_document_text.return_value = {
                'Blocks': [
                    {
                        'BlockType': 'LINE',
                        'Text': 'これは重要な文書です',
                        'Confidence': 95.5
                    },
                    {
                        'BlockType': 'LINE',
                        'Text': '日本語のテキストです',
                        'Confidence': 88.2
                    },
                    {
                        'BlockType': 'WORD',
                        'Text': '単語レベル',
                        'Confidence': 92.0
                    }  # WORD レベルは除外される
                ]
            }
            
            # OCR処理を実行
            result = processor.extract_text_from_image(text_image_data)
            
            # 結果を検証
            assert result['text'] == 'これは重要な文書です\n日本語のテキストです'
            assert 0.8 < result['confidence'] < 1.0  # 平均信頼度
            assert result['language'] == 'mixed'
            assert result['word_count'] == 4  # 2つの文の単語数
            assert result['character_count'] > 0
    
    @mock_aws
    def test_extract_text_empty(self, processor, sample_image_data):
        """テキストが無い画像のOCRテスト"""
        with patch.object(processor, 'textract_client') as mock_textract:
            # 空の結果をモック
            mock_textract.detect_document_text.return_value = {
                'Blocks': []
            }
            
            result = processor.extract_text_from_image(sample_image_data)
            
            assert result['text'] == ''
            assert result['confidence'] == 0.0
            assert result['word_count'] == 0
    
    @mock_aws
    def test_extract_text_error_handling(self, processor, sample_image_data):
        """OCRエラーハンドリングテスト"""
        with patch.object(processor, 'textract_client') as mock_textract:
            from botocore.exceptions import ClientError
            
            # InvalidImageFormatExceptionをシミュレート
            mock_textract.detect_document_text.side_effect = ClientError(
                error_response={'Error': {'Code': 'InvalidImageFormatException'}},
                operation_name='DetectDocumentText'
            )
            
            result = processor.extract_text_from_image(sample_image_data)
            
            assert result['text'] == ''
            assert result['confidence'] == 0.0
            assert 'error' in result
            assert '画像形式が無効です' in result['error']
    
    @mock_aws
    def test_analyze_image_content_success(self, processor, sample_image_data):
        """画像内容分析成功テスト"""
        with patch.object(processor, 'rekognition_client') as mock_rekognition:
            # ラベル検出のモックレスポンス
            mock_rekognition.detect_labels.return_value = {
                'Labels': [
                    {
                        'Name': 'Document',
                        'Confidence': 95.5,
                        'Parents': [{'Name': 'Paper'}, {'Name': 'Text'}]
                    },
                    {
                        'Name': 'Text',
                        'Confidence': 88.2,
                        'Parents': [{'Name': 'Symbol'}]
                    },
                    {
                        'Name': 'Business Card',
                        'Confidence': 82.1,
                        'Parents': [{'Name': 'Document'}]
                    }
                ]
            }
            
            # テキスト検出のモックレスポンス
            mock_rekognition.detect_text.return_value = {
                'TextDetections': [
                    {
                        'Type': 'LINE',
                        'DetectedText': '会社名: サンプル株式会社',
                        'Confidence': 92.5
                    },
                    {
                        'Type': 'LINE',
                        'DetectedText': 'TEL: 03-1234-5678',
                        'Confidence': 87.3
                    }
                ]
            }
            
            # 画像分析を実行
            result = processor.analyze_image_content(sample_image_data)
            
            # 結果を検証
            assert len(result['labels']) == 3
            assert result['labels'][0]['name'] == 'Document'
            assert result['labels'][0]['confidence'] > 0.9
            
            assert len(result['detected_texts']) == 2
            assert '会社名' in result['detected_texts'][0]['text']
            
            assert 'Document' in result['categories']
            assert 'Paper' in result['categories']
            assert 'Text' in result['categories']
            
            assert '文書や資料の画像のようです' in result['description']
            assert result['confidence'] > 0.8
    
    @mock_aws
    def test_analyze_image_natural_scene(self, processor, sample_image_data):
        """自然風景画像の分析テスト"""
        with patch.object(processor, 'rekognition_client') as mock_rekognition:
            # 風景画像のモックレスポンス
            mock_rekognition.detect_labels.return_value = {
                'Labels': [
                    {
                        'Name': 'Mountain',
                        'Confidence': 98.2,
                        'Parents': [{'Name': 'Nature'}, {'Name': 'Landscape'}]
                    },
                    {
                        'Name': 'Sky',
                        'Confidence': 95.7,
                        'Parents': [{'Name': 'Nature'}]
                    },
                    {
                        'Name': 'Tree',
                        'Confidence': 89.3,
                        'Parents': [{'Name': 'Plant'}]
                    }
                ]
            }
            
            # テキストなし
            mock_rekognition.detect_text.return_value = {
                'TextDetections': []
            }
            
            result = processor.analyze_image_content(sample_image_data)
            
            # 自然風景の説明が生成されることを確認
            assert 'Mountain' in result['description'] or 'Sky' in result['description']
            assert len(result['detected_texts']) == 0
            assert result['confidence'] > 0.9
    
    @mock_aws
    def test_analyze_image_error_handling(self, processor, sample_image_data):
        """Vision分析エラーハンドリングテスト"""
        with patch.object(processor, 'rekognition_client') as mock_rekognition:
            from botocore.exceptions import ClientError
            
            # ImageTooLargeExceptionをシミュレート
            mock_rekognition.detect_labels.side_effect = ClientError(
                error_response={'Error': {'Code': 'ImageTooLargeException'}},
                operation_name='DetectLabels'
            )
            
            result = processor.analyze_image_content(sample_image_data)
            
            assert result['description'] == ''
            assert result['confidence'] == 0.0
            assert 'error' in result
            assert '画像サイズが大きすぎます' in result['error']
    
    @mock_aws
    def test_analyze_document_structure_with_tables(self, processor, sample_image_data):
        """文書構造分析（表あり）テスト"""
        with patch.object(processor, 'textract_client') as mock_textract:
            # 表を含む文書のモックレスポンス
            mock_textract.analyze_document.return_value = {
                'Blocks': [
                    {
                        'BlockType': 'TABLE',
                        'Id': 'table-1',
                        'Confidence': 92.5
                    },
                    {
                        'BlockType': 'CELL',
                        'Id': 'cell-1',
                        'RowIndex': 1,
                        'ColumnIndex': 1,
                        'Relationships': [{'Id': 'table-1'}],
                        'Text': 'ヘッダー1'
                    },
                    {
                        'BlockType': 'CELL',
                        'Id': 'cell-2',
                        'RowIndex': 1,
                        'ColumnIndex': 2,
                        'Relationships': [{'Id': 'table-1'}],
                        'Text': 'ヘッダー2'
                    },
                    {
                        'BlockType': 'CELL',
                        'Id': 'cell-3',
                        'RowIndex': 2,
                        'ColumnIndex': 1,
                        'Relationships': [{'Id': 'table-1'}],
                        'Text': 'データ1'
                    },
                    {
                        'BlockType': 'KEY_VALUE_SET',
                        'Id': 'form-1',
                        'EntityTypes': ['KEY'],
                        'Confidence': 88.2
                    }
                ]
            }
            
            result = processor.analyze_document_structure(sample_image_data)
            
            assert result['document_type'] == 'structured'
            assert len(result['tables']) == 1
            assert result['tables'][0]['row_count'] == 2
            assert result['tables'][0]['column_count'] == 2
            assert len(result['form_fields']) == 1
            assert result['confidence'] == 0.8
    
    @mock_aws
    def test_analyze_document_structure_unstructured(self, processor, sample_image_data):
        """非構造化文書の分析テスト"""
        with patch.object(processor, 'textract_client') as mock_textract:
            # 構造のない文書のモックレスポンス
            mock_textract.analyze_document.return_value = {
                'Blocks': [
                    {
                        'BlockType': 'LINE',
                        'Id': 'line-1',
                        'Text': 'これは通常のテキストです',
                        'Confidence': 89.5
                    }
                ]
            }
            
            result = processor.analyze_document_structure(sample_image_data)
            
            assert result['document_type'] == 'unstructured'
            assert len(result['tables']) == 0
            assert len(result['form_fields']) == 0
    
    def test_get_comprehensive_analysis_integration(self, processor, sample_image_data):
        """統合分析テスト"""
        with patch.object(processor, 'extract_text_from_image') as mock_ocr, \
             patch.object(processor, 'analyze_image_content') as mock_vision, \
             patch.object(processor, 'analyze_document_structure') as mock_structure:
            
            # 各分析結果をモック
            mock_ocr.return_value = {
                'text': 'サンプルテキスト',
                'confidence': 0.92
            }
            
            mock_vision.return_value = {
                'description': 'ビジネス文書の画像',
                'confidence': 0.88,
                'labels': [{'name': 'Document', 'confidence': 0.95}]
            }
            
            mock_structure.return_value = {
                'document_type': 'structured',
                'confidence': 0.85,
                'tables': [{'row_count': 3, 'column_count': 2}]
            }
            
            # 統合分析を実行
            result = processor.get_comprehensive_analysis(sample_image_data)
            
            # 結果を検証
            assert 'ocr' in result
            assert 'vision' in result
            assert 'structure' in result
            assert 'summary' in result
            
            summary = result['summary']
            assert summary['has_text'] is True
            assert summary['has_objects'] is True
            assert summary['has_structure'] is True
            assert 0.8 < summary['overall_confidence'] < 1.0
            
            assert result['analysis_version'] == '1.0'
    
    def test_confidence_calculation(self, processor, sample_image_data):
        """信頼度計算のテスト"""
        with patch.object(processor, 'textract_client') as mock_textract:
            # 異なる信頼度のテキストブロック
            mock_textract.detect_document_text.return_value = {
                'Blocks': [
                    {
                        'BlockType': 'LINE',
                        'Text': 'High confidence text',
                        'Confidence': 95.0
                    },
                    {
                        'BlockType': 'LINE',
                        'Text': 'Medium confidence text',
                        'Confidence': 80.0
                    },
                    {
                        'BlockType': 'LINE',
                        'Text': 'Low confidence text',
                        'Confidence': 60.0
                    }
                ]
            }
            
            result = processor.extract_text_from_image(sample_image_data)
            
            # 平均信頼度が正しく計算されることを確認
            expected_confidence = (95.0 + 80.0 + 60.0) / 3 / 100  # 0-1範囲に正規化
            assert abs(result['confidence'] - expected_confidence) < 0.01
    
    def test_japanese_text_handling(self, processor, sample_image_data):
        """日本語テキスト処理のテスト"""
        with patch.object(processor, 'textract_client') as mock_textract:
            # 日本語テキストを含むモックレスポンス
            mock_textract.detect_document_text.return_value = {
                'Blocks': [
                    {
                        'BlockType': 'LINE',
                        'Text': 'これは日本語のテキストです',
                        'Confidence': 90.0
                    },
                    {
                        'BlockType': 'LINE',
                        'Text': '株式会社サンプル',
                        'Confidence': 85.5
                    }
                ]
            }
            
            result = processor.extract_text_from_image(sample_image_data)
            
            # 日本語文字が正しく処理されることを確認
            assert 'これは日本語のテキストです' in result['text']
            assert '株式会社サンプル' in result['text']
            assert result['character_count'] > 0
            assert result['word_count'] > 0
    
    def test_error_recovery(self, processor, sample_image_data):
        """エラー回復のテスト"""
        # 統合分析でOCRは失敗するがVisionは成功する場合
        with patch.object(processor, 'extract_text_from_image') as mock_ocr, \
             patch.object(processor, 'analyze_image_content') as mock_vision, \
             patch.object(processor, 'analyze_document_structure') as mock_structure:
            
            # OCRは失敗
            mock_ocr.side_effect = Exception("OCR processing failed")
            
            # Visionは成功
            mock_vision.return_value = {
                'description': '画像の説明',
                'confidence': 0.85,
                'labels': []
            }
            
            # 構造分析も失敗
            mock_structure.side_effect = Exception("Structure analysis failed")
            
            result = processor.get_comprehensive_analysis(sample_image_data)
            
            # エラーがあっても結果が返されることを確認
            assert 'error' in result
            assert result['summary']['overall_confidence'] == 0.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])