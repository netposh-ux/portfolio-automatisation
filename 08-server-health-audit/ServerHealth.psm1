# Server health audit: HTTP logs (IIS, Nginx/Apache), system logs (syslog, Windows events),
# disk space and certificate expiry, with a JSON and HTML report.
# Works with PowerShell 7 on Windows and Linux.

$Severities = @{ OK = 0; Warning = 1; Critical = 2 }
$Combined = '^(?<ip>\S+) \S+ \S+ \[(?<time>[^\]]+)\] "(?<method>[A-Z]+) (?<url>\S+)[^"]*" (?<status>\d{3}) \S+(?: "[^"]*" "[^"]*")?(?: (?<rt>\d+(?:\.\d+)?))?\s*$'
$Syslog = '^(?<time>\w{3}\s+\d+ [\d:]+) (?<host>\S+) (?<src>[^:\[]+)(?:\[\d+\])?: (?<msg>.*)$'
$Invariant = [Globalization.CultureInfo]::InvariantCulture

function Format-Count([int]$Count, [string]$Word) {
    if ($Count -eq 1) { "1 $Word" } else { "$Count ${Word}s" }
}

function New-Finding([string]$Severity, [string]$Check, [string]$Target, [string]$Message) {
    [pscustomobject]@{ Severity = $Severity; Check = $Check; Target = $Target; Message = $Message }
}

function Read-AccessLog {
    <#
    .SYNOPSIS
    Reads an IIS (W3C) or Nginx/Apache (combined) access log. The format is detected on its own.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $fields = $null
    $bad = 0
    foreach ($line in [IO.File]::ReadLines((Resolve-Path $Path).Path)) {
        if ($line -match '^#Fields:\s*(.+)$') { $fields = $Matches[1].Trim() -split '\s+'; continue }
        if ($line.StartsWith('#') -or -not $line.Trim()) { continue }

        if ($fields) {
            $values = $line.Trim() -split '\s+'
            if ($values.Count -ne $fields.Count) { $bad++; continue }
            $row = @{}
            for ($i = 0; $i -lt $fields.Count; $i++) { $row[$fields[$i]] = $values[$i] }
            [pscustomobject]@{
                Time        = [datetime]::ParseExact("$($row['date']) $($row['time'])", 'yyyy-MM-dd HH:mm:ss', $Invariant)
                Method      = $row['cs-method']
                Path        = $row['cs-uri-stem']
                Status      = [int]$row['sc-status']
                TimeTakenMs = if ($row.ContainsKey('time-taken')) { [int]$row['time-taken'] } else { $null }
                ClientIp    = $row['c-ip']
            }
        }
        elseif ($line -match $Combined) {
            # Nginx writes the offset as -0400; .NET wants -04:00.
            $time = $Matches.time -replace '([+-]\d{2})(\d{2})$', '$1:$2'
            [pscustomobject]@{
                Time        = [DateTimeOffset]::ParseExact($time, 'dd/MMM/yyyy:HH:mm:ss zzz', $Invariant).LocalDateTime
                Method      = $Matches.method
                Path        = ($Matches.url -split '\?')[0]
                Status      = [int]$Matches.status
                TimeTakenMs = if ($Matches.rt) { [int][math]::Round([double]::Parse($Matches.rt, $Invariant) * 1000) } else { $null }
                ClientIp    = $Matches.ip
            }
        }
        else { $bad++ }
    }
    if ($bad) { Write-Warning "${Path}: skipped $bad line(s) that could not be read" }
}

function Get-HttpLogSummary {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Entries,
        [int]$SlowMs = 1000
    )
    $n = $Entries.Count
    $server = @($Entries | Where-Object { $_.Status -ge 500 })
    $times = @($Entries | Where-Object { $null -ne $_.TimeTakenMs } | ForEach-Object TimeTakenMs | Sort-Object)
    [pscustomobject]@{
        Requests        = $n
        ServerErrors    = $server.Count
        ClientErrors    = @($Entries | Where-Object { $_.Status -ge 400 -and $_.Status -lt 500 }).Count
        ServerErrorRate = if ($n) { [math]::Round(100 * $server.Count / $n, 1) } else { 0 }
        SlowRequests    = @($times | Where-Object { $_ -ge $SlowMs }).Count
        # Nearest-rank percentile: the value below which 95 % of the requests fall.
        P95Ms           = if ($times.Count) { $times[[math]::Ceiling(0.95 * $times.Count) - 1] } else { $null }
        TopFailingPaths = @($server | Group-Object Path | Sort-Object Count -Descending | Select-Object -First 5 |
                ForEach-Object { [pscustomobject]@{ Path = $_.Name; Count = $_.Count } })
    }
}

