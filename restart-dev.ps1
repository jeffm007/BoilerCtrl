# Restart Boiler Controller Services on Dev Machine
# This script stops any running Python/Uvicorn processes and restarts both services

Write-Host "Stopping all Python and Uvicorn processes..." -ForegroundColor Yellow
Stop-Process -Name python,uvicorn -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "Starting Backend Server on port 8001..." -ForegroundColor Green
Start-Process pwsh -ArgumentList "-NoExit", "-Command", "cd 'C:\Users\Jeff Mitchell\Documents\Boiler Controller'; .\.venv\Scripts\Activate.ps1; uvicorn backend.main:app --host 0.0.0.0 --port 8001"

Start-Sleep -Seconds 3

Write-Host "Starting Web Dashboard on port 8000..." -ForegroundColor Green
Start-Process pwsh -ArgumentList "-NoExit", "-Command", "cd 'C:\Users\Jeff Mitchell\Documents\Boiler Controller\web-dashboard'; & 'C:\Users\Jeff Mitchell\Documents\Boiler Controller\.venv\Scripts\Activate.ps1'; python main.py"

Write-Host ""
Write-Host "Services starting..." -ForegroundColor Cyan
Write-Host "  Backend (monolith):  http://localhost:8001" -ForegroundColor Cyan
Write-Host "  Web Dashboard:       http://localhost:8000 (will show no data)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Use http://localhost:8001 for local testing" -ForegroundColor Green
