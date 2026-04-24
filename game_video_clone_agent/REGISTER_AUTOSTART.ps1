# ============================================================
# 飞书指挥部 - 开机自启动注册脚本
# 使用方法：右键 -> 以管理员身份运行（Run as Administrator）
# ============================================================

$TaskName = "FeishuHub_AutoStart"
$BatPath = Join-Path -Path $PSScriptRoot -ChildPath "STARTUP_SILENT.bat"

# 检查 bat 文件是否存在
if (-not (Test-Path $BatPath)) {
    Write-Host "❌ 错误：找不到启动脚本: $BatPath" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

# 如果任务已存在就先删掉
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "🔄 已删除旧的自启动任务，重新注册..." -ForegroundColor Yellow
}

# 构建触发器：系统启动后延迟 30 秒执行（等网络稳定）
$Trigger = New-ScheduledTaskTrigger -AtStartup
# 延迟 30 秒（等系统和网络完全就绪）
$Trigger.Delay = "PT30S"

# 构建动作：静默运行 bat 脚本
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatPath`"" `
    -WorkingDirectory (Split-Path $BatPath)

# 构建设置：允许按需运行，运行时不显示任何窗口
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -MultipleInstances IgnoreNew `
    -Hidden

# 注册任务：以当前用户身份运行，最高权限
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Trigger $Trigger `
    -Action $Action `
    -Settings $Settings `
    -Principal $Principal `
    -Description "飞书指挥部后台服务，开机自动静默启动" `
    -Force | Out-Null

Write-Host ""
Write-Host "✅ 自启动任务注册成功！" -ForegroundColor Green
Write-Host "   任务名: $TaskName" -ForegroundColor Cyan
Write-Host "   触发时机: 开机后 30 秒自动运行" -ForegroundColor Cyan
Write-Host "   运行方式: 完全静默，无任何窗口弹出" -ForegroundColor Cyan
Write-Host ""
Write-Host "📋 管理命令（在 PowerShell 中运行）:" -ForegroundColor Yellow
Write-Host "   立即手动触发: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
Write-Host "   查看任务状态: Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
Write-Host "   删除自启动:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor White
Write-Host ""
Read-Host "按 Enter 退出"