function Read-SystemLog {
    <#
    .SYNOPSIS
    Counts errors and critical events in a Linux syslog/journal export, or in a Windows event log
    exported with: Get-WinEvent -LogName System | Export-Csv system.csv
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $events = if ($Path -like '*.csv') {
        Import-Csv $Path | ForEach-Object {
            $level = if ($_.LevelDisplayName) { $_.LevelDisplayName } else { $_.Level }
            [pscustomobject]@{
                Time = $_.TimeCreated; Source = $_.ProviderName; Message = $_.Message
                Level = switch ($level) { { $_ -in 'Critical', '1' } { 'Critical' } { $_ -in 'Error', '2' } { 'Error' } default { 'Info' } }
            }
        }
    }
    else {
        foreach ($line in [IO.File]::ReadLines((Resolve-Path $Path).Path)) {
            if ($line -notmatch $Syslog) { continue }
            $msg = $Matches.msg
            [pscustomobject]@{
                Time = $Matches.time; Source = $Matches.src.Trim(); Message = $msg
                Level = if ($msg -match '\b(crit|critical|emerg|alert|panic|fatal)\b') { 'Critical' }
                elseif ($msg -match '\b(error|err|failed|failure)\b') { 'Error' } else { 'Info' }
            }
        }
    }
    $bad = @($events | Where-Object Level -NE 'Info')
    [pscustomobject]@{
        Path       = $Path
        Errors     = @($bad | Where-Object Level -EQ 'Error').Count
        Critical   = @($bad | Where-Object Level -EQ 'Critical').Count
        TopSources = @($bad | Group-Object Source | Sort-Object Count -Descending | Select-Object -First 5 |
                ForEach-Object { [pscustomobject]@{ Source = $_.Name; Count = $_.Count } })
        Samples    = @($bad | Select-Object -Last 10)
    }
}

function Get-DiskStatus {
    [CmdletBinding()]
    param(
        # Objects with Name, Used and Free (bytes). Default: the machine's file system drives.
        [object[]]$Drives,
        [double]$WarnPercent = 15,
        [double]$CriticalPercent = 5
    )
    if (-not $Drives) { $Drives = Get-PSDrive -PSProvider FileSystem | Where-Object { ($_.Used + $_.Free) -gt 0 } }
    foreach ($d in $Drives) {
        $total = $d.Used + $d.Free
        $pct = [math]::Round(100 * $d.Free / $total, 1)
        [pscustomobject]@{
            Name        = $d.Name
            SizeGB      = [math]::Round($total / 1GB, 1)
            FreeGB      = [math]::Round($d.Free / 1GB, 1)
            FreePercent = $pct
            Severity    = if ($pct -lt $CriticalPercent) { 'Critical' } elseif ($pct -lt $WarnPercent) { 'Warning' } else { 'OK' }
        }
    }
}

function Get-CertificateStatus {
    <#
    .SYNOPSIS
    Checks the expiry date of every .crt, .cer and .pem certificate in a folder.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [int]$WarnDays = 30
    )
    Get-ChildItem -Path $Path -File -Recurse | Where-Object Extension -In '.crt', '.cer', '.pem' | ForEach-Object {
        $file = $_
        try {
            $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($file.FullName)
            $days = [int][math]::Floor(($cert.NotAfter - (Get-Date)).TotalDays)
            [pscustomobject]@{
                File     = $file.Name
                Subject  = $cert.Subject
                NotAfter = $cert.NotAfter.ToString('yyyy-MM-dd')
                DaysLeft = $days
                Severity = if ($days -lt 0) { 'Critical' } elseif ($days -le $WarnDays) { 'Warning' } else { 'OK' }
                Error    = $null
            }
        }
        catch {
            [pscustomobject]@{ File = $file.Name; Subject = $null; NotAfter = $null
                DaysLeft = $null; Severity = 'Warning'; Error = 'not a readable certificate' }
        }
    }
}

