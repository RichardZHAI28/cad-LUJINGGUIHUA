$ErrorActionPreference = 'Stop'
$workspacePath = (Get-Location).Path
$toolsPath = Join-Path $workspacePath '打包工具'
if (-not (Test-Path -LiteralPath (Join-Path $toolsPath 'build_release.py'))) { throw 'Run from project workspace.' }
$extractPath = Join-Path $toolsPath 'install-smoke-20261108-centerline-curves'
$dataPath = Join-Path $toolsPath 'smoke-data-20261108-centerline-curves'
if (Test-Path -LiteralPath $extractPath) { throw 'Smoke extraction target already exists; do not overwrite.' }
if (Test-Path -LiteralPath $dataPath) { throw 'Smoke data target already exists; do not overwrite.' }
$setupPath = Join-Path $workspacePath '发布包/CadWeldPlanner-Setup.exe'
$reportPath = Join-Path $workspacePath '诊断/中心线曲线修复/installer-self-test.json'
$drawingPath = 'C:/Users/Administrator/Desktop/空心实心数字字母模板字1118.dxf'
$setupProcess = Start-Process -FilePath $setupPath -ArgumentList ('/EXTRACT="' + $extractPath + '"') -WindowStyle Hidden -Wait -PassThru
if ($setupProcess.ExitCode -ne 0) { throw ('Extraction failed: ' + $setupProcess.ExitCode) }
$env:CAD_WELD_DATA_DIR = $dataPath
$appPath = Join-Path $extractPath 'CadWeldPlanner.exe'
$appArgs = @('--self-test', '--self-test-input', ('"' + $drawingPath + '"'), '--report', ('"' + $reportPath + '"'))
$appProcess = Start-Process -FilePath $appPath -ArgumentList $appArgs -WindowStyle Hidden -Wait -PassThru
if ($appProcess.ExitCode -ne 0) { throw ('Packaged self-test failed: ' + $appProcess.ExitCode) }
$result = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not ($result.ok -and $result.frozen -and $result.rounded_centerline_preserved -and $result.centerline_holes_preserved -and (-not $result.robot_network_used))) { throw 'Required packaged results missing.' }
Write-Output ('Packaged self-test passed: ' + $reportPath)
