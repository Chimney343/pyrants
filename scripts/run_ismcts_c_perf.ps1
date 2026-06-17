param([string]$TopN = "30")

$p = (Get-Location).Path -replace '\\', '/'
$drive = $p.Substring(0, 1).ToLower()
$projectPath = '/mnt/' + $drive + $p.Substring(2)
$bashCmd = "cd $projectPath; bash scripts/run_ismcts_c_perf.sh $TopN"
wsl -e bash -c $bashCmd
