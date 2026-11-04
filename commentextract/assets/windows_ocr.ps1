param([Parameter(Mandatory=$true)][string]$Manifest, [Parameter(Mandatory=$true)][string]$OutputFile)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await-Result($Operation, [Type]$ResultType) {
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.GetAwaiter().GetResult()
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { throw 'No Windows OCR language is available.' }
$items = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$results = @()
foreach ($item in $items) {
    $stream = $null
    $bitmap = $null
    try {
        $file = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync([string]$item)) ([Windows.Storage.StorageFile])
        $stream = Await-Result ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        if ($decoder.PixelWidth -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension -or
            $decoder.PixelHeight -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension) {
            throw 'Image dimensions exceed Windows OCR limit.'
        }
        $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied)) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $recognized = Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $lines = @($recognized.Lines | ForEach-Object { $_.Text })
        $results += @{ text=($lines -join "`n"); error=''; language=$engine.RecognizerLanguage.LanguageTag }
    } catch {
        $results += @{ text=''; error=$_.Exception.Message; language=$engine.RecognizerLanguage.LanguageTag }
    } finally {
        if ($null -ne $bitmap) { $bitmap.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}
$json = ConvertTo-Json -InputObject @($results) -Depth 5 -Compress
[IO.File]::WriteAllText($OutputFile, $json, [Text.UTF8Encoding]::new($false))
