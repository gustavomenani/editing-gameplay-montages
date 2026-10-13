#!/bin/bash
# Instala a skill editing-gameplay-montages em ~/.claude/skills e confere o que o computador precisa (Git Bash no Windows).
#
# uso, na pasta do repositório clonado:
#     bash install.sh              copia a skill e mostra o que falta, com o comando exato do winget
#     bash install.sh --instalar   além disso, roda o winget para instalar o que faltar (Git, uv, ffmpeg)
#
# 1. Copia skills/editing-gameplay-montages para ~/.claude/skills/ (cria a pasta). Se já existe uma cópia, ela é guardada antes
#    em editing-gameplay-montages.backup-<data> (pode ter anotações que o Claude escreveu) e o caminho é mostrado.
# 2. Confere: Git for Windows (Git Bash), uv, ffmpeg, placa de vídeo com Vulkan, fonte Impact, espaço livre em disco.
# Nada é instalado sem você pedir: sem --instalar o script só imprime os comandos.
set -u

SKILL=editing-gameplay-montages
INSTALAR=0
case "${1:-}" in
  "") ;;
  --instalar|-i|-Instalar) INSTALAR=1 ;;
  *) echo "uso: bash install.sh [--instalar]"; exit 2 ;;
esac

if [ -t 1 ]; then G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; C=$'\e[36m'; Z=$'\e[0m'; else G=""; Y=""; R=""; C=""; Z=""; fi
ok()    { printf '%s[OK]%s    %s\n' "$G" "$Z" "$*"; }
aviso() { printf '%s[AVISO]%s %s\n' "$Y" "$Z" "$*"; }
falta() { printf '%s[FALTA]%s %s\n' "$R" "$Z" "$*"; }
linha() { printf '        %s\n' "$*"; }
titulo() { printf '\n%s== %s ==%s\n' "$C" "$*" "$Z"; }

ROOT=$(cd "$(dirname "$0")" && pwd)
FALTAM=()          # o que falta
CMDS=()            # "Id|Nome" dos comandos do winget

# ------------------------------------------------------------------ 1. copiar a skill
titulo "Instalando a skill $SKILL"
ORIGEM="$ROOT/skills/$SKILL"
[ -f "$ORIGEM/SKILL.md" ] || { falta "não achei $ORIGEM/SKILL.md. Rode este script na pasta do repositório clonado (a que tem a pasta 'skills')."; exit 1; }
SKILLS_DIR="$HOME/.claude/skills"
DESTINO="$SKILLS_DIR/$SKILL"
mkdir -p "$SKILLS_DIR" || { falta "não consegui criar $SKILLS_DIR"; exit 1; }
if [ -e "$DESTINO" ]; then
  if [ "$(cd "$ORIGEM" && pwd -P)" = "$(cd "$DESTINO" && pwd -P)" ]; then
    falta "a pasta de origem já é a instalada ($DESTINO). Rode o script a partir do repositório clonado."; exit 1
  fi
  BACKUP="$DESTINO.backup-$(date +%Y-%m-%d)"
  [ -e "$BACKUP" ] && BACKUP="$BACKUP-$(date +%H%M%S)"
  mv "$DESTINO" "$BACKUP" || { falta "não consegui guardar a cópia anterior. Feche programas que usem $SKILLS_DIR (terminal aberto dentro dela, editor) e rode de novo."; exit 1; }
  [ -f "$BACKUP/SKILL.md" ] && mv "$BACKUP/SKILL.md" "$BACKUP/SKILL.md.backup"      # senão o Claude carregaria a skill duas vezes
  ok "a cópia anterior foi guardada em: $BACKUP"
  linha "(o SKILL.md dela virou SKILL.md.backup para o Claude não carregar a skill em duplicidade; anotações que o Claude tenha feito estão lá)"
