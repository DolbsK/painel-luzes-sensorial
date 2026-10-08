#!/usr/bin/env bash
# Instala ou atualiza o painel de luzes num Raspberry Pi com tela touch.
# Sistema: Raspberry Pi OS com desktop (Bookworm ou Trixie), 64 bits.
#
# Instalar (de dentro da pasta baixada do GitHub):   sudo ./instalar.sh
# Instalar direto da internet:                       curl -fsSL https://raw.githubusercontent.com/DolbsK/painel-luzes-sensorial/main/instalar.sh | sudo bash
# So atualizar o codigo (mantem rede, ajustes e luzes): sudo ./instalar.sh --atualizar
# Refazer as perguntas (nome da sala, Wi-Fi...):     sudo ./instalar.sh --reconfigurar
set -euo pipefail

REPO_GIT="https://github.com/DolbsK/painel-luzes-sensorial.git"
MODO="instalar"
case "${1:-}" in
  --atualizar) MODO="atualizar" ;;
  --reconfigurar) MODO="reconfigurar" ;;
  "") ;;
  *) echo "Opção desconhecida: $1"; exit 1 ;;
esac

passo() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
aviso() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
erro() { printf '\033[1;31m[x] %s\033[0m\n' "$*"; exit 1; }
# le do teclado mesmo quando o script chega por "curl | bash"
pergunta() { local texto=$1 padrao=${2:-} resp; read -r -p "$texto${padrao:+ [$padrao]}: " resp </dev/tty; echo "${resp:-$padrao}"; }

# ---------- 1. conferencias ----------
[ "$(id -u)" -eq 0 ] || erro "Rode com sudo: sudo $0 $*"
# shellcheck source=/dev/null
. /etc/os-release
case "${VERSION_CODENAME:-}" in bookworm|trixie) ;; *) erro "Sistema não suportado (${PRETTY_NAME:-?}). Use Raspberry Pi OS Bookworm ou Trixie." ;; esac
USUARIO=${SUDO_USER:-}
[ -n "$USUARIO" ] && [ "$USUARIO" != root ] || USUARIO=$(pergunta "Usuário que vai rodar o painel" "$(getent passwd 1000 | cut -d: -f1)")
id "$USUARIO" >/dev/null 2>&1 || erro "Usuário $USUARIO não existe."
CASA=$(getent passwd "$USUARIO" | cut -d: -f6)
PASTA="$CASA/luzes"

# ---------- 2. codigo (pasta local ou GitHub) ----------
ORIGEM=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)
if [ ! -f "$ORIGEM/app/app.py" ]; then
  passo "Baixando o painel do GitHub"
  command -v git >/dev/null || { apt-get update -qq && apt-get install -y -qq git; }
  ORIGEM=$(mktemp -d)
  git clone -q --depth 1 "$REPO_GIT" "$ORIGEM"
fi

