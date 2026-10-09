# Painel de luzes da sala sensorial: controla luzes Tuya e Magic Home pela rede local (sem nuvem)
import colorsys, json, subprocess, threading, time, urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote
import tinytuya
from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import magic
import rede
from ajustes import AJ, publico
from efeitos import (BRILHO_MAX, CENAS, EFEITOS, LOCALIZAR_S, ONDA, QUADRO_S, branco_rgb, definir_reacao, esperar_quadro,
                     quadro_efeito, reacao, reagir, zerar_reacao)

BASE = Path(__file__).parent
CONFIG = BASE / "config.json"  # o que muda pela tela: nomes, removidos, cidade do clima, conta Smart Life
FALHAS_OFFLINE = 3  # leituras seguidas falhando (a cada 20 s) ate mostrar "sem resposta"
_trava_config = threading.Lock()


def ler_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"nomes": {}}


def salvar_config(cfg):
    with _trava_config:  # duas gravacoes ao mesmo tempo corromperiam o arquivo
        tmp = CONFIG.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CONFIG)


class Luz:
    def __init__(self, cfg, nome):
        self.cfg = cfg
        self.id = cfg["id"]
        self.nome = nome
        self.lock = threading.Lock()
        self.geracao = 0
        self.localizando, self._voltar = False, False
        self.ligada, self.h, self.s, self.v = True, 210, 0.6, 0.35
        # cor/brilho de destino (o que foi pedido), separado do valor atual no meio de um fade
        self.alvo_h, self.alvo_s, self.alvo_v = 210, 0.6, 0.4
        self.modo, self.temp = None, 0.3
        self.efeito = None  # (nome, velocidade) quando em efeito
        self.online = False
        self.tipo = None  # "B" (dps 20-25), "A" (dps 1-5) ou "so_liga"
        codigos = set((cfg.get("function") or {}).keys()) | set((cfg.get("status") or {}).keys())
        self.tem_branco = any(c.startswith("temp_value") for c in codigos)
        self.tem_cor = any(c.startswith("colour_data") for c in codigos) or not codigos
        self.tem_efeito = any(c.startswith("scene_data") for c in codigos) or not codigos
        self._dev = None
        self._ultima_busca = 0
        self._falhas = 0  # leituras seguidas sem resposta

    # ---------- conexao ----------
    def dev(self):
        if self._dev is None:
            d = tinytuya.Device(self.id, self.cfg.get("ip") or "Auto", self.cfg["key"],
                                version=float(self.cfg.get("version") or 3.3))
            d.set_socketPersistent(True)
            d.set_socketTimeout(2)
            d.set_socketRetryLimit(1)
            self._dev = d
        return self._dev

    def redescobrir(self):
        """Se a luz mudou de IP (DHCP), acha de novo pelo broadcast da rede local."""
        if time.time() - self._ultima_busca < 30:
            return
        self._ultima_busca = time.time()
        try:
            r = tinytuya.find_device(self.id)
            if r and r.get("ip"):
                self.cfg["ip"] = r["ip"]
                if r.get("version"):
                    self.cfg["version"] = r["version"]
                self._dev = None
        except Exception:
            pass

    def _enviar(self, dps, nowait=False):
        for _ in range(2):
            try:
                r = self.dev().set_multiple_values(dps, nowait=nowait)
                if isinstance(r, dict) and r.get("Error"):
                    raise RuntimeError(r.get("Error"))
                self.online, self._falhas = True, 0
                return True
            except Exception:
                self._dev = None
        self.online = False
        threading.Thread(target=self.redescobrir, daemon=True).start()
        return False

    def _status(self):
        try:
            return self.dev().status().get("dps", {})
        except Exception:
            return {}

    def ler(self):
        with self.lock:
            st = self._status()
            if not st:
                # a luz fecha a conexao parada; tenta de novo na hora com conexao nova
                self._dev = None
                st = self._status()
            if not st:
                self._dev = None
                self._falhas += 1
                if self._falhas >= FALHAS_OFFLINE:  # so marca "sem resposta" depois de ~1 min falhando
                    self.online = False
                    threading.Thread(target=self.redescobrir, daemon=True).start()
                return
            self._falhas = 0
            self.online = True
            # o tipo so e decidido uma vez; respostas parciais (so alguns dps) nunca rebaixam a luz
            if self.tipo is None:
                if any(k in st for k in ("20", "21", "22", "23", "24", "25")):
                    self.tipo = "B"
                elif "1" in st and "5" in st:
                    self.tipo = "A"
                elif "1" in st and not (self.tem_cor or self.tem_efeito):
                    self.tipo = "so_liga"
            if self.tipo == "B":
                if "20" in st:
                    self.ligada = bool(st["20"])
                if not self.efeito:  # durante o efeito a luz se reporta em "colour"
                    self.modo = st.get("21", self.modo)
                c = st.get("24")
                if c and len(c) == 12 and self.modo == "colour" and not self.efeito:
                    self.h, self.s, self.v = int(c[0:4], 16), int(c[4:8], 16) / 1000, int(c[8:12], 16) / 1000
                    self.alvo_h, self.alvo_s, self.alvo_v = self.h, self.s, self.v
            elif self.tipo == "A":
                if "1" in st:
                    self.ligada = bool(st["1"])
                if not self.efeito:  # durante o efeito a luz se reporta em "colour"
                    self.modo = st.get("2", self.modo)
            elif self.tipo == "so_liga" and "1" in st:
                self.ligada = bool(st["1"])

    # ---------- formatos ----------
    def _dp(self, nome):
        mapa = {"B": {"liga": "20", "modo": "21", "brilho": "22", "temp": "23", "cor": "24", "cena": "25"},
                "A": {"liga": "1", "modo": "2", "brilho": "3", "temp": "4", "cor": "5"},
                "so_liga": {"liga": "1"}}
        return mapa.get(self.tipo or "B", {}).get(nome)

    def _cor(self, h, s, v):
        h, s, v = h % 360, max(0, min(1, s)), max(0.01, min(1, v))
        if self.tipo == "A":
            r, g, b = (int(x * 255) for x in colorsys.hsv_to_rgb(h / 360, s, v))
            return "%02x%02x%02x%04x%02x%02x" % (r, g, b, int(h), int(s * 255), int(v * 255))
        return "%04x%04x%04x" % (int(h), int(s * 1000), int(v * 1000))

    # ---------- acoes ----------
    def _v(self, v=None):
        return max(0.03, min(v if v is not None else self.alvo_v, BRILHO_MAX))

    def transicao(self, h, s, v=None, dur=1.6):
        """Fade suave ate a cor nova. Um comando novo cancela o fade em andamento."""
        self.geracao += 1
        g = self.geracao
        v = self._v(v)
        self.alvo_h, self.alvo_s, self.alvo_v = h % 360, s, v
        def run():
            with self.lock:
                if g != self.geracao or not self.tem_cor:
                    return
                h0, s0, v0 = self.h, self.s, (self.v if self.ligada else 0.01)
                if not self.ligada or self.modo != "colour":
                    self._enviar({self._dp("liga"): True, self._dp("modo"): "colour", self._dp("cor"): self._cor(h0, s0, v0)})
                    self.ligada, self.modo, self.efeito = True, "colour", None
                dh = ((h - h0 + 180) % 360) - 180  # menor caminho na roda de cor
                passos = 10
                for i in range(1, passos):
                    if g != self.geracao:
                        return
                    t = i / passos
                    t = t * t * (3 - 2 * t)
                    hi, si, vi = h0 + dh * t, s0 + (s - s0) * t, v0 + (v - v0) * t
                    # passos intermediarios sem esperar resposta, so o ultimo e confirmado
                    self._enviar({self._dp("cor"): self._cor(hi, si, vi)}, nowait=True)
                    self.h, self.s, self.v = hi % 360, si, vi
                    time.sleep(dur / passos)
                if g == self.geracao:
                    self._enviar({self._dp("cor"): self._cor(h, s, v)})
                    self.h, self.s, self.v = h % 360, s, v
        threading.Thread(target=run, daemon=True).start()

    def branco(self, t, v=None):
        self.temp = t
        v = self._v(v)
        self.alvo_v = v
        if self.tem_branco and self.tipo in ("B", "A"):
            self.geracao += 1
            escala = 1000 if self.tipo == "B" else 255
            minimo = 10 if self.tipo == "B" else 25
            with self.lock:
                self._enviar({self._dp("liga"): True, self._dp("modo"): "white",
                              self._dp("brilho"): max(minimo, int(v * escala)),
                              self._dp("temp"): int(t * escala)})
                self.ligada, self.modo, self.v, self.efeito = True, "white", v, None
        else:
            h, s = branco_rgb(t)
            self.transicao(h, s, v, dur=1.0)
            return
        self.alvo_h, self.alvo_s = branco_rgb(t)

    def aplicar_efeito(self, nome, vel=1, v=None):
        e = EFEITOS.get(nome)
        if not e or not self.tem_cor:
            return
        self.geracao += 1
        g = self.geracao
        self.alvo_v = self._v(v)
        self.ligada, self.modo, self.efeito = True, "scene", (nome, vel)
        def run():
            with self.lock:
                self._enviar({self._dp("liga"): True, self._dp("modo"): "colour"})
            tentou = 0
            while g == self.geracao:
                n0, agora = reacao["n"], time.time()
                if self.online or agora - tentou > 5:  # luz fora do ar: tenta de novo a cada 5 s
                    tentou = agora
                    h, s, v = quadro_efeito(e, vel, self.alvo_h, self.alvo_s, self.alvo_v, agora)
                    h, s, v = reagir(nome, h, s, v, agora)  # luz acompanhando o som (so se a tela avisou)
                    with self.lock:
                        if g == self.geracao:
                            self._enviar({self._dp("cor"): self._cor(h, s, v)}, nowait=True)
                            self.h, self.s, self.v = h, s, v
                esperar_quadro(n0, time.time())
        threading.Thread(target=run, daemon=True).start()

    def brilho(self, v):
        """Muda so o brilho, mantendo a cor de destino (nunca a cor do meio de um fade)."""
        v = self._v(v)
        self.alvo_v = v
        if self.modo == "scene" and self.efeito:
            return  # o efeito ja usa o brilho novo no proximo passo
        elif self.modo == "white" and self.tem_branco:
            self.branco(self.temp, v)
        elif self.tem_cor:
            self.geracao += 1
            with self.lock:
                dps = {self._dp("cor"): self._cor(self.alvo_h, self.alvo_s, v)}
                if not self.ligada or self.modo != "colour":
                    dps.update({self._dp("liga"): True, self._dp("modo"): "colour"})
                if self._enviar(dps):
                    self.h, self.s, self.v, self.ligada, self.modo = self.alvo_h, self.alvo_s, v, True, "colour"

    def ligar(self, on):
        if on and self.modo == "scene" and self.efeito:
            self.aplicar_efeito(*self.efeito)  # religar continua o efeito
            return
        self.geracao += 1
        with self.lock:
            if self._enviar({self._dp("liga"): bool(on)}):
                self.ligada = bool(on)

    def identificar(self, ligar=True):
        """Pisca devagar ate 30 s (ou ate tocar de novo) e volta ao estado anterior, para saber qual luz e qual.
        Outro comando na luz tambem para a piscada, sem voltar ao estado anterior."""
        self.geracao += 1
        g = self.geracao
        if not ligar:
            self._voltar = self.localizando
            return
        self.localizando, self._voltar = True, False
        h, s, v, ligada = self.h, self.s, self.v, self.ligada
        def run():
            fim, i = time.time() + LOCALIZAR_S, 0
            if self.tem_cor:
                with self.lock:
                    self._enviar({self._dp("liga"): True, self._dp("modo"): "colour"})
            # a trava e pega a cada passo, para outros comandos nao esperarem os 30 s
            while g == self.geracao and time.time() < fim:
                with self.lock:
                    if self.tem_cor:
                        self._enviar({self._dp("cor"): self._cor(45, 0.9, ONDA[i % len(ONDA)])}, nowait=True)
                    else:
                        self._enviar({self._dp("liga"): i % 2 == 0})
                time.sleep(0.18 if self.tem_cor else 0.8)
                i += 1
            voltar = self._voltar or g == self.geracao
            self.localizando = False
            if voltar:
                with self.lock:
                    if self.tem_cor:
                        self._enviar({self._dp("cor"): self._cor(h, s, v)})
                        self.modo, self.efeito = "colour", None
                    self._enviar({self._dp("liga"): ligada})
                    self.ligada = ligada
        threading.Thread(target=run, daemon=True).start()

    def eh_interruptor(self):
        cat = self.cfg.get("category", "")
        return cat in ("kg", "tdq", "cz", "pc", "dlq") or not (self.tem_cor or self.tem_efeito or self.tem_branco)

    def estado(self):
        return {"id": self.id, "nome": self.nome, "tipo": "interruptor" if self.eh_interruptor() else "luz", "ligada": self.ligada, "online": self.online,
                "h": round(self.alvo_h), "s": round(self.alvo_s, 2), "v": round(self.alvo_v, 2), "modo": self.modo,
                "temp": self.temp, "efeito": self.efeito[0] if self.efeito else None, "localizando": self.localizando,
                "cap": {"cor": self.tem_cor, "branco_real": self.tem_branco, "efeito": self.tem_cor}}


