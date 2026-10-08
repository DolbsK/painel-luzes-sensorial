# Cenas, efeitos e conversoes de cor usados por todas as marcas de luz
BRILHO_MAX = 1.0
LOCALIZAR_S = 30  # "Localizar": tempo maximo piscando
ONDA = [0.15, 0.35, 0.6, 0.8, 0.6, 0.35, 0.15, 0.05]  # brilho de cada passo da piscada do "Localizar"
PASSO_S = {1: 6.0, 2: 3.0, 3: 1.5}  # efeitos: segundos de uma cor ate a proxima (Lenta, Media, Rapida)
QUADRO_S = 0.2  # intervalo entre cores enviadas a cada luz durante efeito ou cena viva

# Cenas vivas: passeiam bem devagar entre tons vizinhos (passo_s = segundos de um tom ao proximo).
# passos: (cor em graus, saturacao 0-1, fator do brilho da barra). Cena com h/s fica parada (Foco).
CENAS = {
    "calma":     {"passos": [(205, .60, 1), (218, .55, .85), (195, .62, .95)], "passo_s": 12},
    "relaxar":   {"passos": [(268, .50, 1), (285, .45, .85), (252, .50, .9)], "passo_s": 12},
    "natureza":  {"passos": [(125, .60, 1), (150, .55, .85), (95, .55, .9), (140, .60, .8)], "passo_s": 10},
    "aconchego": {"passos": [(30, .85, 1), (22, .90, .8), (36, .80, .9)], "passo_s": 9},
    "foco":      {"h": 195, "s": 0.15},
    "noite":     {"passos": [(232, .85, .45), (250, .80, .35), (222, .85, .4)], "passo_s": 14},
    "brincar":   {"passos": [(320, .70, 1), (45, .80, 1), (180, .70, 1), (20, .85, 1), (270, .60, 1)], "passo_s": 3},
}

# Efeitos tocados pelo painel (nao pelo efeito interno da luz): a cor de cada instante sai do relogio do
# computador, entao todas as luzes no mesmo efeito e velocidade ficam sincronizadas. Troca sempre suave.
EFEITOS = {
    "arcoiris": {"passos": [(0, .75, 1), (40, .8, 1), (60, .75, 1), (120, .7, 1), (190, .75, 1), (240, .75, 1), (285, .7, 1)]},
    "mar":      {"passos": [(200, .85, 1), (225, .9, .55), (185, .8, .85), (240, .85, .45), (195, .7, .95)]},
    "aurora":   {"passos": [(140, .7, .9), (165, .75, .6), (280, .6, .85), (190, .7, .5), (120, .65, .8)]},
    "lava":     {"passos": [(10, .95, 1), (340, .9, .7), (28, .95, .9), (320, .85, .6)]},
    "fogueira": {"passos": [(28, .95, 1), (18, 1, .55), (35, .9, .85), (22, 1, .4), (30, .95, .9), (15, 1, .65)]},
    "algodao":  {"passos": [(330, .45, 1), (280, .4, .9), (200, .4, 1), (300, .35, .95)]},
    "estrelas": {"passos": [(235, .85, .35), (255, .8, .6), (225, .9, .25), (270, .7, .75), (240, .85, .3)]},
    "respirar": {"respirar": True},
}
EFEITOS.update({"cena_" + n: c for n, c in CENAS.items() if "passos" in c})  # cenas vivas usam o mesmo motor


def quadro_efeito(e, vel, h0, s0, v, t):
    """Cor (h, s, v) do efeito no instante t. Mesmo t = mesma cor em todas as luzes."""
    passos = [(h0, max(s0, .5), 1), (h0, max(s0, .5), .12)] if e.get("respirar") else e["passos"]
    pos = (t / (e.get("passo_s") or PASSO_S.get(vel, 6.0))) % len(passos)
    i = int(pos)
    k = pos - i
    k = k * k * (3 - 2 * k)
    (ha, sa, ma), (hb, sb, mb) = passos[i], passos[(i + 1) % len(passos)]
    dh = ((hb - ha + 180) % 360) - 180
    return (ha + dh * k) % 360, sa + (sb - sa) * k, max(0.03, v * (ma + (mb - ma) * k))


def branco_rgb(t):
    """Simula branco numa luz so RGB. t=0 amarelo (vela) ... t=1 frio (dia)."""
    if t < 0.6:
        k = t / 0.6
        return 30 + 10 * k, 0.78 - 0.66 * k
    k = (t - 0.6) / 0.4
    return 210, 0.04 + 0.08 * k
