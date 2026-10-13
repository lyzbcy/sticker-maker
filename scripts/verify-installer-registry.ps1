$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$source=[IO.File]::ReadAllText((Join-Path $root 'desktop/build/installer/installer-ui.ps1'),[Text.Encoding]::UTF8)
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'installer PowerShell syntax errors'}
$definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Find-RegisteredInstall'},$true)
. ([ScriptBlock]::Create($definition.Extent.Text))
$folder=Join-Path $root 'verification/registry-fixture'
[IO.Directory]::CreateDirectory($folder)|Out-Null
$exe=Join-Path $folder '表情包一键制作.exe';[IO.File]::WriteAllBytes($exe,[byte[]](77,90))
$legacy=Find-RegisteredInstall @(@{DisplayName='表情包一键制作 0.5.0';DisplayVersion='0.5.0';DisplayIcon='"'+$exe+'",0'})
if($legacy.Root -ne $folder -or $legacy.Version -ne '0.5.0'){throw 'legacy appended version not detected'}
$stable=Find-RegisteredInstall @(@{DisplayName='表情包一键制作';DisplayVersion='0.5.1';DisplayIcon=$exe+',0'})
if($stable.Root -ne $folder -or $stable.Version -ne '0.5.1'){throw 'stable name not detected'}
$unrelated=Find-RegisteredInstall @(@{DisplayName='其它软件';DisplayVersion='0.5.1';DisplayIcon=$exe+',0'})
if($unrelated){throw 'unrelated registration accepted'}
'REGISTRY_FIXTURE_PASS legacy_version_suffix=true stable_name=true actual_root=true unrelated_rejected=true'
