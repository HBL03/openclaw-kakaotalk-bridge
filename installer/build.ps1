[CmdletBinding()]
param(
    [switch]$PortableOnly,
    [switch]$PublicRelease,
    [string]$Evidence = "release-evidence.local.json",
    [string]$CertificateThumbprint = "",
    [string]$NodePath = "",
    [string]$PythonPath = "",
    [string]$IsccPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (!$NodePath) { $NodePath = (Get-Command node -ErrorAction Stop).Source }
if (!$PythonPath) { $PythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe" }
$NodePath = (Resolve-Path -LiteralPath $NodePath).Path
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$npmCli = Join-Path (Split-Path $NodePath) "node_modules\npm\bin\npm-cli.js"
if (!(Test-Path -LiteralPath $npmCli)) { throw "Use the official Node 24 distribution with npm." }
function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    Get-Command $Program -ErrorAction Stop | Out-Null
    # Windows PowerShell 5 turns redirected native stderr into ErrorRecord objects.
    # Tools such as npm/PyInstaller write progress there even on successful runs.
    $previousErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Program @Arguments
    } finally { $ErrorActionPreference = $previousErrorPreference }
    if ($LASTEXITCODE -ne 0) { throw "Build command failed: $Program (exit $LASTEXITCODE)" }
}
function Sign-Checked([string]$File) {
    if ($CertificateThumbprint -notmatch '^[0-9A-Fa-f]{40}$') { throw "Public builds require a code-signing certificate thumbprint." }
    Invoke-Checked "signtool.exe" @("sign", "/sha1", $CertificateThumbprint, "/fd", "SHA256", "/tr", "http://timestamp.digicert.com", "/td", "SHA256", $File)
    $signature = Get-AuthenticodeSignature -LiteralPath $File
    if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Thumbprint -ne $CertificateThumbprint) {
        throw "Authenticode signature validation failed."
    }
}
$previousPath = $env:PATH
Push-Location $projectRoot
try {
    $env:PATH = (Split-Path $NodePath) + [IO.Path]::PathSeparator + $previousPath
    Invoke-Checked $NodePath @("-e", "const [a,b]=process.versions.node.split('.').map(Number);if(a!==24||b<16)process.exit(1)")
    if ($PublicRelease) {
        if ($PortableOnly) { throw "Public releases must also build the installer." }
        Invoke-Checked $PythonPath @("scripts/check_release.py", "--evidence", $Evidence)
        if ($CertificateThumbprint -notmatch '^[0-9A-Fa-f]{40}$') { throw "Code-signing certificate required." }
    }
    Invoke-Checked $NodePath @($npmCli, "run", "build")
    $distPath = Join-Path $projectRoot "dist"
    New-Item -ItemType Directory -Force -Path $distPath | Out-Null
    Invoke-Checked $NodePath @($npmCli, "pack", "--workspace", "packages/openclaw-kakao-channel", "--pack-destination", $distPath, "--ignore-scripts")
    $version = (Get-Content -Raw -Encoding UTF8 package.json | ConvertFrom-Json).version
    $packagePath = Join-Path $distPath "openclaw-kakao-channel-$version.tgz"
    if (!(Test-Path -LiteralPath $packagePath)) { throw "Channel package version mismatch." }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $packagePath).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText("$packagePath.sha256", "$hash  $([IO.Path]::GetFileName($packagePath))`n", [Text.UTF8Encoding]::new($false))
    Invoke-Checked $PythonPath @("-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir", "--name", "OpenClawKakaoLocal", "--distpath", $distPath, "--workpath", "build/pyinstaller", "--specpath", "build", "--paths", "apps/windows-bridge/src", "apps/windows-bridge/launcher.py")
    $appPath = Join-Path $distPath "OpenClawKakaoLocal"
    Copy-Item -LiteralPath "LICENSE", "THIRD_PARTY_NOTICES.md", "README.md", "SECURITY.md" -Destination $appPath
    Copy-Item -LiteralPath "docs", "contracts", "release" -Destination $appPath -Recurse -Force
    Copy-Item -LiteralPath "OpenClaw_KakaoTalk_Local_Bridge_Implementation_Plan.md" -Destination $appPath
    Copy-Item -LiteralPath $packagePath, "$packagePath.sha256" -Destination $appPath
    Invoke-Checked $PythonPath @("scripts/collect_licenses.py", (Join-Path $appPath "licenses"))
    if ($PublicRelease) { Sign-Checked (Join-Path $appPath "OpenClawKakaoLocal.exe") }
    $zipPath = Join-Path $distPath "openclaw-kakaotalk-bridge-$version-windows-x64.zip"
    Compress-Archive -LiteralPath $appPath -DestinationPath $zipPath -Force
    if (!$PortableOnly) {
        if (!(Test-Path -LiteralPath $IsccPath)) { throw "Inno Setup 6 compiler missing. Use -IsccPath or -PortableOnly." }
        $compilerArgs = @("/DAppVersion=$version", "/DSourceRoot=$projectRoot")
        if ($PublicRelease) {
            $signCommand = 'signtool.exe sign /sha1 ' + $CertificateThumbprint + ' /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $f'
            $compilerArgs += @("/DPublicBuild=1", "/Sbridge=$signCommand")
        }
        $compilerArgs += "installer/windows.iss"
        Invoke-Checked $IsccPath $compilerArgs
        if ($PublicRelease) { Sign-Checked (Join-Path $distPath "openclaw-kakaotalk-bridge-$version-setup.exe") }
    }
    $checksums = Get-ChildItem -LiteralPath $distPath -File | Where-Object { $_.Extension -in @(".exe", ".zip", ".tgz") } | ForEach-Object {
        (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() + "  " + $_.Name
    }
    [IO.File]::WriteAllLines((Join-Path $distPath "SHA256SUMS.txt"), [string[]]$checksums, [Text.UTF8Encoding]::new($false))
    Write-Output "Build complete: $distPath (public release: $PublicRelease)"
} finally {
    $env:PATH = $previousPath
    Pop-Location
}
