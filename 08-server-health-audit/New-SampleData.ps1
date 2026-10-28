<#
.SYNOPSIS
Creates sample/ with one day of IIS and Nginx logs, a syslog, a Windows event export and
three certificates (expired, expiring soon, valid). All the data is generated and fake.
#>
$root = Join-Path $PSScriptRoot 'sample'
Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
$logs = New-Item -ItemType Directory (Join-Path $root 'logs') -Force
$certs = New-Item -ItemType Directory (Join-Path $root 'certs') -Force
$rng = [Random]::new(7)
$day = [datetime]'2026-10-27'

# IIS: a normal day, then the /api/orders back end starts failing in the afternoon.
$iis = [System.Collections.Generic.List[string]]::new()
$iis.Add('#Software: Microsoft Internet Information Services 10.0')
$iis.Add('#Fields: date time s-ip cs-method cs-uri-stem cs-uri-query s-port cs-username c-ip cs(User-Agent) sc-status sc-substatus sc-win32-status time-taken')
$pages = '/', '/products', '/products/42', '/cart', '/api/orders', '/login', '/static/app.js'
for ($i = 0; $i -lt 2000; $i++) {
    $t = $day.AddSeconds($i * 43)
    $path = $pages[$rng.Next($pages.Count)]
    $status = 200; $ms = $rng.Next(15, 180)
    if ($path -eq '/api/orders' -and $t.Hour -ge 14) { $status = 503; $ms = $rng.Next(2500, 6000) }
    elseif ($rng.Next(100) -lt 2) { $status = 404 }
    $iis.Add("$($t.ToString('yyyy-MM-dd HH:mm:ss')) 10.0.0.5 GET $path - 443 - 203.0.113.$($rng.Next(1,250)) Mozilla/5.0 $status 0 0 $ms")
}
$iis | Set-Content (Join-Path $logs 'u_ex261027.log')

# Nginx in front of a Linux service, with request_time at the end of each line.
$nginx = for ($i = 0; $i -lt 500; $i++) {
    $t = $day.AddMinutes($i * 2).ToString('dd/MMM/yyyy:HH:mm:ss', [Globalization.CultureInfo]::InvariantCulture)
    $status = if ($rng.Next(100) -lt 1) { 502 } else { 200 }
    "198.51.100.$($rng.Next(1,250)) - - [$t -0400] `"GET /api/stock HTTP/1.1`" $status 512 `"-`" `"curl/8.5`" $(($rng.Next(20, 400) / 1000).ToString([Globalization.CultureInfo]::InvariantCulture))"
}
$nginx | Set-Content (Join-Path $logs 'access.log')

@(
    'Oct 27 06:00:01 web01 systemd[1]: Started Daily apt upgrade.'
    'Oct 27 14:02:11 web01 kernel: EXT4-fs error (device sda1): ext4_find_entry: reading directory lblock 0'
    'Oct 27 14:05:42 web01 orders-api[2231]: ERROR database connection pool exhausted'
    'Oct 27 14:05:43 web01 orders-api[2231]: ERROR database connection pool exhausted'
    'Oct 27 14:06:00 web01 nginx[812]: [crit] 812#812: *4411 connect() to unix:/run/orders.sock failed'
    'Oct 27 15:00:01 web01 CRON[901]: (root) CMD (/usr/local/bin/backup.sh)'
) | Set-Content (Join-Path $logs 'syslog')

@(
    [pscustomobject]@{ TimeCreated = '2026-10-27 14:01:12'; LevelDisplayName = 'Error'; ProviderName = 'Service Control Manager'; Id = 7031; Message = 'The World Wide Web Publishing Service terminated unexpectedly.' }
    [pscustomobject]@{ TimeCreated = '2026-10-27 14:01:15'; LevelDisplayName = 'Warning'; ProviderName = 'WAS'; Id = 5011; Message = 'A process serving application pool Orders suffered a fatal communication error.' }
    [pscustomobject]@{ TimeCreated = '2026-10-27 15:30:00'; LevelDisplayName = 'Information'; ProviderName = 'IIS-W3SVC'; Id = 1074; Message = 'Application pool recycled.' }
) | Export-Csv (Join-Path $logs 'system-events.csv') -NoTypeInformation

function New-Cert($name, $days) {
    $rsa = [System.Security.Cryptography.RSA]::Create(2048)
    $req = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new("CN=$name", $rsa,
        [System.Security.Cryptography.HashAlgorithmName]::SHA256, [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
    $now = [DateTimeOffset]::Now
    $req.CreateSelfSigned($now.AddDays(-365), $now.AddDays($days)).ExportCertificatePem() |
        Set-Content (Join-Path $certs "$name.crt")
}
New-Cert 'old.example.test' -3
New-Cert 'shop.example.test' 9
New-Cert 'api.example.test' 240
"Sample data created in $root"