function ConvertTo-HealthHtml($Report) {
    $e = { param($s) [System.Net.WebUtility]::HtmlEncode([string]$s) }
    $badge = @{ OK = '#0b7a3e'; Warning = '#b54708'; Critical = '#b42318' }
    $rows = { param($items, $cols) ($items | ForEach-Object { $i = $_; '<tr>' + (($cols | ForEach-Object { "<td>$(& $e $i.$_)</td>" }) -join '') + '</tr>' }) -join "`n" }
    $findings = ($Report.findings | ForEach-Object {
            "<tr><td><span class='sev' style='background:$($badge[$_.severity])'>$(& $e $_.severity)</span></td><td>$(& $e $_.check)</td><td>$(& $e $_.target)</td><td>$(& $e $_.message)</td></tr>"
        }) -join "`n"
    $h = $Report.http
    @"
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Server health report</title><style>
body{font-family:system-ui,sans-serif;margin:2rem auto;max-width:1100px;padding:0 1rem;color:#1f2933;background:#f7f9fb}
h1{font-size:1.5rem}h2{font-size:1.1rem;margin-top:2rem}
table{border-collapse:collapse;width:100%;background:#fff}td,th{border:1px solid #d9e2ec;padding:.4rem .6rem;text-align:left;font-size:.9rem;word-break:break-word}
th{background:#eef2f6}.sev{color:#fff;border-radius:4px;padding:.1rem .5rem;font-size:.8rem}
.cards{display:flex;gap:1rem;flex-wrap:wrap}.card{background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:.8rem 1.2rem}.card b{display:block;font-size:1.4rem}
</style></head><body>
<h1>Server health report <span class="sev" style="background:$($badge[$Report.status])">$(& $e $Report.status)</span></h1>
<p>$(& $e $Report.host) · $(& $e $Report.generatedAt)</p>
<div class="cards">
<div class="card"><b>$($h.requests)</b>HTTP requests</div>
<div class="card"><b>$($h.serverErrorRate) %</b>5xx errors</div>
<div class="card"><b>$($h.p95Ms) ms</b>p95 latency</div>
<div class="card"><b>$($Report.system.critical) / $($Report.system.errors)</b>critical / error events</div>
</div>
<h2>Findings</h2>
<table><tr><th>Severity</th><th>Check</th><th>Target</th><th>Message</th></tr>
$findings
</table>
<h2>Paths with the most 5xx errors</h2>
<table><tr><th>Path</th><th>5xx</th></tr>
$(& $rows $h.topFailingPaths 'Path', 'Count')
</table>
<h2>Disks</h2>
<table><tr><th>Drive</th><th>Size (GB)</th><th>Free (GB)</th><th>Free %</th><th>Status</th></tr>
$(& $rows $Report.disks 'Name', 'SizeGB', 'FreeGB', 'FreePercent', 'Severity')
</table>
<h2>Certificates</h2>
<table><tr><th>File</th><th>Subject</th><th>Expires</th><th>Days left</th><th>Status</th></tr>
$(& $rows $Report.certificates 'File', 'Subject', 'NotAfter', 'DaysLeft', 'Severity')
</table>
<h2>Recent system errors</h2>
<table><tr><th>Time</th><th>Level</th><th>Source</th><th>Message</th></tr>
$(& $rows $Report.system.samples 'Time', 'Level', 'Source', 'Message')
</table>
</body></html>
"@
}

function Invoke-HealthAudit {
    <#
    .SYNOPSIS
    Runs every check, writes the reports and returns the overall status with an exit code
    (0 OK, 1 Warning, 2 Critical) that monitoring tools and schedulers understand.
    #>
    [CmdletBinding()]
    param(
        [string[]]$AccessLog = @(),
        [string[]]$SystemLog = @(),
        [string[]]$CertificatePath = @(),
        [object[]]$Drives,
        [int]$SlowMs = 1000,
        [double]$ErrorRateWarn = 1,
        [double]$ErrorRateCritical = 5,
        [int]$CertWarnDays = 30,
        [string]$JsonPath,
        [string]$HtmlPath
    )
    $findings = [System.Collections.Generic.List[object]]::new()
    # A missing input is a finding, not a crash: the rest of the audit still runs.
    $existing = {
        param($paths)
        foreach ($p in $paths) {
            if (Test-Path $p) { $p } else { $findings.Add((New-Finding 'Warning' 'missing' $p 'file or folder not found')) }
        }
    }
    $AccessLog = @(& $existing $AccessLog)
    $SystemLog = @(& $existing $SystemLog)
    $CertificatePath = @(& $existing $CertificatePath)

    $entries = @(foreach ($p in $AccessLog) { Read-AccessLog -Path $p })
    $http = Get-HttpLogSummary -Entries $entries -SlowMs $SlowMs
    if ($http.Requests) {
        $sev = if ($http.ServerErrorRate -ge $ErrorRateCritical) { 'Critical' } elseif ($http.ServerErrorRate -ge $ErrorRateWarn) { 'Warning' }
        if ($sev) { $findings.Add((New-Finding $sev 'http-5xx' ($AccessLog -join ', ') "$($http.ServerErrors) of $($http.Requests) requests failed with 5xx ($($http.ServerErrorRate) %)")) }
        if ($http.SlowRequests) { $findings.Add((New-Finding 'Warning' 'http-latency' ($AccessLog -join ', ') "$($http.SlowRequests) requests slower than $SlowMs ms (p95: $($http.P95Ms) ms)")) }
    }

    $system = foreach ($p in $SystemLog) {
        $s = Read-SystemLog -Path $p
        if ($s.Critical) { $findings.Add((New-Finding 'Critical' 'system-log' $p "$(Format-Count $s.Critical 'critical event'), $(Format-Count $s.Errors 'error')")) }
        elseif ($s.Errors) { $findings.Add((New-Finding 'Warning' 'system-log' $p (Format-Count $s.Errors 'error'))) }
        $s
    }

    $disks = @(Get-DiskStatus -Drives $Drives)
    foreach ($d in $disks | Where-Object Severity -NE 'OK') {
        $findings.Add((New-Finding $d.Severity 'disk' $d.Name "$($d.FreePercent) % free ($($d.FreeGB) GB)"))
    }

    $certs = @(foreach ($p in $CertificatePath) { Get-CertificateStatus -Path $p -WarnDays $CertWarnDays })
    foreach ($c in $certs | Where-Object Severity -NE 'OK') {
        $msg = if ($c.Error) { $c.Error } elseif ($c.DaysLeft -lt 0) { "expired on $($c.NotAfter)" } else { "expires in $($c.DaysLeft) days ($($c.NotAfter))" }
        $findings.Add((New-Finding $c.Severity 'certificate' $c.File $msg))
    }

    $worst = ($findings | ForEach-Object { $Severities[$_.Severity] } | Measure-Object -Maximum).Maximum
    $status = @('OK', 'Warning', 'Critical')[[int]$worst]
    $report = [ordered]@{
        generatedAt  = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        host         = [Environment]::MachineName
        status       = $status
        http         = [ordered]@{
            requests = $http.Requests; serverErrors = $http.ServerErrors; clientErrors = $http.ClientErrors
            serverErrorRate = $http.ServerErrorRate; slowRequests = $http.SlowRequests; p95Ms = $http.P95Ms
            topFailingPaths = $http.TopFailingPaths
        }
        system       = [ordered]@{
            errors   = [int]($system | Measure-Object Errors -Sum).Sum
            critical = [int]($system | Measure-Object Critical -Sum).Sum
            samples  = @($system | ForEach-Object Samples)
        }
        disks        = $disks
        certificates = $certs
        findings     = @($findings | ForEach-Object { [ordered]@{ severity = $_.Severity; check = $_.Check; target = $_.Target; message = $_.Message } })
    }
    if ($JsonPath) { $report | ConvertTo-Json -Depth 6 | Set-Content -Path $JsonPath -Encoding utf8 }
    if ($HtmlPath) { ConvertTo-HealthHtml ([pscustomobject]$report) | Set-Content -Path $HtmlPath -Encoding utf8 }

    [pscustomobject]@{ Status = $status; ExitCode = [int]$worst; Findings = $findings; Report = $report }
}

Export-ModuleMember -Function Read-AccessLog, Get-HttpLogSummary, Read-SystemLog, Get-DiskStatus,
    Get-CertificateStatus, Invoke-HealthAudit
