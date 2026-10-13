[CmdletBinding()]
param(
    [ValidateSet("Install", "Doctor", "Check")][string]$Action = "Install",
    [string]$Distro = "OpenClawGateway",
    [string]$NodePath = "",
    [string]$PythonPath = "",
    [switch]$NoRestart
)
# This script installs from the reviewed checkout or the extracted portable bundle.
# Standard output is one JSON object; dependency output stays in a local build log.
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = $PSScriptRoot
$originalPath = $env:PATH
$result = $null
$resultPath = $null
$code = "prerequisite_missing"
function Invoke-Logged([string]$Program, [string[]]$Arguments) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Program @Arguments >> $script:logPath 2>&1
    } finally { $ErrorActionPreference = $previousPreference }
    if ($LASTEXITCODE -ne 0) { throw "command_failed" }
}
Push-Location $root
try {
    if ($env:OS -ne "Windows_NT") { throw "windows_required" }
    $exe = Join-Path $root "OpenClawKakaoLocal.exe"
    $bundled = Test-Path -LiteralPath $exe
    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    if (!$bundled) {
        if (!$PythonPath) {
            if (Test-Path -LiteralPath $venvPython) { $PythonPath = $venvPython }
            else { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
        }
        $PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
        $version = & $PythonPath -c "import sys; print('.'.join(map(str,sys.version_info[:2])))"
        if ($LASTEXITCODE -ne 0 -or $version -ne "3.11") { throw "python_311_required" }
        if ($Action -ne "Doctor") {
            if (!$NodePath) {
                $cached = Join-Path $root ".cache\node-v24.19.0-win-x64\node.exe"
                if (Test-Path -LiteralPath $cached) { $NodePath = $cached }
                else { $NodePath = (Get-Command node -ErrorAction Stop).Source }
            }
            $NodePath = (Resolve-Path -LiteralPath $NodePath).Path
            $nodeVersion = & $NodePath --version
            if ($LASTEXITCODE -ne 0 -or $nodeVersion -ne "v24.19.0") { throw "node_24_19_0_required" }
            $npm = Join-Path (Split-Path $NodePath) "node_modules\npm\bin\npm-cli.js"
            if (!(Test-Path -LiteralPath $npm)) { throw "npm_required" }
            $env:PATH = (Split-Path $NodePath) + [IO.Path]::PathSeparator + $originalPath
        }
    }
    Get-Command wsl.exe -ErrorAction Stop | Out-Null
    if ($Action -eq "Check") {
        $result = @{ok=$true; code="prerequisites_found"; gatewayVerified=$false; next="run_install"}
    } else {
        $cache = Join-Path $root ".cache"
        New-Item -ItemType Directory -Force -Path $cache | Out-Null
        $script:logPath = Join-Path $cache "install-build.log"
        $resultPath = Join-Path $cache ("install-result-" + [guid]::NewGuid().ToString("N") + ".json")
        if ($Action -eq "Install") {
            if (!$bundled) {
                $code = "dependency_install_failed"
                if (!(Test-Path -LiteralPath $venvPython)) { Invoke-Logged $PythonPath @("-m", "venv", ".venv") }
                Invoke-Logged $venvPython @("-m", "pip", "install", "-e", ".\apps\windows-bridge")
                Invoke-Logged $NodePath @($npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund")
                $code = "channel_build_failed"
                Invoke-Logged $NodePath @($npm, "run", "build")
                New-Item -ItemType Directory -Force -Path "dist" | Out-Null
                Invoke-Logged $NodePath @($npm, "pack", "--workspace", "packages/openclaw-kakao-channel", "--pack-destination", "dist", "--ignore-scripts")
                $version = (Get-Content -Raw -Encoding UTF8 "package.json" | ConvertFrom-Json).version
                $package = Join-Path $root "dist\openclaw-kakao-channel-$version.tgz"
                $hash = (Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant()
                [IO.File]::WriteAllText("$package.sha256", "$hash`n", [Text.UTF8Encoding]::new($false))
            } else {
                $packages = @(Get-ChildItem -LiteralPath $root -Filter "openclaw-kakao-channel-*.tgz" -File)
                if ($packages.Count -ne 1) { throw "one_channel_package_required" }
                $package = $packages[0].FullName
            }
            $arguments = @("--install", "--package", $package, "--distro", $Distro)
            if (!$NoRestart) { $arguments += "--restart-gateway" }
        } else { $arguments = @("--doctor") }
        $arguments += @("--result-file", $resultPath)
        $code = "bootstrap_failed"
        if ($bundled) {
            # All arguments are data, not PowerShell expressions. Reject quote injection.
            foreach ($argument in $arguments) { if ($argument.Contains('"')) { throw "invalid_argument" } }
            $quoted = ($arguments | ForEach-Object { '"' + $_ + '"' }) -join " "
            $process = Start-Process -FilePath $exe -ArgumentList $quoted -WindowStyle Hidden -Wait -PassThru
        } else {
            if (!(Test-Path -LiteralPath $venvPython)) { throw "run_install_first" }
            # Bootstrap writes its own JSON even when it exits with a diagnostic failure.
            $previousPreference = $ErrorActionPreference
            try { $ErrorActionPreference = "Continue"; & $venvPython -m kakao_local.main @arguments >> $script:logPath 2>&1 }
            finally { $ErrorActionPreference = $previousPreference }
        }
        if (!(Test-Path -LiteralPath $resultPath)) { throw "bootstrap_result_missing" }
        $result = Get-Content -Raw -Encoding UTF8 -LiteralPath $resultPath | ConvertFrom-Json
    }
} catch {
    $result = @{ok=$false; code=$code; next="read_INSTALL_AGENT.md"}
} finally {
    $env:PATH = $originalPath
    Pop-Location
    if ($resultPath -and (Test-Path -LiteralPath $resultPath)) { Remove-Item -LiteralPath $resultPath }
}
$result | ConvertTo-Json -Compress -Depth 5
if (!$result.ok) { exit 1 }
