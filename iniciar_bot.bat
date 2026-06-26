@echo off
cd /d "%~dp0"

:loop
echo ============================
echo Iniciando o bot...
echo ============================
python bot.py

echo.
echo O bot parou ou caiu. Reiniciando em 5 segundos... (Ctrl+C aqui para sair de vez)
timeout /t 5 /nobreak >nul
goto loop