# Ajustes de cada instalacao (nome da sala, Wi-Fi da sala, hotspot de cadastro, rede).
# Ficam em ajustes.json, criado pelo instalador; ajustes.exemplo.json mostra todos os campos.
import json
from pathlib import Path

BASE = Path(__file__).parent
ARQ = BASE / "ajustes.json"

PADRAO = {
    "sala": "Sala Sensorial",
    "wifi_sala": {"ssid": "", "senha": ""},       # rede 2,4 GHz onde as luzes ficam (roteador da sala)
    "hotspot": {"ssid": "luzesPI", "senha": "12345678"},  # roteador do celular, so para cadastrar luz Tuya
    "rede_sala": "192.168.0.255",                 # broadcast da rede da sala (cabo do computador)
    "wifi_if": "wlan0",                           # placa Wi-Fi do computador
    "smartlife_codigo": "",                       # codigo de usuario padrao da conta Smart Life
}


def _ler():
    try:
        dados = json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    aj = {**PADRAO, **dados}
    for k in ("wifi_sala", "hotspot"):
        aj[k] = {**PADRAO[k], **(dados.get(k) or {})}
    return aj


AJ = _ler()


def publico():
    """O que a tela precisa saber (o assistente mostra o Wi-Fi da sala e do hotspot na tela)."""
    return {"sala": AJ["sala"], "wifi_sala": AJ["wifi_sala"], "hotspot": AJ["hotspot"]}
