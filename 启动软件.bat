@echo off  
chcp 65001 >nul  
call conda activate isd-mvp  
cd /d "D:\M_ISSION\Ionospheric_Scintillation_Detection\src"  
python -m isd  
pause 
