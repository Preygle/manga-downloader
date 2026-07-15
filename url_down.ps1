param (
    [string]$BaseUrl = "https://read-monster.com/",
    [int]$Threads = 32
)

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13

$MainUrl = "$BaseUrl"
if (-not $MainUrl.EndsWith("/")) { $MainUrl += "/" }

$SiteName = $BaseUrl -replace 'https?://(www\.)?([^/]+).*','$2'
$OutRoot = ".\$SiteName"
if (-not (Test-Path $OutRoot)) { New-Item -ItemType Directory -Force -Path $OutRoot | Out-Null }

Write-Host "Fetching chapter links..."
$html = Invoke-WebRequest -Uri $MainUrl -UseBasicParsing | Select-Object -ExpandProperty Content
$pattern = '(?i)<a\s+[^>]*href="([^"]*)"'
$chapters = ([regex]::Matches($html, $pattern) | ForEach-Object { $_.Groups[1].Value } | Where-Object { $_ -match "/manga/monster-chapter-" } | Select-Object -Unique)

if (-not $chapters) {
    Write-Host "No chapters found! Check the URL or patterns."
    exit
}

$chapters | Out-File -FilePath "chapters.txt" -Encoding ascii
$Total = @($chapters).Count
Write-Host "Found $Total chapters."
Write-Host "Saved to chapters.txt"

Read-Host "Press ENTER to start download..." | Out-Null
$startChapStr = Read-Host "Start download from chapter (press ENTER for all)"
$StartChapter = 0
if (-not [string]::IsNullOrWhiteSpace($startChapStr)) {
    $StartChapter = [double]$startChapStr
}

$ScriptBlock = {
    param($url, $BaseUrl, $OutRoot)
    
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
    
    if ($url -match "^https?://") {
        $FullUrl = $url
    } else {
        if (-not $url.StartsWith("/")) { $url = "/$url" }
        $FullUrl = "$BaseUrl$url"
    }

    $chap = [System.IO.Path]::GetFileName($url)
    if ($chap -eq "") {
        $chap = ($url -split "/")[-1]
    }
    if ($chap -eq "") {
        $chap = ($url -split "/")[-2]
    }
    
    $OutDir = "$OutRoot/$chap"
    if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }
    
    Write-Output ">>> Downloading $chap"
    
    try {
        $chapHtml = Invoke-WebRequest -Uri $FullUrl -UseBasicParsing | Select-Object -ExpandProperty Content
        $pattern = '(?i)<img[^>]+src="([^"]+)"'
        $images = ([regex]::Matches($chapHtml, $pattern) | ForEach-Object { $_.Groups[1].Value } | Where-Object { $_ -match "\.(jpg|jpeg|png|webp)" } | Select-Object -Unique)
        
        $count = 1
        foreach ($img in $images) {
            $ext = ($img -split '\.')[-1]
            $save_ext = ($ext -split '\?')[0]
            $outFile = "$OutDir\$count.$save_ext"
            Invoke-WebRequest -Uri $img -OutFile $outFile -UseBasicParsing | Out-Null
            $count++
        }
        
        Write-Output "<<< Finished $chap"
    } catch {
        Write-Output "Error downloading $chap : $_"
    }
}

$pool = [runspacefactory]::CreateRunspacePool(1, $Threads)
$pool.Open()
$runspaces = @()

foreach ($url in $chapters) {
    if ($StartChapter -gt 0) {
        if ($url -match "chapter-([0-9.]+)") {
            $chapNum = [double]$Matches[1]
            if ($chapNum -lt $StartChapter) {
                continue
            }
        }
    }
    
    $ps = [powershell]::Create().AddScript($ScriptBlock).AddArgument($url).AddArgument($BaseUrl).AddArgument($OutRoot)
    $ps.RunspacePool = $pool
    
    $runspaces += [PSCustomObject]@{
        Pipe = $ps
        Status = $ps.BeginInvoke()
    }
}

while ($runspaces.Status.IsCompleted -contains $false) {
    foreach ($rs in $runspaces) {
        if ($rs.Status -and $rs.Status.IsCompleted) {
            $output = $rs.Pipe.EndInvoke($rs.Status)
            if ($output) { $output | Write-Host }
            $rs.Pipe.Dispose()
            $rs.Status = $null
        }
    }
    $runspaces = $runspaces | Where-Object { $null -ne $_.Status }
    Start-Sleep -Milliseconds 200
}

foreach ($rs in $runspaces) {
    if ($rs.Status) {
        $output = $rs.Pipe.EndInvoke($rs.Status)
        if ($output) { $output | Write-Host }
        $rs.Pipe.Dispose()
    }
}

$pool.Close()
$pool.Dispose()

Write-Host "================================="
Write-Host "All chapters downloaded."
Write-Host "Saved under: $OutRoot"
$OutRoot | Out-File -FilePath "download_dir.txt" -Encoding ascii
Write-Host "================================="