config = ler_config()
luzes: list = []


def carregar():
    global luzes
    arq = BASE / "devices.json"
    dados = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else []
    nomes = config.setdefault("nomes", {})
    removidos = set(config.get("removidos", []))
    luzes = [Luz(d, nomes.get(d["id"]) or d.get("name") or d["id"]) for d in dados if d["id"] not in removidos]
    luzes += [magic.LuzMagic(d, nomes.get(d["id"]) or d.get("name") or d["id"]) for d in magic.ler_lista() if d["id"] not in removidos]
    for l in luzes:
        threading.Thread(target=l.ler, daemon=True).start()


def vigia():
    # mantem o status atualizado e reconecta luzes que cairam
    while True:
        time.sleep(20)
        for l in list(luzes):
            if not l.lock.locked() and not l.localizando:
                l.ler()


carregar()
threading.Thread(target=vigia, daemon=True).start()
estado_geral = {"cena": None}

app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


def alvos(ids: Optional[list[str]]):
    return [l for l in luzes if not ids or l.id in ids]


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/estado")
def api_estado():
    return {"cena": estado_geral["cena"], "brilho_max": BRILHO_MAX, "luzes": [l.estado() for l in luzes]}


class Pedido(BaseModel):
    alvos: Optional[list[str]] = None
    nome: Optional[str] = None
    h: Optional[float] = None
    s: Optional[float] = None
    v: Optional[float] = None
    t: Optional[float] = None
    vel: Optional[int] = 1
    on: Optional[bool] = None
    id: Optional[str] = None