fi
cp -r "$ORIGEM" "$DESTINO" || { falta "não consegui copiar a skill para $DESTINO. Feche programas que usem essa pasta e rode de novo."; exit 1; }
find "$DESTINO" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null
if ! cmp -s "$ORIGEM/models/rife-v4.25/flownet.bin" "$DESTINO/models/rife-v4.25/flownet.bin"; then
  falta "a cópia do modelo do RIFE (models/rife-v4.25/flownet.bin) não ficou igual à original. Rode de novo; se repetir, clone o repositório outra vez."; exit 1
fi
N=$(find "$DESTINO" -type f | wc -l | tr -d ' ')
ok "skill instalada em: $DESTINO ($N arquivos, modelo do RIFE conferido)"

# ------------------------------------------------------------------ 2. pré-requisitos
titulo "O que o computador precisa"

# o primeiro arquivo que existe entre os padrões (globs) dados
primeiro() { local p f; for p in "$@"; do for f in $p; do [ -f "$f" ] && { echo "$f"; return 0; }; done; done; return 1; }
LOCAL_APP="${LOCALAPPDATA:-$HOME/AppData/Local}"
PF="${ProgramFiles:-C:\\Program Files}"
if command -v cygpath >/dev/null 2>&1; then LOCAL_APP=$(cygpath -u "$LOCAL_APP"); PF=$(cygpath -u "$PF"); fi

# Git for Windows: este script já roda no Git Bash; confere o git e o bash
GIT=$(command -v git || primeiro "$PF/Git/cmd/git.exe" "$LOCAL_APP/Programs/Git/cmd/git.exe")
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) NO_WINDOWS=0 ;;
  *) NO_WINDOWS=1 ;;
esac
if [ -n "$GIT" ] && [ "$NO_WINDOWS" = 0 ]; then
  ok "Git for Windows com Git Bash: $("$GIT" --version) (bash $BASH_VERSION)"
elif [ -n "$GIT" ]; then
  aviso "este não é o Git Bash do Windows ($(uname -s)): a skill foi feita e testada para Windows com o Git Bash."
else
  falta "Git for Windows (traz o Git Bash, que roda os scripts .sh da skill)"
  linha "winget install --id Git.Git -e"
  FALTAM+=("Git for Windows"); CMDS+=("Git.Git|Git for Windows")
fi

# uv
UV=$(command -v uv || primeiro "$LOCAL_APP/Microsoft/WinGet/Links/uv.exe" "$HOME/.local/bin/uv.exe" "$HOME/.cargo/bin/uv.exe" "$LOCAL_APP/Microsoft/WinGet/Packages/astral-sh.uv*/uv.exe")
if [ -n "$UV" ]; then
  ok "$("$UV" --version | cut -d' ' -f1,2) ($UV)"
else
  falta "uv (cria o ambiente Python 3.11 da skill e instala os pacotes)"
  linha "winget install --id astral-sh.uv -e"
  FALTAM+=("uv"); CMDS+=("astral-sh.uv|uv")
fi

# ffmpeg (mesma busca do ff.py: FF, PATH, pastas do winget / scoop / chocolatey)
FFM=""
if [ -n "${FF:-}" ]; then
  if [ -f "$FF" ]; then FFM="$FF"; elif [ -f "$FF/ffmpeg.exe" ]; then FFM="$FF/ffmpeg.exe"; fi
fi
[ -z "$FFM" ] && FFM=$(command -v ffmpeg || primeiro "$LOCAL_APP/Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin/ffmpeg.exe" "$LOCAL_APP/Microsoft/WinGet/Links/ffmpeg.exe" \
  "$HOME/scoop/shims/ffmpeg.exe" "$HOME/scoop/apps/ffmpeg/current/bin/ffmpeg.exe" "/c/ProgramData/chocolatey/bin/ffmpeg.exe" "/c/ffmpeg/bin/ffmpeg.exe" "$PF/ffmpeg/bin/ffmpeg.exe")
