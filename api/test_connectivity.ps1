# apis.data.go.kr 연결 테스트용 스크립트 (사용자 PC에서 직접 실행)
$envPath = Join-Path $PSScriptRoot ".env"
$envVars = @{}
Get-Content $envPath -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k, $v = $_ -split '=', 2
    $envVars[$k.Trim()] = $v.Trim().Trim('"').Trim("'")
}

$key = $envVars["KMA_SERVICE_KEY_DECODED"]
$base = (Get-Date).AddHours(-1).ToString("yyyyMMdd")
$time = (Get-Date).AddHours(-1).ToString("HH") + "30"

$uri = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst"
$params = @{
    serviceKey = $key
    numOfRows  = 10
    pageNo     = 1
    dataType   = "JSON"
    base_date  = $base
    base_time  = $time
    nx         = 60
    ny         = 127
}

Write-Host "요청 대상: $uri"
try {
    $res = Invoke-RestMethod -Uri $uri -Body $params -Method Get -TimeoutSec 10
    Write-Host "성공! resultCode: $($res.response.header.resultCode) / $($res.response.header.resultMsg)"
    $res.response.body.items.item | Format-Table
} catch {
    Write-Host "실패: $($_.Exception.Message)"
}
