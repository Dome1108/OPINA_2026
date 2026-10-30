$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$localPython = Join-Path $projectPath '.venv\Scripts\pythonw.exe'
if (Test-Path -LiteralPath $localPython) {
    $pythonPath = $localPython
} else {
    $pythonPath = (Get-Command pythonw.exe).Source
}
$syncPath = Join-Path $projectPath 'sync.py'
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument ('"' + $syncPath + '"') -WorkingDirectory $projectPath
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName 'OPINA-Sincronizacion' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Actualiza la copia local de OPINA cada 15 minutos con la sesion Windows iniciada.' -Force | Out-Null
Start-ScheduledTask -TaskName 'OPINA-Sincronizacion'
Get-ScheduledTask -TaskName 'OPINA-Sincronizacion' | Select-Object TaskName, State
