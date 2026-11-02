param([switch]$Publish, [switch]$SkipBuild, [switch]$Stable)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$taskPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Set up the development Python environment first.' }
$appVersion = (& $taskPython -c 'import commentextract; print(commentextract.__version__)').Trim()
$tag = "v$appVersion"
$remote = (& git remote get-url origin).Trim()
if ($remote -notmatch '^(?:https://github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?$') {
    throw 'The origin remote must be a GitHub repository.'
}
$repository = $Matches[1]
if (-not $Publish) {
    Write-Output "Preview only: $repository / $tag"
    Write-Output 'With -Publish: verify a clean main branch, run tests, build, smoke-test, create source and checksums, push a tag, and upload a GitHub release.'
    Write-Output 'No files have been published. Commit version changes and CHANGELOG.md before running with -Publish.'
    exit 0
}
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Program @Arguments
        $commandExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($commandExitCode -ne 0) { throw "Command failed: $Program $($Arguments -join ' ')" }
}
if ((& git status --porcelain)) { throw 'Commit your changes before publishing.' }
if ((& git symbolic-ref --short HEAD).Trim() -ne 'main') { throw 'Publish from the main branch.' }
$ghCommand = Get-Command gh -ErrorAction SilentlyContinue
$ghPath = if ($ghCommand) { $ghCommand.Source } else { Join-Path $projectRoot 'local_data\tools\gh\bin\gh.exe' }
if (-not (Test-Path -LiteralPath $ghPath)) { throw 'Install GitHub CLI from https://cli.github.com/ first.' }
# Inherit the current Windows proxy for this process, without changing system settings.
$proxy = (& $taskPython -c 'import urllib.request,json; print(json.dumps(urllib.request.getproxies()))') | ConvertFrom-Json
if (-not $env:HTTPS_PROXY -and $proxy.https) { $env:HTTPS_PROXY = $proxy.https }
if (-not $env:HTTP_PROXY -and $proxy.http) { $env:HTTP_PROXY = $proxy.http }
Invoke-Checked $ghPath @('auth', 'status')
$env:PATH = (Split-Path -Parent $ghPath) + [IO.Path]::PathSeparator + $env:PATH
$previousPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    $existingRelease = & $ghPath release view $tag --repo $repository --json url 2>&1
    $releaseExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($releaseExitCode -eq 0) { throw "Release $tag already exists. It will not be overwritten." }
if (($existingRelease | Out-String) -notmatch '(?i)release not found|HTTP 404|Not Found') {
    throw 'Could not verify that the release is absent. Check GitHub connectivity and access.'
}
Invoke-Checked $taskPython @('-m', 'pytest', '-q')
if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot 'build_windows.ps1') -SkipInstall
}
$bundle = Join-Path $projectRoot "dist\$tag\CommentExtractor\CommentExtractor.exe"
Invoke-Checked $taskPython @('scripts\smoke_bundle.py', $bundle)
$prepared = & $taskPython scripts\prepare_release.py
if ($LASTEXITCODE -ne 0) { throw 'Preparing release artifacts failed.' }
$artifacts = $prepared | ConvertFrom-Json
if ($artifacts.version -ne $appVersion) { throw 'Release version mismatch.' }
$headSha = (& git rev-parse HEAD).Trim()
$tagSha = & git rev-parse --verify --quiet "$tag^{}"
if ($LASTEXITCODE -eq 0) {
    if ($tagSha.Trim() -ne $headSha) { throw 'The local version tag points at a different commit.' }
} else {
    Invoke-Checked 'git' @('tag', '-a', $tag, '-m', "CommentExtractor $tag")
}
$gitArgs = @('-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential')
if ($env:HTTPS_PROXY) { $gitArgs += @('-c', "http.proxy=$env:HTTPS_PROXY") }
Invoke-Checked 'git' ($gitArgs + @('push', '-u', 'origin', 'main'))
Invoke-Checked 'git' ($gitArgs + @('push', 'origin', $tag))
$releaseArgs = @('release', 'create', $tag, $artifacts.binary, $artifacts.source, $artifacts.checksums,
                 '--repo', $repository, '--title', "CommentExtractor $tag", '--notes-file', $artifacts.notes, '--verify-tag')
if (-not $Stable) { $releaseArgs += '--prerelease' }
Invoke-Checked $ghPath $releaseArgs
Invoke-Checked $ghPath @('release', 'view', $tag, '--repo', $repository, '--json', 'url,assets,isPrerelease')
