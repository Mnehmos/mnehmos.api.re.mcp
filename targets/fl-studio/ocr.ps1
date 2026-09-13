# OCR a PNG with the built-in Windows engine, printing text lines with
# pixel bounding boxes so coordinates can be clicked without vision.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ocr.ps1 <png>
param([Parameter(Mandatory=$true)][string]$Path, [switch]$Words)

Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { Write-Output "OCR engine unavailable for user profile languages"; exit 1 }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

if ($Words) {
    foreach ($line in $result.Lines) {
        foreach ($w in @($line.Words)) {
            $r = $w.BoundingRect
            Write-Output ("{0,5},{1,5}-{2,5},{3,5}  {4}" -f [int]$r.X, [int]$r.Y, [int]($r.X + $r.Width), [int]($r.Y + $r.Height), $w.Text)
        }
    }
    exit 0
}

foreach ($line in $result.Lines) {
    $wordList = @($line.Words)
    if ($wordList.Count -eq 0) { continue }
    $first = $wordList[0]
    $last = $wordList[$wordList.Count - 1]
    $x1 = [int]$first.BoundingRect.X
    $y1 = [int]$first.BoundingRect.Y
    $y2 = [int]($first.BoundingRect.Y + $first.BoundingRect.Height)
    $x2 = [int]($last.BoundingRect.X + $last.BoundingRect.Width)
    Write-Output ("{0,5},{1,5}-{2,5},{3,5}  {4}" -f $x1, $y1, $x2, $y2, $line.Text)
}
