param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$taskPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create Python environment.' }
}
if (-not $SkipInstall) {
    & $taskPython -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
$appVersion = (& $taskPython -c 'import commentextract; print(commentextract.__version__)').Trim()
$distRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot "dist\v$appVersion"))
$allowedDistRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'dist')) + [IO.Path]::DirectorySeparatorChar
if (-not $distRoot.StartsWith($allowedDistRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build output path is outside the workspace distribution directory.'
}
$bundleDir = Join-Path $distRoot 'CommentExtract'
& $taskPython -m PyInstaller --noconfirm --clean --windowed --onedir --name CommentExtract `
    --distpath $distRoot `
    --collect-all pymupdf `
    --copy-metadata PyMuPDF --copy-metadata openpyxl --copy-metadata Pillow `
    --copy-metadata PySide6 --copy-metadata PySide6_Essentials --copy-metadata PySide6_Addons `
    --copy-metadata shiboken6 --copy-metadata defusedxml --copy-metadata et-xmlfile --copy-metadata lxml `
    --add-data 'LICENSE;.' --add-data 'THIRD_PARTY_NOTICES.md;.' run_app.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Copy-Item -LiteralPath README.md,LICENSE,THIRD_PARTY_NOTICES.md,CHANGELOG.md -Destination $bundleDir
Copy-Item -LiteralPath licenses -Destination $bundleDir -Recurse -Force
$archive = "dist\CommentExtract-v$appVersion-win64.zip"
Compress-Archive -LiteralPath $bundleDir -DestinationPath $archive -Force
Write-Output "Ready: $archive"
