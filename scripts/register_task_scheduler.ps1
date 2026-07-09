param(
    [string]$TaskNamePrefix = "FinStock",
    [string[]]$Times = @("08:00", "18:00"),
    [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot)
)

foreach ($i in 0..($Times.Count - 1)) {
    $taskName = "$TaskNamePrefix-$i"
    $time = $Times[$i]

    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }

    $action = New-ScheduledTaskAction -Execute "uv" -Argument "run python -m finstock.main" -WorkingDirectory $ProjectPath
    $trigger = New-ScheduledTaskTrigger -Daily -At $time
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description "FinStock research report run" | Out-Null
    Write-Host "Registered $taskName at $time"
}
