@echo off
cd /d %~dp0
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
if not exist .env ( copy .env.example .env & echo Please open .env in Notepad, add your free AI key, then run this file again. & notepad .env & exit /b )
streamlit run dashboard.py
