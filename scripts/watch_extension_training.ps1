$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = 'FoodLens - ML-05 training progress'
$projectRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $projectRoot 'data/processed/ML-05-job.json'

function Format-Duration([double]$seconds) {
    $span = [TimeSpan]::FromSeconds([Math]::Max(0, $seconds))
    return '{0:00}:{1:00}:{2:00}' -f [int][Math]::Floor($span.TotalHours), $span.Minutes, $span.Seconds
}

while ($true) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $statusPath = Join-Path $state.job 'status.json'
        $status = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $stage = $status.stage
        if ($state.stage -eq 'training' -and $stage -eq 'paused_by_owner') { $stage = 'initializing resume' }
        if ($state.stage -in @('training_failed','evaluation_failed','training_budget_terminated_pending_checkpoint_review')) { $stage = $state.stage }
        Clear-Host
        Write-Host '============================================================' -ForegroundColor Cyan
        Write-Host ' FOODLENS | YOLO11n | 75 CLASSES | RTX 4060' -ForegroundColor Cyan
        Write-Host '============================================================' -ForegroundColor Cyan
        Write-Host ('Stage:              ' + $stage)
        if ($stage -eq 'selecting_extension_checkpoint') {
            Write-Host ('Validation choice:  {0}/{1} checkpoints (no test selection)' -f $status.checkpoint_selection_index,$status.checkpoint_selection_total)
        }
        $finishPath = Join-Path $projectRoot 'data/processed/ML-05-finish.json'
        if (Test-Path -LiteralPath $finishPath) {
            $finish = Get-Content -LiteralPath $finishPath -Raw -Encoding UTF8 | ConvertFrom-Json
            Write-Host ('API/integration:    ' + $finish.stage + ' [' + $finish.status + ']')
        }
        Write-Host ('Completed epochs:   ' + $status.completed_epochs)
        Write-Host ('Current epoch:      ' + (1 + [int]$status.epoch_index))
        $done = [int]$status.batches_seen_in_epoch
        $total = [int]$status.batches_per_epoch
        $fraction = if ($total -gt 0) { [Math]::Min(1, $done / $total) } else { 0 }
        $bars = [int][Math]::Floor(32 * $fraction)
        Write-Host ('Batch:              {0}/{1} [{2}{3}] {4:P0}' -f $done,$total,('#' * $bars),('-' * (32-$bars)),$fraction)
        Write-Host ('Active budget used: ' + (Format-Duration $status.training_job_elapsed_seconds) + ' / 03:00:00 maximum')
        $deadlineText = $state.latest_expected_deadline_utc
        if ($status.latest_expected_deadline_utc) { $deadlineText = $status.latest_expected_deadline_utc }
        if ($deadlineText) {
            $deadline = [DateTimeOffset]::Parse($deadlineText)
            Write-Host ('Training cutoff:    ' + $deadline.ToOffset([TimeSpan]::FromHours(7)).ToString('HH:mm:ss yyyy-MM-dd') + ' UTC+7')
            Write-Host ('Time to cutoff:     ' + (Format-Duration ($deadline - [DateTimeOffset]::UtcNow).TotalSeconds))
        }
        if ($status.validation_metrics) {
            $score = $status.validation_metrics.'metrics/mAP50(B)'
            Write-Host ('Validation mAP50:   {0:N4} (mixed validation set)' -f $score)
        }
        Write-Host ('Status updated UTC: ' + $status.updated_at)
        Write-Host ''
        Write-Host 'Checkpoint and optimizer are saved at each epoch.' -ForegroundColor Green
        Write-Host 'After train: separate evaluation; backend acceptance pending.'
        Write-Host 'This window only monitors. Closing it does not stop training.'
        Write-Host 'Refresh: every 5 seconds. Job runs independently of this chat.'
    }
    catch {
        Write-Host ('Waiting for job status: ' + $_.Exception.GetType().Name) -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 5
}
