param([string]$InputFile, [string]$OutputFile, [string]$ConvertedFile)
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $document = $word.Documents.Open($InputFile, $false, $true, $false, '__no_password_prompt__')
    if ($ConvertedFile) { $document.SaveAs2($ConvertedFile, 16) }
    $document.Repaginate()
    $paragraphs = [Collections.Generic.List[object]]::new()
    $heading = ''
    foreach ($paragraph in $document.Paragraphs) {
        $value = $paragraph.Range.Text.Trim([char]13, [char]7)
        if ($value) {
            if ([int]$paragraph.OutlineLevel -lt 10) { $heading = $value }
            $range = $paragraph.Range.Duplicate
            $range.Collapse(1)
            $endRange = $paragraph.Range.Duplicate
            if ($endRange.End -gt $endRange.Start) { $endRange.Start = $endRange.End - 1 }
            $paragraphs.Add(@{text=$value; page=[int]$range.Information(1); end_page=[int]$endRange.Information(1); heading=$heading})
        }
    }
    [IO.File]::WriteAllText($OutputFile, (ConvertTo-Json -InputObject $paragraphs.ToArray() -Depth 4 -Compress), [Text.UTF8Encoding]::new($false))
} finally {
    if ($null -ne $document) { $document.Close(0) }
    if ($null -ne $word) { $word.Quit() }
}