@app.post("/api/cena")
def api_cena(p: Pedido):
    c = CENAS.get(p.nome or "")
    if not c:
        return {"ok": False}
    zerar_reacao()
    for l in alvos(p.alvos):
        if "passos" in c:
            threading.Thread(target=l.aplicar_efeito, args=("cena_" + p.nome, 1), daemon=True).start()
        else:
            l.transicao(c["h"], c["s"])
    estado_geral["cena"] = p.nome
    return {"ok": True}


@app.post("/api/cor")
def api_cor(p: Pedido):
    zerar_reacao()
    for l in alvos(p.alvos):
        l.transicao(p.h, p.s if p.s is not None else 0.75, dur=1.0)
    estado_geral["cena"] = None
    return {"ok": True}


@app.post("/api/branco")
def api_branco(p: Pedido):
    zerar_reacao()
    for l in alvos(p.alvos):
        threading.Thread(target=l.branco, args=(max(0.0, min(1.0, p.t or 0)),), daemon=True).start()
    estado_geral["cena"] = None
    return {"ok": True}


@app.post("/api/efeito")
def api_efeito(p: Pedido):
    zerar_reacao()
    for l in alvos(p.alvos):
        threading.Thread(target=l.aplicar_efeito, args=(p.nome, p.vel or 1), daemon=True).start()
    estado_geral["cena"] = None
    return {"ok": True}


