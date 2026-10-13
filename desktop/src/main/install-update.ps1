param([Parameter(Mandatory=$true)][string]$PayloadFile)
$ErrorActionPreference = 'Stop'
$p=$null; $committed=$false; $backedUp=$false
try {
  $p=[IO.File]::ReadAllText($PayloadFile,[Text.Encoding]::UTF8) | ConvertFrom-Json
  $root=[IO.Path]::GetFullPath($p.root).TrimEnd('\')
  $old=[IO.Path]::GetFullPath($p.oldExe)
  if ([IO.Path]::GetDirectoryName($old) -ne $root -or [IO.Path]::GetFileName($old) -ne '表情包一键制作.exe') { throw '原安装目录未通过检查' }
  $ready=@{status='ready';nonce=$p.nonce;version=$p.version;pid=$PID}|ConvertTo-Json -Compress
  [IO.File]::WriteAllText($p.readyFile,$ready,(New-Object Text.UTF8Encoding $false))
  $deadline=[DateTime]::UtcNow.AddSeconds(20)
  while (!(Test-Path -LiteralPath $p.commitFile)) {
    if ((Test-Path -LiteralPath $p.abortFile) -or [DateTime]::UtcNow -gt $deadline) { exit 1 }
    Start-Sleep -Milliseconds 100
  }
  if ((Test-Path -LiteralPath $p.abortFile) -or [IO.File]::ReadAllText($p.commitFile) -ne $p.nonce) { exit 1 }
  $committed=$true
  $process=Get-Process -Id $p.pid -ErrorAction SilentlyContinue
  if ($process -and !$process.WaitForExit(45000)) { throw '旧版尚未退出，请稍后重试' }
  $stream=[IO.File]::OpenRead($p.file);$hasher=[Security.Cryptography.SHA256]::Create()
  try {$hash=[BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','').ToLowerInvariant()}
  finally {$stream.Dispose();$hasher.Dispose()}
  if ($hash -ne $p.sha256) {throw '校验失败，旧版保持不变'}
  $backup=Join-Path ([IO.Path]::GetDirectoryName($PayloadFile)) 'rollback'
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  Get-ChildItem -LiteralPath $root -Force | Copy-Item -Destination $backup -Recurse -Force
  $backedUp=$true
  $installer=Start-Process -FilePath $p.file -ArgumentList ('/S /D='+$root) -WindowStyle Hidden -Wait -PassThru
  if ($installer.ExitCode -ne 0) {throw ('安装退出码 '+$installer.ExitCode)}
  if (!(Test-Path -LiteralPath $old -PathType Leaf)) {throw '新版主程序不存在'}
  $v=[Diagnostics.FileVersionInfo]::GetVersionInfo($old).FileVersion
  if ($v -ne $p.version) {throw ('版本不符：'+$v)}
  [IO.File]::WriteAllText($p.resultFile,(@{status='installed';version=$p.version;nonce=$p.nonce;exe=$old;backup=$backup}|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding $false))
  Start-Process -FilePath $old -WindowStyle Normal
} catch {
  if ($p -and $p.resultFile) {[IO.File]::WriteAllText($p.resultFile,(@{status='failed';version=$p.version;nonce=$p.nonce;message=$_.Exception.Message}|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding $false))}
  if ($committed) {
    if ($backedUp) {Get-ChildItem -LiteralPath $backup -Force | Copy-Item -Destination $root -Recurse -Force}
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show(($_.Exception.Message+"`r`n已保留旧版和用户设置，请重试或从发布页手动下载安装。"),'表情包一键制作更新','OK','Warning')|Out-Null
    if (Test-Path -LiteralPath $old -PathType Leaf) {Start-Process -FilePath $old -WindowStyle Normal}
  }
  exit 1
}
