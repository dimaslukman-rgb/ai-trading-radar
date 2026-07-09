[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
SourceFiles=SourceFiles

[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=AI Trading Radar installation complete.
TargetName=C:\Users\ASUS\Documents\Codex\ai-trading-bot-windows-package\release\AITradingRadar_Setup.exe
FriendlyName=AI Trading Radar Installer
AppLaunched=install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=install.cmd
UserQuietInstCmd=install.cmd
FILE0="AITradingRadar.exe"
FILE1="config.json"
FILE2="config.example.json"
FILE3="Start_AITradingRadar.bat"
FILE4="Start_MT5_AutoTrading.bat"
FILE5="Start_Paper_AutoTest.bat"
FILE6="PACKAGE_README.md"
FILE7="README.md"
FILE8="TRADINGVIEW_SETUP.txt"
FILE9="tradingview-dashboard.html"
FILE10="open-tradingview-dashboard.bat"
FILE11="install.bat"
FILE12="install.ps1"
FILE13="README_INSTALL.txt"
FILE14="install.cmd"

[SourceFiles]
SourceFiles0=C:\Users\ASUS\Documents\Codex\ai-trading-bot-windows-package\installer_staging\

[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
%FILE3%=
%FILE4%=
%FILE5%=
%FILE6%=
%FILE7%=
%FILE8%=
%FILE9%=
%FILE10%=
%FILE11%=
%FILE12%=
%FILE13%=
%FILE14%=

