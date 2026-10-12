#!/usr/bin/env bash
# Atualizacao automatica do painel pelo GitHub. Roda como root pelo luzes-atualizar.timer (toda noite, 1h).
# So atualiza com internet, com versao nova no ramo main e com o painel sem uso.
# Se o painel nao voltar depois de atualizar, volta sozinho para a versao anterior e nao tenta de novo essa versao.
# Pausar (ex.: testando codigo novo direto no Pi): crie o arquivo <pasta do painel>/.sem-atualizacao-auto
# Teste sem mudar nada: SIMULAR=1 /usr/local/sbin/luzes-atualizar
set -uo pipefail

REPO="https://github.com/DolbsK/painel-luzes-sensorial.git"
RAMO="main"
USUARIO=${USUARIO:?}
PASTA=${PASTA:?}
OCIOSO_MIN=${OCIOSO_MIN:-1800}   # segundos sem toque na tela antes de poder atualizar
ESTADO=/var/lib/luzes-atualizar
LOG=/var/log/luzes-atualizar.log
VERSAO="$PASTA/.versao"
RUIM="$ESTADO/versao-ruim"

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
painel_ok() { for _ in $(seq 1 60); do curl -fs -o /dev/null -m 3 http://127.0.0.1:8080/api/estado && return 0; sleep 2; done; return 1; }

[ -e "$PASTA/.sem-atualizacao-auto" ] && exit 0

remoto=$(timeout 20 git ls-remote "$REPO" "refs/heads/$RAMO" 2>/dev/null | cut -f1)
[ -n "$remoto" ] || exit 0                                   # sem internet ou GitHub fora: tenta na proxima
[ "$remoto" = "$(cat "$VERSAO" 2>/dev/null)" ] && exit 0     # ja esta na versao do GitHub
[ "$remoto" = "$(cat "$RUIM" 2>/dev/null)" ] && exit 0       # essa versao ja falhou aqui

# Painel sem uso: 30 min sem toque e nenhum efeito ou cena viva rodando.
# De madrugada (0h as 5h) efeito rodando nao segura a atualizacao. Painel fora do ar: atualiza (pode ser a correcao).
uso=$(curl -fs -m 5 http://127.0.0.1:8080/api/ocioso || true)
if [ -n "$uso" ]; then
  read -r ocioso efeito < <(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(int(d["ocioso_s"]), int(bool(d["efeito"])))' "$uso")
  if [ "$ocioso" -lt "$OCIOSO_MIN" ]; then log "versão nova ${remoto:0:7}: painel em uso (último toque há ${ocioso}s), fica para depois"; exit 0; fi
  if [ "$efeito" = 1 ] && [ "$((10#$(date +%H)))" -ge 5 ]; then log "versão nova ${remoto:0:7}: efeito rodando, fica para depois"; exit 0; fi
fi

if [ "${SIMULAR:-}" = 1 ]; then log "SIMULAÇÃO: atualizaria $(cut -c1-7 "$VERSAO" 2>/dev/null || echo '?') -> ${remoto:0:7}"; exit 0; fi

mkdir -p "$ESTADO"
REPO_LOCAL="$ESTADO/repo"
if [ -d "$REPO_LOCAL/.git" ]; then
  git -C "$REPO_LOCAL" fetch -q --depth 1 origin "$RAMO" && git -C "$REPO_LOCAL" reset -q --hard FETCH_HEAD
else
  rm -rf "$REPO_LOCAL" && git clone -q --depth 1 -b "$RAMO" "$REPO" "$REPO_LOCAL"
fi || { log "falha ao baixar ${remoto:0:7}, tenta na próxima"; exit 0; }
novo=$(git -C "$REPO_LOCAL" rev-parse HEAD)

log "atualizando $(cut -c1-7 "$VERSAO" 2>/dev/null || echo '?') -> ${novo:0:7}"
# copia de seguranca do codigo atual (sem o venv e os sons, que o instalador nao apaga)
rm -rf "$PASTA.anterior"
rsync -a --exclude venv --exclude static/sons "$PASTA/" "$PASTA.anterior/"

if SUDO_USER="$USUARIO" bash "$REPO_LOCAL/instalar.sh" --atualizar >>"$LOG" 2>&1 && painel_ok; then
  echo "$novo" >"$VERSAO"; chown "$USUARIO:" "$VERSAO"
  log "ok, painel na versão ${novo:0:7}"
else
  log "painel não voltou com ${novo:0:7}: voltando à versão anterior"
  echo "$novo" >"$RUIM"
  rsync -a --exclude venv --exclude static/sons "$PASTA.anterior/" "$PASTA/"
  systemctl restart luzes
  pkill -x chromium || true
  painel_ok && log "versão anterior de volta" || log "ATENÇÃO: painel fora do ar mesmo na versão anterior"
fi