@app.post("/api/brilho")
def api_brilho(p: Pedido):
    for l in alvos(p.alvos):
        threading.Thread(target=l.brilho, args=(p.v,), daemon=True).start()
    return {"ok": True}


@app.post("/api/ligar")
def api_ligar(p: Pedido):
    if not p.alvos:
        zerar_reacao()
    for l in alvos(p.alvos):
        threading.Thread(target=l.ligar, args=(p.on,), daemon=True).start()
    if not p.on and not p.alvos:
        estado_geral["cena"] = "desligar"
    return {"ok": True}


@app.post("/api/identificar")
def api_identificar(p: Pedido):
    for l in alvos([p.id]):
        l.identificar(p.on is not False)
    return {"ok": True}


@app.post("/api/renomear")
def api_renomear(p: Pedido):
    nome = (p.nome or "").strip()[:24]
    for l in alvos([p.id]):
        if nome:
            l.nome = nome
            config.setdefault("nomes", {})[l.id] = nome
    salvar_config(config)
    return {"ok": True}


# ---------- som das cenas e efeitos (o som toca na tela; aqui so ficam as preferencias e a reacao da luz) ----------
SOM_PADRAO = {"ligado": True, "volume": 0.35, "reagir": True}


@app.get("/api/som")
def api_som():
    return {**SOM_PADRAO, **config.get("som", {})}


