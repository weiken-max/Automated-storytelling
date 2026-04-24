$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut('c:\Users\libohang\Desktop\启动飞书后台.lnk')
$lnk.TargetPath = 'c:\Users\libohang\Desktop\Automated storytelling\game_video_clone_agent\STARTUP_SILENT.bat'
$lnk.WorkingDirectory = 'c:\Users\libohang\Desktop\Automated storytelling\game_video_clone_agent'
$lnk.Save()
Write-Host "Shortcut updated successfully!"
