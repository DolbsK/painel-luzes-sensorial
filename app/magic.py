# Controladores Magic Home (LEDnet / Zengge): controle 100% local, sem chave e sem nuvem
import colorsys, json, socket, subprocess, threading, time
from pathlib import Path
from flux_led import WifiLedBulb
from flux_led.scanner import BulbScanner
from ajustes import AJ
from efeitos import BRILHO_MAX, EFEITOS, LOCALIZAR_S, ONDA, QUADRO_S, branco_rgb, quadro_efeito

BASE = Path(__file__).parent
ARQ = BASE / "magic.json"
WIFI_IF = AJ["wifi_if"]
FALHAS_OFFLINE = 3  # leituras seguidas falhando ate mostrar "sem resposta"
_trava_lista = threading.Lock()


def ler_lista():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def salvar_lista(lista):
    with _trava_lista:
        tmp = ARQ.with_suffix(".tmp")
        tmp.write_text(json.dumps(lista, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(ARQ)


def descobrir(timeout=5):
    """Procura controladores ja na rede da sala; atualiza IPs e devolve os novos."""
    try:
        achados = BulbScanner().scan(timeout=timeout, address=AJ["rede_sala"])
    except Exception:
        achados = []
    lista = ler_lista()
    por_id = {d["id"]: d for d in lista}
    novos = []
    for a in achados:
        d = por_id.get(a["id"])
        if d:
            d["ip"] = a["ipaddr"]
        else:
            d = {"id": a["id"], "name": f"Fita Magic Home {a['id'][-4:]}", "ip": a["ipaddr"], "model": a.get("model_description", "")}
            lista.append(d)
            novos.append(d)
    salvar_lista(lista)
    return novos


class LuzMagic:
    def __init__(self, cfg, nome):
        self.cfg, self.id, self.nome = cfg, cfg["id"], nome
        self.lock = threading.Lock()
        self.geracao = 0
        self.localizando, self._voltar = False, False
        self.ligada, self.h, self.s, self.v = True, 210, 0.6, 0.4
        self.alvo_h, self.alvo_s, self.alvo_v = 210, 0.6, 0.4
        self.modo, self.temp, self.efeito = "colour", 0.3, None
        self.online = False
        self.tem_cor, self.tem_efeito, self.tem_branco = True, True, False
        self._b = None
        self._ultima_busca = 0
        self._falhas = 0  # leituras seguidas sem resposta

    def eh_interruptor(self):
        return False

    # ---------- conexao ----------
    def bulb(self):
        if self._b is None:
            self._b = WifiLedBulb(self.cfg["ip"], timeout=2)
        return self._b

    def _faz(self, fn):
        for _ in range(2):
            try:
                fn(self.bulb())
                self.online, self._falhas = True, 0
                return True
            except Exception:
                try:
                    self._b and self._b.close()
                except Exception:
                    pass
                self._b = None
        self.online = False
        threading.Thread(target=self._rebuscar, daemon=True).start()
        return False

    def _rebuscar(self):
        if time.time() - self._ultima_busca < 30:
            return
        self._ultima_busca = time.time()
        for d in descobrir(3) + ler_lista():
            if d["id"] == self.id and d["ip"] != self.cfg.get("ip"):
                self.cfg["ip"] = d["ip"]
                self._b = None

    @staticmethod
    def _rgb(h, s, v):
        return tuple(int(round(x * 255)) for x in colorsys.hsv_to_rgb((h % 360) / 360, max(0, min(1, s)), max(0.01, min(1, v))))

    def _v(self, v=None):
        return max(0.03, min(v if v is not None else self.alvo_v, BRILHO_MAX))

    # ---------- acoes (mesma interface das luzes Tuya) ----------
    def ler(self):
        with self.lock:
            def f(b):
                b.update_state()
                self.ligada = bool(b.is_on)
                if b.mode == "color":
                    r, g, bb = b.getRgb()
                    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, bb / 255)
                    if v > 0 and not self.efeito:
                        self.h, self.s, self.v = h * 360, s, v
                        self.alvo_h, self.alvo_s, self.alvo_v = self.h, self.s, self.v
            online = self.online
            if not self._faz(f):
                # uma leitura falha nao derruba a luz na tela; so depois de ~1 min falhando
                self._falhas += 1
                self.online = online and self._falhas < FALHAS_OFFLINE

    def transicao(self, h, s, v=None, dur=1.6):
        self.geracao += 1
        g = self.geracao
        v = self._v(v)
        self.alvo_h, self.alvo_s, self.alvo_v = h % 360, s, v
        def run():
            with self.lock:
                if g != self.geracao:
                    return
                h0, s0, v0 = self.h, self.s, (self.v if self.ligada and self.modo == "colour" else 0.01)
                if not self.ligada:
                    self._faz(lambda b: b.turnOn())
                    self.ligada = True
                dh = ((h - h0 + 180) % 360) - 180
                passos = 10
                for i in range(1, passos + 1):
                    if g != self.geracao:
                        return
                    t = i / passos
                    t = t * t * (3 - 2 * t)
                    hi, si, vi = h0 + dh * t, s0 + (s - s0) * t, v0 + (v - v0) * t
                    self._faz(lambda b: b.setRgb(*self._rgb(hi, si, vi), persist=(i == passos), retry=1))
                    self.h, self.s, self.v = hi % 360, si, vi
                    if i < passos:
                        time.sleep(dur / passos)
                self.modo, self.efeito = "colour", None
        threading.Thread(target=run, daemon=True).start()

    def branco(self, t, v=None):
        self.temp = t
        h, s = branco_rgb(t)
        self.transicao(h, s, self._v(v), dur=1.0)

    def aplicar_efeito(self, nome, vel=1, v=None):
        e = EFEITOS.get(nome)
        if not e:
            return
        self.geracao += 1
        g = self.geracao
        self.alvo_v = self._v(v)
        self.ligada, self.modo, self.efeito = True, "scene", (nome, vel)
        def run():
            # cores enviadas pelo painel no ritmo do relogio do Pi (sincroniza com as outras luzes)
            with self.lock:
                self._faz(lambda b: b.turnOn())
            tentou = 0
            while g == self.geracao:
                if self.online or time.time() - tentou > 5:  # fora do ar: tenta de novo a cada 5 s
                    tentou = time.time()
                    h, s, v = quadro_efeito(e, vel, self.alvo_h, self.alvo_s, self.alvo_v, time.time())
                    with self.lock:
                        if g == self.geracao:
                            self._faz(lambda b: b.setRgb(*self._rgb(h, s, v), persist=False, retry=1))
                time.sleep(QUADRO_S)
        threading.Thread(target=run, daemon=True).start()

    def brilho(self, v):
        v = self._v(v)
        self.alvo_v = v
        if self.modo == "scene" and self.efeito:
            return  # o efeito ja usa o brilho novo no proximo passo
        self.geracao += 1
        with self.lock:
            if not self.ligada:
                self._faz(lambda b: b.turnOn())
            if self._faz(lambda b: b.setRgb(*self._rgb(self.alvo_h, self.alvo_s, v))):
                self.h, self.s, self.v, self.ligada, self.modo = self.alvo_h, self.alvo_s, v, True, "colour"

    def ligar(self, on):
        if on and self.modo == "scene" and self.efeito:
            self.aplicar_efeito(*self.efeito)  # religar continua o efeito
            return
        self.geracao += 1
        with self.lock:
            if self._faz(lambda b: b.turnOn() if on else b.turnOff()):
                self.ligada = bool(on)

    def identificar(self, ligar=True):
        """Pisca ate 30 s (ou ate tocar de novo) e volta ao estado anterior. Outro comando tambem para."""
        self.geracao += 1
        g = self.geracao
        if not ligar:
            self._voltar = self.localizando
            return
        self.localizando, self._voltar = True, False
        h, s, v, ligada = self.alvo_h, self.alvo_s, self.alvo_v, self.ligada
        def run():
            fim, i = time.time() + LOCALIZAR_S, 0
            with self.lock:
                self._faz(lambda b: b.turnOn())
            # a trava e pega a cada passo, para outros comandos nao esperarem os 30 s
            while g == self.geracao and time.time() < fim:
                vi = ONDA[i % len(ONDA)]
                with self.lock:
                    self._faz(lambda b: b.setRgb(*self._rgb(45, 0.9, vi), persist=False, retry=1))
                time.sleep(0.18)
                i += 1
            voltar = self._voltar or g == self.geracao
            self.localizando = False
            if voltar:
                with self.lock:
                    self._faz(lambda b: b.setRgb(*self._rgb(h, s, v)))
                    self.modo, self.efeito = "colour", None
                    if not ligada:
                        self._faz(lambda b: b.turnOff())
                        self.ligada = False
        threading.Thread(target=run, daemon=True).start()

    def estado(self):
        return {"id": self.id, "nome": self.nome, "tipo": "luz", "ligada": self.ligada, "online": self.online,
                "h": round(self.alvo_h), "s": round(self.alvo_s, 2), "v": round(self.alvo_v, 2), "modo": self.modo,
                "temp": self.temp, "efeito": self.efeito[0] if self.efeito else None, "marca": "magic", "localizando": self.localizando,
                "cap": {"cor": True, "branco_real": False, "efeito": True}}


# ---------- configurar controlador novo (rede LEDnet), sem app e sem internet ----------
status = {"etapa": "parado", "msg": "", "nomes": []}


LOG = BASE / "magic.log"


def _log(*a):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%d/%m %H:%M:%S ") + " ".join(str(x) for x in a) + "\n")
    except Exception:
        pass


def _nm(*a, timeout=60):
    r = subprocess.run(["sudo", "-n", "nmcli", *a], capture_output=True, text=True, timeout=timeout)
    _log("nmcli", *a[:4], "->", r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()[:150])
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def aps():
    _, out = _nm("-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list", "--rescan", "yes", "ifname", WIFI_IF)
    vistos = {}
    for linha in out.splitlines():
        ssid, _, sinal = linha.rpartition(":")
        if ssid.upper().startswith(("LEDNET", "MAGIC", "HF-LPB", "ZENGGE", "AK001")):
            vistos[ssid] = max(vistos.get(ssid, 0), int(sinal or 0))
    return [{"ssid": k, "sinal": v} for k, v in sorted(vistos.items(), key=lambda x: -x[1])]


def _wifi_ativo():
    _, out = _nm("-t", "-f", "NAME,DEVICE", "con", "show", "--active")
    for linha in out.splitlines():
        nome, _, dev = linha.rpartition(":")
        if dev == WIFI_IF:
            return nome
    return None


def _at(sock, cmd, espera=1.5):
    sock.sendto(cmd.encode(), ("10.10.123.3", 48899))
    resp, fim = [], time.time() + espera
    while time.time() < fim:
        try:
            d, _ = sock.recvfrom(1024)
            resp.append(d.decode(errors="replace").strip())
        except socket.timeout:
            pass
    _log("AT", repr(cmd), "->", resp)
    return resp


def configurar(ap, ao_terminar):
    if status["etapa"] in ("configurando", "buscando"):
        return

    def run():
        voltar = _wifi_ativo()
        try:
            if not AJ["wifi_sala"]["ssid"]:
                raise RuntimeError("o Wi-Fi da sala não está configurado (ajustes.json)")
            status.update(etapa="configurando", msg="Entrando na rede do controlador...", nomes=[])
            ok = False
            # rede aberta = sem senha; com senha = padrao de fabrica 88888888
            _, out = _nm("-t", "-f", "SSID,SECURITY", "dev", "wifi", "list", "ifname", WIFI_IF)
            seg = next((l.rpartition(":")[2] for l in out.splitlines() if l.rpartition(":")[0] == ap), "")
            senha = "88888888" if seg.strip() not in ("", "--") else None
            _nm("con", "delete", ap)
            args = ["con", "add", "type", "wifi", "ifname", WIFI_IF, "con-name", ap, "ssid", ap,
                    "connection.autoconnect", "no", "ipv6.method", "ignore"]
            if senha:
                args += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", senha]
            _nm(*args)
            # o controlador recem-ligado as vezes recusa a conexao; o Wi-Fi do Pi entao
            # ignora a rede por um tempo, por isso a pausa entre as tentativas
            for i in range(3):
                if i:
                    status.update(msg=f"Entrando na rede do controlador (tentativa {i + 1} de 3)...")
                    time.sleep(20)
                if _nm("--wait", "30", "con", "up", ap, timeout=40)[0] == 0:
                    ok = True
                    break
            if not ok:
                raise RuntimeError("não consegui entrar na rede do controlador. Aproxime o controlador do painel e tente de novo")
            time.sleep(3)
            status.update(msg="Enviando o Wi-Fi da sala para o controlador...")
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.bind(("0.0.0.0", 0))
            resposta = None
            for _ in range(4):
                resposta = _at(s, "HF-A11ASSISTHREAD", 2)
                if resposta:
                    break
            if not resposta:
                raise RuntimeError("o controlador não respondeu")
            _at(s, "+ok", 0.5)
            r1 = _at(s, f"AT+WSSSID={AJ['wifi_sala']['ssid']}\r")
            r2 = _at(s, f"AT+WSKEY=WPA2PSK,AES,{AJ['wifi_sala']['senha']}\r")
            _at(s, "AT+WSSSID\r")
            _at(s, "AT+WSKEY\r")
            _at(s, "AT+WMODE=STA\r")
            _at(s, "AT+Z\r")
            if not (r1 and r2):
                raise RuntimeError("o controlador não aceitou a configuração")
        except Exception as e:
            _log("ERRO", e)
            status.update(etapa="erro", msg=f"Não deu certo: {e}.")
            return
        finally:
            _nm("con", "delete", ap)
            if voltar and voltar != ap:
                _nm("con", "up", voltar)
        status.update(etapa="buscando", msg="Controlador configurado! Esperando ele entrar na rede da sala...")
        novos = []
        for _ in range(12):  # ate ~60 s
            time.sleep(5)
            novos = descobrir(4)
            if novos:
                break
        ao_terminar()
        _log("busca na sala ->", [d["id"] for d in novos])
        if novos:
            status.update(etapa="pronto", nomes=[d["name"] for d in novos], msg="1 fita nova no painel!" if len(novos) == 1 else f"{len(novos)} fitas novas no painel!")
        else:
            status.update(etapa="erro", msg="O controlador foi configurado mas ainda não apareceu na rede. Toque em \"Procurar fitas já na sala\" em 1 minuto.")

    threading.Thread(target=run, daemon=True).start()


def buscar_na_sala(ao_terminar):
    if status["etapa"] in ("configurando", "buscando"):
        return

    def run():
        status.update(etapa="buscando", msg="Procurando fitas Magic Home na rede da sala...", nomes=[])
        novos = descobrir(6)
        ao_terminar()
        if novos:
            status.update(etapa="pronto", nomes=[d["name"] for d in novos], msg="1 fita nova no painel!" if len(novos) == 1 else f"{len(novos)} fitas novas no painel!")
        else:
            status.update(etapa="pronto", nomes=[], msg="Nenhuma fita nova encontrada na rede da sala.")

    threading.Thread(target=run, daemon=True).start()
