<#
.SYNOPSIS
  Instala a skill editing-gameplay-montages em ~/.claude/skills e confere o que o computador precisa.

.DESCRIPTION
  Rode na pasta do repositório clonado:
      powershell -ExecutionPolicy Bypass -File .\install.ps1
  (o -ExecutionPolicy Bypass vale só para esta execução; é necessário se você baixou o repositório como .zip.)

  1. Copia skills\editing-gameplay-montages para %USERPROFILE%\.claude\skills\ (cria a pasta). Se já existe uma cópia, ela é
     guardada antes em editing-gameplay-montages.backup-<data> (pode ter anotações que o Claude escreveu) e o caminho é mostrado.
  2. Confere o que a skill precisa e diz, em português, o que está OK e o que falta, com o comando exato do winget:
     Git for Windows (Git Bash), uv, ffmpeg, placa de vídeo com Vulkan, fonte Impact e espaço livre em disco.
  Nada é instalado sem você pedir: o script só imprime os comandos. Com -Instalar ele roda os comandos do winget que faltam.

.PARAMETER Instalar
  Roda o winget para instalar o que faltar (Git, uv, ffmpeg). Sem esta opção, só mostra os comandos.
#>
param([switch]$Instalar)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$Skill = 'editing-gameplay-montages'
$userHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$aqui = (Get-Location).ProviderPath
$raiz = if ($PSScriptRoot) { $PSScriptRoot } else { $aqui }
$faltam = New-Object System.Collections.ArrayList        # descrições do que falta
$comandos = New-Object System.Collections.ArrayList      # @{ Id = ...; Nome = ... } do winget

function Ok($t)    { Write-Host '[OK]    ' -NoNewline -ForegroundColor Green;  Write-Host $t }
function Aviso($t) { Write-Host '[AVISO] ' -NoNewline -ForegroundColor Yellow; Write-Host $t }
function Falta($t) { Write-Host '[FALTA] ' -NoNewline -ForegroundColor Red;    Write-Host $t }
function Linha($t) { Write-Host "        $t" }