class Som(BaseModel):
    ligado: Optional[bool] = None
    volume: Optional[float] = None
    reagir: Optional[bool] = None


@app.post("/api/som")
def api_som_salvar(p: Som):
    som = {**SOM_PADRAO, **config.get("som", {})}
    if p.ligado is not None:
        som["ligado"] = p.ligado
    if p.reagir is not None:
        som["reagir"] = p.reagir
    if p.volume is not None:
        som["volume"] = round(max(0.0, min(1.0, p.volume)), 2)
    config["som"] = som
    salvar_config(config)
    return som


class Reacao(BaseModel):
    alvo: Optional[str] = None     # nome do efeito que esta tocando ("fogueira", "mar", "cena_aconchego"); vazio desliga
    pulso: Optional[float] = None  # estalo, forca 0 a 1
    nivel: Optional[float] = None  # onda, 0 a 1


@app.post("/api/reacao")
def api_reacao(p: Reacao):
    """A tela avisa cada estalo ou o nivel da onda. Pulso a menos de 0,5 s do anterior e ignorado (seguranca sensorial)."""
    return {"ok": definir_reacao(p.alvo, p.pulso, p.nivel)}


@app.post("/api/recarregar")
def api_recarregar():
    carregar()
    return {"ok": True, "luzes": len(luzes)}


# ---------- clima da tela Inicio (so quando houver internet) ----------
clima = {"dados": None, "quando": 0}


def baixar(url):
    with urllib.request.urlopen(url, timeout=6) as r:
        return json.load(r)


def atualizar_clima():
    """Local: config["local"] (cidade, lat, lon), escolhido em Ajustes. Sem local, tenta pelo IP (impreciso)."""
    try:
        if not rede.internet_ok():
            return
        local = config.get("local")
        if not local:
            g = baixar("http://ip-api.com/json/?fields=status,city,lat,lon")
            if g.get("status") == "success":
                local = config["local"] = {"cidade": g["city"], "lat": g["lat"], "lon": g["lon"], "pelo_ip": True}
                salvar_config(config)
        if local:
            r = baixar(f"https://api.open-meteo.com/v1/forecast?latitude={local['lat']}&longitude={local['lon']}"
                       "&current=temperature_2m,weather_code,is_day&timezone=auto")
            c = r["current"]
            clima.update(dados={"cidade": local["cidade"], "temp": round(c["temperature_2m"]),
                                "codigo": c["weather_code"], "dia": bool(c.get("is_day", 1))}, quando=time.time())
    except Exception:
        pass


def laco_clima():
    while True:
        atualizar_clima()
        time.sleep(900)


threading.Thread(target=laco_clima, daemon=True).start()


@app.get("/api/local")
def api_local():
    return config.get("local") or {}


@app.get("/api/local/buscar")
def api_local_buscar(nome: str):
    if not rede.internet_ok():
        return {"erro": "Precisa de internet para buscar a cidade. Use \"Conectar Wi-Fi\" ou o roteador do celular."}
    try:
        r = baixar(f"https://geocoding-api.open-meteo.com/v1/search?name={quote(nome.strip())}&count=6&language=pt&format=json")
    except Exception:
        return {"erro": "Não consegui buscar agora. Tente de novo em instantes."}
    achadas = [{"cidade": x["name"], "estado": x.get("admin1", ""), "pais": x.get("country_code", ""),
                "lat": x["latitude"], "lon": x["longitude"]} for x in r.get("results", [])]
    achadas.sort(key=lambda x: x["pais"] != "BR")  # cidades do Brasil primeiro
    return {"cidades": achadas} if achadas else {"erro": "Nenhuma cidade encontrada com esse nome."}


