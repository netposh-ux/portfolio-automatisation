BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..' 'ServerHealth.psm1') -Force

    function New-TestCertificate([string]$Path, [int]$DaysLeft) {
        $rsa = [System.Security.Cryptography.RSA]::Create(2048)
        $req = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
            "CN=$([IO.Path]::GetFileNameWithoutExtension($Path))", $rsa,
            [System.Security.Cryptography.HashAlgorithmName]::SHA256,
            [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
        $now = [DateTimeOffset]::Now
        $cert = $req.CreateSelfSigned($now.AddDays(-400), $now.AddDays($DaysLeft))
        Set-Content -Path $Path -Value $cert.ExportCertificatePem()
    }
}

Describe 'Read-AccessLog' {
    It 'parses IIS W3C logs using the #Fields header' {
        $log = Join-Path $TestDrive 'u_ex261027.log'
        @(
            '#Software: Microsoft Internet Information Services 10.0'
            '#Fields: date time s-ip cs-method cs-uri-stem cs-uri-query s-port cs-username c-ip cs(User-Agent) sc-status sc-substatus sc-win32-status time-taken'
            '2026-10-27 08:00:01 10.0.0.5 GET /index.html - 443 - 203.0.113.9 Mozilla/5.0 200 0 0 35'
            '2026-10-27 08:00:02 10.0.0.5 POST /api/orders - 443 - 203.0.113.9 curl/8.0 500 0 0 2300'
        ) | Set-Content $log
        $entries = @(Read-AccessLog -Path $log)
        $entries.Count | Should -Be 2
        $entries[1].Status | Should -Be 500
        $entries[1].Path | Should -Be '/api/orders'
        $entries[1].Method | Should -Be 'POST'
        $entries[1].TimeTakenMs | Should -Be 2300
        $entries[0].Time | Should -Be ([datetime]'2026-10-27 08:00:01')
    }

    It 'parses Nginx/Apache combined logs with an optional request time' {
        $log = Join-Path $TestDrive 'access.log'
        @(
            '203.0.113.9 - - [27/Oct/2026:10:00:01 -0400] "GET /api/orders?id=4 HTTP/1.1" 502 157 "-" "curl/8.0" 1.204'
            '198.51.100.7 - - [27/Oct/2026:10:00:02 -0400] "GET /health HTTP/1.1" 200 2 "-" "kube-probe"'
        ) | Set-Content $log
        $entries = @(Read-AccessLog -Path $log)
        $entries.Count | Should -Be 2
        $entries[0].Status | Should -Be 502
        $entries[0].Path | Should -Be '/api/orders'
        $entries[0].TimeTakenMs | Should -Be 1204
        $entries[1].TimeTakenMs | Should -BeNullOrEmpty
    }

    It 'skips lines it cannot read and counts them' {
        $log = Join-Path $TestDrive 'mixed.log'
        @('garbage line', '198.51.100.7 - - [27/Oct/2026:10:00:02 -0400] "GET / HTTP/1.1" 200 2 "-" "x"') | Set-Content $log
        $entries = @(Read-AccessLog -Path $log -WarningVariable w -WarningAction SilentlyContinue)
        $entries.Count | Should -Be 1
        "$w" | Should -Match '1 line'
    }
}

Describe 'Get-HttpLogSummary' {
    BeforeAll {
        $entries = @(
            1..90 | ForEach-Object { [pscustomobject]@{ Status = 200; Path = '/'; TimeTakenMs = 50 } }
            1..6  | ForEach-Object { [pscustomobject]@{ Status = 503; Path = '/api/orders'; TimeTakenMs = 3000 } }
            1..2  | ForEach-Object { [pscustomobject]@{ Status = 500; Path = '/login'; TimeTakenMs = 120 } }
            1..2  | ForEach-Object { [pscustomobject]@{ Status = 404; Path = '/missing'; TimeTakenMs = 10 } }
        )
        $s = Get-HttpLogSummary -Entries $entries -SlowMs 1000
    }
    It 'counts requests, 5xx and 4xx'   { $s.Requests | Should -Be 100; $s.ServerErrors | Should -Be 8; $s.ClientErrors | Should -Be 2 }
    It 'computes the 5xx rate in %'     { $s.ServerErrorRate | Should -Be 8 }
    It 'counts slow requests'           { $s.SlowRequests | Should -Be 6 }
    It 'computes the 95th percentile'   { $s.P95Ms | Should -Be 3000 }
    It 'lists the paths failing most'   { $s.TopFailingPaths[0].Path | Should -Be '/api/orders'; $s.TopFailingPaths[0].Count | Should -Be 6 }
}

Describe 'Read-SystemLog' {
    It 'counts errors and critical events in a Linux syslog' {
        $log = Join-Path $TestDrive 'syslog'
        @(
            'Oct 27 08:00:01 web01 systemd[1]: Started nginx.service.'
            'Oct 27 08:05:12 web01 kernel: EXT4-fs error (device sda1): bad block'
            'Oct 27 08:06:00 web01 nginx[812]: [crit] 812#812: connect() failed'
            'Oct 27 08:07:00 web01 CRON[901]: (root) CMD (backup)'
        ) | Set-Content $log
        $r = Read-SystemLog -Path $log
        $r.Errors | Should -Be 1
        $r.Critical | Should -Be 1
        $r.TopSources[0].Source | Should -BeIn @('kernel', 'nginx')
    }

    It 'reads a Windows event log exported to CSV' {
        $csv = Join-Path $TestDrive 'system.csv'
        @(
            [pscustomobject]@{ TimeCreated = '2026-10-27 08:00:00'; LevelDisplayName = 'Error'; ProviderName = 'Service Control Manager'; Id = 7031; Message = 'The W3SVC service terminated' }
            [pscustomobject]@{ TimeCreated = '2026-10-27 08:01:00'; LevelDisplayName = 'Critical'; ProviderName = 'Microsoft-Windows-Kernel-Power'; Id = 41; Message = 'Unexpected reboot' }
            [pscustomobject]@{ TimeCreated = '2026-10-27 08:02:00'; LevelDisplayName = 'Information'; ProviderName = 'IIS-W3SVC'; Id = 1; Message = 'ok' }
        ) | Export-Csv -Path $csv -NoTypeInformation
        $r = Read-SystemLog -Path $csv
        $r.Errors | Should -Be 1
        $r.Critical | Should -Be 1
        $r.Samples.Count | Should -Be 2
    }
}

