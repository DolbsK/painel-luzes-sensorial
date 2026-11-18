#!/usr/bin/env python3
"""Vigia da tela: garante que um toque acende a tela, mesmo se a pagina (Chromium) parar de responder.

Le o toque direto do kernel (/dev/input), por fora do labwc e do Chromium. Com a tela apagada, espera 3 s
pela pagina acender sozinha; se nao acendeu, acende o monitor (wlopm) e reabre o Chromium (o lwrespawn reabre).
Grava em tela.log (na pasta do painel) cada toque com a tela apagada, cada mudanca de estado e um resumo a cada
30 min. O arquivo vai para o cartao na hora (fsync), para sobrar registro se a energia for cortada.
Sem dependencias: so a biblioteca padrao do Python.
"""
import glob, os, select, struct, subprocess, sys, time
from datetime import datetime
from pathlib import Path

PASTA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
LOG = PASTA / "tela.log"
LOG_MAX = 512 * 1024
EVENTO = struct.Struct("llHHi")  # struct input_event (timeval, type, code, value)
ESPERA_PAGINA = 3.0  # segundos para a pagina acender sozinha antes da vigia agir
RESUMO_S = 30 * 60
RUN = Path(f"/run/user/{os.getuid()}")


def log(msg):
    try:
        if LOG.exists() and LOG.stat().st_size > LOG_MAX:
            LOG.replace(LOG.with_suffix(".log.1"))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass


def env_wayland():
    soquetes = sorted(s.name for s in RUN.glob("wayland-*") if not s.name.endswith(".lock"))
    if not soquetes:
        return None
    return {**os.environ, "XDG_RUNTIME_DIR": str(RUN), "WAYLAND_DISPLAY": soquetes[0]}


def estado_tela():
    """{'HDMI-A-1': 'on'} ou None se o labwc nao estiver rodando."""
    env = env_wayland()
    if not env:
        return None
    try:
        r = subprocess.run(["wlopm"], env=env, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    saidas = {}
    for linha in r.stdout.splitlines():
        p = linha.split()
        if len(p) == 2:
            saidas[p[0]] = p[1]
    return saidas


def hdmi():
    return " ".join(f"{Path(f).parent.name.split('-', 1)[1]}={Path(f).read_text().strip()}"
                    for f in sorted(glob.glob("/sys/class/drm/card*-HDMI-*/status")))


def acender():
    env = env_wayland()
    if env:
        subprocess.run(["wlopm", "--on", "*"], env=env, capture_output=True, timeout=5)


def nome_disp(ev):
    try:
        return Path(f"/sys/class/input/{ev}/device/name").read_text().strip()
    except OSError:
        return "?"


def abrir_dispositivos(abertos):
    """Abre os /dev/input/event* novos (toque, mouse). Ignora o CEC do HDMI."""
    atuais = {Path(p).name for p in glob.glob("/dev/input/event*")}
    for ev in list(abertos):
        if ev not in atuais:
            os.close(abertos.pop(ev)[0])
            log(f"dispositivo saiu: {ev}")
    for ev in sorted(atuais - set(abertos)):
        nome = nome_disp(ev)
        if nome.startswith("vc4-hdmi"):
            continue
        try:
            abertos[ev] = (os.open(f"/dev/input/{ev}", os.O_RDONLY | os.O_NONBLOCK), nome)
            log(f"dispositivo: {ev} {nome}")
        except OSError as e:
            log(f"sem acesso a {ev} ({nome}): {e}")


def chromium_rodando():
    return subprocess.run(["pgrep", "-x", "chromium"], capture_output=True).returncode == 0


def main():
    log(f"vigia iniciada, pid {os.getpid()}")
    abertos = {}
    abrir_dispositivos(abertos)
    ultimo_toque = 0.0
    conferir_em = None  # hora em que a vigia confere se a pagina acendeu a tela
    ult_estado, ult_hdmi = None, None
    prox_scan = prox_estado = prox_toque = 0.0
    prox_resumo = time.monotonic() + 60
    while True:
        fds = {v[0]: ev for ev, v in abertos.items()}
        try:
            prontos, _, _ = select.select(list(fds), [], [], 1.0)
        except (OSError, ValueError):
            prontos = []
        agora = time.monotonic()
        for fd in prontos:
            ev = fds[fd]
            try:
                dados = os.read(fd, EVENTO.size * 64)
            except OSError:
                os.close(abertos.pop(ev)[0])
                log(f"dispositivo saiu: {ev}")
                continue
            if any(EVENTO.unpack_from(dados, i)[2] != 0 for i in range(0, len(dados) - EVENTO.size + 1, EVENTO.size)):
                ultimo_toque = agora
                if conferir_em is None and agora >= prox_toque:  # no maximo 1 consulta a cada 2 s (arrastar gera 100 eventos/s)
                    prox_toque = agora + 2
                    est = estado_tela() or {}
                    if any(v == "off" for v in est.values()):
                        log(f"toque com a tela apagada ({abertos[ev][1]})")
                        conferir_em = agora + ESPERA_PAGINA
        if conferir_em is not None and agora >= conferir_em:
            conferir_em = None
            est = estado_tela()
            if est and any(v == "off" for v in est.values()):
                log(f"a pagina nao acendeu a tela em {ESPERA_PAGINA:.0f} s: vigia acende e reabre o Chromium")
                acender()
                pids = subprocess.run(["pgrep", "-x", "chromium"], capture_output=True, text=True).stdout.split()
                subprocess.run(["pkill", "-x", "chromium"], capture_output=True)
                time.sleep(5)
                presos = [p for p in pids if Path(f"/proc/{p}").exists()]  # travado nao atende o pedido de fechar
                if presos:
                    subprocess.run(["kill", "-KILL", *presos], capture_output=True)
                    log(f"Chromium nao fechou em 5 s: {len(presos)} processos fechados a forca")
            else:
                log("pagina acendeu a tela")
        if agora >= prox_scan:
            abrir_dispositivos(abertos)
            prox_scan = agora + 60
        if agora >= prox_estado:
            est, h = estado_tela(), hdmi()
            if est != ult_estado or h != ult_hdmi:
                log(f"tela {est} | {h}")
                ult_estado, ult_hdmi = est, h
            prox_estado = agora + 15
        if agora >= prox_resumo:
            toque = f"{(agora - ultimo_toque) / 60:.0f} min" if ultimo_toque else "nenhum desde o inicio"
            mem = next((l.split()[1] for l in open("/proc/meminfo") if l.startswith("MemAvailable")), "?")
            log(f"resumo: tela {ult_estado} | {ult_hdmi} | ultimo toque ha {toque} | "
                f"dispositivos {[v[1] for v in abertos.values()]} | chromium {'sim' if chromium_rodando() else 'NAO'} | "
                f"memoria livre {int(mem) // 1024} MB")
            prox_resumo = agora + RESUMO_S


if __name__ == "__main__":
    main()
