#!/bin/sh
# Abre o painel em tela cheia quando o servidor local responder. O zoom vem do ajustes.json.
PASTA=$(dirname "$(readlink -f "$0")")
ZOOM=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('zoom', 1))" "$PASTA/ajustes.json" 2>/dev/null || echo 1)
NAVEGADOR=$(command -v chromium || command -v chromium-browser)
until curl -s -o /dev/null http://localhost:8080/; do sleep 1; done
exec "$NAVEGADOR" --kiosk --force-device-scale-factor="$ZOOM" --app=http://localhost:8080/ --noerrdialogs --disable-infobars --no-first-run \
  --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 \
  --password-store=basic --disable-features=Translate,TranslateUI --check-for-update-interval=31536000
