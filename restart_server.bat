@echo off
echo ==========================================
echo ALCOEN ERP 服务器重启脚本
echo ==========================================
echo.

cd /d E:\AI\alcoen_erp_system

echo [1/3] 正在停止现有服务器...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul
echo.

echo [2/3] 清除缓存...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
echo.

echo [3/3] 启动服务器...
echo 服务器将启动在 http://localhost:8080
echo 按 Ctrl+C 停止服务器
echo.
python run.py

pause
