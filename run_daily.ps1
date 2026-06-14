# MLB K Props — daily runner
# Called by Windows Task Scheduler at 8 AM

$host.UI.RawUI.WindowTitle = "MLB K Props"
Write-Host "`e]9;4;2`a" -NoNewline  # green tab color (Windows Terminal)

$env:ODDS_API_KEY      = "c87cc0c5b57c258cb6b099a85bb70372"
$env:GMAIL_USER        = "bennettevans0@gmail.com"
$env:GMAIL_APP_PASSWORD = "ptno rwle tdyb dtnx"
$env:GMAIL_TO          = "bennettevans0@gmail.com"

$log = "C:\Users\benne\mlb-k-props\logs\run.log"
$py  = "C:\Users\benne\AppData\Local\Programs\Python\Launcher\py.exe"

"" | Out-File -FilePath $log -Append -Encoding utf8
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -FilePath $log -Append -Encoding utf8

Set-Location "C:\Users\benne\mlb-k-props"
& $py main.py 2>&1 | Out-File -FilePath $log -Append -Encoding utf8

"Exit code: $LASTEXITCODE" | Out-File -FilePath $log -Append -Encoding utf8

# Push updated site data to GitHub
Set-Location "C:\Users\benne\mlb-k-props"
git add docs/data/
git commit -m "data: $(Get-Date -Format 'yyyy-MM-dd')" 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
git push 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
