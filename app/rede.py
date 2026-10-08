# Internet do painel (Wi-Fi do computador) e cadastro de luzes novas pelo QR do Smart Life
import json, socket, subprocess, threading, time
from pathlib import Path
import tinytuya
from ajustes import AJ

BASE = Path(__file__).parent
CID, SCHEMA = "HA_3y9q4ak7g4ephrvke", "haauthorize"  # mesmo login por QR do Home Assistant


# ---------- internet / Wi-Fi ----------
_cache = {"t": 0, "ok": False}


def internet_ok():
    if time.time() - _cache["t"] < 4:
        return _cache["ok"]
    ok = False
    for host, porta in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            socket.create_connection((host, porta), timeout=2).close()
            ok = True
            break
        except OSError:
            pass
    _cache.update(t=time.time(), ok=ok)
    return ok


def _nmcli(*args, timeout=30):
    r = subprocess.run(["sudo", "-n", "nmcli", *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


_wifi = {"t": 0, "nome": None}


def wifi_atual():
    if time.time() - _wifi["t"] < 10:
        return _wifi["nome"]
    _wifi["t"] = time.time()
    _wifi["nome"] = _wifi_atual()
    return _wifi["nome"]


def _wifi_atual():
    _, out = _nmcli("-t", "-f", "NAME,DEVICE", "con", "show", "--active")
    for linha in out.splitlines():
        nome, _, dev = linha.rpartition(":")
        if dev == AJ["wifi_if"]:
            _, ssid = _nmcli("-g", "802-11-wireless.ssid", "con", "show", nome)
            return ssid.strip() or nome
    return None


def wifi_lista():
    _, out = _nmcli("-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes", "ifname", AJ["wifi_if"])
    redes = {}
    for linha in out.splitlines():
        partes = linha.replace("\\:", "\x00").split(":")
        if len(partes) < 3:
            continue
        ssid, sinal, seg = (p.replace("\x00", ":") for p in partes[:3])
        if not ssid or ssid == AJ["wifi_sala"]["ssid"]:  # a rede da sala nao tem internet
            continue
        sinal = int(sinal or 0)
        if ssid not in redes or redes[ssid]["sinal"] < sinal:
            redes[ssid] = {"ssid": ssid, "sinal": sinal, "senha": bool(seg and seg != "--")}
    return sorted(redes.values(), key=lambda r: -r["sinal"])


def wifi_conectar(ssid, senha):
    args = ["dev", "wifi", "connect", ssid, "ifname", AJ["wifi_if"]]
    if senha:
        args += ["password", senha]
    cod, out = _nmcli(*args, timeout=60)
    if cod == 0:
        # rede escolhida na tela tem prioridade sobre o hotspot do celular
        _nmcli("con", "mod", ssid, "connection.autoconnect", "yes", "connection.autoconnect-priority", "20")
        _cache["t"] = 0
        _wifi["t"] = 0
        return True, "Conectado"
    if "Secrets were required" in out or "password" in out.lower():
        return False, "Senha incorreta"
    return False, "Não foi possível conectar"


FIXAS = (AJ["hotspot"]["ssid"], "hotspot")  # hotspot do celular (criado pelo instalador); "hotspot" e o perfil antigo do Pi


def wifi_salvas():
    _, out = _nmcli("-t", "-f", "NAME,TYPE", "con", "show")
    redes = []
    for linha in out.splitlines():
        nome, _, tipo = linha.rpartition(":")
        if tipo != "802-11-wireless" or nome == "hotspot":
            continue
        _, ssid = _nmcli("-g", "802-11-wireless.ssid", "con", "show", nome)
        redes.append({"perfil": nome, "ssid": ssid.strip() or nome, "fixa": nome in FIXAS})
    return redes


def wifi_esquecer(perfil):
    if perfil in FIXAS:
        return False, "Essa rede é a padrão do painel e não pode ser esquecida"
    cod, _ = _nmcli("con", "delete", perfil)
    _cache["t"] = 0
    _wifi["t"] = 0
    return cod == 0, "Rede esquecida" if cod == 0 else "Não foi possível esquecer"


# ---------- cadastro de luzes (QR do Smart Life) ----------
cadastro = {"etapa": "parado", "msg": "", "novas": [], "nomes": [], "qr": 0}


def _qr_svg(texto):
    import qrcode, qrcode.image.svg
    img = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
    img.save(str(BASE / "static" / "qr.svg"))


def _buscar_ips():
    """Procura as luzes na rede local pelo broadcast Tuya; devolve {id: (ip, versao)}."""
    try:
        achados = tinytuya.deviceScan(verbose=False, maxretry=8)
    except Exception:
        return {}
    return {d.get("gwId") or d.get("id"): (ip, d.get("version", "")) for ip, d in achados.items()}


def iniciar_cadastro(user_code, ao_terminar):
    if cadastro["etapa"] in ("qr", "importando"):
        return

    def run():
        try:
            from tuya_sharing import LoginControl, Manager
            cadastro.update(etapa="qr", msg="Gerando o código...", novas=[], nomes=[], qr=0)
            lc = LoginControl()
            r = lc.qr_code(CID, SCHEMA, user_code)
            if not r.get("success"):
                cadastro.update(etapa="erro", msg="Não deu para gerar o código. Confira a internet e o código de usuário da conta.")
                return
            token = r["result"]["qrcode"]
            _qr_svg(f"tuyaSmart--qrLogin?token={token}")
            cadastro.update(msg="Aguardando a leitura do código no app...", qr=time.time())
            info = None
            for _ in range(80):  # ~4 minutos
                ok, resp = lc.login_result(token, CID, user_code)
                if ok:
                    info = resp
                    break
                time.sleep(3)
            if not info:
                cadastro.update(etapa="erro", msg="O código expirou sem ser lido. Toque em Tentar de novo.")
                return
            cadastro.update(etapa="importando", msg="Login confirmado! Procurando os aparelhos na rede...")
            m = Manager(CID, user_code, info["terminal_id"], info["endpoint"], info)
            m.update_device_cache()
            ips = _buscar_ips()
            arq = BASE / "devices.json"
            antigos = {d["id"]: d for d in json.loads(arq.read_text(encoding="utf-8"))} if arq.exists() else {}
            # soma aos aparelhos ja cadastrados (podem ser de outras contas), nunca substitui
            novos = [d for i, d in antigos.items() if i not in m.device_map]
            for d in m.device_map.values():
                ip, ver = ips.get(d.id, ("", ""))
                velho = antigos.get(d.id, {})
                novos.append({"name": d.name, "id": d.id, "key": d.local_key,
                              "ip": ip or velho.get("ip", ""), "version": ver or velho.get("version", ""),
                              "product_id": d.product_id, "category": d.category, "status": d.status,
                              "function": {k: {"type": v.type, "values": v.values} for k, v in d.function.items()},
                              "chave_mudou": bool(velho) and velho.get("key") != d.local_key})
            if arq.exists():
                (BASE / "devices.bak.json").write_text(arq.read_text(encoding="utf-8"), encoding="utf-8")
            tmp = arq.with_suffix(".tmp")
            tmp.write_text(json.dumps(novos, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(arq)
            novas = [d["id"] for d in novos if d["id"] not in antigos or d.get("chave_mudou")]
            nomes = [d["name"] for d in novos if d["id"] in novas]
            ao_terminar(novas)
            n = len(novas)
            cadastro.update(etapa="pronto", novas=novas, nomes=nomes,
                            msg="1 aparelho novo no painel!" if n == 1 else f"{n} aparelhos novos no painel!" if n else "Nenhum aparelho novo. Confira se o app terminou de adicionar e se é a mesma conta do código.")
        except Exception as e:
            cadastro.update(etapa="erro", msg=f"Algo deu errado ({e}). Toque em Tentar de novo.")

    threading.Thread(target=run, daemon=True).start()