# ---------- 3. perguntas (so na primeira vez ou com --reconfigurar) ----------
WIFI_IF=$(nmcli -t -f DEVICE,TYPE dev 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')
CABO_IF=$(nmcli -t -f DEVICE,TYPE dev 2>/dev/null | awk -F: '$2=="ethernet"{print $1; exit}')
WIFI_IF=${WIFI_IF:-wlan0}; CABO_IF=${CABO_IF:-eth0}
if [ "$MODO" = reconfigurar ] || { [ "$MODO" = instalar ] && [ ! -f "$PASTA/ajustes.json" ]; }; then
  passo "Perguntas da instalação (Enter aceita o valor entre colchetes)"
  echo "A sala precisa de um roteador com Wi-Fi 2,4 GHz, onde as luzes vão ficar. Este computador fica ligado nele pelo cabo."
  SALA=$(pergunta "Nome da sala, aparece no topo da tela" "Sala Sensorial")
  WIFI_SSID=$(pergunta "Nome do Wi-Fi da sala (rede das luzes)")
  [ -n "$WIFI_SSID" ] || erro "O nome do Wi-Fi da sala é obrigatório."
  while :; do WIFI_SENHA=$(pergunta "Senha do Wi-Fi da sala (mínimo 8 caracteres)"); [ ${#WIFI_SENHA} -ge 8 ] && break; aviso "Senha curta demais."; done
  echo "Hotspot: o roteador do celular, usado só para cadastrar luzes Tuya (precisam de internet uma vez)."
  HOT_SSID=$(pergunta "Nome do hotspot do celular" "luzesPI")
  while :; do HOT_SENHA=$(pergunta "Senha do hotspot (mínimo 8 caracteres)" "12345678"); [ ${#HOT_SENHA} -ge 8 ] && break; aviso "Senha curta demais."; done
  IP_CABO=$(pergunta "IP deste computador na rede da sala" "192.168.0.2")
  ZOOM=$(pergunta "Zoom da tela (1.8 para tela 7\" em 1920x1080; 1 para tela comum)" "1.8")
  CODIGO=$(pergunta "Código de usuário da conta Smart Life (pode deixar em branco)" "")
fi

# ---------- 4. pacotes ----------
if [ "$MODO" != atualizar ]; then
  passo "Instalando pacotes do sistema"
  apt-get update -qq
  apt-get install -y -qq python3-venv network-manager iw curl rsync labwc kanshi libinput-tools
  apt-get install -y -qq chromium 2>/dev/null || apt-get install -y -qq chromium-browser
fi

# ---------- 5. painel ----------
passo "Copiando o painel para $PASTA"
mkdir -p "$PASTA/static"
cp "$ORIGEM"/app/*.py "$ORIGEM/app/ajustes.exemplo.json" "$PASTA/"
rsync -a --exclude qr.svg "$ORIGEM/app/static/" "$PASTA/static/"
install -m 755 "$ORIGEM/sistema/kiosk.sh" "$PASTA/kiosk.sh"
[ -d "$PASTA/venv" ] || python3 -m venv "$PASTA/venv"
"$PASTA/venv/bin/pip" install -q --upgrade pip
"$PASTA/venv/bin/pip" install -q -r "$ORIGEM/requirements.txt"

if [ -n "${WIFI_SSID:-}" ]; then
  passo "Gravando ajustes.json"
  BROADCAST="${IP_CABO%.*}.255"
  SALA="$SALA" WIFI_SSID="$WIFI_SSID" WIFI_SENHA="$WIFI_SENHA" HOT_SSID="$HOT_SSID" HOT_SENHA="$HOT_SENHA" BROADCAST="$BROADCAST" \
  WIFI_IF="$WIFI_IF" CODIGO="$CODIGO" ZOOM="$ZOOM" python3 - "$PASTA/ajustes.json" <<'PY'
import json, os, sys
e = os.environ
aj = {"sala": e["SALA"], "wifi_sala": {"ssid": e["WIFI_SSID"], "senha": e["WIFI_SENHA"]},
      "hotspot": {"ssid": e["HOT_SSID"], "senha": e["HOT_SENHA"]}, "rede_sala": e["BROADCAST"],
      "wifi_if": e["WIFI_IF"], "smartlife_codigo": e["CODIGO"], "zoom": float(e["ZOOM"].replace(",", "."))}
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(aj, indent=2, ensure_ascii=False) + "\n")
PY
  chmod 600 "$PASTA/ajustes.json"
fi
[ -f "$PASTA/ajustes.json" ] || erro "Falta $PASTA/ajustes.json. Rode: sudo $0 --reconfigurar"
chown -R "$USUARIO:$USUARIO" "$PASTA"

# ---------- 6. servico do painel ----------
passo "Serviço do painel (luzes.service)"
sed -e "s|__USUARIO__|$USUARIO|g" -e "s|__PASTA__|$PASTA|g" "$ORIGEM/sistema/luzes.service" >/etc/systemd/system/luzes.service
systemctl daemon-reload
systemctl enable -q luzes
systemctl restart luzes

if [ "$MODO" = atualizar ]; then
  pkill -x chromium 2>/dev/null || pkill -f chromium-browser 2>/dev/null || true
  passo "Pronto: código atualizado e painel reiniciado."
  exit 0
fi

# ---------- 7. permissoes, navegador e Wi-Fi ----------
passo "Permissões do painel (só nmcli e date, sem senha)"
echo "$USUARIO ALL=(root) NOPASSWD: /usr/bin/nmcli" >/tmp/luzes-nmcli
echo "$USUARIO ALL=(root) NOPASSWD: /usr/bin/date" >/tmp/luzes-hora
for f in luzes-nmcli luzes-hora; do visudo -cqf "/tmp/$f" && install -m 440 "/tmp/$f" "/etc/sudoers.d/$f"; rm -f "/tmp/$f"; done

passo "Política do navegador (só abre o painel)"
install -d /etc/chromium/policies/managed
install -m 644 "$ORIGEM/sistema/chromium-policy-kiosk.json" /etc/chromium/policies/managed/kiosk.json

passo "Wi-Fi sem economia de energia ($WIFI_IF)"
sed "s|__WIFI__|$WIFI_IF|g" "$ORIGEM/sistema/99-wifi-nopowersave" >/etc/NetworkManager/dispatcher.d/99-wifi-nopowersave
chmod 755 /etc/NetworkManager/dispatcher.d/99-wifi-nopowersave

# ---------- 8. rede ----------
if [ -n "${WIFI_SSID:-}" ]; then
  passo "Rede: cabo ($CABO_IF) distribui IP para o roteador da sala; hotspot do celular para cadastro"
  CON_CABO=$(nmcli -t -f NAME,DEVICE con show | awk -F: -v d="$CABO_IF" '$2==d{print $1; exit}')
  if [ -z "$CON_CABO" ]; then
    CON_CABO="luzes-cabo"
    nmcli con delete "$CON_CABO" >/dev/null 2>&1 || true
    nmcli con add type ethernet ifname "$CABO_IF" con-name "$CON_CABO" >/dev/null
  fi
  # vale no proximo boot: aplicar agora derrubaria quem esta conectado pelo cabo
  nmcli con mod "$CON_CABO" ipv4.method shared ipv4.addresses "$IP_CABO/24" ipv6.method ignore connection.autoconnect yes
  nmcli con delete "$HOT_SSID" >/dev/null 2>&1 || true
  nmcli con add type wifi ifname "$WIFI_IF" con-name "$HOT_SSID" ssid "$HOT_SSID" \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$HOT_SENHA" connection.autoconnect yes connection.autoconnect-priority 10 >/dev/null
fi

# ---------- 9. tela cheia ----------
passo "Tela: login automático e painel em tela cheia"
if command -v raspi-config >/dev/null; then raspi-config nonint do_boot_behaviour B4; else aviso "raspi-config não encontrado: ligue o login automático na mão."; fi
install -d -o "$USUARIO" -g "$USUARIO" "$CASA/.config/labwc"
AUTO="$CASA/.config/labwc/autostart"
[ -f "$AUTO" ] && ! grep -q "kiosk.sh" "$AUTO" && cp "$AUTO" "$AUTO.antes-painel"
sed "s|__PASTA__|$PASTA|g" "$ORIGEM/sistema/labwc-autostart" >"$AUTO"
command -v lwrespawn >/dev/null || sed -i "s|/usr/bin/lwrespawn ||" "$AUTO"
# toque: liga a tela touch a saida HDMI (com duas saidas o toque cairia no lugar errado)
TOQUE=$(libinput list-devices 2>/dev/null | awk '/^Device:/{sub(/^Device: +/,""); n=$0} /^Capabilities:.*touch/{print n; exit}')
SAIDA=$(for s in /sys/class/drm/card*-HDMI-A-*/status; do [ "$(cat "$s" 2>/dev/null)" = connected ] && basename "$(dirname "$s")" | sed 's/^card[0-9]*-//' && break; done || true)
if [ -n "$TOQUE" ] && [ -n "$SAIDA" ]; then
  cat >"$CASA/.config/labwc/rc.xml" <<XML
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
	<touch deviceName="$TOQUE" mapToOutput="$SAIDA" mouseEmulation="yes"/>
</openbox_config>
XML
else
  aviso "Tela touch ou saída HDMI não encontrada agora. Se o toque ficar no lugar errado, rode de novo com a tela ligada."
fi
chown -R "$USUARIO:$USUARIO" "$CASA/.config/labwc"

timedatectl set-timezone America/Sao_Paulo || true

passo "Pronto"
cat <<FIM
Painel instalado em $PASTA (serviço: luzes).
Wi-Fi da sala: ${WIFI_SSID:-(sem mudança)} · hotspot de cadastro: ${HOT_SSID:-(sem mudança)} · IP no cabo: ${IP_CABO:-(sem mudança)}

Próximos passos:
  1. Ligue o cabo deste computador numa porta LAN do roteador da sala.
  2. No roteador: Wi-Fi 2,4 GHz com o nome e senha acima, DHCP desligado, sem isolamento de clientes.
  3. Reinicie: sudo reboot
  4. Na tela: aba Ajustes > "+ Adicionar luz ou interruptor".
FIM
