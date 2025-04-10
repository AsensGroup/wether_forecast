@echo off
echo Запуск сервера FastAPI на http://127.0.0.1:8001 ...
python -m uvicorn main:app --reload --port 8001
pause
