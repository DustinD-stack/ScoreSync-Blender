# Paths
$SRC = "E:\Apps\blender\ScoreSync v control\ScoreSync_v0_1_1_preview\ScoreSync"
$DST = "$env:APPDATA\Blender Foundation\Blender\4.2\scripts\addons\ScoreSync"

# Clean target and mirror
cmd /c rmdir /S /Q "$DST" 2>$null
New-Item -ItemType Directory -Force -Path "$DST" | Out-Null
robocopy "$SRC" "$DST" /MIR


 robocopy "E:\Apps\blender\ScoreSync v control\ScoreSync_v0_1_1_preview\ScoreSync" "$env:APPDATA\Blender Foundation\Blender\4.2\scripts\addons\ScoreSync" /MIR


$SRC = "E:\Apps\blender\ScoreSync v control\ScoreSync_v0_1_1_preview\ScoreSync"
$DST = "$env:APPDATA\Blender Foundation\Blender\4.2\scripts\addons\ScoreSync"

while ($true) {
  robocopy "$SRC" "$DST" /MIR /NFL /NDL /NJH /NJS /NC /NS > $null
  Start-Sleep -Milliseconds 800
}
