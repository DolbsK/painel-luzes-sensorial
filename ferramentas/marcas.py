# Marca os estalos (modo pulsos) e o nivel das ondas (modo nivel) de um audio, uma vez, antes de usar no painel.
# Precisa de ffmpeg e numpy. Roda no notebook, sobre o .ogg final (nao sobre o original).
#   python ferramentas/marcas.py pulsos app/static/sons/fogueira.ogg --k 4
#   python ferramentas/marcas.py nivel app/static/sons/mar.ogg
# Grava ao lado do audio: <nome>.marcas.json
import argparse, json, subprocess
from pathlib import Path
import numpy as np

TAXA = 22050
INTERVALO_MIN = 0.5  # s entre estalos: regra de seguranca (no maximo 2 pulsos por segundo)


def decodificar(arq, filtro=None):
    cmd = ["ffmpeg", "-v", "error", "-i", str(arq), "-ac", "1", "-ar", str(TAXA)]
    if filtro:
        cmd += ["-af", filtro]
    cmd += ["-f", "f32le", "-"]
    saida = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(saida, dtype=np.float32)


def energia(x, janela_s):
    n = int(TAXA * janela_s)
    quadros = len(x) // n
    return np.sqrt((x[:quadros * n].reshape(quadros, n) ** 2).mean(axis=1))


def mediana_movel(e, largura):
    meio = largura // 2
    pad = np.pad(e, meio, mode="edge")
    return np.array([np.median(pad[i:i + largura]) for i in range(len(e))])


def pulsos(arq, k, piso):
    x = decodificar(arq, "highpass=f=2000")
    passo = 0.01
    e = energia(x, passo)
    med = mediana_movel(e, int(1 / passo) | 1)
    acima = (e > k * med) & (e > piso)
    # so o pico de cada estalo
    picos = []
    i = 0
    while i < len(e):
        if acima[i]:
            j = i
            while j < len(e) and acima[j]:
                j += 1
            m = i + int(np.argmax(e[i:j]))
            picos.append((m * passo, float(e[m])))
            i = j
        else:
            i += 1
    # descarta estalo a menos de 0,5 s do anterior (fica o mais forte do grupo)
    ok = []
    for t, f in picos:
        if ok and t - ok[-1][0] < INTERVALO_MIN:
            if f > ok[-1][1]:
                ok[-1] = (t, f)
            continue
        ok.append((t, f))
    duracao = len(x) / TAXA
    if not ok:
        return [], duracao, {}
    fs = np.array([f for _, f in ok])
    lo, hi = fs.min(), fs.max()
    forca = 0.3 + 0.7 * (fs - lo) / (hi - lo) if hi > lo else np.ones_like(fs)
    lista = [[round(t, 2), round(float(f), 2)] for (t, _), f in zip(ok, forca)]
    stats = {"estalos": len(ok), "por_minuto": round(len(ok) / duracao * 60, 1),
             "forca_max_sobre_mediana": round(float(fs.max() / np.median(fs)), 2)}
    return lista, duracao, stats


def nivel(arq):
    x = decodificar(arq)
    e = energia(x, 0.2)
    n = 5  # 5 janelas de 200 ms = 1 s
    suave = np.convolve(np.pad(e, (n // 2, n // 2), mode="edge"), np.ones(n) / n, mode="valid")
    p5, p95 = np.percentile(suave, 5), np.percentile(suave, 95)
    v = np.clip((suave - p5) / (p95 - p5), 0, 1) if p95 > p5 else np.zeros_like(suave)
    return [round(float(a), 3) for a in v], len(x) / TAXA


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["pulsos", "nivel"])
    ap.add_argument("arquivo")
    ap.add_argument("--k", type=float, default=4.0, help="estalo = energia k vezes a mediana de 1 s")
    ap.add_argument("--piso", type=float, default=0.004, help="energia minima absoluta de um estalo")
    ap.add_argument("--saida")
    a = ap.parse_args()
    arq = Path(a.arquivo)
    saida = Path(a.saida) if a.saida else arq.with_suffix(".marcas.json")
    if a.modo == "pulsos":
        lista, dur, st = pulsos(arq, a.k, a.piso)
        print(json.dumps(st))
        dados = {"pulsos": lista, "duracao": round(dur, 2)}
    else:
        v, dur = nivel(arq)
        print(f"{len(v)} valores de nivel, {dur:.1f} s")
        dados = {"nivel": v, "passo": 0.2, "duracao": round(dur, 2)}
    saida.write_text(json.dumps(dados, separators=(",", ":")), encoding="utf-8")
    print("gravado", saida)
