@echo off
REM Schedule daily Weaviate backups using Windows Task Scheduler
REM Run this batch file as Administrator

echo Creating scheduled task for Weaviate backups...

REM Create the scheduled task
schtasks /create /tn "NORTH_Weaviate_Backup" /tr "python %~dp0backup_weaviate.py" /sc daily /st 02:00 /ru SYSTEM

echo.
echo Scheduled task created successfully!
echo Weaviate will be backed up daily at 2:00 AM
echo.
echo To run backup manually: python backup_weaviate.py
echo To view task: schtasks /query /tn "NORTH_Weaviate_Backup"
echo To delete task: schtasks /delete /tn "NORTH_Weaviate_Backup"
echo.
pause