"""
File processing utilities for NORTH AI
Handles various file types and converts them for AI consumption
"""

import base64
import io
import logging
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import mimetypes

# Optional libraries - will gracefully degrade if not available
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    logging.warning("PyPDF2 not installed - PDF text extraction disabled")

try:
    import pandas as pd
    EXCEL_SUPPORT = True
except ImportError:
    EXCEL_SUPPORT = False
    logging.warning("pandas not installed - Excel/CSV support disabled")

try:
    from PIL import Image
    IMAGE_SUPPORT = True
except ImportError:
    IMAGE_SUPPORT = False
    logging.warning("PIL not installed - Image optimization disabled")

logger = logging.getLogger(__name__)


class FileProcessor:
    """Processes various file types for AI consumption"""
    
    # Supported MIME types
    SUPPORTED_IMAGE_TYPES = [
        'image/jpeg', 'image/jpg', 'image/png', 
        'image/gif', 'image/webp', 'image/bmp'
    ]
    
    SUPPORTED_TEXT_TYPES = [
        'text/plain', 'text/markdown', 'text/x-markdown',
        'text/html', 'text/css', 'text/javascript',
        'application/json', 'application/xml', 'text/xml',
        'text/csv', 'text/x-python', 'text/x-yaml'
    ]
    
    SUPPORTED_DOCUMENT_TYPES = [
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # xlsx
        'application/vnd.ms-excel',  # xls
    ]
    
    MAX_IMAGE_SIZE = (1920, 1080)  # Resize large images to this max
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    @classmethod
    def process_file(cls, file_content: bytes, filename: str, mime_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a file and return it in a format suitable for AI consumption
        
        Returns:
            Dict with:
                - type: 'image', 'text', or 'document'
                - content: processed content (base64 for images, text for others)
                - metadata: file information
                - error: error message if processing failed
        """
        if not mime_type:
            mime_type, _ = mimetypes.guess_type(filename)
            
        result = {
            'filename': filename,
            'mime_type': mime_type,
            'size': len(file_content)
        }
        
        # Check file size
        if len(file_content) > cls.MAX_FILE_SIZE:
            result['error'] = f"File too large: {len(file_content) / 1024 / 1024:.1f}MB (max {cls.MAX_FILE_SIZE / 1024 / 1024}MB)"
            return result
            
        try:
            # Process based on type
            if mime_type in cls.SUPPORTED_IMAGE_TYPES:
                return cls._process_image(file_content, filename, mime_type)
            elif mime_type in cls.SUPPORTED_TEXT_TYPES or filename.endswith(('.md', '.txt', '.json', '.yaml', '.yml')):
                return cls._process_text(file_content, filename, mime_type)
            elif mime_type == 'application/pdf':
                return cls._process_pdf(file_content, filename)
            elif mime_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'] or filename.endswith(('.xlsx', '.xls', '.csv')):
                return cls._process_spreadsheet(file_content, filename, mime_type)
            else:
                result['error'] = f"Unsupported file type: {mime_type}"
                return result
                
        except Exception as e:
            logger.error(f"Error processing file {filename}: {str(e)}")
            result['error'] = f"Processing error: {str(e)}"
            return result
    
    @classmethod
    def _process_image(cls, content: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
        """Process image files - resize if needed and convert to base64"""
        result = {
            'type': 'image',
            'filename': filename,
            'mime_type': mime_type
        }
        
        # Optionally resize large images
        if IMAGE_SUPPORT:
            try:
                img = Image.open(io.BytesIO(content))
                
                # Store original dimensions
                result['original_size'] = img.size
                
                # Resize if too large
                if img.size[0] > cls.MAX_IMAGE_SIZE[0] or img.size[1] > cls.MAX_IMAGE_SIZE[1]:
                    img.thumbnail(cls.MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
                    
                    # Convert back to bytes
                    buffer = io.BytesIO()
                    format = 'PNG' if mime_type == 'image/png' else 'JPEG'
                    img.save(buffer, format=format, optimize=True)
                    content = buffer.getvalue()
                    result['resized'] = True
                    result['new_size'] = img.size
                    
            except Exception as e:
                logger.warning(f"Could not optimize image: {e}")
        
        # Convert to base64
        base64_content = base64.b64encode(content).decode('utf-8')
        result['content'] = f"data:{mime_type};base64,{base64_content}"
        
        return result
    
    @classmethod
    def _process_text(cls, content: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
        """Process text files - decode and return as string"""
        result = {
            'type': 'text',
            'filename': filename,
            'mime_type': mime_type
        }
        
        try:
            # Try UTF-8 first, then fallback to other encodings
            for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
                try:
                    text = content.decode(encoding)
                    result['content'] = text
                    result['encoding'] = encoding
                    result['lines'] = len(text.splitlines())
                    break
                except UnicodeDecodeError:
                    continue
            else:
                result['error'] = "Could not decode text file"
                
        except Exception as e:
            result['error'] = f"Text processing error: {str(e)}"
            
        return result
    
    @classmethod
    def _process_pdf(cls, content: bytes, filename: str) -> Dict[str, Any]:
        """Extract text from PDF files"""
        result = {
            'type': 'document',
            'subtype': 'pdf',
            'filename': filename,
            'mime_type': 'application/pdf'
        }
        
        if not PDF_SUPPORT:
            result['error'] = "PDF processing not available (install PyPDF2)"
            return result
            
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            
            # Extract text from all pages
            text_content = []
            for page_num, page in enumerate(pdf_reader.pages, 1):
                page_text = page.extract_text()
                if page_text.strip():
                    text_content.append(f"--- Page {page_num} ---\n{page_text}")
            
            result['content'] = "\n\n".join(text_content)
            result['pages'] = len(pdf_reader.pages)
            result['has_text'] = bool(text_content)
            
            if not text_content:
                result['warning'] = "PDF appears to be image-based or empty (no extractable text)"
                
        except Exception as e:
            result['error'] = f"PDF processing error: {str(e)}"
            
        return result
    
    @classmethod
    def _process_spreadsheet(cls, content: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
        """Process Excel/CSV files"""
        result = {
            'type': 'document',
            'subtype': 'spreadsheet',
            'filename': filename,
            'mime_type': mime_type
        }
        
        if not EXCEL_SUPPORT:
            result['error'] = "Spreadsheet processing not available (install pandas and openpyxl)"
            return result
            
        try:
            # Determine file type and read accordingly
            if filename.endswith('.csv') or mime_type == 'text/csv':
                df = pd.read_csv(io.BytesIO(content))
                sheets = {'Sheet1': df}
            else:
                # Excel file - try to read all sheets
                excel_file = pd.ExcelFile(io.BytesIO(content))
                sheets = {sheet: excel_file.parse(sheet) for sheet in excel_file.sheet_names}
            
            # Convert to readable format
            content_parts = []
            for sheet_name, df in sheets.items():
                if len(sheets) > 1:
                    content_parts.append(f"=== Sheet: {sheet_name} ===")
                
                # Basic info
                content_parts.append(f"Rows: {len(df)}, Columns: {len(df.columns)}")
                content_parts.append(f"Columns: {', '.join(df.columns.astype(str))}")
                
                # Sample data (first 10 rows)
                if len(df) > 0:
                    content_parts.append("\nFirst 10 rows:")
                    content_parts.append(df.head(10).to_string())
                
                # Basic statistics for numeric columns
                numeric_cols = df.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    content_parts.append("\nNumeric column statistics:")
                    content_parts.append(df[numeric_cols].describe().to_string())
            
            result['content'] = "\n\n".join(content_parts)
            result['sheets'] = list(sheets.keys())
            result['total_rows'] = sum(len(df) for df in sheets.values())
            
        except Exception as e:
            result['error'] = f"Spreadsheet processing error: {str(e)}"
            
        return result
    
    @classmethod
    def prepare_for_vision_api(cls, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prepare processed files for OpenAI/Anthropic vision API
        
        Returns list of content blocks for the API
        """
        content_blocks = []
        
        for file in files:
            if file.get('type') == 'image' and 'content' in file:
                # Image block for vision API
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {
                        "url": file['content'],
                        "detail": "high"  # Use high detail for construction docs
                    }
                })
            elif file.get('type') in ['text', 'document'] and 'content' in file:
                # Text block
                header = f"--- File: {file['filename']} ---\n"
                content_blocks.append({
                    "type": "text",
                    "text": header + file['content']
                })
            elif 'error' in file:
                # Error message
                content_blocks.append({
                    "type": "text",
                    "text": f"[Error processing {file['filename']}: {file['error']}]"
                })
                
        return content_blocks