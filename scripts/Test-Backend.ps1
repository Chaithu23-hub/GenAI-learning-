param(
    [string]$Image = '',
    [switch]$IncludeFormatParity
)

# Run review checks in a disposable container. No .env file or user index is copied.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$containerName = 'legalrag-review-' + [guid]::NewGuid().ToString('N').Substring(0, 12)
$containerStarted = $false

function Invoke-DockerCommand {
    param([string[]]$DockerArguments)
    & docker @DockerArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker check failed (exit $LASTEXITCODE): $($DockerArguments[0])"
    }
}

Push-Location $repositoryRoot
try {
    if (-not $Image) {
        $images = @(& docker compose images -q backend)
        if ($LASTEXITCODE -ne 0 -or $images.Count -eq 0) {
            throw 'Build/start the backend with docker compose up -d --build first.'
        }
        $Image = $images[0].Trim()
    }
    Invoke-DockerCommand -DockerArguments @('run', '-d', '--name', $containerName, '--entrypoint', 'sleep', $Image, 'infinity')
    $containerStarted = $true
    foreach ($relativePath in @('legal_rag', 'tests', 'pyproject.toml', 'requirements.txt', 'requirements-dev.txt', 'README.md')) {
        $source = Join-Path $repositoryRoot "backend/$relativePath"
        Invoke-DockerCommand -DockerArguments @('cp', $source, "${containerName}:/app/")
    }
    Invoke-DockerCommand -DockerArguments @('exec', $containerName, 'python', '-m', 'pip', 'install', '--user', '-q', '--no-warn-script-location', '-r', 'requirements-dev.txt')
    Invoke-DockerCommand -DockerArguments @('exec', $containerName, 'python', '-m', 'ruff', 'check', '.', '--output-format', 'concise')
    Invoke-DockerCommand -DockerArguments @('exec', $containerName, 'python', '-m', 'pytest', '-m', 'not slow', '-q')
    if ($IncludeFormatParity) {
        Invoke-DockerCommand -DockerArguments @(
            'exec', $containerName, 'python', '-m', 'pytest', '-q',
            'tests/slow/test_chroma_metadata_filters.py',
            'tests/slow/test_real_infrastructure.py::test_shared_corpus_loader_supports_all_formats_with_parity'
        )
    }
    Write-Output 'Backend review checks passed. The running application was not modified.'
}
finally {
    if ($containerStarted) {
        & docker rm -f $containerName | Out-Null
    }
    Pop-Location
}