if [ -n "$FFM" ]; then
  FFD=$(dirname "$FFM")
  if [ -f "$FFD/ffprobe.exe" ] || [ -f "$FFD/ffprobe" ] || command -v ffprobe >/dev/null 2>&1; then
    ok "ffmpeg e ffprobe: $("$FFM" -version 2>/dev/null | head -n 1 | cut -d' ' -f1-3) ($FFM)"
  else
    falta "ffmpeg em $FFM, mas sem ffprobe ao lado (é preciso a versão completa)"
    linha "winget install --id Gyan.FFmpeg -e"
    FALTAM+=("ffprobe (ffmpeg completo)"); CMDS+=("Gyan.FFmpeg|ffmpeg")
  fi
else
  falta "ffmpeg (corta, codifica e mixa o vídeo)"
  linha "winget install --id Gyan.FFmpeg -e"
  linha "(depois feche e abra o terminal; a skill também procura o ffmpeg na pasta do winget)"
  FALTAM+=("ffmpeg"); CMDS+=("Gyan.FFmpeg|ffmpeg")
fi

# Vulkan (o RIFE, que cria os quadros intermediários, roda na placa de vídeo)
VKN=""
if command -v vulkaninfo >/dev/null 2>&1; then
  VKN=$(vulkaninfo --summary 2>/dev/null | tr -d '\r' | sed -n 's/^[[:space:]]*deviceName[[:space:]]*=[[:space:]]*//p' | paste -sd ';' - | sed 's/;/; /g')
fi
if [ -n "$VKN" ]; then
  ok "Vulkan (vulkaninfo): $VKN"
else
  if command -v vulkaninfo >/dev/null 2>&1; then
    aviso "o vulkaninfo não listou nenhuma placa: sem Vulkan o RIFE roda na CPU (cerca de 15 vezes mais lento)."
  else
    aviso "vulkaninfo não encontrado, então não consigo confirmar o Vulkan daqui (placas NVIDIA, AMD e Intel com driver em dia costumam ter)."
  fi
  PLACAS=$(powershell.exe -NoProfile -Command "Get-CimInstance Win32_VideoController | ForEach-Object { \$_.Name + ' (driver ' + \$_.DriverVersion + ')' }" 2>/dev/null | tr -d '\r')
  if [ -n "$PLACAS" ]; then
    while IFS= read -r p; do [ -n "$p" ] && linha "placa de vídeo: $p"; done <<< "$PLACAS"
  else
    linha "não consegui listar as placas de vídeo (Get-CimInstance Win32_VideoController)."
  fi
  SO_BASICO=0
  [ -n "$PLACAS" ] && ! printf '%s\n' "$PLACAS" | grep -v -i -E 'Basic|Remote|Virtual|Hyper-V' | grep -q . && SO_BASICO=1
  if [ "$SO_BASICO" = 1 ] || command -v vulkaninfo >/dev/null 2>&1; then
    linha "Instale o driver mais novo no site da NVIDIA, AMD ou Intel (não o driver básico do Windows) e reinicie."
    linha "Sem placa utilizável a skill ainda funciona na CPU (RIFE_GPU=-1), mas um edit de 30 s leva horas."
    FALTAM+=("placa de vídeo com Vulkan")
  else
    linha 'O teste de verdade é o doctor.py (roda o RIFE na placa); veja "Próximos passos" abaixo.'
  fi
fi

# Fonte Impact (só o estilo da referência, com as palavras da letra)
WIN="${WINDIR:-C:\\Windows}"
command -v cygpath >/dev/null 2>&1 && WIN=$(cygpath -u "$WIN")
IMPACT=$(primeiro "$WIN/Fonts/impact.ttf" "$LOCAL_APP/Microsoft/Windows/Fonts/impact.ttf")
if [ -n "$IMPACT" ]; then
  ok "fonte Impact: $IMPACT"
else
  aviso "fonte Impact não encontrada (só o estilo da referência, com as palavras da letra na tela, precisa dela)"
  linha 'Ela vem com o Windows: Configurações > Personalização > Fontes, procure "Impact". Ou use IMPACT_FONT=<caminho de um .ttf pesado e condensado>.'
fi