class Local(BaseModel):
    cidade: str
    estado: Optional[str] = ""
    lat: float
    lon: float


@app.post("/api/local")
def api_local_salvar(p: Local):
    config["local"] = {"cidade": p.cidade, "estado": p.estado, "lat": p.lat, "lon": p.lon}
    salvar_config(config)
    threading.Thread(target=atualizar_clima, daemon=True).start()
    return {"ok": True}


class Hora(BaseModel):
    quando: str  # "AAAA-MM-DD HH:MM" no horario local


@app.post("/api/hora")
def api_hora(p: Hora):
    """Acerta o relogio na mao (sala sem internet depois de faltar energia). Com internet, o NTP acerta sozinho."""
    try:
        datetime.strptime(p.quando, "%Y-%m-%d %H:%M")
    except ValueError:
        return {"ok": False, "msg": "Data ou hora inválida."}
    r = subprocess.run(["sudo", "-n", "/usr/bin/date", "-s", p.quando], capture_output=True, text=True, timeout=10)
    return {"ok": r.returncode == 0, "msg": "Hora acertada." if r.returncode == 0 else "Não consegui acertar a hora."}


@app.get("/api/clima")
def api_clima():
    # sem internet o clima some na hora (o dado guardado seria velho); dado com mais de 3 h tambem nao aparece
    if not rede.internet_ok():
        return {}
    if time.time() - clima["quando"] > 900:  # internet voltou com dado velho: busca de novo
        threading.Thread(target=atualizar_clima, daemon=True).start()
    return clima["dados"] if clima["dados"] and time.time() - clima["quando"] < 3 * 3600 else {}


# ---------- internet do painel e cadastro de luzes ----------
@app.get("/api/rede")
def api_rede():
    return {"internet": rede.internet_ok(), "wifi": rede.wifi_atual(),
            "cadastro": rede.cadastro, "magic": magic.status, "user_code": codigo_smartlife()}


@app.get("/api/ajustes")
def api_ajustes():
    return publico()


def codigo_smartlife():
    return config.get("user_code") or AJ["smartlife_codigo"]


@app.get("/api/wifi/lista")
def api_wifi_lista():
    return {"redes": rede.wifi_lista()}


class Wifi(BaseModel):
    ssid: str
    senha: Optional[str] = ""


@app.get("/api/wifi/salvas")
def api_wifi_salvas():
    return {"redes": rede.wifi_salvas()}


@app.post("/api/wifi/esquecer")
def api_wifi_esquecer(w: Wifi):
    ok, msg = rede.wifi_esquecer(w.ssid)
    return {"ok": ok, "msg": msg}


@app.post("/api/wifi/conectar")
def api_wifi_conectar(w: Wifi):
    ok, msg = rede.wifi_conectar(w.ssid, w.senha)
    return {"ok": ok, "msg": msg}


def _apos_cadastro(novas):
    # luz pareada de novo volta mesmo que tenha sido removida antes
    config["removidos"] = [i for i in config.get("removidos", []) if i not in novas]
    salvar_config(config)
    carregar()


@app.post("/api/adicionar/iniciar")
def api_adicionar(p: Pedido):
    if p.nome:
        config["user_code"] = p.nome.strip()
        salvar_config(config)
    rede.iniciar_cadastro(codigo_smartlife(), _apos_cadastro)
    return {"ok": True}


@app.get("/api/adicionar/qr.svg")
def api_qr():
    if not (BASE / "static" / "qr.svg").exists():
        return Response(status_code=404)
    return FileResponse(BASE / "static" / "qr.svg", media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.post("/api/remover")
def api_remover(p: Pedido):
    rem = config.setdefault("removidos", [])
    if p.id and p.id not in rem:
        rem.append(p.id)
    salvar_config(config)
    carregar()
    return {"ok": True}


# ---------- Magic Home (sem internet e sem app) ----------
@app.get("/api/magic/aps")
def api_magic_aps():
    return {"aps": magic.aps()}


@app.post("/api/magic/configurar")
def api_magic_configurar(w: Wifi):
    magic.configurar(w.ssid, carregar)
    return {"ok": True}


@app.post("/api/magic/buscar")
def api_magic_buscar():
    magic.buscar_na_sala(carregar)
    return {"ok": True}
