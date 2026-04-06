@echo off
:: BunkerM Extended - Launcher for deploy.ps1
:: Runs the PowerShell deployment script bypassing execution policy for this script only.
:: Usage: deploy.bat [action]
::   deploy.bat setup
::   deploy.bat start
::   deploy.bat stop
::   deploy.bat restart
::   deploy.bat patch-frontend
::   deploy.bat patch-backend
::   deploy.bat status
::   deploy.bat logs

if "%~1"=="" (
    powershell.exe -ExecutionPolicy Bypass -File "%~dp0deploy.ps1"
) else (
    powershell.exe -ExecutionPolicy Bypass -File "%~dp0deploy.ps1" -Action %*
)
