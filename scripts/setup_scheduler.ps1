# ============================================================
#  SAINHE — Enregistrement des tâches planifiées Windows
#  Lancer UNE SEULE FOIS (en tant qu'Administrateur) :
#      powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler.ps1
#
#  Tâches créées :
#    SAINHE_Nightly_Pipeline  — 01:00 AM  (fetch + calc + render)
#    SAINHE_Nightly_Backfill  — 03:30 AM  (extension historique 7 ans)
#
#  Prérequis :
#    - Python installé avec le launcher `py`
#    - Packages requirements.txt installés : pip install -r requirements.txt
#    - Fichier .env présent à la racine du projet (FRED_API_KEY etc.)
# ============================================================

$ErrorActionPreference = "Stop"

# Répertoire du projet (parent de \scripts\)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projDir   = Split-Path -Parent $scriptDir

Write-Host "Projet : $projDir"
Write-Host ""

# Vérifier si le dossier existe
if (-not (Test-Path $projDir)) {
    Write-Error "Répertoire projet introuvable : $projDir"
    exit 1
}

$pipelineBat = Join-Path $projDir "scripts\nightly_pipeline.bat"
$backfillBat = Join-Path $projDir "scripts\nightly_backfill.bat"

# Tache 1 : Pipeline principal - 01:00 AM
$task1Name = "SAINHE_Nightly_Pipeline"

$action1  = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$pipelineBat`"" `
    -WorkingDirectory $projDir

$trigger1 = New-ScheduledTaskTrigger -Daily -At "01:00"

$settings1 = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -StartWhenAvailable

# Supprimer si existe déjà
if (Get-ScheduledTask -TaskName $task1Name -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $task1Name -Confirm:$false
    Write-Host "Ancienne tâche supprimée : $task1Name"
}

Register-ScheduledTask `
    -TaskName $task1Name `
    -Action $action1 `
    -Trigger $trigger1 `
    -Settings $settings1 `
    -Description "SAINHE - fetch prix + fx + macro + calc + render HTML (01h00)" `
    -Force | Out-Null

Write-Host "Tache creee : $task1Name (01:00 AM)"

# Tache 2 : Backfill historique - 03:30 AM
$task2Name = "SAINHE_Nightly_Backfill"

$action2  = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$backfillBat`"" `
    -WorkingDirectory $projDir

$trigger2 = New-ScheduledTaskTrigger -Daily -At "03:30"

$settings2 = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable

if (Get-ScheduledTask -TaskName $task2Name -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $task2Name -Confirm:$false
    Write-Host "Ancienne tâche supprimée : $task2Name"
}

Register-ScheduledTask `
    -TaskName $task2Name `
    -Action $action2 `
    -Trigger $trigger2 `
    -Settings $settings2 `
    -Description "SAINHE - backfill historique 7 ans (+30j/ticker/nuit) (03h30)" `
    -Force | Out-Null

Write-Host "Tache creee : $task2Name (03:30 AM)"

Write-Host ""
Write-Host "Verification :"
Get-ScheduledTask -TaskName "SAINHE_*" | Format-Table TaskName, State -AutoSize
