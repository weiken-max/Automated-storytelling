$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut('c:\Users\libohang\Desktop\启动飞书后台.lnk')
Write-Host "Target: $($lnk.TargetPath)"
Write-Host "Args: $($lnk.Arguments)"
Write-Host "WorkDir: $($lnk.WorkingDirectory)"
