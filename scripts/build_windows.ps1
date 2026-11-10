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
    & $taskPython -m pip install -e '.[dev,ocr]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
$appVersion = (& $taskPython -c 'import commentextract; print(commentextract.__version__)').Trim()
$distRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot "dist\v$appVersion"))
$allowedDistRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'dist')) + [IO.Path]::DirectorySeparatorChar
if (-not $distRoot.StartsWith($allowedDistRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build output path is outside the workspace distribution directory.'
}
$bundleDir = Join-Path $distRoot 'CommentExtractor'
& $taskPython scripts\collect_dependency_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'Runtime license collection failed.' }
& $taskPython -m PyInstaller --noconfirm --clean --windowed --onedir --name CommentExtractor `
    --distpath $distRoot `
    --icon 'commentextract\assets\app.ico' --add-data 'commentextract/assets;commentextract/assets' `
    --exclude-module pymupdf --exclude-module fitz --exclude-module lxml `
    --hidden-import commentextract.developer_word `
    --collect-all rapidocr_onnxruntime --collect-data onnxruntime --copy-metadata Pillow `
    --exclude-module onnxruntime.transformers --exclude-module onnxruntime.quantization --exclude-module onnxruntime.tools `
    --recursive-copy-metadata rapidocr-onnxruntime `
    --copy-metadata openpyxl `
    --copy-metadata PySide6 --copy-metadata PySide6_Essentials --copy-metadata PySide6_Addons `
    --copy-metadata shiboken6 --copy-metadata defusedxml --copy-metadata et-xmlfile `
    --add-data 'LICENSE;.' --add-data 'THIRD_PARTY_NOTICES.md;.' run_app.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Copy-Item -LiteralPath README.md,QUICK_START.md,USAGE.md,LICENSE,THIRD_PARTY_NOTICES.md,CHANGELOG.md,COMPATIBILITY.md,SUPPORT.md -Destination $bundleDir
Get-Content -LiteralPath USAGE.md -Raw -Encoding UTF8 | Set-Content -LiteralPath (Join-Path $bundleDir 'USAGE.txt') -Encoding UTF8
Copy-Item -LiteralPath licenses -Destination $bundleDir -Recurse -Force
& $taskPython scripts\package_windows.py $bundleDir
if ($LASTEXITCODE -ne 0) { throw 'Split package creation or 100 MB size check failed.' }
