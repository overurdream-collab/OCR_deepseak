@echo off
REM Windows 11 launcher. Prerequisites: Python 3.10+ and Tesseract (UB Mannheim build) with the Arabic language data.
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate
pip install -r requirements.txt
REM Put Amiri-Regular.ttf in the .\fonts folder (https://fonts.google.com/specimen/Amiri) for Arabic PDF reports.
python -m mdia.server
pause
