$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$setupScriptPath = Join-Path $projectRoot "deploy\oci\setup_vm.sh"
$sshKey = "C:\Users\lsota\Downloads\ssh-key-2026-08-17.key"
$ip = "137.131.162.168"
$remote = "opc@$ip"

if (-not (Test-Path -LiteralPath $sshKey)) {
    throw "Chave SSH não encontrada: $sshKey"
}
if (-not (Test-Path -LiteralPath $setupScriptPath)) {
    throw "Instalador remoto não encontrado: $setupScriptPath"
}

Write-Host "Deploy OCI leve (sem Docker)" -ForegroundColor Cyan
Write-Host "Destino: $remote" -ForegroundColor DarkGray

$secureApiKey = Read-Host -Prompt "Cole sua chave da Gemini API" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureApiKey)
try {
    $plainApiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if ([string]::IsNullOrWhiteSpace($plainApiKey)) {
        throw "A chave Gemini não pode ficar vazia."
    }
    $apiKeyBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($plainApiKey))
}
finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    $plainApiKey = $null
}

$sshArgs = @(
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=15",
    "-o", "ServerAliveInterval=15",
    "-o", "ServerAliveCountMax=4",
    "-o", "StrictHostKeyChecking=no",
    "-i", $sshKey
)

Write-Host "[1/3] Verificando o SSH..." -ForegroundColor Yellow
& ssh @sshArgs $remote "echo SSH_READY"
if ($LASTEXITCODE -ne 0) {
    throw "A VM não respondeu ao SSH. Reinicie a instância na console OCI, aguarde 2 minutos e execute este script novamente."
}

$remoteScript = Get-Content -Raw -LiteralPath $setupScriptPath
$payload = "export GEMINI_API_KEY_B64='$apiKeyBase64'`n$remoteScript"
$apiKeyBase64 = $null

Write-Host "[2/3] Instalando diretamente no Python da VM..." -ForegroundColor Yellow
$payload | & ssh @sshArgs $remote "bash -s"
if ($LASTEXITCODE -ne 0) {
    throw "O instalador remoto terminou com erro. A última etapa exibida acima identifica a causa."
}

Write-Host "[3/3] Testando a URL pública..." -ForegroundColor Yellow
$url = "http://${ip}:8501"
try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "$url/_stcore/health" -TimeoutSec 15
    if ($response.StatusCode -eq 200) {
        Write-Host "DEPLOY CONCLUÍDO: $url" -ForegroundColor Green
    }
}
catch {
    Write-Warning "O serviço iniciou na VM, mas a porta 8501 não está pública. Na VCN da OCI, adicione uma regra de entrada TCP para a porta 8501 e teste: $url"
}
