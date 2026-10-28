<#
.SYNOPSIS
Audits a web server: HTTP logs (IIS or Nginx/Apache), system logs, disk space and certificates.

.EXAMPLE
./Invoke-HealthAudit.ps1 -AccessLog sample/logs/u_ex261027.log, sample/logs/access.log `
    -SystemLog sample/logs/syslog, sample/logs/system-events.csv -CertificatePath sample/certs `
    -JsonPath report.json -HtmlPath report.html

.EXAMPLE
# On a Windows server, in a scheduled task:
./Invoke-HealthAudit.ps1 -AccessLog (Get-ChildItem C:\inetpub\logs\LogFiles\W3SVC1\*.log) `
    -CertificatePath C:\certs -HtmlPath C:\reports\health.html
#>
[CmdletBinding()]
param(
    [string[]]$AccessLog = @(),
    [string[]]$SystemLog = @(),
    [string[]]$CertificatePath = @(),
    [int]$SlowMs = 1000,
    [double]$ErrorRateWarn = 1,
    [double]$ErrorRateCritical = 5,
    [int]$CertWarnDays = 30,
    [string]$JsonPath,
    [string]$HtmlPath
)
Import-Module (Join-Path $PSScriptRoot 'ServerHealth.psm1') -Force
# From bash (pwsh -File), "a.log,b.log" arrives as one string: split it.
foreach ($name in 'AccessLog', 'SystemLog', 'CertificatePath') {
    if ($PSBoundParameters.ContainsKey($name)) { $PSBoundParameters[$name] = @($PSBoundParameters[$name] -split ',') }
}
$result = Invoke-HealthAudit @PSBoundParameters

$h = $result.Report.http
"Status: $($result.Status)"
"HTTP: $($h.requests) requests, $($h.serverErrorRate) % 5xx, p95 $($h.p95Ms) ms"
$result.Findings | Format-Table Severity, Check, Target, Message -AutoSize -Wrap | Out-String -Width 120
if ($JsonPath) { "JSON report: $JsonPath" }
if ($HtmlPath) { "HTML report: $HtmlPath" }
exit $result.ExitCode
