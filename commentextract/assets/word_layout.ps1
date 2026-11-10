param([string]$InputFile, [string]$OutputFile, [string]$ConvertedFile, [switch]$IncludeComments)
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
$stage = 'START'
try {
    $stage = 'WORD_START'
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $stage = 'OPEN'
    $document = $word.Documents.Open($InputFile, $false, $true, $false, '__no_password_prompt__')
    $stage = 'CONVERT'
    if ($ConvertedFile) {
        $document.SaveAs2($ConvertedFile, 16)
    }
    $stage = 'LAYOUT'
    $document.Repaginate()
    $paragraphs = [Collections.Generic.List[object]]::new()
    $heading = ''
    foreach ($paragraph in $document.Paragraphs) {
        $value = $paragraph.Range.Text.Trim([char]13, [char]7)
        if ($value) {
            $numberedHeading = $value -match '^(?:\d+(?:\.\d+){1,5}\s*\S.{0,120}|第[一二三四五六七八九十百\d]+[章节].{0,120})$'
            if ([int]$paragraph.OutlineLevel -lt 10 -or $numberedHeading) {
                $number = [string]$paragraph.Range.ListFormat.ListString
                $heading = if ($number -and -not $value.StartsWith($number)) { "$number $value" } else { $value }
            }
            $range = $paragraph.Range.Duplicate
            $range.Collapse(1)
            $endRange = $paragraph.Range.Duplicate
            if ($endRange.End -gt $endRange.Start) { $endRange.Start = $endRange.End - 1 }
            $paragraphs.Add(@{text=$value; page=[int]$range.Information(1); end_page=[int]$endRange.Information(1); heading=$heading; start=[int]$range.Start})
        }
    }
    $commentRows = [Collections.Generic.List[object]]::new()
    if ($IncludeComments) {
        foreach ($comment in $document.Comments) {
            try {
                $scope = $comment.Scope
                $startRange = $scope.Duplicate
                $startRange.Collapse(1)
                $endRange = $scope.Duplicate
                $endRange.Collapse(0)
                $scopeStart = [int]$scope.Start
                $headingRows = @($paragraphs | Where-Object { $_.start -le $scopeStart -and $_.heading })
                $scopeHeading = if ($headingRows.Count) { [string]$headingRows[-1].heading } else { '' }
                $commentRows.Add(@{
                    author=[string]$comment.Author
                    text=[string]$comment.Range.Text
                    scope=[string]$scope.Text
                    start_page=[int]$startRange.Information(1)
                    end_page=[int]$endRange.Information(1)
                    heading=$scopeHeading
                })
            } catch {
                # Leave this comment to the extraction fallback if Word cannot expose its scope.
            }
        }
    }
    $payload = @{paragraphs=$paragraphs.ToArray(); comments=$commentRows.ToArray()}
    [IO.File]::WriteAllText($OutputFile, (ConvertTo-Json -InputObject $payload -Depth 5 -Compress), [Text.UTF8Encoding]::new($false))
} catch {
    [Console]::Error.WriteLine('CE_WORD_STAGE=' + $stage)
    exit 1
} finally {
    if ($null -ne $document) { $document.Close(0) }
    if ($null -ne $word) { $word.Quit() }
}