# Espaço livre no disco da pasta atual
set -- $(df -Pk . 2>/dev/null | tail -n 1)
if [ -n "${4:-}" ] && [ "$4" -eq "$4" ] 2>/dev/null; then
  LIVRE_KB=$4
  LIVRE=$(( LIVRE_KB / 1048576 )).$(( (LIVRE_KB % 1048576) * 10 / 1048576 ))
  TXT="$LIVRE GB livres no disco de $(pwd) (cada vídeo usa de 7 a 13 GB de quadros intermediários; apague depois de entregar)"
  if [ "$LIVRE_KB" -lt 7340032 ]; then falta "$TXT"; linha "Libere espaço ou trabalhe num disco maior: os projetos ficam ao lado dos clipes."; FALTAM+=("espaço em disco")
  elif [ "$LIVRE_KB" -lt 13631488 ]; then aviso "$TXT"; linha "Cabe o estilo da casa; o da referência (1080p largo) pode não caber."
  else ok "$TXT"; fi
else
  aviso "não consegui medir o espaço livre de $(pwd). Os projetos precisam de 7 a 13 GB livres no disco onde ficam."
fi
linha "(o disco medido é o desta pasta; os projetos ficam onde estão os clipes: rode o doctor.py lá para medir esse disco)"

# ------------------------------------------------------------------ 3. o que fazer com o que falta
if [ "${#CMDS[@]}" -gt 0 ]; then
  titulo "Instalar o que falta"
  if ! command -v winget >/dev/null 2>&1; then
    aviso 'o winget não foi encontrado neste Windows. Instale o "Instalador de Aplicativo" (App Installer) pela Microsoft Store, ou baixe cada programa no site oficial:'
    linha "Git: git-scm.com/download/win   uv: docs.astral.sh/uv   ffmpeg: gyan.dev/ffmpeg/builds"
  elif [ "$INSTALAR" = 1 ]; then
    for c in "${CMDS[@]}"; do
      printf '%sInstalando %s: winget install --id %s -e%s\n' "$C" "${c#*|}" "${c%|*}" "$Z"
      winget install --id "${c%|*}" -e --accept-package-agreements --accept-source-agreements || aviso "o winget terminou com erro em ${c#*|} (se a mensagem acima diz que já está instalado e não há atualização, está tudo certo: só feche e abra o terminal)."
    done
    aviso "Feche e abra o terminal antes de usar o que acabou de ser instalado (o PATH só atualiza em terminais novos)."
  else
    echo "Nada foi instalado. Para instalar, cole no terminal (um por linha):"
    for c in "${CMDS[@]}"; do echo "    winget install --id ${c%|*} -e"; done
    echo "  ou rode este script de novo com --instalar:   bash install.sh --instalar"
  fi
fi

titulo "Resumo"
if [ "${#FALTAM[@]}" -eq 0 ]; then
  printf '%sPRONTO: a skill está instalada e nada obrigatório falta.%s\n' "$G" "$Z"
elif [ "$INSTALAR" = 1 ] && [ "${#CMDS[@]}" -gt 0 ] && command -v winget >/dev/null 2>&1; then
  NOMES=""; for c in "${CMDS[@]}"; do NOMES="${NOMES:+$NOMES, }${c#*|}"; done
  printf '%sA skill está instalada. O winget foi chamado para: %s. Feche e abra o terminal e rode bash install.sh de novo para conferir.%s\n' "$Y" "$NOMES" "$Z"
else
  NOMES=""; for f in "${FALTAM[@]}"; do NOMES="${NOMES:+$NOMES, }$f"; done
  printf '%sA skill está instalada, mas falta: %s.%s\n' "$Y" "$NOMES" "$Z"
fi
echo
echo "Próximos passos:"
echo '  1. Abra o Claude Code numa pasta e peça o vídeo (ex.: "faça um montage com os clipes de C:\Users\...\Videos\valorant e a música X").'
echo "  2. Quando o projeto tiver o venv (a skill cria: pipeline.md, Setup), confira tudo de verdade, inclusive o RIFE na placa:"
echo "       ./venv311/Scripts/python doctor.py        (dentro da pasta _editor do projeto)"
exit 0
