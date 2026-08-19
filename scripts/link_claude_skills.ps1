# Expose the Kilo skills (.kilo/skills) to Claude Code, which scans .claude/skills.
# Creates a one-way alias: .claude/skills -> .kilo/skills.
# The alias is a Windows directory junction (or a symlink on Unix) and is git-ignored,
# so run this once per clone. Idempotent.

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$source = Join-Path $repoRoot ".kilo\skills"
$link = Join-Path $repoRoot ".claude\skills"

if (Test-Path -LiteralPath $link) {
    Write-Host "Skipped: $link already exists"
    exit 0
}

if (-not (Test-Path -LiteralPath $source)) {
    Write-Error "Source not found: $source"
    exit 1
}

$claudeDir = Join-Path $repoRoot ".claude"
if (-not (Test-Path -LiteralPath $claudeDir)) {
    New-Item -ItemType Directory -Path $claudeDir | Out-Null
}

if ($env:OS -eq "Windows_NT") {
    New-Item -ItemType Junction -Path $link -Target $source | Out-Null
} else {
    New-Item -ItemType SymbolicLink -Path $link -Target $source | Out-Null
}

Write-Host "Linked $link -> $source"
