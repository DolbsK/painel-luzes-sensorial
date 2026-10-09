# Painel de luzes para sala sensorial

Painel touch para controlar as luzes de uma sala sensorial (por exemplo, para crianças no espectro autista) **sem nuvem e sem internet no dia a dia**. Roda num Raspberry Pi com tela touch e conversa direto com as luzes pela rede local.

- **Início:** cartões de cada aparelho (liga/desliga com um toque), hora, data e clima (quando há internet).
- **Cenas vivas:** Calma, Relaxar, Natureza, Aconchego, Foco, Noite e Brincar. As cores passeiam bem devagar entre tons vizinhos, sem trocas bruscas.
- **Branco, Cores e Efeitos:** efeitos suaves e **sincronizados entre todas as luzes**, porque o próprio painel conduz o efeito.
- **Som:** cenas e efeitos podem tocar música ou sons de ambiente, e a luz pode reagir ao som (estalos da fogueira, ondas do mar). Ver a seção "Som" abaixo.
- **Ajustes:** cadastro de luzes com assistente passo a passo, conexão Wi-Fi, "Localizar" (a luz pisca para ser identificada), renomear, remover, cidade do clima e acerto de hora.

## Luzes compatíveis
| Tipo | Como é cadastrada | Internet |
|---|---|---|
| **Tuya / Smart Life** (lâmpadas, fitas, interruptores; muitas marcas nacionais são Tuya por dentro) | Pareia no app Smart Life e lê um QR na tela do painel | Só no momento do cadastro |
| **Magic Home** (controladores de fita LEDnet / Zengge) | O painel configura o controlador sozinho | Nunca |

Depois do cadastro, tudo funciona 100% local.

## O que você precisa
- Raspberry Pi 4 (testado) com **Raspberry Pi OS com desktop** (Bookworm ou Trixie, 64 bits).
- Tela touch HDMI (testado com tela 7" 1920x1080).
- Um roteador Wi-Fi 2,4 GHz só para a sala, ligado no Pi pelo cabo.

### Como a rede funciona
```
 luzes Wi-Fi ))) roteador da sala (2,4 GHz, DHCP desligado) ── cabo ── Raspberry Pi (192.168.0.2, distribui os IPs)
                                                                            )))  Wi-Fi do Pi: hotspot do celular, só para cadastrar luz Tuya
```
O Wi-Fi do próprio Pi como ponto de acesso **não** funciona bem com essas luzes; por isso o roteador separado.

## Instalação
1. Grave o Raspberry Pi OS com desktop no cartão e ligue o Pi com a tela.
2. No terminal do Pi (ou por SSH), rode:
   ```
   curl -fsSL https://raw.githubusercontent.com/DolbsK/painel-luzes-sensorial/main/instalar.sh | sudo bash
   ```
3. Responda as perguntas: nome da sala, Wi-Fi da sala, hotspot do celular, IP e tamanho da interface na tela (1,8 para tela 7" Full HD; 1 para tela 7" 1024x600 ou monitor comum).
4. Ligue o cabo do Pi no roteador da sala, configure o roteador como o script indicar e reinicie.

Atualizar só o código, mantendo luzes, ajustes e rede:
```
curl -fsSL https://raw.githubusercontent.com/DolbsK/painel-luzes-sensorial/main/instalar.sh | sudo bash -s -- --atualizar
```
Refazer as perguntas (nome da sala, Wi-Fi...): o mesmo comando com `--reconfigurar` no lugar de `--atualizar`.

## Som
O som toca no navegador da tela (Web Audio), não no servidor. Cada cena ou efeito aponta para um som em `app/static/sons/sons.json`; trocar ou acrescentar som é só mexer nesse arquivo e nos áudios, sem mexer no código.
- **Os áudios não vão para este repositório** (a licença de muitos bancos de som proíbe distribuir o arquivo sozinho). Ponha os `.ogg` em `app/static/sons/` do seu painel. Sem eles o painel funciona normal, só sem som. `app/static/sons/CREDITOS.md` registra de onde veio cada faixa na instalação original.
- `sons.json`: `sons` (cada som é `playlist` de várias faixas ou `loop` de uma gravação, com `ganho` opcional), `cenas` e `efeitos` (qual som toca em cada um, com `ganho` e `reacao` opcionais por cena), `antecipa` (segundos que o aviso da luz sai antes do estalo, para a luz acender junto com o som). Um som `loop` pode ter `eventos` (sons curtos sorteados por cima do fundo, como bichos da mata).
- **A luz acompanhar o som:** o som pode ter `marcas`, um `.marcas.json` gerado uma vez pelo script `ferramentas/marcas.py` (precisa de ffmpeg e numpy): `python ferramentas/marcas.py pulsos fogueira.ogg --k 10` marca os estalos, `python ferramentas/marcas.py nivel mar.ogg` marca o sobe e desce das ondas. A tela avisa o servidor (`POST /api/reacao`) e o servidor só aplica na luz. Limite sensorial: no máximo 2 pulsos por segundo, a luz nunca apaga. Em Ajustes, um interruptor desliga só a reação, outro desliga o som.
- Fade de entrada de 4 s e de saída de 3 s, volume inicial de 35%. Os áudios devem ter o mesmo volume percebido (`loudnorm`, cerca de -27 LUFS).

## Estrutura
```
app/        servidor (FastAPI) e tela (static/index.html)
  app.py      rotas e luzes Tuya (tinytuya)
  magic.py    luzes Magic Home (flux_led) e configuração sem app
  rede.py     Wi-Fi do Pi e cadastro Tuya pelo QR
  efeitos.py  cenas, efeitos e cores
  ajustes.py  lê o ajustes.json de cada instalação
  static/sons/  sons.json, marcas e (só no painel) os áudios
ferramentas/ marcas.py: marca estalos e ondas dos áudios
sistema/    modelos de serviço, tela cheia (labwc + Chromium), permissões e rede
instalar.sh instalador
```
Arquivos de cada instalação (`ajustes.json`, `devices.json` com as chaves das luzes, `config.json`, `magic.json`) ficam só no Pi e nunca entram no repositório.

## Notas técnicas
- **Tuya:** as chaves locais vêm pelo login por QR do app Smart Life, o mesmo fluxo da integração oficial do Home Assistant (`tuya-device-sharing-sdk`). Não precisa de conta de desenvolvedor Tuya.
- **Magic Home:** o painel entra na rede `LEDnet...` do controlador e envia o Wi-Fi da sala por comandos AT na porta UDP 48899.
- **Segurança:** o servidor escuta só em `127.0.0.1` (só a própria tela acessa). As permissões de administrador do painel se limitam a `nmcli` e `date`.
- **Hora:** sem internet, o Pi 4 não guarda a hora quando falta energia. Use "Acertar hora" em Ajustes ou um módulo de relógio DS3231.

## Licença
MIT. A fonte Nunito é distribuída sob a SIL Open Font License.