# ------------------------------------------------------------------ 1. copiar a skill
Write-Host ''
Write-Host "== Instalando a skill $Skill ==" -ForegroundColor Cyan
$origem = Join-Path $raiz "skills\$Skill"
if (-not (Test-Path -LiteralPath (Join-Path $origem 'SKILL.md'))) {
    Falta "não achei $origem\SKILL.md. Rode este script na pasta do repositório clonado (a que tem a pasta 'skills')."
    exit 1
}
$skillsDir = Join-Path $userHome '.claude\skills'
$destino = Join-Path $skillsDir $Skill
try {
    New-Item -ItemType Directory -Force -Path $skillsDir | Out-Null
    if (Test-Path -LiteralPath $destino) {
        if ((Resolve-Path -LiteralPath $origem).ProviderPath.TrimEnd('\') -eq (Resolve-Path -LiteralPath $destino).ProviderPath.TrimEnd('\')) {
            Falta "a pasta de origem já é a instalada ($destino). Rode o script a partir do repositório clonado."
            exit 1
        }
        $backup = "$destino.backup-" + (Get-Date -Format 'yyyy-MM-dd')
        if (Test-Path -LiteralPath $backup) { $backup = $backup + '-' + (Get-Date -Format 'HHmmss') }
        Move-Item -LiteralPath $destino -Destination $backup
        $velho = Join-Path $backup 'SKILL.md'
        if (Test-Path -LiteralPath $velho) { Rename-Item -LiteralPath $velho -NewName 'SKILL.md.backup' }   # senão o Claude carregaria a skill duas vezes
        Ok "a cópia anterior foi guardada em: $backup"
        Linha "(o SKILL.md dela virou SKILL.md.backup para o Claude não carregar a skill em duplicidade; anotações que o Claude tenha feito estão lá)"
    }
    Copy-Item -LiteralPath $origem -Destination $destino -Recurse
    Get-ChildItem -LiteralPath $destino -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
} catch {
    Falta "não consegui copiar a skill: $($_.Exception.Message)"
    Linha "Feche programas que estejam usando a pasta $skillsDir (terminal aberto dentro dela, editor) e rode de novo."
    exit 1
}
$arquivos = @(Get-ChildItem -LiteralPath $destino -Recurse -File)
$modelo = Join-Path $destino "models\rife-v4.25\flownet.bin"
$modeloOrigem = Join-Path $origem "models\rife-v4.25\flownet.bin"
if (-not (Test-Path -LiteralPath $modelo) -or (Get-Item -LiteralPath $modelo).Length -ne (Get-Item -LiteralPath $modeloOrigem).Length) {
    Falta "a cópia do modelo do RIFE (models\rife-v4.25\flownet.bin) não ficou igual à original. Rode de novo; se repetir, clone o repositório outra vez."
    exit 1
}
Ok "skill instalada em: $destino ($($arquivos.Count) arquivos, modelo do RIFE conferido)"

# ------------------------------------------------------------------ 2. pré-requisitos
Write-Host ''
Write-Host '== O que o computador precisa ==' -ForegroundColor Cyan

$ErrorActionPreference = 'Continue'      # programas nativos (vulkaninfo, winget) escrevem avisos no stderr: não são erro

function Achar-Comando($nome, $extras) {
    $c = Get-Command $nome -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -eq 'Application' } | Select-Object -First 1
    if ($c) { return $c.Source }
    foreach ($e in $extras) {
        $hit = @(Get-ChildItem -Path $e -ErrorAction SilentlyContinue) | Select-Object -Last 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

# Git for Windows (traz o Git Bash, que roda run.sh e deliver.sh)
$git = Achar-Comando 'git' @("$env:ProgramFiles\Git\cmd\git.exe", "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe")
$bash = $null
if ($git) {
    $gitRaiz = Split-Path (Split-Path $git)
    foreach ($b in @((Join-Path $gitRaiz 'bin\bash.exe'), "$env:ProgramFiles\Git\bin\bash.exe", "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe")) {
        if (Test-Path -LiteralPath $b) { $bash = $b; break }
    }
}
if ($git -and $bash) {
    $v = (& $git --version) -join ' '
    Ok "Git for Windows com Git Bash: $v ($bash)"
} else {
    Falta 'Git for Windows (traz o Git Bash, que roda os scripts .sh da skill)'
    Linha 'winget install --id Git.Git -e'
    [void]$faltam.Add('Git for Windows'); [void]$comandos.Add(@{ Id = 'Git.Git'; Nome = 'Git for Windows' })
}

# uv (cria o venv com Python 3.11 e instala os pacotes)
$uv = Achar-Comando 'uv' @("$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe", "$userHome\.local\bin\uv.exe", "$userHome\.cargo\bin\uv.exe",
                           "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\astral-sh.uv*\uv.exe")
if ($uv) {
    $uvv = ((((& $uv --version) -join ' ') -split ' ') | Select-Object -First 2) -join ' '
    Ok "$uvv ($uv)"
} else {
    Falta 'uv (cria o ambiente Python 3.11 da skill e instala os pacotes)'
    Linha 'winget install --id astral-sh.uv -e'
    [void]$faltam.Add('uv'); [void]$comandos.Add(@{ Id = 'astral-sh.uv'; Nome = 'uv' })
}

# ffmpeg (mesma busca do ff.py: FF, PATH, pastas do winget / scoop / chocolatey)
$ffmpeg = $null
if ($env:FF) {
    if (Test-Path -LiteralPath $env:FF -PathType Leaf) { $ffmpeg = $env:FF }
    elseif (Test-Path -LiteralPath (Join-Path $env:FF 'ffmpeg.exe')) { $ffmpeg = Join-Path $env:FF 'ffmpeg.exe' }
}
if (-not $ffmpeg) {
    $ffmpeg = Achar-Comando 'ffmpeg' @("$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffmpeg.exe", "$env:LOCALAPPDATA\Microsoft\WinGet\Links\ffmpeg.exe",
                                       "$userHome\scoop\shims\ffmpeg.exe", "$userHome\scoop\apps\ffmpeg\current\bin\ffmpeg.exe", 'C:\ProgramData\chocolatey\bin\ffmpeg.exe',
                                       'C:\ffmpeg\bin\ffmpeg.exe', "$env:ProgramFiles\ffmpeg\bin\ffmpeg.exe")
}
if ($ffmpeg) {
    $v = ((& $ffmpeg -version | Select-Object -First 1) -split ' ' | Select-Object -First 3) -join ' '
    $sonda = Join-Path (Split-Path $ffmpeg) 'ffprobe.exe'
    if ((Test-Path -LiteralPath $sonda) -or (Get-Command ffprobe -ErrorAction SilentlyContinue)) { Ok "ffmpeg e ffprobe: $v ($ffmpeg)" }
    else {
        Falta "ffmpeg em $ffmpeg, mas sem ffprobe ao lado (é preciso a versão completa)"
        Linha 'winget install --id Gyan.FFmpeg -e'
        [void]$faltam.Add('ffprobe (ffmpeg completo)'); [void]$comandos.Add(@{ Id = 'Gyan.FFmpeg'; Nome = 'ffmpeg' })
    }
} else {
    Falta 'ffmpeg (corta, codifica e mixa o vídeo)'
    Linha 'winget install --id Gyan.FFmpeg -e'
    Linha '(depois feche e abra o terminal; a skill também procura o ffmpeg na pasta do winget)'
    [void]$faltam.Add('ffmpeg'); [void]$comandos.Add(@{ Id = 'Gyan.FFmpeg'; Nome = 'ffmpeg' })
}

# Vulkan (o RIFE, que cria os quadros intermediários, roda na placa de vídeo)
$vk = Get-Command vulkaninfo -ErrorAction SilentlyContinue | Select-Object -First 1
$placas = @()
try { $placas = @(Get-CimInstance Win32_VideoController -ErrorAction Stop) } catch { }
$vkNomes = @()
if ($vk) {
    try { $vkNomes = @((& $vk.Source --summary 2>&1) | ForEach-Object { if ("$_" -match 'deviceName\s*=\s*(.+?)\s*$') { $Matches[1] } }) } catch { }
}
if ($vkNomes.Count -gt 0) {
    Ok ("Vulkan (vulkaninfo): " + ($vkNomes -join '; '))
} else {
    if ($vk) { Aviso 'o vulkaninfo não listou nenhuma placa: sem Vulkan o RIFE roda na CPU (cerca de 15 vezes mais lento).' }
    else     { Aviso 'vulkaninfo não encontrado, então não consigo confirmar o Vulkan daqui (placas NVIDIA, AMD e Intel com driver em dia costumam ter).' }
    if ($placas.Count -gt 0) {
        foreach ($p in $placas) { Linha ("placa de vídeo: $($p.Name) (driver $($p.DriverVersion))") }
    } else { Linha 'não consegui listar as placas de vídeo (Get-CimInstance Win32_VideoController).' }
    $soBasico = ($placas.Count -gt 0) -and (@($placas | Where-Object { $_.Name -notmatch 'Basic|Remote|Virtual|Hyper-V' }).Count -eq 0)
    if ($soBasico -or $vk) {
        Linha 'Instale o driver mais novo no site da NVIDIA, AMD ou Intel (não o driver básico do Windows) e reinicie.'
        Linha 'Sem placa utilizável a skill ainda funciona na CPU (RIFE_GPU=-1), mas um edit de 30 s leva horas.'
        [void]$faltam.Add('placa de vídeo com Vulkan')
    } else {
        Linha 'O teste de verdade é o doctor.py (roda o RIFE na placa); veja "Próximos passos" abaixo.'
    }
}

# Fonte Impact (só o estilo da referência, com as palavras da letra)
$impact = @("$env:WINDIR\Fonts\impact.ttf", "$env:LOCALAPPDATA\Microsoft\Windows\Fonts\impact.ttf") | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if ($impact) { Ok "fonte Impact: $impact" }
else {
    Aviso 'fonte Impact não encontrada (só o estilo da referência, com as palavras da letra na tela, precisa dela)'
    Linha 'Ela vem com o Windows: Configurações > Personalização > Fontes, procure "Impact". Ou use IMPACT_FONT=<caminho de um .ttf pesado e condensado>.'
}

# Espaço livre no disco da pasta atual
try {
    $livre = ([System.IO.DriveInfo][System.IO.Path]::GetPathRoot($aqui)).AvailableFreeSpace / 1GB
    $txt = ('{0:N1} GB livres em {1} (cada vídeo usa de 7 a 13 GB de quadros intermediários; apague depois de entregar)' -f $livre, [System.IO.Path]::GetPathRoot($aqui))
    if ($livre -lt 7) { Falta $txt; Linha 'Libere espaço ou trabalhe num disco maior: os projetos ficam ao lado dos clipes.'; [void]$faltam.Add('espaço em disco') }
    elseif ($livre -lt 13) { Aviso $txt; Linha 'Cabe o estilo da casa; o da referência (1080p largo) pode não caber.' }
    else { Ok $txt }
} catch {
    Aviso "não consegui medir o espaço livre de $aqui (pasta de rede?). Os projetos precisam de 7 a 13 GB livres no disco onde ficam."
}
Linha '(o disco medido é o desta pasta; os projetos ficam onde estão os clipes: rode o doctor.py lá para medir esse disco)'

# ------------------------------------------------------------------ 3. o que fazer com o que falta
Write-Host ''
$winget = Get-Command winget -ErrorAction SilentlyContinue
if ($comandos.Count -gt 0) {
    Write-Host '== Instalar o que falta ==' -ForegroundColor Cyan
    if (-not $winget) {
        Aviso 'o winget não foi encontrado neste Windows. Instale o "Instalador de Aplicativo" (App Installer) pela Microsoft Store, ou baixe cada programa no site oficial:'
        Linha 'Git: git-scm.com/download/win   uv: docs.astral.sh/uv   ffmpeg: gyan.dev/ffmpeg/builds'
    } elseif ($Instalar) {
        foreach ($c in $comandos) {
            Write-Host "Instalando $($c.Nome): winget install --id $($c.Id) -e" -ForegroundColor Cyan
            & winget install --id $c.Id -e --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { Aviso "o winget terminou com código $LASTEXITCODE em $($c.Nome) (se a mensagem acima diz que já está instalado e não há atualização, está tudo certo: só feche e abra o terminal)." }
        }
        Aviso 'Feche e abra o terminal antes de usar o que acabou de ser instalado (o PATH só atualiza em terminais novos).'
    } else {
        Write-Host 'Nada foi instalado. Para instalar, cole no PowerShell (um por linha):'
        foreach ($c in $comandos) { Write-Host "    winget install --id $($c.Id) -e" -ForegroundColor White }
        Write-Host '  ou rode este script de novo com -Instalar:   .\install.ps1 -Instalar'
    }
    Write-Host ''
}

Write-Host '== Resumo ==' -ForegroundColor Cyan
if ($faltam.Count -eq 0) { Write-Host 'PRONTO: a skill está instalada e nada obrigatório falta.' -ForegroundColor Green }
elseif ($Instalar -and $winget -and $comandos.Count -gt 0) { Write-Host ('A skill está instalada. O winget foi chamado para: ' + (($comandos | ForEach-Object { $_.Nome }) -join ', ') + '. Feche e abra o terminal e rode .\install.ps1 de novo para conferir.') -ForegroundColor Yellow }
else { Write-Host ('A skill está instalada, mas falta: ' + ($faltam -join ', ') + '.') -ForegroundColor Yellow }
Write-Host ''
Write-Host 'Próximos passos:'
Write-Host '  1. Abra o Claude Code numa pasta e peça o vídeo (ex.: "faça um montage com os clipes de C:\Users\...\Videos\valorant e a música X").'
Write-Host '  2. Quando o projeto tiver o venv (a skill cria: pipeline.md, Setup), confira tudo de verdade, inclusive o RIFE na placa:'
Write-Host '       ./venv311/Scripts/python doctor.py        (dentro da pasta _editor do projeto)'
exit 0
