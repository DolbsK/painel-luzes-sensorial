# Creditos dos sons

Todos os sons vem do Pixabay (Pixabay Content License, uso livre, atribuicao nao exigida mas registrada aqui).
Os arquivos de audio NAO vao para o GitHub (a licenca proibe distribuir o arquivo sozinho): so este arquivo, o `sons.json` e os `.marcas.json` entram no repositorio.

| Arquivo | Titulo | Autor | Link | Duracao original | Observacao |
|---|---|---|---|---|---|
| tranquila-1.ogg | Calm Piano | leberch | https://pixabay.com/music/ambient-calm-piano-586711/ | 1:52 |  |
| tranquila-2.ogg | Flowing (Piano) | leberch | https://pixabay.com/music/ambient-flowing-piano-606083/ | 1:58 |  |
| tranquila-3.ogg | Rolfied (Ambient Piano) | leberch | https://pixabay.com/music/ambient-rolfied-ambient-piano-615225/ | 2:30 |  |
| tranquila-4.ogg | Calmness Meditation | AtlasAudio | https://pixabay.com/music/meditationspiritual-calmness-meditation-613486/ | 4:40 |  |
| tranquila-5.ogg | Calm Ambient Dreamscape | MondaMusic | https://pixabay.com/music/ambient-calm-ambient-dreamscape-589108/ | 1:54 |  |
| caixinha-1.ogg | Baby Lullaby Music Box Sweet Dreams | Denis-Pavlov-Music | https://pixabay.com/music/lullabies-baby-lullaby-music-box-sweet-dreams-296594/ | 6:23 |  |
| caixinha-2.ogg | Music Box Sleep Lullaby | Tunetank | https://pixabay.com/music/lullabies-music-box-sleep-lullaby-349471/ | 1:51 |  |
| caixinha-3.ogg | Beethoven - For Elise (Arr. for Music Box) | GregorQuendel | https://pixabay.com/music/lullabies-beethoven-for-elise-arr-for-music-box-173061/ | 3:12 |  |
| fogueira.ogg | Campfire Crackling - Fireplace Sound | SoundsForYou | https://pixabay.com/sound-effects/nature-campfire-crackling-fireplace-sound-119594/ | 2:20 | corte do 38 s ao fim (os primeiros 38 s do original tem estalos fracos demais para marcar); 31 estalos em 102 s = 18,3 por minuto (k=10 em ferramentas/marcas.py) |
| natureza.ogg | Birds Singing - Calm River - Nature Ambient Sound | SoundsForYou | https://pixabay.com/sound-effects/nature-birds-singing-calm-river-nature-ambient-sound-127411/ | 3:00 |  |
| mar.ogg | calm ocean waves, early in the morning. | MarcinFlorida | https://pixabay.com/sound-effects/nature-calm-ocean-waves-early-in-the-morning-140020/ | 3:12 |  |
| bicho-macaco-1.ogg | several monkeys chattering version 1 | flutie8211 | https://pixabay.com/sound-effects/nature-several-monkeys-chattering-version-1-502861/ | 0:08 | corte 0 a 8 s |
| bicho-macaco-2.ogg | monkey  chattering | flutie8211 | https://pixabay.com/sound-effects/nature-monkey-chattering-494429/ | 0:08 | corte 0 a 8 s |
| bicho-tucano-1.ogg | 111013__soundbytez__chesnut-mandibled-toucan | freesound_community | https://pixabay.com/sound-effects/nature-111013-soundbytez-chesnut-mandibled-toucan-34105/ | 0:42 | corte de 10 s (9 s a 19 s do original) |
| bicho-ave-1.ogg | Tropical birds | MagiaZ | https://pixabay.com/sound-effects/nature-tropical-birds-507634/ | 0:05 | original inteiro (5 s) |
| bicho-sapos-1.ogg | Frogs croaking in shallow water | dbsound | https://pixabay.com/sound-effects/nature-frogs-croaking-in-shallow-water-252307/ | 2:21 | corte de 12 s (40 s a 52 s do original) |
| chuva.ogg | Calming Rain Loop | DRAGON-STUDIO | https://pixabay.com/sound-effects/nature-calming-rain-loop-398653/ | 3:00 | escolhida entre 4 por ser a mais constante (LRA 0,4 LU, sem pico nem grave de trovão, emenda de 0,3 dB); -28,7 LUFS mono 64k |
| tempestade.ogg | Rain and little storm | AudioPapkin | https://pixabay.com/sound-effects/nature-rain-and-little-storm-298087/ | 4:04 | escolhida entre 5: chuva mais constante (LRA 4,2), trovao sobe 14 dB, menor estalo agudo (13 dB, outras ate 26); -28,3 LUFS mono 64k; 11 trovoes marcados (marcas.py --filtro lowpass=f=250 --passo 0.05 --mediana 10 --intervalo 5 --k 2.75 --piso 0.001) |
| festa-1.ogg | Playful Joyful Cheerful Music | ViacheslavStarostin | https://pixabay.com/music/happy-childrens-tunes-playful-joyful-cheerful-music-340809/ | 1:50 | festa: instrumental, LRA 4,0, ~99 bpm; -25,8 LUFS estereo 96k |
| festa-2.ogg | Sunny Ukulele | 331music | https://pixabay.com/music/happy-childrens-tunes-sunny-ukulele-590555/ | 1:49 | festa: grave mais leve das candidatas; -26,0 LUFS estereo 96k |
| festa-3.ogg | Happy Whistling Ukulele | CreativeFoxMusic | https://pixabay.com/music/happy-childrens-tunes-happy-whistling-ukulele-593156/ | 2:29 | festa: ukulele e assobio, LRA 7,0; -25,8 LUFS estereo 96k |
| bicho-leao-1.ogg | Lion loud | freesound_community | https://pixabay.com/sound-effects/nature-lion-loud-6813/ | 0:48 | corte 11,5 a 24 s (serie de grunhidos, sobe aos poucos); 2026-10-13, -33 a -35 LUFS, pico ate -15 dBFS, mono opus 64k |
| bicho-leao-2.ogg | lion roar | freesound_community | https://pixabay.com/sound-effects/nature-lion-roar-6011/ | 0:04 | original inteiro; rugido curto e abafado; 2026-10-13, -33 a -35 LUFS, pico ate -15 dBFS, mono opus 64k |
| bicho-macaco-3.ogg | Gibbon Monkey | freesound_community | https://pixabay.com/sound-effects/nature-gibbon-monkey-105463/ | 0:07 | original inteiro; 2026-10-13, -33 a -35 LUFS, pico ate -15 dBFS, mono opus 64k |
| bicho-macaco-4.ogg | Monkey | MagiaZ | https://pixabay.com/sound-effects/nature-monkey-411848/ | 0:05 | original inteiro; 2026-10-13, -33 a -35 LUFS, pico ate -15 dBFS, mono opus 64k |
| bicho-macaco-5.ogg | Chimp Monkey HQ sound wav | TanwerAman | https://pixabay.com/sound-effects/nature-chimp-monkey-hq-sound-wav-247599/ | 0:09 | original inteiro; 2026-10-13, -33 a -35 LUFS, pico ate -15 dBFS, mono opus 64k |
| bicho-elefante-1.ogg | ANMLWild-CU_Elephant Trumpet_Nicholas Judy_TDC | designerschoice | https://pixabay.com/sound-effects/nature-anmlwild-cu-elephant-trumpet-nicholas-judy-tdc-482702/ | 0:02 | original inteiro; 2026-10-13, -33 a -35 LUFS, pico ate -15 dBFS, mono opus 64k |
| bicho-elefante-2.ogg | Elephant | MagiaZ | https://pixabay.com/sound-effects/nature-elephant-384822/ | 0:08 | corte 1,9 a 5,2 s; 2026-10-13, -33 a -35 LUFS, pico ate -15 dBFS, mono opus 64k |
| bicho-papagaio-1.ogg | jungle.Parrot.Tambopata | freesound_community | https://pixabay.com/sound-effects/nature-jungleparrottambopata-67599/ | 0:20 | corte 0 a 11,5 s (gravado na mata, sem os estalos do fim); 2026-10-13, -33 a -35 LUFS, pico ate -15 dBFS, mono opus 64k |
| bicho-papagaio-2.ogg | Birds Kea | freesound_community | https://pixabay.com/sound-effects/nature-birds-kea-105461/ | 0:08 | original inteiro; 2026-10-13, -33 a -35 LUFS, pico ate -15 dBFS, mono opus 64k |