Describe 'Get-DiskStatus' {
    It 'flags low free space' {
        $drives = @(
            [pscustomobject]@{ Name = 'C'; Used = 96GB; Free = 4GB }
            [pscustomobject]@{ Name = 'D'; Used = 88GB; Free = 12GB }
            [pscustomobject]@{ Name = 'E'; Used = 50GB; Free = 50GB }
        )
        $r = Get-DiskStatus -Drives $drives -WarnPercent 15 -CriticalPercent 5
        ($r | Where-Object Name -EQ 'C').Severity | Should -Be 'Critical'
        ($r | Where-Object Name -EQ 'D').Severity | Should -Be 'Warning'
        ($r | Where-Object Name -EQ 'E').Severity | Should -Be 'OK'
        ($r | Where-Object Name -EQ 'D').FreePercent | Should -Be 12
    }

    It 'reads the real drives when none are given' {
        @(Get-DiskStatus).Count | Should -BeGreaterThan 0
    }
}

Describe 'Get-CertificateStatus' {
    It 'flags expired and soon-to-expire certificates' {
        $dir = Join-Path $TestDrive 'certs'
        New-Item -ItemType Directory $dir | Out-Null
        New-TestCertificate (Join-Path $dir 'expired.crt') -10
        New-TestCertificate (Join-Path $dir 'soon.pem') 12
        New-TestCertificate (Join-Path $dir 'fine.cer') 200
        $r = Get-CertificateStatus -Path $dir -WarnDays 30
        ($r | Where-Object File -EQ 'expired.crt').Severity | Should -Be 'Critical'
        ($r | Where-Object File -EQ 'soon.pem').Severity | Should -Be 'Warning'
        ($r | Where-Object File -EQ 'soon.pem').DaysLeft | Should -BeIn 11, 12
        ($r | Where-Object File -EQ 'fine.cer').Severity | Should -Be 'OK'
    }

    It 'reports a file that is not a certificate instead of failing' {
        $dir = Join-Path $TestDrive 'bad'
        New-Item -ItemType Directory $dir | Out-Null
        Set-Content (Join-Path $dir 'broken.crt') 'not a certificate'
        $r = Get-CertificateStatus -Path $dir
        $r.Severity | Should -Be 'Warning'
        $r.File | Should -Be 'broken.crt'
    }
}

Describe 'Invoke-HealthAudit' {
    BeforeAll {
        $root = Join-Path $TestDrive 'server'
        New-Item -ItemType Directory (Join-Path $root 'logs'), (Join-Path $root 'certs') | Out-Null
        @(
            '#Fields: date time cs-method cs-uri-stem sc-status time-taken'
            '2026-10-27 08:00:01 GET /<script>alert(1)</script> 500 40'
            '2026-10-27 08:00:02 GET / 200 30'
        ) | Set-Content (Join-Path $root 'logs' 'u_ex261027.log')
        'Oct 27 08:05:12 web01 kernel: EXT4-fs error (device sda1)' | Set-Content (Join-Path $root 'logs' 'syslog')
        New-TestCertificate (Join-Path $root 'certs' 'site.crt') 5
        $json = Join-Path $TestDrive 'report.json'
        $html = Join-Path $TestDrive 'report.html'
        $drives = @([pscustomobject]@{ Name = '/'; Used = 40GB; Free = 60GB })
        $result = Invoke-HealthAudit -AccessLog (Join-Path $root 'logs' 'u_ex261027.log') `
            -SystemLog (Join-Path $root 'logs' 'syslog') -CertificatePath (Join-Path $root 'certs') `
            -Drives $drives -JsonPath $json -HtmlPath $html
    }

    It 'gives an overall status from the worst finding' { $result.Status | Should -Be 'Critical' }
    It 'returns an exit code for monitoring tools'     { $result.ExitCode | Should -Be 2 }

    It 'writes a JSON report' {
        $r = Get-Content $json -Raw | ConvertFrom-Json
        $r.status | Should -Be 'Critical'
        $r.http.requests | Should -Be 2
        $r.http.serverErrorRate | Should -Be 50
        @($r.findings | Where-Object check -EQ 'certificate').Count | Should -Be 1
    }

    It 'writes an HTML report with escaped content' {
        $h = Get-Content $html -Raw
        $h | Should -Match '^<!doctype html>'
        $h | Should -Match '&lt;script&gt;'
        $h | Should -Not -Match '<script>alert'
    }
}

Describe 'Invoke-HealthAudit with missing files' {
    It 'reports a missing log as a finding and keeps going' {
        $drives = @([pscustomobject]@{ Name = '/'; Used = 40GB; Free = 60GB })
        $r = Invoke-HealthAudit -AccessLog (Join-Path $TestDrive 'nope.log') -SystemLog (Join-Path $TestDrive 'nope-syslog') `
            -CertificatePath (Join-Path $TestDrive 'no-certs') -Drives $drives -ErrorAction Stop
        $r.Status | Should -Be 'Warning'
        @($r.Findings | Where-Object Check -EQ 'missing').Count | Should -Be 3
    }
}
