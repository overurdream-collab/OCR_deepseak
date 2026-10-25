@echo off
setlocal
REM MDIA local-only medical invoice reader. Requires Python 3.11/3.12 and Tesseract Arabic.
REM Downloads PUBLIC PaddleOCR model weights on first launch; no medical invoices sent to cloud.
if not exist .venv (
    python -m venv .venv
    if errorlevel 1 goto :failed
)
call .venv\Scripts\activate
if errorlevel 1 goto :failed
python -m pip install -r requirements.txt
if errorlevel 1 goto :failed
python -m pip install "paddlepaddle==3.2.0" "paddleocr>=3.2,<4"
if errorlevel 1 goto :failed
set "MDIA_OCR_ENGINE=paddle_arabic"
set "MDIA_EVIDENCE_RECONCILIATION=1"
set "MDIA_STRICT_INVOICE_REVIEW=1"
set "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True"
python -m mdia.doctor
if errorlevel 1 goto :failed
python -m mdia.server
goto :end
:failed
echo FAILED: Check Python, required OCR models or installed dependencies.
exit /b 1
:end
pause
