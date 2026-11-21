[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('normal', 'crash-before-commit', 'crash-after-commit', 'postgres-down', 'redis-down', 'cleanup')]
    [string]$Scenario,
    [switch]$KeepOpen
)

$ErrorActionPreference = 'Stop'
if ($KeepOpen -and $Scenario -ne 'normal') {
    throw 'Параметр -KeepOpen доступен только для сценария normal.'
}

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$temp = Join-Path ([IO.Path]::GetTempPath()) "unitime-quest8-$([Guid]::NewGuid())"
$null = New-Item -ItemType Directory -Path $temp
$envFile = Join-Path $temp 'demo.env'
$override = Join-Path $temp 'compose.yml'
$mount = ConvertTo-Json -Compress ($PSScriptRoot.Replace('\', '/'))
[IO.File]::WriteAllText($envFile, '')
[IO.File]::WriteAllText($override, @"
services:
  migrate:
    env_file: !reset []
  api:
    env_file: !reset []
    environment:
      APP_SECRET: quest8-local-fixture-key-for-api-and-worker
      PYTHONPATH: /app:/quest8
    volumes:
      - type: bind
        source: $mount
        target: /quest8
        read_only: true
    ports: !reset []
    command: uvicorn demo_fixture:app --host 0.0.0.0 --port 8000
  relay:
    env_file: !reset []
    environment:
      SYNC_VISIBILITY_TIMEOUT: "10"
  worker:
    env_file: !reset []
    environment:
      APP_SECRET: quest8-local-fixture-key-for-api-and-worker
      PYTHONPATH: /app:/quest8
      SYNC_ON_WORKER_START: "false"
      SYNC_VISIBILITY_TIMEOUT: "10"
    volumes:
      - type: bind
        source: $mount
        target: /quest8
        read_only: true
  beat:
    env_file: !reset []
  web:
    ports: !override
      - "127.0.0.1::80"
"@)

$compose = @('compose', '--project-directory', $repo, '--env-file', $envFile,
    '-f', (Join-Path $repo 'docker-compose.yml'), '-f', $override)
$demoScenarios = @('normal', 'crash-before-commit', 'crash-after-commit', 'postgres-down', 'redis-down')
$project = "unitime-quest8-$Scenario"
$started = $false
$leaveRunning = $false

function Invoke-Docker {
    $ErrorActionPreference = 'Continue'
    $output = & docker @args 2>&1
    $exitCode = $LASTEXITCODE
    $output = @($output | ForEach-Object { $_.ToString() })
    if ($exitCode -ne 0) {
        throw "Docker завершился с кодом $exitCode. $($output -join [Environment]::NewLine)"
    }
    $output
}

function Invoke-Compose {
    Invoke-Docker @compose -p $project @args
}

function Assert-Demo([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Wait-For([string]$Description, [scriptblock]$Probe, [int]$Seconds = 60) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $lastError = ''
    do {
        try {
            if (& $Probe) { return }
        }
        catch { $lastError = $_.Exception.Message }
        Start-Sleep -Milliseconds 300
    } while ($timer.Elapsed.TotalSeconds -lt $Seconds)
    throw "Истекло время ожидания: $Description. $lastError"
}

function Wait-DemoLog([string]$Container, [string]$Pattern) {
    $script:matchedLog = $null
    Wait-For "$Container log $Pattern" {
        $script:matchedLog = Invoke-Docker logs $Container | Where-Object { $_ -match $Pattern } | Select-Object -Last 1
        [bool]$script:matchedLog
    }
    Write-Verbose $script:matchedLog
}

function Start-Worker([string]$Label, [string]$Pause) {
    $container = "$project-worker-$Label"
    $workerArgs = @('python', '-m', 'demo_fixture', 'worker', '--hostname', "$Label@%h",
        '--pool', 'solo', '--concurrency', '1', '--prefetch-multiplier', '1', '--loglevel', 'info')
    $null = Invoke-Compose run --detach --no-deps --name $container -e "QUEST8_PAUSE=$Pause" worker @workerArgs
    return $container
}

function Invoke-Sql([string]$Query) {
    (Invoke-Compose exec -T postgres psql -U slot -d slot -v ON_ERROR_STOP=1 -Atc $Query) -join [Environment]::NewLine
}

function Get-ResultSnapshot {
    Invoke-Sql @"
SELECT json_build_object(
    'last_synced_at', c.last_synced_at,
    'intervals', coalesce(
        (SELECT json_agg(json_build_array(b.id, b.uid, b.period) ORDER BY b.uid, b.occurrence_start)
         FROM busy_intervals b JOIN calendar_collections col ON col.id = b.collection_id
         WHERE col.connection_id = c.id), '[]'::json)
) FROM calendar_connections c WHERE c.id = '$connectionId';
"@
}

function Get-Job {
    Invoke-RestMethod "$url$jobPath" -WebSession $session -TimeoutSec 10 -Verbose:$false
}

function Show-Step([string]$Title) {
    Write-Host ''
    Write-Host $Title
}

function Show-Job($Job) {
    Write-Host "  Статус API: $($Job.status) | попыток: $($Job.attempts) | записей результата: $($Job.process_count)"
    Write-Verbose (ConvertTo-Json -InputObject $Job -Depth 5 -Compress)
}

function Assert-Grid {
    $grid = Invoke-RestMethod "$url/api/grid?date_from=$day&date_to=$day&step_minutes=60" -WebSession $session -TimeoutSec 10 -Verbose:$false
    $busy = @($grid.cells | Where-Object { $_.total -eq 1 -and $_.free_count -eq 0 } | ForEach-Object { $_.hour })
    Assert-Demo (($busy -join ',') -eq '10,14') "Сетка вернула другие часы занятости: $busy"
    Write-Host "  Сетка на $($day): занято с 10:00 до 11:00 и с 14:00 до 15:00 (МСК)."
}

function Register-DemoUser([string]$Email, $Session) {
    $credentials = @{ email = $Email; password = $password } | ConvertTo-Json -Compress
    $null = Invoke-RestMethod "$url/api/auth/register" -Method Post -WebSession $Session -ContentType 'application/json' -Body $credentials -TimeoutSec 10 -Verbose:$false
}

try {
    if ($Scenario -eq 'cleanup') {
        foreach ($item in $demoScenarios) {
            $project = "unitime-quest8-$item"
            $null = Invoke-Compose down --volumes --remove-orphans
        }
        Write-Host 'Демонстрационные стенды квеста 8 остановлены.'
        return
    }

    if (Invoke-Compose ps --all --quiet) {
        throw "Стенд $project уже запущен или сохранён. Для нового прогона сначала выполните -Scenario cleanup."
    }
    $started = $true
    $pause = if ($Scenario -eq 'crash-after-commit') { 'after_commit' } else { 'before_commit' }
    $title = switch ($Scenario) {
        normal { 'Обычная синхронизация' }
        'crash-before-commit' { 'Остановка воркера до коммита' }
        'crash-after-commit' { 'Остановка воркера после коммита, до ACK' }
        'postgres-down' { 'Остановка PostgreSQL до коммита' }
        'redis-down' { 'Остановка Redis до публикации' }
    }
    $expectation = switch ($Scenario) {
        normal { 'Задание пройдёт queued → running → succeeded, в сетке появятся два интервала.' }
        'crash-before-commit' { 'Воркер B получит тот же job_id и сохранит результат один раз.' }
        'crash-after-commit' { 'Воркер B получит тот же job_id и пропустит уже сохранённый результат.' }
        'postgres-down' { 'Запись откатится, после восстановления БД то же задание завершится.' }
        'redis-down' { 'Задание останется в PostgreSQL и будет выполнено после запуска Redis.' }
    }
    Write-Host "Квест 8. $title ($Scenario)"
    Write-Host "Ожидание: $expectation"
    Write-Host 'Подготовка: запускаем отдельный стенд Docker Compose.'
    $null = Invoke-Compose up -d --build postgres redis api web
    $port = (Invoke-Compose port web 80 | Select-Object -Last 1).Split(':')[-1]
    $url = "http://127.0.0.1:$port"
    Wait-For 'Unitime API' { (Invoke-RestMethod "$url/api/health" -TimeoutSec 3 -Verbose:$false).ok }

    $day = [DateTime]::UtcNow.AddHours(3).Date.AddDays(1).ToString('yyyy-MM-dd')
    $email = 'quest8@example.test'
    $password = [Guid]::NewGuid().ToString('N')
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Register-DemoUser $email $session
    $source = @{ url = "https://quest8.example/$day.ics" } | ConvertTo-Json -Compress
    $connection = Invoke-RestMethod "$url/api/connections/link" -Method Post -WebSession $session -ContentType 'application/json' -Body $source -TimeoutSec 10 -Verbose:$false
    $connectionId = [Guid]::Parse($connection.id).ToString()
    $null = Invoke-Sql @"
INSERT INTO busy_intervals (id, collection_id, uid, occurrence_start, period, source)
SELECT gen_random_uuid(), id, 'quest8-before', TIMESTAMPTZ '$day 09:00+03',
       tstzrange(TIMESTAMPTZ '$day 09:00+03', TIMESTAMPTZ '$day 10:00+03', '[)'), 'auto'
FROM calendar_collections WHERE connection_id = '$connectionId';
"@
    $baseline = Get-ResultSnapshot
    Assert-Demo ($baseline -match 'quest8-before') 'В базе отсутствует исходный интервал занятости.'
    $job = Invoke-RestMethod "$url/api/connections/$connectionId/sync?date_from=$day&date_to=$day" -Method Post -WebSession $session -TimeoutSec 10 -Verbose:$false
    $jobId = [Guid]::Parse($job.job_id).ToString()
    $jobPath = "/api/connections/$connectionId/sync/$jobId"
    $enqueued = Get-Job
    Assert-Demo ($enqueued.status -eq 'queued' -and $enqueued.process_count -eq 0) 'Ожидалось новое задание в статусе queued.'
    Show-Step '[1/4] Постановка задания'
    Write-Host "  API сохранил задание в PostgreSQL. job_id=$jobId"
    Show-Job $enqueued

    if ($Scenario -eq 'normal') {
        $otherSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        Register-DemoUser 'other@example.test' $otherSession
        try {
            $null = Invoke-RestMethod "$url$jobPath" -WebSession $otherSession -TimeoutSec 10 -Verbose:$false
            throw 'Другой пользователь получил доступ к статусу задания.'
        }
        catch {
            if ($null -eq $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 404) { throw }
            Write-Host '  Проверка доступа: запрос из другого аккаунта вернул HTTP 404.'
        }
    }

    Show-Step '[2/4] Публикация в Redis'
    if ($Scenario -eq 'redis-down') {
        Write-Host '  Останавливаем Redis после записи задания в PostgreSQL.'
        $null = Invoke-Compose stop redis
        $null = Invoke-Compose up -d --build --no-deps relay
        Wait-DemoLog "$project-relay-1" 'publication_delayed'
        $pending = Invoke-Sql "SELECT id || ':' || status FROM sync_jobs WHERE id = '$jobId' AND published_at IS NULL;"
        Assert-Demo ($pending -eq "$($jobId):queued") 'Запись задания без отметки о публикации не найдена.'
        Write-Host '  PostgreSQL сохранил задание в статусе queued. Отметки о публикации пока нет.'
        Write-Verbose "outbox_pending=$pending"
        Write-Host '  Запускаем Redis. Процесс публикации отправит то же задание.'
        $null = Invoke-Compose start redis
    }
    else {
        $null = Invoke-Compose up -d --build --no-deps relay
    }
    Wait-DemoLog "$project-relay-1" "published job_id=$jobId "
    $ready = [int](Invoke-Compose exec -T redis redis-cli LLEN celery | Select-Object -Last 1)
    Assert-Demo ($ready -eq 1) "В очереди celery ожидалось одно сообщение, получено $ready."
    Write-Host "  В очереди celery ждёт $ready сообщение. Воркер ещё не запущен."

    Show-Step '[3/4] Работа воркера'
    $worker = Start-Worker 'a' $pause
    Wait-DemoLog $worker "running job_id=$jobId attempt=1"
    Write-Host '  Воркер A получил задание. Это первая попытка.'
    Wait-DemoLog $worker "demo_pause stage=$pause job_id=$jobId"

    if ($Scenario -eq 'crash-after-commit') {
        $beforeRepeat = Get-ResultSnapshot
        $jobAtCommit = Get-Job
        Assert-Demo ($jobAtCommit.status -eq 'succeeded' -and $jobAtCommit.process_count -eq 1) 'К моменту ACK результат должен быть сохранён.'
        Assert-Demo ($beforeRepeat -ne $baseline) 'После коммита ожидались новые интервалы.'
        Write-Host '  После коммита, до ACK: PostgreSQL уже сохранил результат.'
        Write-Verbose "before_redelivery=$beforeRepeat"
        Show-Job $jobAtCommit
    }
    else {
        $running = Get-Job
        Assert-Demo ($running.status -eq 'running' -and $running.process_count -eq 0) 'До коммита ожидался статус running без сохранённого результата.'
        Assert-Demo ((Get-ResultSnapshot) -eq $baseline) 'Другая сессия PostgreSQL увидела незакоммиченные изменения.'
        Write-Host '  До коммита другая сессия PostgreSQL видит прежний интервал с 09:00 до 10:00 (МСК).'
        Write-Verbose "before_commit=$baseline"
        Show-Job $running
    }

    if ($Scenario.StartsWith('crash-')) {
        $null = Invoke-Docker kill --signal KILL $worker
        Write-Host '  Воркер A остановлен до ACK. Ждём истечения таймаута доставки Redis.'
        Write-Verbose "worker_killed=$worker job_id=$jobId"
        Start-Sleep -Seconds 11
        $worker = Start-Worker 'b' ''
        if ($Scenario -eq 'crash-after-commit') {
            Wait-DemoLog $worker "duplicate job_id=$jobId .*redelivered=true"
            $afterRepeat = Get-ResultSnapshot
            Assert-Demo ($afterRepeat -eq $beforeRepeat) 'Повторная доставка изменила сохранённый результат.'
            Write-Host "  Воркер B получил тот же job_id=$jobId (redelivered=true)."
            Write-Host '  duplicate: совпали ID и границы интервалов, а также время обновления.'
            Write-Verbose "after_redelivery=$afterRepeat"
        }
        else {
            Wait-DemoLog $worker "running job_id=$jobId attempt=2 .*redelivered=true"
            Write-Host "  Воркер B получил тот же job_id=$jobId (redelivered=true)."
            Wait-DemoLog $worker "committed job_id=$jobId attempt=2"
            Write-Host '  Воркер B сохранил результат на второй попытке.'
        }
    }
    elseif ($Scenario -eq 'postgres-down') {
        Write-Host '  Останавливаем PostgreSQL перед коммитом.'
        $null = Invoke-Compose stop postgres
        $null = Invoke-Docker exec $worker touch /tmp/quest8-release
        Wait-DemoLog $worker "requeue_database job_id=$jobId"
        Write-Host '  Запись прервалась. Воркер вернул доставку в очередь (requeue_database).'
        $null = Invoke-Compose up -d --wait --no-deps postgres
        Wait-DemoLog $worker "running job_id=$jobId .*redelivered=true"
        Wait-DemoLog $worker "committed job_id=$jobId"
        Write-Host "  После запуска PostgreSQL воркер сохранил результат задания $jobId."
    }
    else {
        $null = Invoke-Docker exec $worker touch /tmp/quest8-release
        Wait-DemoLog $worker "committed job_id=$jobId attempt=1"
    }

    $result = Get-Job
    $validResult = $result.status -eq 'succeeded' -and $result.process_count -eq 1 -and $result.result.interval_count -eq 2
    Assert-Demo $validResult 'Ожидалась одна успешная запись результата с двумя интервалами.'
    Show-Step '[4/4] Результат'
    Show-Job $result
    Write-Host "  Записано интервалов: $($result.result.interval_count)."
    Assert-Grid
    Write-Host "  PASS | $Scenario | job_id=$jobId"
    if ($KeepOpen) {
        Show-Step 'Показ в браузере'
        Write-Host "  Адрес Unitime: $url"
        Write-Host "  Логин: $email"
        Write-Host "  Пароль: $password"
        Write-Host "  Откройте в сетке $day и покажите ячейки 10:00 и 14:00 (МСК)."
        $leaveRunning = $true
    }
}
finally {
    try {
        if ($started -and -not $leaveRunning) {
            $null = Invoke-Compose down --volumes --remove-orphans
        }
    }
    finally {
        Remove-Item -LiteralPath $override, $envFile -Force
        Remove-Item -LiteralPath $temp
    }
}
