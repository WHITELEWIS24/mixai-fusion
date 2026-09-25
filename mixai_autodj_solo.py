# -*- coding: utf-8 -*-
"""
mixai_autodj_solo.py — MixAi DJ Pro v5.0 "Solo"
================================================
Janela do AUTOMIX com os 2 PLAYERS EMBUTIDOS (mixai_engine) no lugar do
VirtualDJ, mantendo o funcionamento da janela antiga:

  • pesquisa na biblioteca + referência (duplo clique) + ⚡ Gerar Playlist
  • Histórico (Generated Playlists) · Iniciar · Parar · ↩ MixAi Co-Pilot
  • painel do agente: efeitos criativos (raro/médio/frequente) + log ao vivo
  • destaque da faixa a tocar + Total/Restante em contagem decrescente
  • decks A/B com waveform, EQ, FILTER, ECHO/VERB/FLG e crossfader

Sem MIDI, sem loopMIDI, sem OS2L, sem AutoHotkey: o beat É uma posição de
amostra do motor — os efeitos caem sample-accurate no beat certo.

Integração: em mixai_dj_autodj.py, open_automix_player usa esta janela
(com fallback para a antiga AutoDJWindow se este módulo faltar).
"""
from __future__ import annotations

import os
import random as _random
import sys
import threading
import time
import collections

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mixai_engine import Engine, AutoDJ, TrackSpec

# log estruturado em ficheiro (espelha o Agent log da UI) — opcional
try:
    from mixai_log import get_logger as _get_logger
    _flog = _get_logger("solo").info
except Exception:                          # pragma: no cover
    _flog = lambda *_a, **_k: None

# ═══════════════════════════════════════════════════════════════════════════
# i18n da janela Automix — segue o idioma escolhido na app principal
# (current_lang: 'pt' por defeito, 'en' e 'es' selecionáveis). Termos de DJ
# universais (MASTER, CUE, SYNC, PFL, BPM, …) ficam iguais em todos.
# ═══════════════════════════════════════════════════════════════════════════
_TX = {
    # ── REC (gravação do set) ──────────────────────────────────────────
    "rec_off":     {"pt": "● REC OFF", "en": "● REC OFF", "es": "● REC OFF"},
    "rec_on":      {"pt": "● REC ON", "en": "● REC ON", "es": "● REC ON"},
    "rec_saving":  {"pt": "💾 a guardar…", "en": "💾 saving…",
                    "es": "💾 guardando…"},
    "rec_tip":     {"pt": "Gravar o set (WAV, qualidade máxima).\n"
                          "Clica, dá um nome e OK: fica armado e começa a "
                          "gravar ao\ndetetar som (ex.: quando o Automix "
                          "arranca).\nVolta a clicar para terminar e guardar "
                          "na pasta Gravações.",
                    "en": "Record the set (WAV, top quality).\n"
                          "Click, name it and OK: it arms and starts "
                          "recording when\nsound is detected (e.g. when "
                          "Automix starts).\nClick again to stop and save to "
                          "the Recordings folder.",
                    "es": "Grabar el set (WAV, máxima calidad).\n"
                          "Haz clic, ponle nombre y OK: queda armado y "
                          "empieza a grabar\nal detectar sonido (p. ej. "
                          "cuando arranca el Automix).\nVuelve a hacer clic "
                          "para terminar y guardar en Grabaciones."},
    "rec_dlg_t":   {"pt": "Gravar set", "en": "Record set",
                    "es": "Grabar set"},
    "rec_dlg_q":   {"pt": "Nome da gravação:", "en": "Recording name:",
                    "es": "Nombre de la grabación:"},
    "rec_folder":  {"pt": "Gravações", "en": "Recordings",
                    "es": "Grabaciones"},
    "rec_armed":   {"pt": "[REC] armado — começa ao detetar som ({f}).",
                    "en": "[REC] armed — starts when sound is detected ({f}).",
                    "es": "[REC] armado — empieza al detectar sonido ({f})."},
    "rec_armed2":  {"pt": "[REC] armado — a gravação arranca quando o "
                          "Automix iniciar e houver som.",
                    "en": "[REC] armed — recording starts when Automix "
                          "begins and there is sound.",
                    "es": "[REC] armado — la grabación arranca cuando el "
                          "Automix empiece y haya sonido."},
    "rec_stopped": {"pt": "[REC] gravação parada — a guardar WAV…",
                    "en": "[REC] recording stopped — saving WAV…",
                    "es": "[REC] grabación detenida — guardando WAV…"},
    "rec_saved":   {"pt": "[REC] guardado: {p}", "en": "[REC] saved: {p}",
                    "es": "[REC] guardado: {p}"},
    "rec_nothing": {"pt": "[REC] nada gravado — nunca chegou a haver som.",
                    "en": "[REC] nothing recorded — there was never any sound.",
                    "es": "[REC] nada grabado — nunca hubo sonido."},
    "rec_fail":    {"pt": "[REC] falhou: {e}", "en": "[REC] failed: {e}",
                    "es": "[REC] falló: {e}"},
    "rec_dir_err": {"pt": "[REC] pasta indisponível: {e}",
                    "en": "[REC] folder unavailable: {e}",
                    "es": "[REC] carpeta no disponible: {e}"},
    "rec_ok_t":    {"pt": "Gravação guardada", "en": "Recording saved",
                    "es": "Grabación guardada"},
    "rec_ok_q":    {"pt": "O set foi guardado em:\n\n{p}\n\nAbrir a pasta "
                          "das gravações?",
                    "en": "The set was saved to:\n\n{p}\n\nOpen the "
                          "recordings folder?",
                    "es": "El set se guardó en:\n\n{p}\n\n¿Abrir la carpeta "
                          "de grabaciones?"},
    # ── atalhos do BROWSER lateral ─────────────────────────────────────
    "br_local":    {"pt": "Música Local", "en": "Local Music",
                    "es": "Música Local"},
    "br_pc":       {"pt": "Meu Computador", "en": "My Computer",
                    "es": "Mi Ordenador"},
    "br_karaoke":  {"pt": "Karaoke", "en": "Karaoke", "es": "Karaoke"},
    "br_music":    {"pt": "Música", "en": "Music", "es": "Música"},
    "br_videos":   {"pt": "Vídeos", "en": "Videos", "es": "Vídeos"},
    "br_karaoke":  {"pt": "Karaoke", "en": "Karaoke", "es": "Karaoke"},
    "br_docs":     {"pt": "Documentos", "en": "Documents", "es": "Documentos"},
    "br_drives":   {"pt": "Discos", "en": "Drives", "es": "Discos"},
    "br_desktop":  {"pt": "Ambiente de trabalho", "en": "Desktop",
                    "es": "Escritorio"},
    "br_genpl":    {"pt": "Playlists Geradas", "en": "Generated Playlists",
                    "es": "Playlists Generadas"},
    # ── menu de contexto da PASTA ──────────────────────────────────────
    "m_gen_from":  {"pt": "⚡ Gerar playlist a partir desta faixa",
                    "en": "⚡ Generate playlist from this track",
                    "es": "⚡ Generar playlist a partir de esta pista"},
    "m_set_ref":   {"pt": "Definir como referência",
                    "en": "Set as reference",
                    "es": "Definir como referencia"},
    "m_load_deck": {"pt": "Carregar no deck livre",
                    "en": "Load into free deck",
                    "es": "Cargar en el deck libre"},
    # PEDIDOS — mete a faixa a seguir a que esta a tocar, sem refazer o set.
    "m_play_next": {"pt": "▶ Tocar a seguir (pedido)",
                    "en": "▶ Play next (request)",
                    "es": "▶ Tocar a continuación (petición)"},
    "l_next_no_dj": {"pt": "[Pedido] O automix não está a tocar.",
                     "en": "[Request] Automix is not playing.",
                     "es": "[Petición] El automix no está sonando."},
    "l_next_no_bpm": {"pt": "[Pedido] {n} não tem BPM analisado — "
                            "analisa a faixa primeiro.",
                      "en": "[Request] {n} has no analysed BPM — "
                            "analyse the track first.",
                      "es": "[Petición] {n} no tiene BPM analizado — "
                            "analiza la pista primero."},
    "l_next_added": {"pt": "[Pedido] {n} entra a seguir.",
                     "en": "[Request] {n} plays next.",
                     "es": "[Petición] {n} suena a continuación."},
    "l_xf_adoptado": {
        "pt": "[Automix] Mistura manual — o automix assumiu o deck {d} "
              "({n}). O outro foi libertado e a próxima já está a carregar.",
        "en": "[Automix] Manual mix — automix took over deck {d} ({n}). "
              "The other was freed and the next track is loading.",
        "es": "[Automix] Mezcla manual — el automix asumió el deck {d} "
              "({n}). El otro quedó libre y la siguiente ya está cargando."},
    "l_deck_a_tocar": {
        "pt": "O deck {d} está a tocar «{n}».\n\nParar a reprodução e "
              "carregar a faixa nova?",
        "en": "Deck {d} is playing “{n}”.\n\nStop playback and load the "
              "new track?",
        "es": "El deck {d} está sonando «{n}».\n\n¿Parar la reproducción y "
              "cargar la nueva pista?"},
    "l_deck_titulo": {"pt": "Deck a tocar", "en": "Deck is playing",
                      "es": "Deck sonando"},
    "l_xf_manual": {
        "pt": "[Automix] Crossfader movido à mão — o automix está à espera. "
              "Carrega em Seguinte para ele retomar a partir do que se ouve.",
        "en": "[Automix] Crossfader moved manually — automix is waiting. "
              "Press Next for it to resume from what is playing.",
        "es": "[Automix] Crossfader movido a mano — el automix espera. "
              "Pulsa Siguiente para que retome desde lo que suena."},
    "l_reordered":  {"pt": "[Playlist] Ordem alterada — {n} por tocar.",
                     "en": "[Playlist] Order changed — {n} left to play.",
                     "es": "[Playlist] Orden cambiado — {n} por sonar."},
    "l_pl_drop_adiante": {
        "pt": "[Playlist] Largada antes da faixa a tocar — "
              "colocada logo a seguir a ela.",
        "en": "[Playlist] Dropped before the playing track — "
              "placed right after it.",
        "es": "[Playlist] Soltada antes de la pista en curso — "
              "colocada justo después."},
    "m_edit_grid": {"pt": "Editar Beatgrid…", "en": "Edit Beatgrid…",
                    "es": "Editar Beatgrid…"},
    "m_open_loc":  {"pt": "Abrir localização no Explorador",
                    "en": "Open location in Explorer",
                    "es": "Abrir ubicación en el Explorador"},
    "m_load_pl":   {"pt": "Carregar playlist", "en": "Load playlist",
                    "es": "Cargar playlist"},
    "m_analyze":   {"pt": "Analisar músicas desta pasta",
                    "en": "Analyze tracks in this folder",
                    "es": "Analizar canciones de esta carpeta"},
    "l_ref_na":    {"pt": "[Playlist] faixa não analisada — usa «Analisar "
                          "músicas desta pasta» (botão direito no browser).",
                    "en": "[Playlist] track not analyzed — use «Analyze "
                          "tracks in this folder» (right-click in browser).",
                    "es": "[Playlist] pista sin analizar — usa «Analizar "
                          "canciones de esta carpeta» (clic derecho)."},
    "l_pl_drop":   {"pt": "[Playlist] + {n} faixa(s) arrastada(s).",
                    "en": "[Playlist] + {n} dragged track(s).",
                    "es": "[Playlist] + {n} pista(s) arrastrada(s)."},
    "l_grid_na":   {"pt": "[Grid] editor indisponível: {e}",
                    "en": "[Grid] editor unavailable: {e}",
                    "es": "[Grid] editor no disponible: {e}"},
    "l_grid_ok":   {"pt": "[Grid] grelha guardada: {n}",
                    "en": "[Grid] grid saved: {n}",
                    "es": "[Grid] rejilla guardada: {n}"},
    "l_grid_err":  {"pt": "[Grid] falhou: {e}", "en": "[Grid] failed: {e}",
                    "es": "[Grid] falló: {e}"},
    # ── mix contínuo (∞) ───────────────────────────────────────────────
    "inf_chk":     {"pt": "∞ Contínuo", "en": "∞ Continuous",
                    "es": "∞ Continuo"},
    "inf_tip":     {"pt": "MIX CONTÍNUO: quando a playlist está a acabar, "
                          "procura mais\nfaixas sozinho e nunca pára. "
                          "Primeiro no mesmo cluster; se\nesgotar, alarga aos "
                          "clusters VIZINHOS; depois à biblioteca\ncom filtro "
                          "de BPM e tom. Para bares, lojas e hotéis.",
                    "en": "CONTINUOUS MIX: when the playlist is running out, "
                          "it finds\nmore tracks on its own and never stops. "
                          "First in the same\ncluster; if exhausted, it "
                          "widens to NEIGHBORING clusters,\nthen to the whole "
                          "library with BPM/key filtering. For bars,\nshops "
                          "and hotels.",
                    "es": "MEZCLA CONTINUA: cuando la playlist se está "
                          "acabando, busca\nmás pistas por su cuenta y nunca "
                          "para. Primero en el mismo\ncluster; si se agota, "
                          "amplía a los clusters VECINOS; después\na la "
                          "biblioteca con filtro de BPM y tonalidad. Para "
                          "bares,\ntiendas y hoteles."},
    "inf_on":      {"pt": "[∞] Mix contínuo LIGADO — a playlist deixa de "
                          "acabar.",
                    "en": "[∞] Continuous mix ON — the playlist never ends.",
                    "es": "[∞] Mezcla continua ACTIVA — la playlist ya no "
                          "termina."},
    "inf_off":     {"pt": "[∞] Mix contínuo desligado.",
                    "en": "[∞] Continuous mix off.",
                    "es": "[∞] Mezcla continua desactivada."},
    "inf_lib_end": {"pt": "[∞] biblioteca esgotada — a recomeçar o histórico.",
                    "en": "[∞] library exhausted — restarting history.",
                    "es": "[∞] biblioteca agotada — reiniciando el historial."},
    "inf_none":    {"pt": "[∞] sem candidatos compatíveis; histórico limpo.",
                    "en": "[∞] no compatible candidates; history cleared.",
                    "es": "[∞] sin candidatos compatibles; historial "
                          "limpiado."},
    "inf_widen":   {"pt": "[∞] cluster esgotado — a alargar ({a}).",
                    "en": "[∞] cluster exhausted — widening ({a}).",
                    "es": "[∞] cluster agotado — ampliando ({a})."},
    # ── REPOSTO A 18/09/2026 ─────────────────────────────────────────────
    # Esta chave chamava-se `inf_parei`; foi renomeada para
    # `inf_stopped_fail` na chamada (linha ~8099) e a entrada do dicionario
    # desapareceu na mesma passagem. Sem ela o `_t()` devolve a propria
    # chave: quem fosse ver o log de um hotel lia «inf_stopped_fail» em vez
    # de uma explicacao. Apanhado pelo `teste_interface_3linguas` e pelo
    # `teste_inf_nao_para`.
    "inf_stopped_fail": {
        "pt": "[∞] parei: nem a volta ao princípio deu faixas. A playlist "
              "tem menos de duas faixas com grelha, ou a biblioteca ficou "
              "sem nada que o motor consiga tocar.",
        "en": "[∞] stopped: not even restarting from the top produced any "
              "tracks. The playlist has fewer than two tracks with a beat "
              "grid, or the library has nothing left the engine can play.",
        "es": "[∞] paré: ni volver al principio dio pistas. La lista tiene "
              "menos de dos pistas con rejilla, o la biblioteca se quedó "
              "sin nada que el motor pueda reproducir."},
    "inf_neigh":   {"pt": "vizinhos", "en": "neighbors", "es": "vecinos"},
    "inf_lib":     {"pt": "biblioteca", "en": "library", "es": "biblioteca"},
    "inf_add":     {"pt": "[∞] + {n}", "en": "[∞] + {n}", "es": "[∞] + {n}"},
    "inf_na":      {"pt": "[∞] indisponível: {e}",
                    "en": "[∞] unavailable: {e}",
                    "es": "[∞] no disponible: {e}"},
    "inf_err":     {"pt": "[∞] erro ({a}): {e}", "en": "[∞] error ({a}): {e}",
                    "es": "[∞] error ({a}): {e}"},
    "history":     {"pt": "Histórico", "en": "History", "es": "Historial"},
    "remove":      {"pt": "Remover", "en": "Remove", "es": "Quitar"},
    "start":       {"pt": "Iniciar", "en": "Start", "es": "Iniciar"},
    "stop":        {"pt": "Parar", "en": "Stop", "es": "Parar"},
    "ref_hint":    {"pt": "Duplo clique numa faixa para a definir como referência",
                    "en": "Double-click a track to set it as reference",
                    "es": "Doble clic en una pista para definirla como referencia"},
    # A pesquisa passou a ser por FICHEIROS na pasta escolhida (e subpastas),
    # nao pela base de dados — encontra faixas ainda por analisar.
    "search_ph":   {"pt": "nome, artista ou género (disco, house…)…",
                    "en": "name, artist or genre (disco, house…)…",
                    "es": "nombre, artista o género (disco, house…)…"},
    "l_busca_sem_pasta": {
        "pt": "[Pesquisa] Não encontrei pastas de música para procurar.",
        "en": "[Search] No music folders found to search.",
        "es": "[Búsqueda] No encontré carpetas de música donde buscar."},
    "l_busca_res": {"pt": "[Pesquisa] {n} ficheiro(s) para «{q}». "
                          "A amarelo: ainda não analisados.",
                    "en": "[Search] {n} file(s) for “{q}”. "
                          "In amber: not analysed yet.",
                    "es": "[Búsqueda] {n} archivo(s) para «{q}». "
                          "En ámbar: aún sin analizar."},
    "gen_pl":      {"pt": "⚡ Gerar Playlist", "en": "⚡ Generate Playlist",
                    "es": "⚡ Generar Playlist"},
    "clear":       {"pt": "✕ Limpar", "en": "✕ Clear", "es": "✕ Limpiar"},
    "next":        {"pt": "Seguinte", "en": "Next", "es": "Siguiente"},
    "auto_hw":     {"pt": "AUTO (detetar hardware)",
                    "en": "AUTO (detect hardware)",
                    "es": "AUTO (detectar hardware)"},
    "folder_hdr":  {"pt": "PASTA", "en": "FOLDER", "es": "CARPETA"},
    "drag_hint":   {"pt": "Arrasta para um deck ou para a playlist · duplo "
                          "clique = referência p/ Gerar Playlist · botão "
                          "direito = menu",
                    "en": "Drag to a deck or the playlist · double-click = "
                          "reference for Generate · right-click = menu",
                    "es": "Arrastra a un deck o a la playlist · doble clic = "
                          "referencia para Generar · clic derecho = menú"},
    "agent":       {"pt": "Agente:", "en": "Agent:", "es": "Agente:"},
    "agent_log":   {"pt": "Log do agente:", "en": "Agent log:",
                    "es": "Log del agente:"},
    "monitor_on":  {"pt": "Monitor ON", "en": "Monitor ON", "es": "Monitor ON"},
    "monitor_off": {"pt": "Monitor OFF", "en": "Monitor OFF",
                    "es": "Monitor OFF"},
    "gen_pl_hdr":  {"pt": "PLAYLIST GERADA", "en": "GENERATED PLAYLIST",
                    "es": "PLAYLIST GENERADA"},
    "pl_tab_tip":  {"pt": "Mostrar/ocultar a playlist gerada",
                    "en": "Show/hide the generated playlist",
                    "es": "Mostrar/ocultar la playlist generada"},
    "hide_pl":     {"pt": "Ocultar a playlist", "en": "Hide the playlist",
                    "es": "Ocultar la playlist"},
    "hdr_title":   {"pt": "Título", "en": "Title", "es": "Título"},
    "hdr_artist":  {"pt": "Artista", "en": "Artist", "es": "Artista"},
    "hdr_dur":     {"pt": "Duração", "en": "Duration", "es": "Duración"},
    "hdr_key":     {"pt": "Tom", "en": "Key", "es": "Tono"},
    "remaining":   {"pt": "Restante", "en": "Remaining", "es": "Restante"},
    "manual_mix":  {"pt": "mistura manual", "en": "manual mix",
                    "es": "mezcla manual"},
    "saved_pls":   {"pt": "Playlists Guardadas", "en": "Saved Playlists",
                    "es": "Playlists Guardadas"},
    "tracks_w":    {"pt": "faixas", "en": "tracks", "es": "pistas"},
    "load_sel":    {"pt": "Carregar Playlist Selecionada",
                    "en": "Load Selected Playlist",
                    "es": "Cargar Playlist Seleccionada"},
    "save_cur":    {"pt": "Guardar Playlist Atual",
                    "en": "Save Current Playlist",
                    "es": "Guardar Playlist Actual"},
    "remove_pl":   {"pt": "Remover Playlist", "en": "Remove Playlist",
                    "es": "Quitar Playlist"},
    "save_t":      {"pt": "Guardar", "en": "Save", "es": "Guardar"},
    "no_pl_save":  {"pt": "Sem playlist para guardar.",
                    "en": "No playlist to save.",
                    "es": "No hay playlist para guardar."},
    "save_pl_t":   {"pt": "Guardar Playlist", "en": "Save Playlist",
                    "es": "Guardar Playlist"},
    "set_name":    {"pt": "Nome do set:", "en": "Set name:",
                    "es": "Nombre del set:"},
    "remove_t":    {"pt": "Remover", "en": "Remove", "es": "Quitar"},
    "del_disk":    {"pt": "Apagar do disco?", "en": "Delete from disk?",
                    "es": "¿Borrar del disco?"},
    "close_t":     {"pt": "Fechar", "en": "Close", "es": "Cerrar"},
    "close_q":     {"pt": "Ainda está música a tocar.\nQueres mesmo fechar?",
                    "en": "Music is still playing.\nClose anyway?",
                    "es": "La música sigue sonando.\n¿Cerrar de todas formas?"},
    # ---- operações do agente DJ (log) — templates com {campos} -----------
    "l_search_na":   {"pt": "[Pesquisa] indisponível: {e}",
                      "en": "[Search] unavailable: {e}",
                      "es": "[Búsqueda] no disponible: {e}"},
    "l_search_ref":  {"pt": "[Pesquisa] Referência: {name}  {bpm} BPM  {key}",
                      "en": "[Search] Reference: {name}  {bpm} BPM  {key}",
                      "es": "[Búsqueda] Referencia: {name}  {bpm} BPM  {key}"},
    "l_sp_na":       {"pt": "[Set Planner] indisponível: {e}",
                      "en": "[Set Planner] unavailable: {e}",
                      "es": "[Set Planner] no disponible: {e}"},
    "l_sp_dlg_err":  {"pt": "[Set Planner] erro no diálogo: {e}",
                      "en": "[Set Planner] dialog error: {e}",
                      "es": "[Set Planner] error en el diálogo: {e}"},
    "l_sp_planning": {"pt": "[Set Planner] A planear set de {min} min "
                            "({shape} · {bpm}) para: {ref}…",
                      "en": "[Set Planner] Planning a {min}-min set "
                            "({shape} · {bpm}) for: {ref}…",
                      "es": "[Set Planner] Planeando un set de {min} min "
                            "({shape} · {bpm}) para: {ref}…"},
    "l_sp_ready":    {"pt": "[Set Planner] Set pronto: {n} faixas. "
                            "Clica 'Iniciar' para tocar.",
                      "en": "[Set Planner] Set ready: {n} tracks. "
                            "Click 'Start' to play.",
                      "es": "[Set Planner] Set listo: {n} pistas. "
                            "Pulsa 'Iniciar' para reproducir."},
    "l_sp_none":     {"pt": "[Set Planner] Sem resultados.",
                      "en": "[Set Planner] No results.",
                      "es": "[Set Planner] Sin resultados."},
    "l_sp_err":      {"pt": "[Set Planner] Erro: {e}",
                      "en": "[Set Planner] Error: {e}",
                      "es": "[Set Planner] Error: {e}"},
    "l_sp_start_err": {"pt": "[Set Planner] Erro ao iniciar: {e}",
                       "en": "[Set Planner] Error starting: {e}",
                       "es": "[Set Planner] Error al iniciar: {e}"},
    "l_clear":       {"pt": "[Limpar] Pesquisa, referência e playlist limpas.",
                      "en": "[Clear] Search, reference and playlist cleared.",
                      "es": "[Limpiar] Búsqueda, referencia y playlist limpiadas."},
    "l_set_out":     {"pt": "[Set] {n} faixa(s) fora (salto de BPM > 4).",
                      "en": "[Set] {n} track(s) left out (BPM jump > 4).",
                      "es": "[Set] {n} pista(s) fuera (salto de BPM > 4)."},
    "l_br_both":     {"pt": "[Browser] Ambos os decks a tocar — pára um "
                            "antes de carregar.",
                      "en": "[Browser] Both decks playing — stop one "
                            "before loading.",
                      "es": "[Browser] Ambos decks sonando — para uno "
                            "antes de cargar."},
    "l_br_open":     {"pt": "[Browser] Abri: {p}",
                      "en": "[Browser] Opened: {p}",
                      "es": "[Browser] Abrí: {p}"},
    "l_br_open_err": {"pt": "[Browser] Não consegui abrir a pasta: {e}",
                      "en": "[Browser] Couldn't open the folder: {e}",
                      "es": "[Browser] No pude abrir la carpeta: {e}"},
    "l_br_an_na":    {"pt": "[Browser] Análise indisponível (sem app principal).",
                      "en": "[Browser] Analysis unavailable (no main app).",
                      "es": "[Browser] Análisis no disponible (sin app principal)."},
    "l_br_an_busy":  {"pt": "[Browser] Já há uma análise a decorrer — aguarda.",
                      "en": "[Browser] An analysis is already running — wait.",
                      "es": "[Browser] Ya hay un análisis en curso — espera."},
    "l_br_read_err": {"pt": "[Browser] Erro a ler a pasta: {e}",
                      "en": "[Browser] Error reading the folder: {e}",
                      "es": "[Browser] Error al leer la carpeta: {e}"},
    "l_br_no_audio": {"pt": "[Browser] Sem ficheiros de áudio nesta pasta.",
                      "en": "[Browser] No audio files in this folder.",
                      "es": "[Browser] No hay archivos de audio en esta carpeta."},
    "l_br_eng_na":   {"pt": "[Browser] Motor de análise indisponível: {e}",
                      "en": "[Browser] Analysis engine unavailable: {e}",
                      "es": "[Browser] Motor de análisis no disponible: {e}"},
    "l_br_analyzing": {"pt": "[Browser] A analisar {n} faixa(s) de '{f}' em "
                             "segundo plano — os decks continuam operativos.",
                       "en": "[Browser] Analyzing {n} track(s) from '{f}' in "
                             "the background — decks keep running.",
                       "es": "[Browser] Analizando {n} pista(s) de '{f}' en "
                             "segundo plano — los decks siguen operativos."},
    "l_br_an_msg":   {"pt": "[Browser] Análise: {m}",
                      "en": "[Browser] Analysis: {m}",
                      "es": "[Browser] Análisis: {m}"},
    "l_br_an_done":  {"pt": "[Browser] Análise concluída — BPM/tom atualizados.",
                      "en": "[Browser] Analysis finished — BPM/key updated.",
                      "es": "[Browser] Análisis terminado — BPM/tono actualizados."},
    "l_br_pl_err":   {"pt": "[Browser] Erro a ler a playlist: {e}",
                      "en": "[Browser] Error reading the playlist: {e}",
                      "es": "[Browser] Error al leer la playlist: {e}"},
    "l_br_pl_empty": {"pt": "[Browser] Playlist vazia (ou ficheiros não "
                            "encontrados no disco).",
                      "en": "[Browser] Playlist empty (or files not found "
                            "on disk).",
                      "es": "[Browser] Playlist vacía (o archivos no "
                            "encontrados en el disco)."},
    "l_br_pl_loaded": {"pt": "[Browser] Playlist '{p}' carregada ({n} faixas).",
                       "en": "[Browser] Playlist '{p}' loaded ({n} tracks).",
                       "es": "[Browser] Playlist '{p}' cargada ({n} pistas)."},
    "l_am_sel_remove": {"pt": "[Automix] Seleciona faixa(s) para remover.",
                        "en": "[Automix] Select track(s) to remove.",
                        "es": "[Automix] Selecciona pista(s) para quitar."},
    "l_am_removed":  {"pt": "[Automix] Removida(s) {n} faixa(s).",
                      "en": "[Automix] Removed {n} track(s).",
                      "es": "[Automix] Quitada(s) {n} pista(s)."},
    "l_am_playing":  {"pt": "[Automix] Já está a tocar. 'Parar' primeiro.",
                      "en": "[Automix] Already playing. 'Stop' first.",
                      "es": "[Automix] Ya está sonando. 'Parar' primero."},
    "l_am_min2":     {"pt": "[Automix] Playlist com menos de 2 faixas.",
                      "en": "[Automix] Playlist has fewer than 2 tracks.",
                      "es": "[Automix] Playlist con menos de 2 pistas."},
    # Sem mencionar o VirtualDJ: este e' o motor de audio do proprio Fusion.
    # O VirtualDJ so' entra no DJ Co-Pilot, que e' outra coisa — e dizer
    # "sem VirtualDJ" aqui so' fazia sentido quando o player era novidade.
    "l_am_prep":     {"pt": "[Automix] A preparar o motor de áudio…",
                      "en": "[Automix] Preparing the audio engine…",
                      "es": "[Automix] Preparando el motor de audio…"},
    "l_am_audio_err": {"pt": "[Automix] Placa de som: {e}",
                       "en": "[Automix] Sound card: {e}",
                       "es": "[Automix] Tarjeta de sonido: {e}"},
    "l_am_live":     {"pt": "[Automix] AO VIVO 🎧  master {bpm} BPM. Transições "
                            "beat-perfeitas com bass-swap; efeitos no beat.",
                      "en": "[Automix] LIVE 🎧  master {bpm} BPM. Beat-perfect "
                            "transitions with bass-swap; effects on the beat.",
                      "es": "[Automix] EN VIVO 🎧  master {bpm} BPM. Transiciones "
                            "perfectas al beat con bass-swap; efectos en el beat."},
    "l_am_prep_err": {"pt": "[Automix] Erro na preparação: {m}",
                      "en": "[Automix] Error preparing: {m}",
                      "es": "[Automix] Error en la preparación: {m}"},
    "l_am_stopped":  {"pt": "[Automix] Parado.",
                      "en": "[Automix] Stopped.",
                      "es": "[Automix] Parado."},
    "l_pl_stopped":  {"pt": "[Automix] Playlist parada — a faixa atual toca "
                            "até ao fim. Estás em MISTURA MANUAL ('Parar' "
                            "outra vez = parar tudo).",
                      "en": "[Automix] Playlist stopped — the current track "
                            "plays to the end. You're in MANUAL MIX ('Stop' "
                            "again = stop everything).",
                      "es": "[Automix] Playlist parada — la pista actual "
                            "suena hasta el final. Estás en MEZCLA MANUAL "
                            "('Parar' otra vez = parar todo)."},
    "l_am_replan":   {"pt": "[Automix] Transição replaneada após o seek.",
                      "en": "[Automix] Transition replanned after the seek.",
                      "es": "[Automix] Transición replanificada tras el seek."},
    "l_am_replan_err": {"pt": "[Automix] replan falhou: {e}",
                        "en": "[Automix] replan failed: {e}",
                        "es": "[Automix] replan falló: {e}"},
    "l_am_nothing":  {"pt": "[Automix] Nada a tocar.",
                      "en": "[Automix] Nothing playing.",
                      "es": "[Automix] Nada sonando."},
    "l_am_next_err": {"pt": "[Automix] NEXT falhou: {e}",
                      "en": "[Automix] NEXT failed: {e}",
                      "es": "[Automix] NEXT falló: {e}"},
    "l_next_go":     {"pt": ">> NEXT: a misturar já para a faixa seguinte…",
                      "en": ">> NEXT: mixing into the next track now…",
                      "es": ">> NEXT: mezclando ya a la siguiente pista…"},
    "l_am_next_skip": {"pt": "[Automix] NEXT ignorado (transição em curso "
                             "ou sem faixa seguinte).",
                       "en": "[Automix] NEXT ignored (transition running "
                             "or no next track).",
                       "es": "[Automix] NEXT ignorado (transición en curso "
                             "o sin pista siguiente)."},
    "l_fx_toggle":   {"pt": "[Agente] Efeitos criativos: {s}",
                      "en": "[Agent] Creative FX: {s}",
                      "es": "[Agente] Efectos creativos: {s}"},
    "l_fx_int":      {"pt": "[Agente] Intensidade: {s}",
                      "en": "[Agent] Intensity: {s}",
                      "es": "[Agente] Intensidad: {s}"},
    "l_mixing":      {"pt": ">> A misturar: {a}  →  {b}",
                      "en": ">> Mixing: {a}  →  {b}",
                      "es": ">> Mezclando: {a}  →  {b}"},
    "l_end_early":   {"pt": "[Automix] Faixa terminou antes do planeado — "
                            "a avançar já.",
                      "en": "[Automix] Track ended earlier than planned — "
                            "advancing now.",
                      "es": "[Automix] La pista terminó antes de lo previsto — "
                            "avanzando ya."},
    "l_set_done":    {"pt": "[Automix] Set terminado ✔",
                      "en": "[Automix] Set finished ✔",
                      "es": "[Automix] Set terminado ✔"},
    "l_now_playing": {"pt": ">> A tocar: {n}",
                      "en": ">> Now playing: {n}",
                      "es": ">> Sonando: {n}"},
    "l_man_audio_err": {"pt": "[Manual] Placa de som: {e}",
                        "en": "[Manual] Sound card: {e}",
                        "es": "[Manual] Tarjeta de sonido: {e}"},
    "l_man_ready":   {"pt": "[Manual] Motor pronto (master {bpm} BPM). Arrasta "
                            "músicas para os decks e mistura à mão.",
                      "en": "[Manual] Engine ready (master {bpm} BPM). Drag "
                            "tracks onto the decks and mix by hand.",
                      "es": "[Manual] Motor listo (master {bpm} BPM). Arrastra "
                            "pistas a los decks y mezcla a mano."},
    "l_man_playing": {"pt": "[Manual] Deck {d} está a TOCAR — pára o deck "
                            "antes de carregar outra música.",
                      "en": "[Manual] Deck {d} is PLAYING — stop it before "
                            "loading another track.",
                      "es": "[Manual] El deck {d} está SONANDO — páralo antes "
                            "de cargar otra pista."},
    "l_man_busy":    {"pt": "[Manual] Deck {d} ainda a carregar…",
                      "en": "[Manual] Deck {d} still loading…",
                      "es": "[Manual] Deck {d} aún cargando…"},
    "l_man_loading": {"pt": "[Manual] A carregar no deck {d}: {n}…",
                      "en": "[Manual] Loading into deck {d}: {n}…",
                      "es": "[Manual] Cargando en el deck {d}: {n}…"},
    "l_man_ok":      {"pt": "[Manual] Deck {d} pronto: {n} (CUE/▶ para tocar)",
                      "en": "[Manual] Deck {d} ready: {n} (CUE/▶ to play)",
                      "es": "[Manual] Deck {d} listo: {n} (CUE/▶ para reproducir)"},
    "l_man_fail":    {"pt": "[Manual] Deck {d} falhou: {e}",
                      "en": "[Manual] Deck {d} failed: {e}",
                      "es": "[Manual] Deck {d} falló: {e}"},
    "l_pfl_later":   {"pt": "[Pré-escuta] Placa escolhida — liga quando o "
                            "motor arrancar.",
                      "en": "[Cue] Device selected — it connects when the "
                            "engine starts.",
                      "es": "[Preescucha] Tarjeta elegida — se conecta cuando "
                            "arranque el motor."},
    "l_pfl_none":    {"pt": "[Pré-escuta] AUTO não detetou nenhuma placa de "
                            "controladora ligada.",
                      "en": "[Cue] AUTO found no controller audio device.",
                      "es": "[Preescucha] AUTO no detectó ninguna tarjeta de "
                            "controladora."},
    "l_pfl_err":     {"pt": "[Pré-escuta] erro: {e}",
                      "en": "[Cue] error: {e}",
                      "es": "[Preescucha] error: {e}"},
    "l_ddj_na":      {"pt": "[DDJ-400] módulo indisponível: {e}",
                      "en": "[DDJ-400] module unavailable: {e}",
                      "es": "[DDJ-400] módulo no disponible: {e}"},
    "l_ddj_mon_on":  {"pt": "[DDJ-400] modo monitor ON — mexe nos controlos "
                            "e vê os códigos no log",
                      "en": "[DDJ-400] monitor mode ON — move the controls "
                            "and watch the codes in the log",
                      "es": "[DDJ-400] modo monitor ON — mueve los controles "
                            "y mira los códigos en el log"},
    "l_ddj_mon_off": {"pt": "[DDJ-400] modo monitor OFF",
                      "en": "[DDJ-400] monitor mode OFF",
                      "es": "[DDJ-400] modo monitor OFF"},
    "l_hist_na":     {"pt": "[Histórico] indisponível: {e}",
                      "en": "[History] unavailable: {e}",
                      "es": "[Historial] no disponible: {e}"},
    "l_hist_saved":  {"pt": "[Histórico] Guardada: {n} ({k} faixas).",
                      "en": "[History] Saved: {n} ({k} tracks).",
                      "es": "[Historial] Guardada: {n} ({k} pistas)."},
    "l_hist_loaded": {"pt": "[Histórico] '{n}' ({k} faixas). Agora 'Iniciar'.",
                      "en": "[History] '{n}' ({k} tracks). Now click 'Start'.",
                      "es": "[Historial] '{n}' ({k} pistas). Ahora 'Iniciar'."},
    "l_prep_bpm":    {"pt": "a detetar BPM: {n}…",
                      "en": "detecting BPM: {n}…",
                      "es": "detectando BPM: {n}…"},
    "l_prep_load":   {"pt": "a carregar/esticar as 2 primeiras faixas…",
                      "en": "loading/stretching the first 2 tracks…",
                      "es": "cargando/estirando las 2 primeras pistas…"},
    # ---- consola da MANUTENÇÃO (30/08/2026) ------------------------------
    # A janela estava só em português, incluindo os quatro botões. O
    # relatório e as descrições das suites vivem no `mixai_manutencao`, com
    # o seu próprio dicionário; aqui fica a moldura.
    "man_titulo":  {"pt": "MixAi Fusion — Manutenção",
                    "en": "MixAi Fusion — Maintenance",
                    "es": "MixAi Fusion — Mantenimiento"},
    "man_pronto":  {"pt": "Pronto a correr.", "en": "Ready to run.",
                    "es": "Listo para correr."},
    "man_correr":  {"pt": "A correr…", "en": "Running…",
                    "es": "Corriendo…"},
    "man_bt_diag": {"pt": "Diagnosticar e testar", "en": "Diagnose and test",
                    "es": "Diagnosticar y probar"},
    "man_bt_fix":  {"pt": "Corrigir e testar", "en": "Fix and test",
                    "es": "Corregir y probar"},
    "man_bt_parar": {"pt": "Parar", "en": "Stop", "es": "Parar"},
    "man_bt_fechar": {"pt": "Fechar", "en": "Close", "es": "Cerrar"},
    "man_bt_zip":  {"pt": "Guardar diagnóstico",
                    "en": "Save diagnostics",
                    "es": "Guardar diagnóstico"},
    "man_zip_a_fazer": {"pt": "\nA juntar o diagnóstico…",
                        "en": "\nCollecting diagnostics…",
                        "es": "\nRecogiendo el diagnóstico…"},
    "man_zip_ok":  {"pt": "Diagnóstico guardado em:\n  {p}",
                    "en": "Diagnostics saved to:\n  {p}",
                    "es": "Diagnóstico guardado en:\n  {p}"},
    "man_zip_leva": {"pt": "  Leva: {q}",
                     "en": "  Includes: {q}",
                     "es": "  Incluye: {q}"},
    "man_zip_falta": {"pt": "  Não existiam: {q}",
                      "en": "  Not present: {q}",
                      "es": "  No existían: {q}"},
    "man_zip_aviso": {
        "pt": "  ATENÇÃO: os registos têm os CAMINHOS dos teus ficheiros de\n"
              "  música. Abre o zip e vê o que vai lá dentro antes de o\n"
              "  mandares a alguém. A base de dados NÃO vai, nem música.",
        "en": "  NOTE: the logs contain the PATHS of your music files. Open\n"
              "  the zip and check what is inside before sending it to\n"
              "  anyone. The database is NOT included, nor any audio.",
        "es": "  ATENCIÓN: los registros llevan las RUTAS de tus ficheros de\n"
              "  música. Abre el zip y mira lo que lleva dentro antes de\n"
              "  enviarlo. La base de datos NO va, ni música."},
    "man_zip_erro": {"pt": "Não consegui juntar o diagnóstico: {e}",
                     "en": "Could not collect diagnostics: {e}",
                     "es": "No pude recoger el diagnóstico: {e}"},
    "man_cab":     {"pt": "  MANUTENÇÃO DO MIXAI FUSION",
                    "en": "  MIXAI FUSION MAINTENANCE",
                    "es": "  MANTENIMIENTO DEL MIXAI FUSION"},
    "man_p1":      {"pt": "\n[1/3] Diagnóstico", "en": "\n[1/3] Diagnosis",
                    "es": "\n[1/3] Diagnóstico"},
    "man_p2":      {"pt": "\n[2/3] Suites de teste",
                    "en": "\n[2/3] Test suites",
                    "es": "\n[2/3] Suites de test"},
    "man_p3":      {"pt": "\n[3/3] Correcções", "en": "\n[3/3] Fixes",
                    "es": "\n[3/3] Correcciones"},
    "man_resumo":  {"pt": "\n  {p} suite(s) passaram · {f} falharam · "
                          "{s} saltadas",
                    "en": "\n  {p} suite(s) passed · {f} failed · "
                          "{s} skipped",
                    "es": "\n  {p} suite(s) pasaron · {f} fallaron · "
                          "{s} saltadas"},
    "man_nao_ped": {"pt": "  (não pedidas — carrega em «Corrigir e testar»)",
                    "en": "  (not requested — click “Fix and test”)",
                    "es": "  (no pedidas — pulsa «Corregir y probar»)"},
    "man_musica1": {"pt": "  ✖ Há música a tocar. As correcções ficam à "
                          "espera:",
                    "en": "  ✖ Music is playing. The fixes will wait:",
                    "es": "  ✖ Hay música sonando. Las correcciones esperan:"},
    "man_musica2": {"pt": "    recalcular grelhas come o CPU que o áudio "
                          "precisa,",
                    "en": "    recomputing grids eats the CPU the audio "
                          "needs,",
                    "es": "    recalcular rejillas se come la CPU que el "
                          "audio necesita,"},
    "man_musica3": {"pt": "    e o resultado seria o som a cortar a meio do "
                          "set.",
                    "en": "    and the result would be the sound breaking up "
                          "mid-set.",
                    "es": "    y el resultado sería el sonido cortando en "
                          "medio del set."},
    "man_musica4": {"pt": "    Pára os decks e volta a correr.",
                    "en": "    Stop the decks and run it again.",
                    "es": "    Para los decks y vuelve a correr."},
    "man_nada":    {"pt": "  Nada a corrigir — a biblioteca está sã.",
                    "en": "  Nothing to fix — the library is healthy.",
                    "es": "  Nada que corregir — la biblioteca está sana."},
    "man_ordem":   {"pt": "Tudo em ordem ✔", "en": "All in order ✔",
                    "es": "Todo en orden ✔"},
    "man_atencao": {"pt": "{n} coisa(s) a precisar de atenção",
                    "en": "{n} thing(s) needing attention",
                    "es": "{n} cosa(s) que necesitan atención"},
    "man_corrig":  {"pt": "  ·  {n} corrigida(s)", "en": "  ·  {n} fixed",
                    "es": "  ·  {n} corregida(s)"},
    "man_anterior": {"pt": "A corrida anterior ainda está a terminar — espera "
                           "um instante.",
                     "en": "The previous run is still finishing — wait a "
                           "moment.",
                     "es": "La corrida anterior aún está terminando — espera "
                           "un instante."},
    "man_fundo":   {"pt": "[Manutenção] a terminar em segundo plano — o que "
                          "já foi corrigido está gravado.",
                    "en": "[Maintenance] finishing in the background — what "
                          "was already fixed is saved.",
                    "es": "[Mantenimiento] terminando en segundo plano — lo "
                          "que ya se corrigió está guardado."},
    "man_na":      {"pt": "[Manutenção] indisponível: {e}",
                    "en": "[Maintenance] unavailable: {e}",
                    "es": "[Mantenimiento] no disponible: {e}"},
    # ---- efeitos criativos (_CreativeFX) ---------------------------------
    "l_fx_plan":     {"pt": "Agente: plano estrutural ({t}): {k}",
                      "en": "Agent: structural plan ({t}): {k}",
                      "es": "Agente: plan estructural ({t}): {k}"},
    "l_fx_riser":    {"pt": "FX: riser de filtro → drop no beat {b} (deck {d})",
                      "en": "FX: filter riser → drop at beat {b} (deck {d})",
                      "es": "FX: riser de filtro → drop en el beat {b} (deck {d})"},
    "l_fx_break":    {"pt": "FX: echo no breakdown (beat {b}, deck {d})",
                      "en": "FX: echo on the breakdown (beat {b}, deck {d})",
                      "es": "FX: echo en el breakdown (beat {b}, deck {d})"},
    "l_fx_body":     {"pt": "FX: flanger no corpo (beat {b}, deck {d})",
                      "en": "FX: flanger on the body (beat {b}, deck {d})",
                      "es": "FX: flanger en el cuerpo (beat {b}, deck {d})"},
    "l_fx_sweep":    {"pt": "FX: filter sweep (8 beats) no deck {d}",
                      "en": "FX: filter sweep (8 beats) on deck {d}",
                      "es": "FX: filter sweep (8 beats) en el deck {d}"},
    "l_fx_echo":     {"pt": "FX: echo 3/4 beat (4 beats) no deck {d}",
                      "en": "FX: echo 3/4 beat (4 beats) on deck {d}",
                      "es": "FX: echo 3/4 beat (4 beats) en el deck {d}"},
    "l_fx_flanger":  {"pt": "FX: flanger (8 beats) no deck {d}",
                      "en": "FX: flanger (8 beats) on deck {d}",
                      "es": "FX: flanger (8 beats) en el deck {d}"},
    "l_fx_reverb":   {"pt": "FX: reverb (8 beats) no deck {d}",
                      "en": "FX: reverb (8 beats) on deck {d}",
                      "es": "FX: reverb (8 beats) en el deck {d}"},
    "l_fx_fail":     {"pt": "FX falhou: {e}",
                      "en": "FX failed: {e}",
                      "es": "FX falló: {e}"},

    # ═══════════════════════════════════════════════════════════════════
    #  31/08/2026 — O QUE FALTAVA TRADUZIR NA JANELA
    #
    #  A janela ja' falava tres linguas, mas havia texto escrito em cru no
    #  meio do codigo: as ajudas dos botoes (que so' aparecem ao passar o
    #  rato, e por isso ninguem dava por elas), os cabecalhos da tabela de
    #  pesquisa quando nao ha janela principal, e vinte e tal linhas do log
    #  do agente. Numa sessao em ingles saía tudo em portugues.
    #
    #  Nao rebentava nada — e' esse o problema: um texto por traduzir nao
    #  se queixa. So' se descobre a olhar, como aconteceu com o ⚙.
    # ═══════════════════════════════════════════════════════════════════

    # ── ajudas dos botoes da barra de cima ─────────────────────────────
    "master_tip":  {"pt": "Master tempo do set. AUTO = mediana dos BPM da "
                          "playlist.\nAplica-se ao carregar em Iniciar.",
                    "en": "Set master tempo. AUTO = median BPM of the "
                          "playlist.\nApplied when you press Start.",
                    "es": "Tempo master del set. AUTO = mediana de los BPM "
                          "de la lista.\nSe aplica al pulsar Iniciar."},
    "man_tip":     {"pt": "Manutenção: diagnostica a máquina, a biblioteca "
                          "e a instalação,\ne corrige sozinho o que for "
                          "dados da biblioteca.",
                    "en": "Maintenance: checks the machine, the library and "
                          "the install,\nand fixes library data on its own.",
                    "es": "Mantenimiento: diagnostica la máquina, la "
                          "biblioteca y la instalación,\ny corrige solo lo "
                          "que sean datos de la biblioteca."},
    "phones_tip":  {"pt": "Placa de som da pré-escuta (auscultadores).\n"
                          "AUTO deteta a controladora ligada (Pioneer, "
                          "Denon, Hercules…);\npodes forçar outra saída se "
                          "preferires.",
                    "en": "Sound card for pre-listening (headphones).\n"
                          "AUTO detects the controller you have plugged in "
                          "(Pioneer, Denon, Hercules…);\nyou can force "
                          "another output if you prefer.",
                    "es": "Tarjeta de sonido de la pre-escucha "
                          "(auriculares).\nAUTO detecta la controladora "
                          "conectada (Pioneer, Denon, Hercules…);\npuedes "
                          "forzar otra salida si lo prefieres."},
    "ddj_tip":     {"pt": "Modo MONITOR: liga a controladora (DDJ-400/…) e "
                          "mostra no log o\ncódigo MIDI (canal/nota/CC) de "
                          "cada botão/knob que mexeres —\npara afinar o "
                          "mapeamento. Desligado = uso normal.",
                    "en": "MONITOR mode: connects the controller (DDJ-400/…) "
                          "and prints the\nMIDI code (channel/note/CC) of "
                          "every button/knob you touch —\nto tune the "
                          "mapping. Off = normal use.",
                    "es": "Modo MONITOR: conecta la controladora (DDJ-400/…) "
                          "y muestra en el log\nel código MIDI "
                          "(canal/nota/CC) de cada botón/mando que muevas —"
                          "\npara afinar el mapeo. Apagado = uso normal."},
    "xf_on_tip":   {"pt": "Crossfader ENABLE — clica para DISABLE (os dois "
                          "decks passam inteiros e mistura-se só com os "
                          "faders de canal).",
                    "en": "Crossfader ENABLE — click for DISABLE (both decks "
                          "come through at full and you mix with the channel "
                          "faders only).",
                    "es": "Crossfader ENABLE — pulsa para DISABLE (los dos "
                          "decks pasan enteros y se mezcla solo con los "
                          "faders de canal)."},
    "xf_off_tip":  {"pt": "Crossfader DISABLE — clica para ENABLE (o cursor "
                          "volta a mandar na mistura).",
                    "en": "Crossfader DISABLE — click for ENABLE (the slider "
                          "takes charge of the mix again).",
                    "es": "Crossfader DISABLE — pulsa para ENABLE (el cursor "
                          "vuelve a mandar en la mezcla)."},

    # ── cabecalhos da tabela de pesquisa ───────────────────────────────
    #
    # So' se usam quando a janela principal nao esta' la' (o player aberto
    # sozinho). Com ela, os textos vem de la'. Antes o recurso era sempre o
    # portugues, mesmo com a app em ingles.
    "header_track":  {"pt": "Faixa", "en": "Track", "es": "Pista"},
    "header_bpm":    {"pt": "BPM", "en": "BPM", "es": "BPM"},
    "header_camelot": {"pt": "Camelot", "en": "Camelot", "es": "Camelot"},
    "header_loudness": {"pt": "Volume", "en": "Loudness", "es": "Volumen"},
    "header_energy": {"pt": "Energia", "en": "Energy", "es": "Energía"},
    "header_centroid": {"pt": "Brilho", "en": "Brightness", "es": "Brillo"},
    "header_cluster": {"pt": "Cluster", "en": "Cluster", "es": "Clúster"},
    "header_compatibility": {"pt": "Compatibilidade", "en": "Compatibility",
                             "es": "Compatibilidad"},

    # ── barra de progresso e etiqueta do MASTER ────────────────────────
    "an_prep":     {"pt": "A preparar análise…", "en": "Preparing analysis…",
                    "es": "Preparando análisis…"},
    "master_auto": {"pt": "MASTER {b} BPM · automático",
                    "en": "MASTER {b} BPM · automatic",
                    "es": "MASTER {b} BPM · automático"},
    "master_xfade": {"pt": "MASTER {b} BPM · crossfade 32 beats · "
                           "bass-swap + echo-out",
                     "en": "MASTER {b} BPM · crossfade 32 beats · "
                           "bass-swap + echo-out",
                     "es": "MASTER {b} BPM · crossfade 32 beats · "
                           "bass-swap + echo-out"},

    # ── janela do histórico de playlists ───────────────────────────────
    "l_hist_save_t": {"pt": "Guardar", "en": "Save", "es": "Guardar"},
    "l_hist_del_t":  {"pt": "Remover", "en": "Remove", "es": "Quitar"},
    "l_fail":        {"pt": "Falha: {e}", "en": "Failed: {e}",
                      "es": "Fallo: {e}"},

    # ── linhas do log do agente ────────────────────────────────────────
    "l_fx_sem_estrutura": {
        "pt": "[FX] sem estrutura em {t} — efeitos a cada ~{f} frases "
              "({b} batidas).",
        "en": "[FX] no structure in {t} — effects every ~{f} phrases "
              "({b} beats).",
        "es": "[FX] sin estructura en {t} — efectos cada ~{f} frases "
              "({b} tiempos)."},
    "l_fx_passados": {
        "pt": "[FX] {n} evento(s) já passaram (agente ligado a meio da faixa) — ficaram para trás.",
        "en": "[FX] {n} event(s) already gone by (agent switched on mid-track) — left behind.",
        "es": "[FX] {n} evento(s) ya pasaron (agente activado a mitad de la pista) — quedaron atrás.",
    },
    "l_fx_poucos": {
        "pt": "[FX] {s} secções mas {n} evento(s) utilizáveis — efeitos por "
              "intervalo de batidas.",
        "en": "[FX] {s} sections but {n} usable event(s) — effects by beat "
              "interval instead.",
        "es": "[FX] {s} secciones pero {n} evento(s) utilizables — efectos "
              "por intervalo de tiempos."},
    "l_search_ms": {"pt": "[Pesquisa] lista construída em {ms} ms",
                    "en": "[Search] list built in {ms} ms",
                    "es": "[Búsqueda] lista construida en {ms} ms"},
    "l_inf_set":   {"pt": "[∞] set com {m} min de {k} pedidos — contínuo "
                          "ligado, ancorado em {r}",
                    "en": "[∞] set of {m} min out of {k} requested — "
                          "continuous on, anchored on {r}",
                    "es": "[∞] set de {m} min de {k} pedidos — continuo "
                          "activado, anclado en {r}"},
    "l_grelhas_ok": {"pt": "[Grelhas] prontas ({n} calculadas) — o Iniciar "
                           "já não espera por elas.",
                     "en": "[Grids] ready ({n} computed) — Start no longer "
                           "waits for them.",
                     "es": "[Rejillas] listas ({n} calculadas) — Iniciar ya "
                           "no espera por ellas."},
    "l_folder_ms": {"pt": "[Pasta] {n} item(ns) em {ms} ms",
                    "en": "[Folder] {n} item(s) in {ms} ms",
                    "es": "[Carpeta] {n} elemento(s) en {ms} ms"},
    "l_am_adopt_fail": {"pt": "[Automix] adopção do deck falhou: {e}",
                        "en": "[Automix] deck adoption failed: {e}",
                        "es": "[Automix] la adopción del deck falló: {e}"},
    "l_pl_sync_fail": {"pt": "[Playlist] sincronização falhou: {e}",
                       "en": "[Playlist] sync failed: {e}",
                       "es": "[Playlist] la sincronización falló: {e}"},
    "l_req_prev":  {"pt": "[Pedido] transição prevista: {d}",
                    "en": "[Request] planned transition: {d}",
                    "es": "[Petición] transición prevista: {d}"},
    "l_am_protegida": {
        "pt": "[Automix] a faixa que está a tocar não foi removida — usa o "
              "Seguinte para saltar.",
        "en": "[Automix] the playing track was not removed — use Next to "
              "skip it.",
        "es": "[Automix] la pista que suena no se quitó — usa Siguiente para "
              "saltarla."},
    "l_am_rem_fail": {"pt": "[Automix] remoção no motor falhou: {e}",
                      "en": "[Automix] removal in the engine failed: {e}",
                      "es": "[Automix] el borrado en el motor falló: {e}"},
    "l_am_rem_ok": {"pt": "[Automix] {n} faixa(s) tiradas também do motor "
                          "({k} por tocar).",
                    "en": "[Automix] {n} track(s) also taken out of the "
                          "engine ({k} still to play).",
                    "es": "[Automix] {n} pista(s) quitadas también del motor "
                          "({k} por sonar)."},
    "l_am_align":  {"pt": "[Automix] A preparar o alinhamento — vai engatar "
                          "no ponto de mistura da faixa que está a tocar.",
                    "en": "[Automix] Preparing the alignment — it will latch "
                          "on at the mix point of the playing track.",
                    "es": "[Automix] Preparando la alineación — enganchará "
                          "en el punto de mezcla de la pista que suena."},
    "l_am_align_ok": {
        "pt": "[Automix] Alinhamento novo engatado sobre a faixa que está a "
              "tocar — sem cortes.",
        "en": "[Automix] New alignment latched onto the playing track — no "
              "cuts.",
        "es": "[Automix] Nueva alineación enganchada sobre la pista que "
              "suena — sin cortes."},
    "l_am_align_fail": {
        "pt": "[Automix] engate falhou ({e}); a arrancar pelo caminho normal.",
        "en": "[Automix] latching failed ({e}); starting the normal way.",
        "es": "[Automix] el enganche falló ({e}); arrancando por el camino "
              "normal."},
    "l_rec_armed": {"pt": "[REC] armado — começa ao detetar som.",
                    "en": "[REC] armed — starts when sound is detected.",
                    "es": "[REC] armado — empieza al detectar sonido."},
    "l_rec_fail":  {"pt": "[REC] falhou: {e}", "en": "[REC] failed: {e}",
                    "es": "[REC] falló: {e}"},
    "l_am_stop_again": {
        "pt": "[Automix] Carregue em PARAR outra vez para limpar tudo, ou em "
              "INICIAR para voltar ao automático.",
        "en": "[Automix] Press STOP again to clear everything, or START to go "
              "back to automatic.",
        "es": "[Automix] Pulsa PARAR otra vez para limpiarlo todo, o INICIAR "
              "para volver al automático."},
    "l_am_replan_fail": {"pt": "[Automix] não consegui reagendar: {e}",
                         "en": "[Automix] could not reschedule: {e}",
                         "es": "[Automix] no pude reprogramar: {e}"},
    "l_am_auto_back": {
        "pt": "[Automix] Modo AUTOMÁTICO retomado a partir da faixa que está "
              "a tocar.",
        "en": "[Automix] AUTOMATIC mode resumed from the playing track.",
        "es": "[Automix] Modo AUTOMÁTICO retomado desde la pista que suena."},
    "l_am_off_manual": {"pt": "[Automix] Desligado. A música continua em "
                              "MANUAL.",
                        "en": "[Automix] Off. The music carries on in MANUAL.",
                        "es": "[Automix] Apagado. La música sigue en MANUAL."},
    "l_am_clear_playing": {
        "pt": "[Automix] Limpo. A faixa no ar CONTINUA a tocar em manual — "
              "carregue outra playlist quando quiser.",
        "en": "[Automix] Cleared. The track on air KEEPS playing in manual — "
              "load another playlist whenever you want.",
        "es": "[Automix] Limpio. La pista en el aire SIGUE sonando en "
              "manual — carga otra lista cuando quieras."},
    "l_am_clear_engine": {"pt": "[Automix] Limpo. Motor de áudio mantido "
                                "ligado.",
                          "en": "[Automix] Cleared. Audio engine left "
                                "running.",
                          "es": "[Automix] Limpio. Motor de audio mantenido "
                                "encendido."},
    "l_xf_on":     {"pt": "[Mixer] crossfader ENABLE — o cursor manda.",
                    "en": "[Mixer] crossfader ENABLE — the slider is in "
                          "charge.",
                    "es": "[Mixer] crossfader ENABLE — manda el cursor."},
    "l_xf_off":    {"pt": "[Mixer] crossfader DISABLE — os dois decks passam "
                          "inteiros; mistura pelos faders de canal.",
                    "en": "[Mixer] crossfader DISABLE — both decks come "
                          "through at full; mix with the channel faders.",
                    "es": "[Mixer] crossfader DISABLE — los dos decks pasan "
                          "enteros; mezcla con los faders de canal."},
    "l_ui_parou":  {"pt": "[UI] parou {s}s · {f}",
                    "en": "[UI] stalled {s}s · {f}",
                    "es": "[UI] se paró {s}s · {f}"},
}


def _tr(lang: str, key: str) -> str:
    d = _TX.get(key) or {}
    return d.get(lang) or d.get("pt") or key
from mixai_automix_window import (WaveformWidget, DeckPanel, MixerPanel,
                                  RhythmWave, COL_A, COL_B, COL_DIM,
                                  COL_ACCENT)
from mixai_automix_window import definir_idioma as _idioma_do_player

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QDir, QMimeData, QUrl
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QWidget, QLabel,
                               QPushButton, QLineEdit, QComboBox, QCheckBox,
                               QVBoxLayout, QHBoxLayout, QListWidget,
                               QListWidgetItem, QTextEdit, QMessageBox,
                               QAbstractItemView, QSizePolicy, QSpinBox,
                               QSplitter, QTreeView, QTreeWidget,
                               QTreeWidgetItem, QProgressBar)
# QFileSystemModel mudou de módulo entre versões do Qt6 (QtGui no Qt6,
# QtWidgets em algumas builds do PySide6) — importa do que existir.
try:
    from PySide6.QtGui import QFileSystemModel
except ImportError:                       # pragma: no cover
    from PySide6.QtWidgets import QFileSystemModel


def _do_app(*nomes):
    """Vai buscar nomes à aplicação ANFITRIÃ, seja ela qual for.

    PORQUÊ. Este módulo é a janela do DJ Player e precisa de coisas que vivem
    na aplicação principal: gravar na base, ordenar um set, o diálogo do Set
    Planner, a lista de música. Estava a ir buscá-las sempre ao
    `mixai_dj_autodj` — mas quando se corre o Fusion, o anfitrião é o
    `mixai_fusion`, que TEM as mesmas funções e já está carregado.

    O custo disso não era teórico: `from mixai_dj_autodj import upsert_track`
    puxa o módulo INTEIRO — 19 mil linhas, mais o librosa, o sklearn e o
    onnxruntime nos imports do topo. Ou seja, à primeira grelha gravada
    carregava-se uma segunda cópia de toda a aplicação de análise, com as suas
    constantes e os seus caminhos de base de dados. Anulava o arranque
    preguiçoso do Fusion e duplicava a memória.

    Regra: primeiro procura-se nos módulos JÁ CARREGADOS (custo zero); só se
    nenhum estiver é que se importa, e aí prefere-se o Fusion. Assim o Solo
    continua a funcionar sozinho, com o `mixai_dj_autodj` como recurso.
    """
    import importlib
    # O `mixai_dj_autodj` era o segundo candidato. Saiu a 05/09/2026:
    # esta' abandonado desde 12/08 e servia so' para o PyInstaller o
    # levar para dentro do exe. O anfitriao e' o Fusion.
    candidatos = ("mixai_fusion",)

    def _tira(m):
        vals = tuple(getattr(m, n) for n in nomes)     # AttributeError sobe
        return vals[0] if len(vals) == 1 else vals

    falha = None
    for fase in (0, 1):
        for nome_mod in candidatos:
            m = sys.modules.get(nome_mod)
            if m is None:
                if fase == 0:
                    continue                    # 1ª volta: só o que já existe
                try:
                    m = importlib.import_module(nome_mod)
                except Exception as e:
                    falha = e
                    continue
            try:
                return _tira(m)
            except AttributeError as e:
                falha = e
    raise ImportError(f"{'/'.join(nomes)} não existe no mixai_fusion nem no "
                      f"mixai_dj_autodj ({falha})")


def _norm(p):
    return os.path.normpath(p) if p else p


def _info_of(md, p):
    return md.get(_norm(p)) or md.get(p) or {}


# ── Mixai Fusion V.5: grelha calculada LAZY ao carregar no player ────────────
# A análise de pasta é rápida e NÃO corre o modelo de grelha "Beat This!"
# (ver mixai_dj_autodj.FUSION_GRID_ON_LOAD). A grelha do modelo é calculada
# aqui, uma vez por faixa, no momento em que ela entra no player — e gravada
# na BD (upsert_track) para não repetir. Assim uma pasta de 200 faixas
# analisa em minutos e só as faixas realmente tocadas pagam o custo do modelo.
RAMPA_MIN_S = 0.005      # 5 ms — chao, para uma rajada de eventos no mesmo ms
RAMPA_MAX_S = 0.050      # 50 ms — o valor fixo que havia antes; nunca pior

# ── INTERRUPTOR (24/08/2026) ─────────────────────────────────────────────
# Ver a nota grande no `mixai_engine.py`. Esta e' a terceira das tres
# alteracoes de 23/08 e desliga-se com MIXAI_RAMPA_FADER=0 (ou de uma vez
# com MIXAI_SOM_ANTIGO=1), voltando aos 50 ms fixos que havia antes.
#
# NOTA HONESTA: esta so' toca no CROSSFADER A MAO. O `rampa_adaptativa` e'
# chamado uma unica vez, no `_xf_moved`, que e' o slider. O automix nao
# passa por aqui. Portanto se o som so' falha em automix, esta nao pode ser
# a culpada — mas fica com interruptor na mesma, para nao ser preciso
# acreditar em mim.
def _interruptor_solo(nome, por_omissao):
    v = str(os.environ.get(nome, "")).strip().lower()
    if v in ("0", "nao", "não", "false", "off"):
        return False
    if v in ("1", "sim", "true", "on"):
        return True
    return bool(por_omissao)


_SOM_ANTIGO = _interruptor_solo("MIXAI_SOM_ANTIGO", False)
if not _interruptor_solo("MIXAI_RAMPA_FADER", not _SOM_ANTIGO):
    RAMPA_MIN_S = RAMPA_MAX_S = 0.050


def rampa_adaptativa(dt_s, sr, minimo=RAMPA_MIN_S, maximo=RAMPA_MAX_S):
    """Quantas amostras deve durar a rampa do fader, dado o intervalo desde
    a ultima mexida.

    PORQUE NAO UM NUMERO FIXO (23/08/2026). O crossfader usava 50 ms sempre.
    Isso tem dois problemas ao mesmo tempo, e sao opostos:

      • O slider dispara a cada 8-16 ms enquanto se arrasta. Com 50 ms de
        rampa, o ganho NUNCA chega ao destino antes de o destino mudar --
        anda sempre 50 ms atras do dedo. Somado aos 43 ms da placa, e' o
        que se sente como fader mole.

      • Encurtar para um numero pequeno fixo tambem nao serve: entre duas
        actualizacoes o ganho fica parado, e o que se ouve e' uma ESCADA.
        Medido no pior caso (cortar no pico de uma onda de 50 Hz, que e' o
        bombo): instantaneo da' -43,6 dB de clique, 5 ms da' -55,7 dB e
        50 ms da' -73,5 dB. Nos graves o degrau ouve-se mesmo.

    A rampa certa e' do TAMANHO DO INTERVALO entre actualizacoes: assim o
    ganho chega ao destino exactamente quando chega o valor seguinte. Fica
    continuo, sem escada, e sem atraso.

    E corrige-se sozinha na direccao certa: um arrasto rapido traz
    intervalos curtos e saltos pequenos (rampa curta, clique nenhum); um
    clique numa posicao nova depois de uma pausa traz um intervalo enorme e
    um salto grande (rampa no tecto, que e' o que um salto grande precisa).

    `dt_s` a None ou <= 0 (primeira mexida) devolve o tecto, que e' o mais
    seguro.
    """
    try:
        sr = int(sr)
    except (TypeError, ValueError):
        return 0
    if sr <= 0:
        return 0
    try:
        dt = float(dt_s)
    except (TypeError, ValueError):
        dt = -1.0
    if not (dt > 0.0):
        dt = float(maximo)
    dt = max(float(minimo), min(float(maximo), dt))
    return max(1, int(dt * sr))


def aceitar_refinamento(conf_novo, conf_antigo, limiar=None):
    """A estrutura recalculada com a grelha do modelo deve substituir a antiga?

    (23/08/2026) Antes disto, substituia SEMPRE. A confianca anterior era
    lida aqui ao lado, mas so' para aparecer no log -- ninguem decidia nada
    com ela. Visto no log do utilizador, numa faixa real:

        [Estrutura] refinada com a grelha do modelo: ... 1 sec · conf 0.94 -> 0.00

    Abaixo do CONFIANCA_ESTRUTURA_MINIMA a estrutura e' IGNORADA por quem a
    consome, e os pontos de mistura caem na heuristica por duracao. Trocar
    uma estrutura utilizavel por uma que ninguem vai usar e' perda pura --
    e fica GRAVADA na base a seguir, portanto o estrago acumula-se a cada
    corrida do automix.

    A REGRA E' SO' ESTA: recusa-se quando a nova nao chega ao limiar E a
    antiga chegava. Uma descida pequena (0.94 -> 0.91) e' aceite de
    propostio: a grelha do modelo continua melhor ancorada mesmo quando a
    metrica desce um pouco, e e' esse o motivo de o refinamento existir.
    Recusar toda e qualquer descida anulava-o.
    """
    try:
        conf_novo = float(conf_novo or 0.0)
        conf_antigo = float(conf_antigo or 0.0)
    except (TypeError, ValueError):
        return True
    if limiar is None:
        try:
            from mixai_core import CONFIANCA_ESTRUTURA_MINIMA as _lim
            limiar = float(_lim)
        except Exception:
            limiar = 0.35
    return not (conf_novo < limiar <= conf_antigo)


def _grelha_fiavel(info) -> bool:
    """A grelha JÁ guardada serve, ou tem de ser recalculada pelo modelo?

    É a regra do _ensure_grid_beats extraída para poder ser consultada SEM
    fazer trabalho nenhum — o pré-cálculo em segundo plano precisa de saber
    depressa quais as faixas que faltam, e correr o modelo só para descobrir
    que não era preciso derrotava o objectivo.

    Confia-se em: correcção MANUAL (intocável) ou grelha do MODELO numa versão
    igual ou superior à actual. Tudo o resto é descartado — validar o andamento
    não valida a FASE, e é a fase que estraga a mistura.
    """
    info = info or {}
    beats = info.get("beats") or None
    if not beats or len(beats) < 8:
        return False
    if info.get("grid_manual"):
        return True
    if not info.get("_grid_engine"):
        return False
    try:
        from mixai_beatthis import GRID_VERSION as _GV
    except Exception:
        _GV = 1
    try:
        return int(info.get("_grid_ver") or 1) >= _GV
    except (TypeError, ValueError):
        return False


def _e_valor_musical(bpm) -> bool:
    """O BPM já está num valor de produção (inteiro ou meio-inteiro)?"""
    try:
        b = float(bpm)
    except (TypeError, ValueError):
        return False
    if b <= 0:
        return False
    return (abs(b - round(b)) < 0.005
            or abs(b * 2.0 - round(b * 2.0)) < 0.005)


def _migrar_grelha(md, path, info, persist=True):
    """Sobe uma grelha antiga à versão actual SEM voltar a correr o modelo.

    O QUE MUDOU, E PORQUE NÃO PRECISA DO MODELO. Da v2 para cá, as correcções
    foram todas na AFINAÇÃO pelos kicks — o arredondamento do BPM ao valor
    musical, o detector de bombos, o chão de qualidade. Nenhuma delas mexe nas
    batidas que o modelo detectou, que são a parte cara (15-25 s por faixa) e
    continuam boas. O que é preciso refazer é só a afinação, e essa custa a
    descodificação a 11 kHz mais uns milissegundos de contas: 2-4 s.

    A alternativa era invalidar as 812 faixas da base e mandar o modelo correr
    outra vez em todas — cinco horas de trabalho para refazer o que já estava
    certo. Não faz sentido nenhum.

    Devolve as batidas se migrou, ou None se a faixa tiver mesmo de voltar ao
    modelo (sem BPM, sem batidas, ou grelha curta de mais para se aproveitar).
    """
    try:
        bpm = float(info.get("bpm") or 0)
    except (TypeError, ValueError):
        return None
    beats = info.get("beats") or []
    if bpm <= 0 or len(beats) < 8:
        return None

    def _gravar(entry):
        try:
            from mixai_beatthis import GRID_VERSION as _GV
        except Exception:
            _GV = 1
        entry["_grid_ver"] = int(_GV)
        key = _norm(path)
        md[key] = entry
        if persist:
            try:
                _do_app("upsert_track")(key, entry)
            except Exception as e:
                print(f"[Fusion] não gravou a migração ({path}): {e}")

    entry = dict(info)

    # NOTA (31/07/2026): havia aqui um atalho — "se o BPM já é redondo, carimba
    # a versão e não abras o ficheiro". Fazia sentido quando a única diferença
    # entre versões era o arredondamento. Deixou de fazer: a v4 mudou também o
    # detector de bombos e, com ele, a FASE do «1» — que é o que estraga uma
    # mistura. Medido nas faixas de referência, o erro de fase mediano caiu de
    # 0.033 para 0.013 de batida, e faixas com o BPM já certo (a Kylie, a
    # 126.00) estavam entre as que melhoraram. Saltá-las por terem o BPM
    # redondo era deixar de fora metade do ganho.
    # O custo continua a ser só a descodificação a 11 kHz — o modelo não corre.

    # ── afinação pelos kicks, sem modelo ─────────────────────────────────
    try:
        import mixai_beatthis as _bt
    except Exception:
        return None
    db = _downbeat_of(info)
    try:
        y, sr = _bt.audio_para_kicks(_norm(path), sr=11025)
        b2, d2, nfo = _bt.afinar_grelha(y, sr, bpm, db)
        if nfo.get("aplicou"):
            T = 60.0 / b2
            dur = len(y) / float(sr)
            st = d2 % T
            n = max(2, min(100000, int((dur - st) / T) + 1))
            beats = [st + i * T for i in range(n)]
            entry["bpm"] = float(b2)
            entry["beats"] = beats
            cues = [c for c in (entry.get("hot_cues") or [])
                    if "downbeat" not in str(c.get("label", "")).lower()]
            cues.append({"label": "downbeat", "time": float(d2)})
            entry["hot_cues"] = cues
            print(f"[Fusion] {os.path.basename(str(path))}: "
                  f"BPM {bpm:.2f} -> {b2:.2f} (migração v2->v3, sem modelo)")
        if not entry.get("kick_in"):
            try:
                ki = _bt.entrada_do_bombo(y, sr, float(entry.get("bpm") or bpm))
                if ki is not None and ki > 1.0:
                    entry["kick_in"] = float(ki)
            except Exception:
                pass
        del y
    except Exception as e:
        print(f"[Fusion] migração v2->v3 falhou em "
              f"{os.path.basename(str(path))}: {e}")
        # falhou a medição, mas as batidas do modelo continuam boas —
        # carimba-se na mesma para não ficar a repetir isto para sempre
    _gravar(entry)
    return entry.get("beats") or beats


def _ensure_grid_beats(md, path, progress=None, persist=True):
    """Garante uma grelha do modelo para `path`. Devolve a lista de beats (s)
    ou None. Reutiliza a que já estiver na BD; senão corre o beatthis, grava
    o resultado na BD e no dict `md` em memória."""
    info = _info_of(md, path)
    beats = info.get("beats") or None
    # ── DE QUEM É ESTA GRELHA? ──────────────────────────────────────────
    # Antes aceitava-se QUALQUER grelha com >=8 beats. O problema: a maior
    # parte das grelhas na base vem do librosa.beat_track da analise antiga
    # e nao tem nada que ver com a musica — medido, a "Mazia" tem bpm=100 na
    # base e uma grelha cujo espacamento implica 136 BPM. Aceita-la fazia o
    # motor esticar o audio 1.36x para a encaixar: a faixa tocava lenta e
    # destruida.
    # Agora so se reutiliza a grelha se ela for de CONFIANCA:
    #   • correcao MANUAL tua (grid_manual)     -> intocavel
    #   • produzida pelo modelo (_grid_engine)  -> boa
    #   • coerente com o BPM da faixa (<=4%)    -> aceitavel (grelhas antigas
    #     que por acaso estao certas nao pagam re-analise)
    # Tudo o resto e descartado e o modelo corre uma vez, como pediste — e
    # fica gravado, portanto o custo e unico por faixa.
    if beats and len(beats) >= 8:
        if _grelha_fiavel(info):
            return beats                     # manual ou do modelo, actual
        if info.get("_grid_engine"):
            # É do modelo, mas de uma versão anterior da cadeia. NÃO se manda
            # logo o modelo correr outra vez: o que mudou entre versões foi a
            # AFINAÇÃO pelos kicks, e essa refaz-se sem o modelo — as batidas
            # detectadas continuam boas. Só se a migração barata não
            # der é que se paga a análise completa.
            _mig = _migrar_grelha(md, path, info, persist=persist)
            if _mig:
                return _mig
            print(f"[Fusion] grelha de versão antiga em "
                  f"{os.path.basename(str(path))} -> a reprocessar")
            beats = None
        else:
            # REGRA APERTADA (28/07/2026). A versão anterior também reutilizava
            # grelhas antigas cujo BPM implícito batesse com o da faixa (±4%).
            # Prova em contrário, do próprio utilizador: seleccionou a playlist
            # toda, mandou "Auto-detetar" (que corre o MODELO) e TODAS as
            # transições ficaram perfeitas — nas mesmas faixas cuja grelha
            # antiga passava no teste dos 4%. O BPM estava certo; o «1» é que
            # não. As DISCO GURLS são o exemplo: 124/126 exactos, downbeat
            # errado. Validar o andamento não valida a FASE, e é a fase que
            # estraga a mistura. Portanto: só se confia em grelhas MANUAIS ou
            # do MODELO. O custo é uma passagem do modelo por faixa, uma única
            # vez, gravada na BD — que é o que já se fazia à mão com o lote.
            print(f"[Fusion] grelha sem proveniência em "
                  f"{os.path.basename(str(path))} -> a recalcular com o modelo")
            beats = None
    try:
        import mixai_beatthis as _bt
    except Exception:
        return beats
    try:
        if not _bt.available():
            return beats
    except Exception:
        return beats
    # UMA VEZ POR FAIXA E POR SESSAO (14/08/2026).
    #
    # Visto no log: «America - You Can Do Magic» passou pelo modelo DUAS
    # vezes seguidas, 25,2 s e 23,8 s, e a segunda nao mudou nada
    # («conf 0.88 -> 0.88»). Sao 24 s de CPU deitados fora numa maquina de
    # dois nucleos, com musica a tocar — e apareceu um `output underflow`
    # nesse intervalo.
    #
    # A razao e' que cada _PrepThread leva o SEU instantaneo do music_data.
    # Quando se prepara o motor outra vez (playlist nova, novo Iniciar), o
    # instantaneo novo ainda nao tem a proveniencia que a corrida anterior
    # gravou, e a faixa parece por fazer. Havia ate' duas threads _bg_grids
    # vivas ao mesmo tempo, cada uma com a sua copia.
    #
    # Este registo e' do PROCESSO, nao do instantaneo: uma faixa que ja
    # passou pelo modelo nesta sessao nao volta a passar, venha o pedido de
    # onde vier. E' memoria a serio (um caminho por faixa) e resolve o caso
    # geral, em vez de remendar cada chamador.
    _chave = _norm(str(path))
    with _GRIDS_LOCK:
        if _chave in _GRIDS_FEITAS:
            # Devolve a grelha QUE JA SE CALCULOU, nao a antiga. O
            # instantaneo do music_data deste chamador pode ser anterior a
            # gravacao na BD, e sem isto a segunda preparacao ficava com a
            # grelha velha — evitava-se o gasto mas perdia-se o resultado.
            return _GRIDS_FEITAS[_chave] or beats
        _GRIDS_FEITAS[_chave] = None      # reserva: ninguem mais comeca esta
    if progress:
        try:
            progress(os.path.basename(str(path)))
        except Exception:
            pass
    try:
        _r = _bt.detect_file(_norm(path))
    except Exception as e:
        print(f"[Fusion] grelha (beatthis) falhou em {path}: {e}")
        return beats
    if not (_r and _r.get("beats") and len(_r["beats"]) >= 8):
        return beats
    new_beats = [float(t) for t in _r["beats"]]
    new_db = float(_r.get("downbeat") or 0.0)
    new_bpm = float(_r.get("bpm") or 0.0)
    entry_kick_in = None
    entry_grid_acerto = None     # fraccao de kicks que caem na grelha (0..1)
    _audio_kicks = None          # guardado para o refinamento da estrutura
    # ── AFINAÇÃO PELOS KICKS (v5.2): TEMPO primeiro, FASE depois ──────────
    # O BPM do modelo sai por vezes "quase certo" e o quase acumula: 1.3% de
    # erro são 4.8 s de deriva em 6 min — a grelha começa certa e acaba noutro
    # sítio. Aqui procura-se o BPM que explica os kicks ao longo da faixa
    # INTEIRA e só depois se encosta a fase ao bombo.
    # Só se aplica se o acerto aos kicks SUBIR — no pior caso não faz nada.
    if new_bpm > 0:
        try:
            # REAPROVEITA o áudio que o detect_file acabou de descodificar
            # (era um segundo librosa.load do mesmo mp3: 2-5 s por faixa,
            # pagos duas vezes no arranque do automix).
            _yk, _sk = _bt.audio_para_kicks(_norm(path), sr=11025)
            _b2, _d2, _nfo = _bt.afinar_grelha(_yk, _sk, new_bpm, new_db)
            # ACERTO AOS KICKS — guardado, nao so' escrito no log.
            # E' a unica medida objectiva de quao boa e' a grelha, e estava a
            # ser deitada fora. Sem ela, nada a jusante sabe distinguir uma
            # grelha com 85% de acerto de uma com 34% — e as de 34% sao as
            # que estragam as transicoes. Ver analisar_confianca no mixai_core.
            try:
                _ac = float(_nfo.get("acerto1", 0.0) or 0.0)
                if _ac <= 0:
                    _ac = float(_nfo.get("acerto0", 0.0) or 0.0)
                if _ac > 0:
                    entry_grid_acerto = _ac
            except (TypeError, ValueError):
                pass
            if _nfo.get("aplicou"):
                new_bpm, new_db = _b2, _d2
                # grelha constante regenerada com o BPM afinado
                _T = 60.0 / new_bpm
                _dur = len(_yk) / float(_sk)
                _st = new_db % _T
                _n = max(2, min(100000, int((_dur - _st) / _T) + 1))
                new_beats = [_st + _i * _T for _i in range(_n)]
            # PONTO DE ENTRADA para a mistura: onde o bombo entra a sério.
            # Guardado na BD para o AutoDJ saltar a intro em vez de arrancar
            # a faixa do princípio (nas afro house a intro chega a 1 min).
            try:
                _ki = _bt.entrada_do_bombo(_yk, _sk, new_bpm)
                if _ki is not None and _ki > 1.0:
                    entry_kick_in = float(_ki)
            except Exception:
                pass
            # NAO se larga o audio ja: o refinamento da estrutura, mais
            # abaixo, reaproveita-o. Era o terceiro librosa.load do mesmo mp3.
            _audio_kicks = (_yk, _sk)
        except Exception as _e_af:
            print(f"[Grelha] afinação ignorada em "
                  f"{os.path.basename(str(path))}: {_e_af}")
    # Atualiza o dict em memória (na chave que existir; senão normalizada).
    key = _norm(path) if _norm(path) in md else (path if path in md else _norm(path))
    entry = md.get(key)
    if not isinstance(entry, dict):
        entry = dict(info) if isinstance(info, dict) else {}
    entry["beats"] = new_beats
    if new_bpm > 0:
        entry["bpm"] = new_bpm
    if new_db > 0:
        # downbeat guardado como hot cue "downbeat" (convenção do projeto)
        cues = [c for c in (entry.get("hot_cues") or [])
                if "downbeat" not in str(c.get("label", "")).lower()]
        cues.append({"label": "downbeat", "time": new_db})
        entry["hot_cues"] = cues
    entry["_grid_engine"] = "beatthis"
    try:
        entry["_grid_ver"] = int(getattr(_bt, "GRID_VERSION", 1))
    except Exception:
        entry["_grid_ver"] = 1
    if entry_kick_in is not None:
        entry["kick_in"] = entry_kick_in
    if entry_grid_acerto is not None:
        entry["_grid_acerto"] = round(float(entry_grid_acerto), 3)

    # ── REFINAR A ESTRUTURA COM A GRELHA BOA (12/08/2026) ────────────────
    # A estrutura calculada na analise da pasta usa grelha propria — o
    # mixai_beatgrid (heuristica) ou o librosa. As fronteiras das seccoes sao
    # multiplos de frase ancorados no downbeat, por isso um downbeat no
    # contratempo desloca a estrutura inteira meia frase, e com ela os pontos
    # de mistura.
    #
    # Agora que o BeatThis produziu a grelha certa, recalcula-se com ela.
    # Custo: quase nenhum. O audio ja esta descodificado (do calculo dos
    # kicks) e as batidas ja existem — nao ha segundo load nem segunda
    # deteccao de batidas, que era o caro.
    #
    # Nas faixas do utilizador o BeatThis levou o acerto aos kicks de 27%
    # para 72% e de 25% para 87%: nessas, a estrutura anterior estava
    # simplesmente no sitio errado.
    if _audio_kicks is not None and len(new_beats) >= 64:
        try:
            import mixai_estrutura
            _yk2, _sk2 = _audio_kicks
            _est = mixai_estrutura.detectar(
                _yk2, _sk2,
                beats=new_beats,
                downbeat=(new_db if new_db > 0 else None),
                bpm=(new_bpm if new_bpm > 0 else None),
            )
            _secs = _est.get("sections") or []
            if _secs:
                _conf_ant = 0.0
                try:
                    _conf_ant = float((entry.get("estrutura_v2") or {})
                                      .get("confianca", 0.0) or 0.0)
                except (TypeError, ValueError):
                    _conf_ant = 0.0
                _conf = float(_est.get("confianca", 0.0) or 0.0)

                # ── NAO TROCAR UMA ESTRUTURA BOA POR UMA INUTIL ──────────
                # (23/08/2026) A confianca anterior ja' era lida aqui, mas
                # so' para a IMPRIMIR: o resultado novo entrava sempre.
                #
                # Visto no log do utilizador, numa faixa real:
                #     conf 0.94 -> 0.00   com 1 seccao so'
                #
                # Abaixo de CONFIANCA_ESTRUTURA_MINIMA a estrutura e'
                # IGNORADA por quem a consome, e os pontos de mistura caem
                # na heuristica por duracao. Ou seja: substituir uma
                # estrutura utilizavel por uma que ninguem vai usar e' perda
                # pura -- e fica GRAVADA na base pelo upsert_track a seguir,
                # portanto o estrago acumula-se a cada corrida do automix.
                #
                # A regra e' so' esta: se a nova nao chega ao limiar e a
                # antiga chegava, fica a antiga. Uma descida pequena
                # (0.94 -> 0.91) passa, porque a grelha do modelo continua
                # melhor ancorada mesmo quando a metrica desce um pouco --
                # e' esse o motivo de existir este refinamento.
                if not aceitar_refinamento(_conf, _conf_ant):
                    print(f"[Estrutura] refinamento DESCARTADO em "
                          f"{os.path.basename(str(path))[:40]} · "
                          f"conf {_conf_ant:.2f} -> {_conf:.2f} "
                          f"({len(_secs)} sec) — fica a da analise")
                    _secs = None

            if _secs:
                entry["sections_v2"] = _secs
                entry["estrutura_v2"] = {
                    "confianca": _conf,
                    "qualidade": float(_est.get("qualidade", 0.0) or 0.0),
                    "bpm": float(_est.get("bpm", 0.0) or 0.0),
                    "downbeat": float(_est.get("downbeat", 0.0) or 0.0),
                    "drops": _est.get("drops") or [],
                    "breakdowns": _est.get("breakdowns") or [],
                    "fonte": "beatthis",     # <- distingue da da analise
                }
                print(f"[Estrutura] refinada com a grelha do modelo: "
                      f"{os.path.basename(str(path))[:40]} · {len(_secs)} sec "
                      f"· conf {_conf_ant:.2f} -> {_conf:.2f}")
        except Exception as _e_est:
            print(f"[Estrutura] refinamento falhou em "
                  f"{os.path.basename(str(path))}: {_e_est}")

    try:
        del _audio_kicks
    except Exception:
        pass

    md[key] = entry
    if persist:
        try:
            _do_app("upsert_track")(key, entry)
        except Exception as e:
            print(f"[Fusion] não gravou a grelha na BD ({path}): {e}")
    with _GRIDS_LOCK:
        _GRIDS_FEITAS[_chave] = new_beats
    return new_beats


def _downbeat_of(info):
    for cue in (info.get("hot_cues") or []):
        try:
            if "downbeat" in str(cue.get("label", "")).lower():
                return float(cue.get("time", 0.0))
        except Exception:
            continue
    return 0.0


def _sections_of(info):
    """As seccoes que vao no TrackSpec — a estrutura BOA, se existir.

    O ELO QUE FALTAVA PARA O AGENTE CRIATIVO (13/08/2026)
    -----------------------------------------------------
    O `_CreativeFX._build_plan` (o agente de efeitos do player) le
    `spec.sections` para saber onde estao os build-ups, os drops e os
    breakdowns. Esse campo era preenchido com `info["sections"]` — o campo
    ANTIGO, que em 810 faixas medidas traz sempre uma unica seccao 'Intro' a
    cobrir a faixa toda.

    Consequencia: o agente nunca encontrava um build nem um breakdown, o
    plano saia vazio, e caia na rotacao por intervalo de batidas — flanger,
    filter sweep, echo, sempre no mesmo compasso, independentemente da
    musica. Era isso que se ouvia.

    O `sections_v2` existe agora em toda a biblioteca e traz Intro,
    Build-up/Chorus, Breakdown/Bridge, Verse/Main Body e Outro — exactamente
    o vocabulario que o `_build_plan` procura. So' faltava entregar-lho.

    Devolve o v2 quando a confianca chega; senao o campo antigo, para nao
    piorar nada nas bases que ainda nao foram reanalisadas.
    """
    if not isinstance(info, dict):
        return None
    try:
        from mixai_core import estrutura_fiavel
        if estrutura_fiavel(info):
            secs = info.get("sections_v2") or None
            if secs:
                return secs
    except Exception:
        pass
    return info.get("sections") or None


def _mix_out_of(info):
    """Início do outro (em s), para o TrackSpec que vai para o motor.

    UMA CONTA SÓ, E É A DO `mixai_pontos` (20/09/2026)
    ---------------------------------------------------
    Isto era a TERCEIRA implementação do ponto de saída — havia esta, a do
    `mixai_fusion.compute_mix_points` e a do `mixai_pontos.calcular`. E era
    justamente esta, a que ninguém vigiava, a única que o DJ Player usa: o
    valor daqui vai direito ao `TrackSpec` que o motor recebe.

    Duas consequências, ambas medidas nas 763 faixas da biblioteca:

      • NÃO LIA OS PONTOS GUARDADOS. O editor de grelhas grava a correcção
        do DJ (`mixai_pontos.marcar_manual`) e o `mixai_pontos` recusa-se a
        escrevê-la por cima numa reanálise — toda essa promessa morria aqui,
        porque o player nunca perguntava. Relatado assim: «no editor de
        grids não muda a zona de saída». Não mudava mesmo.

      • NÃO TINHA O TRAVÃO DAS 36 BATIDAS, e caía na heurística
        `max(duração − 32, duração × 0.85)`. O `0.85` ganha em qualquer
        faixa com mais de 3:33, e numa de 7,6 min pôs a saída a 109,7 s do
        fim. Vinte faixas saíam a mais de um minuto do fim; a conta certa
        põe-nas todas aos ~32 s. Relatado assim: «uma transição que ocorreu
        a mais de 1 minuto do final».

    O `teste_pontos_equivalentes.py` existe para impedir exactamente isto —
    mas comparava DUAS contas e esta era a terceira. Passou a comparar as
    três.

    A FRASE FICA COMO ESTAVA. Este caminho encostava à frase de quatro
    compassos (o `FRASE_COMPASSOS` do mixai_core) e o `mixai_pontos` encosta
    ao compasso. Delegar às cegas mudava o alinhamento do player sem
    ninguém pedir, o que é uma decisão de ouvido e não de arrumação — por
    isso passa-se o valor explicitamente e o som do alinhamento não muda.
    """
    if not isinstance(info, dict):
        return None
    try:
        duration = float(info.get("duration", 0.0) or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        return None

    try:
        import mixai_pontos as _mp
    except Exception as _e_mp:
        # Sem o módulo não há como calcular como deve ser. Fica a heurística
        # antiga, com aviso — é melhor tocar mal do que não tocar.
        print(f"[Fusion] mixai_pontos indisponivel ({_e_mp}); "
              f"ponto de saida pela heuristica")
        return float(max(duration - 32.0, duration * 0.85))

    # A frase a que este caminho sempre encostou.
    try:
        from mixai_core import FRASE_ALINHADA, FRASE_COMPASSOS
        _frase = FRASE_COMPASSOS if FRASE_ALINHADA else 0
    except Exception:
        _frase = 0

    # 1. O QUE O DJ CORRIGIU À MÃO manda em tudo o resto.
    try:
        _guardado = _mp.ler(info, duracao=duration)
    except Exception:
        _guardado = None
    if _guardado is not None:
        try:
            _mo = float(_guardado["mix_out"])
            if 0 < _mo < duration:
                if _guardado.get("fonte") == _mp.FONTE_MANUAL:
                    print(f"[Fusion] ponto de saida MANUAL: {_mo:.1f}s")
                return _mo
        except (KeyError, TypeError, ValueError):
            pass

    # 2. Senão, a conta única — estrutura, heurística, travão das 36
    #    batidas e encosto à grelha, tudo lá dentro.
    try:
        mo = float(_mp.calcular(info, frase_compassos=_frase)[1])
    except Exception as _e_calc:
        print(f"[Fusion] falhou o calculo dos pontos ({_e_calc}); heuristica")
        mo = float(max(duration - 32.0, duration * 0.85))

    # TRAVAO: NUNCA SAIR ANTES DE METADE DA FAIXA (15/08/2026).
    #
    # Relatado: "corta as musicas, so' toca aproximadamente 1 minuto".
    # Numa faixa que acaba em fade longo o detector de batidas nao encontra
    # batidas na cauda, a GRELHA acaba muito antes da faixa, e o encosto a'
    # ultima batida leva o ponto atras dela.
    #
    # O QUE MUDOU AQUI (20/09/2026): o recurso era `duration * 0.85` — a
    # mesma conta que punha a saida a 109 s do fim. Um travao cuja saida de
    # emergencia e' a causa do problema nao e' um travao. Passa a recuar
    # para a folga minima, que e' o que o resto do sistema ja' usa.
    try:
        if float(mo) < duration * 0.50:
            _seguro = duration - 32.0
            print(f"[Fusion] ponto de saida em {float(mo):.0f}s numa faixa de "
                  f"{duration:.0f}s — cedo de mais (grelha curta?); "
                  f"a usar {_seguro:.0f}s")
            mo = _seguro
    except (TypeError, ValueError):
        pass

    return float(mo)


# Threads mandadas parar que ainda não acabaram. Se a última referência
# Python a uma QThread viva desaparecer, o Qt aborta o processo ("QThread:
# Destroyed while thread is still running") — no Windows isso aparece como
# excepção win32 com o depurador Just-In-Time, não como erro de Python.
# Ficam aqui até morrerem sozinhas.
_ORFAOS = []




def _largar_thread(th):
    """Larga a referência a uma QThread SEM arriscar o aborto do Qt.

    ISTO É A CAUSA DO DEPURADOR AO GERAR UMA PLAYLIST.

    Escrever `self._gen_thread = None` dentro do callback de resultado parece
    arrumação inofensiva, mas os sinais de resultado são emitidos DE DENTRO do
    run(): quando o callback corre, a thread ainda não terminou. Se aquela era
    a última referência Python — e era, porque `self._gen_thread = t` é a
    única —, o Qt destrói uma QThread a correr e chama qFatal(). No Windows
    qFatal() é abort(), e o abort() é que abre o depurador Just-In-Time. Nunca
    aparece como erro de Python; só deixa "[Qt FATAL] QThread: Destroyed while
    thread is still running" no mixai_crash.log.

    Aqui a referência sobrevive ao callback e só se larga quando a thread já
    não está a correr. A limpeza é feita à entrada, por isso não se acumula.
    """
    if th is None:
        return
    try:
        _ORFAOS[:] = [t for t in _ORFAOS if t.isRunning()]
        if not th.isRunning():
            return
    except Exception:
        pass
    _ORFAOS.append(th)


# ═══════════════════════════════════════════════════════════════════════════
# VIGIA DA INTERFACE — diz O QUE a bloqueou, não só que bloqueou.
# ---------------------------------------------------------------------------
# O detector anterior media o intervalo entre dois disparos do temporizador e
# dizia "parou 0.75s". Serviu para eliminar a carga da faixa seguinte, mas não
# chega: quando a resposta é "(sem carga a decorrer)" ficamos ao mesmo ponto.
#
# Este vigia corre numa thread própria e olha para o RELÓGIO DE PULSO que o
# _tick actualiza. Quando ele fica parado, vai buscar a pilha de chamadas da
# thread principal com sys._current_frames() e escreve-a — ou seja, apanha a
# função que está a segurar a interface NO MOMENTO em que a segura, em vez de
# se descobrir depois que houve um buraco. Custo: uma thread a acordar 10
# vezes por segundo para comparar dois números.
# ── O DIAGNOSTICO PASSA A SER OPCIONAL (24/08/2026) ─────────────────────
#
# ISTO E' UM ERRO MEU, E O REGISTO DO UTILIZADOR APANHOU-O.
#
# A paragem de 8,03 s tem a thread principal aqui:
#       mixai_automix_window.py:601 em paintEvent
# A linha 601 nao desenha nada. E' o `print` do meu proprio diagnostico.
#
# Numa consola do Windows com `chcp 65001`, escrever uma linha longa com
# caracteres fora do ASCII (·, ✔, ⚠, →) e' sincrono e caro; se o utilizador
# clicar dentro da janela (QuickEdit), BLOQUEIA ate' carregar numa tecla. E
# o VigiaUI despeja pilhas de 10 a 25 linhas de cada vez, na mesma consola,
# a partir de outra thread — a principal fica a espera do mesmo handle.
#
# Pior: isto realimenta-se. Uma pintura passa dos 50 ms -> escreve-se uma
# linha -> a escrita custa tempo -> a pintura seguinte tambem passa dos
# 50 ms -> outra linha. Sao as sete linhas seguidas de `[UI] paintEvent`
# no registo, e e' por isso que o utilizador diz "esta cada vez pior": eu
# fui acrescentando instrumentacao a um caminho quente sem contar o que a
# propria instrumentacao custa.
#
# A medicao continua toda escrita e disponivel. Passa e' a estar DESLIGADA
# por omissao. Liga-se com a variavel de ambiente MIXAI_DIAG=1, ou pelo
# "Testar Fusion com Diagnostico.bat".
#
# O que NAO se desliga: as linhas da almofada e dos cortes de som. Essas
# sao poucas, sao raras, e sao o que interessa ouvir.
DIAGNOSTICO_UI = str(os.environ.get("MIXAI_DIAG", "")).strip().lower() \
    in ("1", "sim", "true", "on")

_PULSO_UI = [0.0]


class _VigiaUI(threading.Thread):
    def __init__(self, limite=0.35):
        super().__init__(daemon=True, name="vigia-ui")
        self.limite = float(limite)
        self._parar = False
        self._tid_principal = threading.main_thread().ident

    def parar(self):
        self._parar = True
        # Quem escreve o pulso e o _tick DESTA janela. Sem esta linha, ao
        # fechar a janela o pulso ficava congelado no ultimo valor e o vigia
        # passava a acusar "interface parada ha N segundos" com N sempre a
        # crescer — falso alarme, e dos que fazem perder tempo a procurar um
        # bloqueio que nao existe.
        _PULSO_UI[0] = 0.0

    def run(self):
        import sys as _sys
        import traceback as _tb

        def _pilha(frame, fundo=14):
            """Pilha de `frame`, do mais antigo para o mais recente, SEM ler o
            código-fonte.

            O traceback.extract_stack() faz lookup_lines=True: para cada frame
            vai ao linecache buscar a linha de código, o que em ficheiros
            grandes (mixai_fusion.py tem ~19 mil linhas) significa abrir e
            tokenizar o ficheiro — com o GIL na mão. Um vigia que existe para
            medir bloqueios da interface não pode ser ele próprio a causar
            centenas de ms de bloqueio, e ainda por cima a atribuí-los à thread
            que estava a observar. Nunca usamos as linhas de código, só
            ficheiro/linha/função, por isso lookup_lines=False é de graça.
            """
            p = _tb.StackSummary.extract(_tb.walk_stack(frame),
                                         limit=fundo, lookup_lines=False)
            p.reverse()
            return p

        def _amostra(n, parado):
            """Uma fotografia da thread principal (e das outras, se ela não
            tiver pilha Python)."""
            frame = _sys._current_frames().get(self._tid_principal)
            if frame is None:
                return
            # 14 frames e não 6: com 6 via-se o fundo da chamada
            # (linecache, tokenize, inspect.getsource) mas não QUEM a
            # tinha pedido — e é o pedinte que interessa. Bibliotecas
            # como o numba/librosa metem várias camadas pelo meio.
            pilha = _pilha(frame)
            linhas = [f"      {os.path.basename(f.filename)}:{f.lineno} "
                      f"em {f.name}" for f in pilha]
            print(f"[VigiaUI] amostra {n} · parada há {parado:.2f}s. "
                  f"A thread principal está em:\n" + "\n".join(linhas))

            # Quando a thread principal so mostra "<module>", ela esta
            # dentro de codigo C do Qt e a pilha Python nao diz nada. Nesse
            # caso o culpado costuma estar NOUTRA thread — tipicamente uma
            # que segura um lock (base de dados, abertura da placa) que a
            # principal esta a tentar adquirir. Sem isto ficamos a adivinhar.
            if len(pilha) <= 2:
                nomes = {t.ident: t.name for t in threading.enumerate()}
                for tid, fr in _sys._current_frames().items():
                    if tid == self._tid_principal:
                        continue
                    try:
                        p2 = _pilha(fr, fundo=4)
                        topo = [f"        "
                                f"{os.path.basename(f.filename)}:{f.lineno}"
                                f" em {f.name}" for f in p2[-4:]]
                        print(f"      · thread "
                              f"{nomes.get(tid, tid)}:\n"
                              + "\n".join(topo))
                    except Exception:
                        pass

        def _assinatura():
            """Identidade da paragem: onde esta a thread principal.

            Serve para nao repetir o mesmo relatorio dezenas de vezes.
            """
            try:
                fr = _sys._current_frames().get(self._tid_principal)
                if fr is None:
                    return None
                return tuple((f.filename, f.lineno) for f in _pilha(fr))
            except Exception:
                return None

        # ── ANTI-INUNDACAO (13/08/2026) ───────────────────────────────────
        # Com um dialogo MODAL aberto (o editor de Beatgrid, por exemplo) o
        # tick da janela de tras corre devagar — 0,2 a 0,3 s entre pulsos. O
        # vigia via isso como paragem, e reportava DE NOVO a cada pulso: umas
        # quatro vezes por segundo, seis linhas de cada vez.
        #
        # Isso deixa de ser diagnostico e passa a ser a causa: escrever nessa
        # cadencia numa consola do Windows e' bloqueante e rouba tempo ao
        # motor. Medido pelo utilizador com o editor aberto: `stream status
        # x1: output underflow` — a placa de som ficou sem dados.
        #
        # Agora paragens no MESMO sitio sao contadas em silencio e resumidas
        # numa linha. Uma paragem nova continua a ser reportada por inteiro.
        SILENCIO_S = 15.0
        assinatura_ant = None
        repetidas = 0
        t_ultimo = 0.0

        def _resumir():
            nonlocal repetidas
            if repetidas > 0:
                print(f"[VigiaUI] (+{repetidas} paragens iguais no mesmo "
                      f"sitio, silenciadas)")
                repetidas = 0

        ja_reportado = 0.0
        while not self._parar:
            time.sleep(0.1)
            pulso = _PULSO_UI[0]
            if pulso <= 0.0:
                continue
            parado = time.monotonic() - pulso
            if parado < self.limite or pulso == ja_reportado:
                continue
            ja_reportado = pulso

            _ass = _assinatura()
            _agora = time.monotonic()
            if _ass is not None and _ass == assinatura_ant \
                    and (_agora - t_ultimo) < SILENCIO_S:
                repetidas += 1
                continue
            _resumir()
            assinatura_ant = _ass
            t_ultimo = _agora

            # AMOSTRAGEM REPETIDA, e não uma fotografia só.
            #
            # Antes tirava-se UMA pilha, no instante em que a paragem passava
            # o limiar, e o `ja_reportado` calava o resto. Numa paragem de 3 s
            # isso mostra os primeiros 0,35 s e mais nada — e se essa primeira
            # amostra calhar em código C do Qt (como calhou), ficamos sem
            # saber o que aconteceu nos 2,6 s seguintes. Agora acompanha-se a
            # paragem de meio em meio segundo até ela acabar, e no fim
            # escreve-se a duração real. Uma sequência de amostras diz se a
            # thread está SEMPRE no mesmo sítio (bloqueada num lock ou em
            # trabalho nativo) ou se vai andando (código lento nosso).
            _n = 0
            try:
                _n = 1
                _amostra(_n, parado)
                _prox = time.monotonic() + 0.5
                # o tecto de 8 amostras (~4 s) evita encher o log se a
                # interface morrer de vez em vez de recuperar
                while (not self._parar and _PULSO_UI[0] == pulso and _n < 8):
                    time.sleep(0.05)
                    if time.monotonic() < _prox:
                        continue
                    _prox = time.monotonic() + 0.5
                    _n += 1
                    _amostra(_n, time.monotonic() - pulso)
            except Exception as e:
                print(f"[VigiaUI] não consegui ler a pilha: {e}")
            print(f"[VigiaUI] fim da paragem: {time.monotonic() - pulso:.2f}s "
                  f"em {_n} amostra(s)")

        _resumir()      # o que ficou por dizer, ao sair


# ═══════════════════════════════════════════════════════════════════════════
class _GridWarmThread(QThread):
    """Calcula as grelhas da playlist ANTES de se carregar em «Iniciar».

    PORQUÊ. O modelo demora 15-25 s por faixa, e a regra de confiança (só
    grelhas manuais ou do próprio modelo) obriga a recalcular quase tudo o que
    veio da base antiga. Feito no arranque do automix, isso são 40-60 s de
    silêncio a olhar para «a calcular grelha…» — que foi exactamente o que se
    viu no log. Mas o trabalho não tem de ser feito nesse instante: entre
    gerar a playlist e carregar em Iniciar passam-se sempre segundos ou
    minutos em que a máquina está a fazer nada. É aí que isto corre.

    REGRAS: prioridade mínima; NUNCA trabalha com som a tocar (o modelo rouba
    CPU ao produtor de áudio e ouve-se o engasgo); pára à primeira ordem; e
    salta de imediato as faixas cuja grelha já é de confiança, para o custo
    ser só o das que faltam. O resultado fica gravado na base, portanto cada
    faixa paga isto UMA vez na vida.
    """
    progress = Signal(int, int, str)      # feitas, total_em_falta, nome
    done = Signal(int)                    # quantas foram calculadas

    def __init__(self, playlist, md, ha_som=None):
        super().__init__()
        self.playlist = list(playlist or [])
        self.md = md
        self._ha_som = ha_som              # callable -> bool
        self._parar = False

    def parar(self):
        self._parar = True

    def _tocando(self):
        try:
            return bool(self._ha_som and self._ha_som())
        except Exception:
            return False

    def run(self):
        try:
            import sys as _s
            if _s.platform == "win32":
                import ctypes as _ct
                _k = _ct.windll.kernel32
                _k.SetThreadPriority(_k.GetCurrentThread(), -2)   # LOWEST
        except Exception:
            pass
        # só as que faltam — a contagem mostrada tem de ser a do trabalho real
        #
        # ESTA CONTA SUBIU PARA AQUI (30/08/2026). Estava DEPOIS do arranque
        # do processo de carga, e isso explicava um sintoma que parecia nao
        # ter pes nem cabeca: com uma playlist curta (4-5 faixas) nao havia
        # corte nenhum, com 10 ou mais havia. A razao e' que numa lista curta
        # o `faltam` costuma sair VAZIO — as faixas escolhidas ja' tem grelha
        # de confianca — e a thread saia por aqui sem fazer nada. Numa lista
        # grande ha' quase sempre uma faixa por calcular, e entao a thread
        # seguia em frente.
        #
        # Se nao ha' nada a fazer, sai-se ANTES de arrancar seja o que for.
        faltam = [p for p in self.playlist
                  if not _grelha_fiavel(_info_of(self.md, p))]
        if not faltam:
            self.done.emit(0)
            return
        # ── E SO' AGORA O PROCESSO DE CARGA, COM O SOM RESPEITADO ────────
        #
        # É um interpretador Python NOVO (spawn) que importa o librosa: uns
        # bons segundos de CPU e de disco. Se ficar para o «Iniciar», esses
        # segundos somam-se ao silencio inicial — por isso continua a ser
        # arrancado aqui, que e' o ponto certo.
        #
        # O que estava errado era arranca-lo SEM OLHAR AO SOM. A regra desta
        # thread, escrita na sua propria docstring, e' «NUNCA trabalha com
        # som a tocar (o modelo rouba CPU ao produtor de audio e ouve-se o
        # engasgo)» — e a primeira coisa que ela fazia era exactamente isso,
        # e logo a seguir a playlist aparecer na janela. Era o corte que
        # sobrava depois de a almofada ja' estar bem posta.
        #
        # Agora espera pela mesma condicao que o ciclo la' em baixo espera.
        # Ninguem fica a perder: entre gerar a playlist e carregar em
        # Iniciar passam-se sempre segundos, e assim que a musica pare (ou
        # se ela nunca tiver comecado) o processo arranca na mesma.
        while not self._parar and self._tocando():
            self.msleep(1000)
        if self._parar:
            self.done.emit(0)
            return
        try:
            from mixai_engine import _LoadProc
            _LoadProc._ensure()
        except Exception as e:
            print(f"[Fusion] processo de carga não arrancou já: {e}")
        feitas = 0
        for p in faltam:
            if self._parar:
                break
            # espera enquanto houver som; verifica a paragem a cada segundo
            while not self._parar and self._tocando():
                self.msleep(1000)
            if self._parar:
                break
            # a faixa pode ter sido calculada entretanto (pelo _PrepThread)
            if _grelha_fiavel(_info_of(self.md, p)):
                continue
            try:
                self.progress.emit(feitas + 1, len(faltam),
                                   os.path.basename(str(p)))
                _ensure_grid_beats(self.md, p)
                feitas += 1
            except Exception as e:
                print(f"[Fusion] pré-grelha falhou ({p}): {e}")
        self.done.emit(feitas)


# ═══════════════════════════════════════════════════════════════════════════
class _CarregarSaidasThread(QThread):
    """Enumera as saídas de som em fundo.

    A `sd.query_devices()` obriga o PortAudio a inicializar e listar TODOS
    os host APIs do Windows (MME, DirectSound, WASAPI, WDM-KS, ASIO se
    houver) — é conhecida por ser lenta, e bateu certo com os 4.0-4.2s que
    o `[tempos] construir DJ Player` media inteiros no bloco
    "cabecalho+barra_pesquisa" (medido pelos logs dele, 20-21/09/2026):
    todos os outros blocos levavam 0.02s, só este demorava segundos — e
    era a única coisa aí a tocar em hardware. Corre aqui, fora da thread da
    interface, para a janela abrir logo; a combo de saída fica com
    "Automático" até esta thread emitir a lista real.
    """
    pronto = Signal(list)

    def run(self):
        _saidas = []
        try:
            import sounddevice as sd
            apis = sd.query_hostapis()
            for i, d in enumerate(sd.query_devices()):
                if d.get("max_output_channels", 0) >= 2:
                    api = str(apis[d["hostapi"]]["name"])
                    _saidas.append((f"{d['name']}  [{api}]", i))
        except Exception:
            pass
        self.pronto.emit(_saidas)


class _PrepThread(QThread):
    """Prepara TrackSpecs + Engine + AutoDJ (carrega/estica as 2 primeiras
    faixas) em background para a UI não congelar."""
    progress = Signal(str)
    done = Signal(object, object, float)     # engine, dj, master_bpm
    failed = Signal(str)

    def __init__(self, playlist, md, event_q, crossfade_beats=32,
                 master_bpm=None):
        super().__init__()
        self.playlist = list(playlist)
        self.md = md
        self.event_q = event_q
        self.xf_beats = int(crossfade_beats)
        self.master_bpm = master_bpm

    def run(self):
        try:
            specs, bpms = [], []
            for p in self.playlist:
                info = _info_of(self.md, p)
                try:
                    bpm = float(info.get("bpm", 0) or 0)
                except (TypeError, ValueError):
                    bpm = 0.0
                db = _downbeat_of(info)
                if not (40.0 < bpm < 300.0):
                    self.progress.emit(
                        getattr(self, "msg_bpm", "a detetar BPM: {n}…")
                        .format(n=os.path.basename(str(p))))
                    try:
                        import librosa
                        y, sr = librosa.load(p, sr=22050, mono=True, duration=90)
                        t, beats = librosa.beat.beat_track(y=y, sr=sr)
                        bpm = float(np.atleast_1d(t)[0]) or 120.0
                        while bpm < 70:  bpm *= 2
                        while bpm > 190: bpm /= 2
                        if db <= 0 and len(beats):
                            db = float(librosa.frames_to_time(beats[0], sr=sr))
                    except Exception:
                        bpm = 120.0
                bpms.append(bpm)
                _sp = TrackSpec(path=p, bpm=bpm, downbeat=db,
                                mix_out=_mix_out_of(info),
                                name=os.path.basename(str(p)),
                                sections=_sections_of(info),
                                beats=info.get("beats") or None,
                                mix_in=info.get("kick_in"))
                # Listas explicitas de drops/breakdowns para o agente de
                # efeitos. Ver _CreativeFX._build_plan.
                _sp.estrutura = info.get("estrutura_v2") or None
                specs.append(_sp)
            if self.master_bpm and float(self.master_bpm) >= 60:
                master = float(self.master_bpm)   # MASTER TEMPO manual
            else:
                master = float(np.median([b for b in bpms if b > 0])) if bpms else 124.0

            # GRELHA LAZY (Fusion): o modelo de grelha corre AGORA, ao carregar
            # a playlist — mas só as 2 PRIMEIRAS faixas de forma síncrona (as
            # que tocam já); o resto num fio em segundo plano, a corrigir cada
            # spec ANTES de a faixa ser carregada pelo AutoDJ. Assim o som
            # arranca depressa e as grids ficam prontas a tempo (cada faixa
            # dura minutos; o modelo leva segundos). Tudo gravado na BD.
            def _apply_grid(spec):
                _b = _ensure_grid_beats(
                    self.md, spec.path,
                    progress=lambda nm: self.progress.emit(
                        getattr(self, "msg_grid",
                                "a calcular grelha: {n}…").format(n=nm)))
                _inf = _info_of(self.md, spec.path)
                if _b:
                    spec.beats = _b
                _ndb = _downbeat_of(_inf)
                if _ndb:
                    spec.downbeat = float(_ndb)
                if _inf.get("kick_in"):
                    spec.mix_in = float(_inf["kick_in"])
                try:
                    _gb = float(_inf.get("bpm", 0) or 0)
                    if 40.0 < _gb < 300.0:
                        spec.bpm = _gb
                except (TypeError, ValueError):
                    pass

            # AS DUAS PRIMEIRAS EM PARALELO. Corriam uma a seguir à outra:
            # cada uma são ~15-25 s de modelo ONNX, logo o utilizador esperava
            # 30-50 s a olhar para "a calcular grelha…" antes de sair som.
            # A sessão do onnxruntime é criada com intra_op=1 (uma thread), por
            # isso uma faixa sozinha usa UM núcleo e o outro fica parado; duas
            # threads a partilhar a mesma sessão usam os dois e o tempo de
            # espera fica praticamente a metade. É seguro: as InferenceSession
            # do ORT são thread-safe para `run` e não há áudio a tocar ainda —
            # este é o único momento do programa em que os núcleos estão livres.
            _dois = specs[:2]
            if len(_dois) == 2:
                import threading as _th0
                _erros = []

                def _um(_s):
                    try:
                        _apply_grid(_s)
                    except Exception as _e:
                        _erros.append(_e)

                _t0 = _th0.Thread(target=_um, args=(_dois[1],), daemon=True)
                _t0.start()
                _um(_dois[0])
                _t0.join()
                for _e in _erros:
                    print(f"[Fusion] grelha inicial falhou: {_e}")
            else:
                for _sp in _dois:
                    _apply_grid(_sp)

            eng = Engine(master_bpm=master)
            q = self.event_q
            # ── DECISOR DO ESTILO DE TRANSICAO (12/08/2026) ──────────────
            # O motor so conhece TrackSpec; a decisao precisa do music_data
            # (energia, tom, timbre, estrutura, onsets). Por isso vive aqui e
            # entra no AutoDJ como funcao.
            _md_plano = self.md or {}

            def _plano_transicao(spec_saida, spec_entrada):
                try:
                    from mixai_core import planear_transicao
                except Exception:
                    return None
                if spec_saida is None or spec_entrada is None:
                    return None
                try:
                    _i_sai = _info_of(_md_plano, getattr(spec_saida, "path", ""))
                    _i_ent = _info_of(_md_plano, getattr(spec_entrada, "path", ""))
                except Exception:
                    return None
                if not _i_sai or not _i_ent:
                    return None
                return planear_transicao(_i_sai, _i_ent,
                                         beats_omissao=self.xf_beats)

            dj = AutoDJ(eng, crossfade_beats=self.xf_beats, snap_beats=4,
                        echo_out=True,
                        on_track_change=lambda n: q.append(("track", n)),
                        on_transition=lambda a, b: q.append(("mix", a, b)),
                        plano_fn=_plano_transicao)
            dj.set_playlist(specs)
            self.progress.emit(getattr(
                self, "msg_load", "a carregar/esticar as 2 primeiras faixas…"))
            dj.start()
            self.done.emit(eng, dj, master)

            # resto das grids em segundo plano (não bloqueia o som)
            if len(specs) > 2:
                def _bg_grids():
                    """Grelhas das faixas seguintes, EM RITMO DE SET.

                    Antes percorria a playlist inteira à velocidade máxima:
                    numa lista de 13 faixas são ~4 min de modelo ONNX a correr
                    sem parar, a começar no instante do arranque — em cima das
                    primeiras transições. Numa máquina de 2 núcleos isso rouba
                    o CPU ao produtor de áudio e ouve-se o engasgo.
                    Agora: prioridade mínima, mantém-se só 2 faixas à frente
                    do que está a tocar, e NUNCA trabalha durante um crossfade.
                    O trabalho total é o mesmo, espalhado pelo set em vez de
                    concentrado no arranque — e a análise continua a ser feita
                    só nas faixas que realmente tocam, como deve ser."""
                    import time as _tm
                    try:
                        import sys as _s
                        if _s.platform == "win32":
                            import ctypes as _ct
                            _k = _ct.windll.kernel32
                            # THREAD_PRIORITY_LOWEST = -2
                            _k.SetThreadPriority(_k.GetCurrentThread(), -2)
                    except Exception:
                        pass
                    # SO' A MAIS RECENTE TRABALHA (15/08/2026).
                    #
                    # Cada preparacao do motor criava um destes fios, e o
                    # anterior continuava vivo — vistas duas e tres threads
                    # _bg_grids ao mesmo tempo no vigia, cada uma com a sua
                    # copia da playlist antiga. Numa maquina de dois nucleos
                    # sao duas passagens do modelo ONNX a competir com o
                    # produtor de audio, e ouve-se («output underflow»).
                    #
                    # A geracao e' incrementada por quem arranca; quem tiver
                    # geracao velha desiste no proximo ciclo. Nao se mata a
                    # thread a meio de uma faixa — deixa-se acabar a que
                    # esta' a fazer, que ja' esta' paga.
                    global _BG_GRIDS_GER
                    with _GRIDS_LOCK:
                        _BG_GRIDS_GER += 1
                        _minha_ger = _BG_GRIDS_GER

                    for _k, _sp in enumerate(specs[2:], start=2):
                        if _minha_ger != _BG_GRIDS_GER:
                            print("[Fusion] grelhas em fundo: playlist nova, "
                                  "este fio desiste.")
                            return
                        # ficar no máximo 2 faixas à frente da que toca
                        for _ in range(6000):
                            try:
                                _i = int(getattr(dj, "_idx", 0) or 0)
                            except Exception:
                                _i = 0
                            if _k <= _i + 2:
                                break
                            _tm.sleep(1.0)
                        # PRIORIDADE AO ÁUDIO: não calcular grelhas com
                        # música a tocar. Numa máquina de 2 núcleos o modelo
                        # ONNX rouba CPU ao produtor e ouve-se. As grelhas
                        # podem esperar; o som não. Só trabalha com os decks
                        # parados (entre sets, ou antes de carregar Iniciar).
                        #
                        # ── A GUARDA ESTAVA A OLHAR PARA O INSTANTE ERRADO
                        #    (29/08/2026) ─────────────────────────────────
                        # Ela verificava UMA VEZ, e a seguir chamava um
                        # trabalho de 11 a 18 SEGUNDOS. Bastava um instante
                        # com os dois decks parados — antes de o utilizador
                        # carregar em Iniciar, ou a pausa que o editor de
                        # grelhas provoca — para o modelo arrancar; a música
                        # começava logo a seguir e não havia mais nada a
                        # olhar para isto até ao fim da faixa.
                        #
                        # Apanhado no log com MIXAI_DIAG=1: o vigia mostra a
                        # `Thread-9 (_bg_grids)` dentro do `_apply_grid` com
                        # o produtor preso no `lfilter` do EQ, e treze
                        # segundos seguidos de «o produtor nao chegou a
                        # tempo» — 7, 11, 12, 9, 11 furos por segundo, até
                        # 284 ms de silêncio injectado num único segundo.
                        # Note-se a mensagem: o PRODUTOR não chegou a tempo.
                        # Não é o GIL, é CPU a menos — outro mecanismo, e por
                        # isso nenhuma das correcções da pintura lhe tocava.
                        #
                        # Agora exige-se SOSSEGO SUSTENTADO: os decks têm de
                        # estar parados em várias verificações seguidas, e
                        # confirma-se outra vez mesmo antes de começar. Um
                        # silêncio de passagem entre duas faixas deixa de
                        # servir de senha para dezoito segundos de modelo.
                        def _sossegado():
                            try:
                                _a = eng.deck("A")
                                _b = eng.deck("B")
                                if (getattr(_a, "playing", False)
                                        or getattr(_b, "playing", False)):
                                    return False
                                _xf = eng.crossfade
                                return abs(_xf.value - _xf.tgt) <= 1e-3
                            except Exception:
                                return True     # sem motor, nada a proteger

                        _SEGUIDAS = 3           # segundos de sossego exigidos
                        _quietos = 0
                        _desistiu = False
                        for _ in range(7200):
                            if _minha_ger != _BG_GRIDS_GER:
                                return
                            if _sossegado():
                                _quietos += 1
                                # a última confirmação é feita já sem sleep
                                # pelo meio: fecha a frincha de um segundo
                                # entre verificar e arrancar o modelo
                                if _quietos >= _SEGUIDAS and _sossegado():
                                    break
                            else:
                                _quietos = 0
                            _tm.sleep(1.0)
                        else:
                            _desistiu = True    # duas horas à espera: passa
                        if _desistiu:
                            continue
                        # ── A ALMOFADA FALTAVA AQUI (30/08/2026) ──────────
                        # O motor tem um mecanismo pronto para isto — o
                        # `trabalho_pesado`, que alarga a almofada de saída
                        # antes de trabalho que rouba CPU e a devolve no fim.
                        # Já protege «planear o set», «análise da pasta»,
                        # «preparar as faixas» e «carregar faixa». Faltava
                        # exactamente ESTE sítio, que é o mais pesado de
                        # todos: o BeatThis leva 11 a 26 segundos.
                        #
                        # O comentário aqui abaixo já admitia o buraco — «se
                        # a música arrancou durante o cálculo, não há como
                        # parar o modelo a meio… pode ter havido furos» — e
                        # ficava-se pelo lamento. Não há mesmo como parar o
                        # modelo a meio, mas há como o som aguentar: com a
                        # almofada já larga, a música que arranca no meio do
                        # cálculo encontra margem em vez de ser apanhada de
                        # surpresa.
                        #
                        # `esperar=False`: isto corre numa thread de fundo e
                        # não pode ficar bloqueada à espera que a almofada
                        # encha — o trabalho é para começar já; a protecção
                        # vai subindo por trás.
                        _quem = "grelha em fundo"
                        try:
                            eng.trabalho_pesado(True, _quem, esperar=False)
                        except Exception:
                            pass
                        try:
                            _apply_grid(_sp)
                            # Fica dito na mesma, para quem ler um log de
                            # furos saber onde olhar em vez de voltar a caçar
                            # o GIL. Com a almofada larga isto passa a ser um
                            # aviso, e já não uma explicação para um corte.
                            if not _sossegado():
                                print("[Fusion] grelhas em fundo: a música "
                                      "arrancou a meio do calculo de "
                                      f"'{_sp.name}' — com a almofada larga.")
                        except Exception as _e:
                            print(f"[Fusion] grelha bg falhou ({_sp.name}): {_e}")
                        finally:
                            # SEMPRE. Uma almofada que sobe e não desce deixa
                            # o set inteiro com segundos de atraso nos
                            # controlos — já aconteceu neste motor (ver o
                            # «RESTAURO INCONDICIONAL DA ALMOFADA»).
                            try:
                                eng.trabalho_pesado(False, _quem)
                            except Exception:
                                pass
                import threading as _th
                _t = _th.Thread(target=_bg_grids, daemon=True)
                _t.start()
        except Exception as e:
            import traceback; traceback.print_exc()
            self.failed.emit(str(e))


# ═══════════════════════════════════════════════════════════════════════════
# FAIXAS LONGAS — o caso do set gravado (06/09/2026)
# ═══════════════════════════════════════════════════════════════════════════
#
# Log de 05/09, 21:10:17: «[Manual] A carregar no deck B: DARIO REMIX 2.wav».
# A partir dai, 100+ furos em menos de um minuto, e a `_mload_B` ainda a
# correr quando o motor foi desligado as 21:11:25 — a carga nunca terminou.
#
# Eram tres coisas ao mesmo tempo, nenhuma delas visivel:
#
#   1. A CARGA MANUAL NAO PEDIA A ALMOFADA DE PROTECCAO. A carga do automix
#      pede (ve-se no log: «[Almofada] carregar faixa: 2500 ms de
#      proteccao»); esta nao pedia nada. Dois caminhos para a mesma
#      operacao, um protegido e o outro nao.
#
#   2. A GRELHA CORRIA O MODELO SOBRE O FICHEIRO INTEIRO. O «Beat This!»
#      leva ~24 s numa faixa de 5 minutos — esta medido, ver a nota no
#      `_ensure_grid_beats`. Em 45 minutos sao uns 4 MINUTOS de CPU, no
#      mesmo processo do audio, numa maquina de 2 nucleos. E um set gravado
#      nem precisa de grelha nenhuma: toca-se de fio a pavio.
#
#   3. O BUFFER E' ENORME. 45 minutos em estereo float32 sao ~950 MB so' de
#      amostras, sem contar o que a descodificacao gasta pelo caminho.
#
# O que esta aqui resolve 1 e 2 e AVISA sobre 3. O streaming a serio — o
# deck a ler do disco em vez de ter o ficheiro todo em memoria — fica para
# o motor nativo; ver PLANO_MOTOR_NATIVO.md.

# Acima disto nao se corre o modelo de grelha ao carregar a faixa. 12 min
# cobrem qualquer musica e qualquer extended mix; um set gravado fica de
# fora, que e' o que se quer.
LONGA_SEM_GRELHA_S = float(os.environ.get("MIXAI_LONGA_GRELHA_S", "720"))
# Acima disto diz-se no log quanta memoria a faixa vai ocupar.
LONGA_AVISO_S = float(os.environ.get("MIXAI_LONGA_AVISO_S", "600"))


def _duracao_ficheiro_s(path) -> float:
    """Duracao em segundos LENDO SO' O CABECALHO.

    Nao descodifica nada: para um wav de 45 minutos custa o mesmo que para
    um mp3 de 3. Devolve 0.0 se nao conseguir — quem chama trata o 0 como
    «nao sei» e segue pelo caminho normal, que e' o de hoje."""
    try:
        import soundfile as _sf
        return float(_sf.info(str(path)).duration or 0.0)
    except Exception:
        pass
    try:
        # mp3/m4a e outros que o soundfile nao abre: o mutagen le' so' as tags
        import mutagen as _mut
        _m = _mut.File(str(path))
        if _m is not None and getattr(_m, "info", None) is not None:
            return float(getattr(_m.info, "length", 0.0) or 0.0)
    except Exception:
        pass
    return 0.0


def _mb_do_buffer(dur_s: float, sr: int = 44100) -> float:
    """Quanto ocupa em RAM: estereo float32, que e' como o deck a guarda."""
    return dur_s * sr * 2.0 * 4.0 / (1024.0 * 1024.0)


class _ManualLoadThread(QThread):
    """Carrega uma faixa num deck (análise + stretch) sem congelar a UI."""
    done = Signal(str, str)      # deck, nome
    failed = Signal(str, str)
    regrid = Signal(str)         # aviso de grelha corrigida automaticamente
    aviso = Signal(str)          # faixa longa: o que se decidiu e porquê

    def __init__(self, eng, deck_name, path, md):
        super().__init__()
        self.eng = eng
        self.deck_name = deck_name
        self.path = path
        self.md = md

    def run(self):
        # ── A ALMOFADA DE PROTECCAO, QUE FALTAVA AQUI (06/09/2026) ───────
        # Pedida antes de qualquer trabalho e largada no `finally`: cobre a
        # saida normal, o erro, e a faixa que nem chega a abrir.
        _pesado = False
        try:
            from mixai_engine import trabalho_pesado_global as _tp
        except Exception:
            _tp = None
        try:
            if _tp is not None:
                _tp(True, f"carga manual {self.deck_name}", esperar=True)
                _pesado = True
        except Exception:
            _tp = None
        try:
            self._run_protegido()
        finally:
            if _pesado and _tp is not None:
                try:
                    _tp(False, f"carga manual {self.deck_name}")
                except Exception:
                    pass

    def _run_protegido(self):
        try:
            # NÃO se re-corrige a grelha ao carregar. Antes corria aqui o
            # auto_fix_if_misaligned (mixai_regrid, o motor ANTIGO), que:
            #   1) re-analisava o áudio a cada carga — LENTO (o utilizador
            #      notava o atraso e a mensagem "grelha corrigida");
            #   2) usava a heurística antiga, que ESTRAGAVA a grelha que o
            #      modelo já tinha corrigido na base (ex.: mexia o downbeat de
            #      0.05 para 0.55).
            # A grelha vem agora da base de dados, já detectada pelo modelo
            # "Beat This!". Para faixas SEM grelha guardada, o bloco abaixo
            # faz a detecção de recurso com o librosa.
            info = _info_of(self.md, self.path)
            try:
                bpm = float(info.get("bpm", 0) or 0)
            except (TypeError, ValueError):
                bpm = 0.0
            db = _downbeat_of(info)
            if not (40.0 < bpm < 300.0):
                import librosa
                y, sr = librosa.load(self.path, sr=22050, mono=True,
                                     duration=90)
                t, beats = librosa.beat.beat_track(y=y, sr=sr)
                bpm = float(np.atleast_1d(t)[0]) or 120.0
                while bpm < 70:  bpm *= 2
                while bpm > 190: bpm /= 2
                if db <= 0 and len(beats):
                    db = float(librosa.frames_to_time(beats[0], sr=sr))
            # ── FAIXA LONGA: nem grelha do modelo, nem surpresas ─────────
            # A duracao le-se do CABECALHO (nao descodifica nada), por isso
            # este teste custa o mesmo num wav de 45 min e num mp3 de 3.
            _dur = _duracao_ficheiro_s(self.path)
            if _dur >= LONGA_AVISO_S:
                self.aviso.emit(
                    f"{os.path.basename(str(self.path))}: {_dur / 60.0:.0f} "
                    f"min — vai ocupar ~{_mb_do_buffer(_dur):.0f} MB de "
                    f"memoria enquanto estiver no deck.")
            # GRELHA LAZY (Fusion): calcula o beatgrid do modelo ao carregar a
            # faixa no deck, se ainda não existir (uma vez por faixa, na BD).
            if _dur >= LONGA_SEM_GRELHA_S:
                # O modelo sobre 45 minutos sao uns 4 minutos de CPU no
                # MESMO processo do audio. E um set gravado nao se
                # sincroniza com nada — toca-se de fio a pavio. Usa-se a
                # grelha que ja houver na base, ou nenhuma.
                _beats = info.get("beats") or None
                self.aviso.emit(
                    f"faixa com mais de {LONGA_SEM_GRELHA_S / 60.0:.0f} min "
                    f"— a grelha do modelo NAO corre (poupa minutos de CPU "
                    f"com musica no ar). MIXAI_LONGA_GRELHA_S muda o limite.")
            else:
                _beats = _ensure_grid_beats(self.md, self.path)
            info = _info_of(self.md, self.path)
            db = _downbeat_of(info) or db
            try:
                _gb = float(info.get("bpm", 0) or 0)
                if 40.0 < _gb < 300.0:
                    bpm = _gb
            except (TypeError, ValueError):
                pass
            # carga manual: SEM stretch — a faixa toca no BPM ORIGINAL;
            # o SYNC é que iguala ao deck que está a tocar
            self.eng.deck(self.deck_name).load_file(self.path, bpm, db,
                                                    stretch=False,
                                                    beats=_beats or info.get("beats"))
            self.done.emit(self.deck_name, os.path.basename(self.path))
        except Exception as e:
            import traceback; traceback.print_exc()
            self.failed.emit(self.deck_name, str(e))


# ═══════════════════════════════════════════════════════════════════════════
class _CreativeFX:
    """O 'agente' de efeitos: aplica FX no deck AO VIVO, no beat exato,
    fora das zonas de transição.

    v5.0.1 — CONSCIENTE DA ESTRUTURA: quando a faixa tem `sections` da
    análise MixAi (Intro / Build-up / Breakdown / Verse / Outro), os
    efeitos caem nos momentos musicais certos:
      • fim de um Build-up (= o drop): riser de filtro nos 8 beats
        anteriores que abre em cheio exatamente no drop
      • início de um Breakdown: echo suave (acalma, deixa respirar)
      • corpo/Verse: flanger ocasional (só na intensidade "frequent")
    Sem sections → rotação clássica por intervalo de beats (fallback):
    filter sweep → echo → flanger."""

    # ── QUANTOS EFEITOS, SEM PLANO DE ESTRUTURA (28/08/2026) ──────────────
    #
    # Era um efeito de 32 em 32 batidas no «medium» — quinze em quinze
    # segundos a 124 BPM, sem parar, em rotação fixa filtro → eco → flanger.
    # Numa faixa de cinco minutos davam DEZANOVE efeitos. Do log do
    # utilizador, e da frase dele: «está exagerado».
    #
    # O problema não era só a quantidade: era a assimetria. Uma faixa COM
    # estrutura produz dois a cinco eventos, nos drops e nos breakdowns, e
    # soa bem. O caminho sem estrutura não era um recurso — era um
    # metrónomo de efeitos.
    #
    # Agora conta-se em FRASES de 32 batidas, que é a unidade em que a
    # música de dança está construída, e não em batidas soltas:
    #
    #     rare      6 frases  (192 batidas, ~93 s)  ~3 por faixa
    #     medium    3 frases  ( 96 batidas, ~46 s)  ~6 por faixa
    #     frequent  2 frases  ( 64 batidas, ~31 s)  ~9 por faixa
    #
    # O «medium» fica assim na mesma ordem de grandeza do que uma faixa com
    # estrutura dá, que é o comportamento que já estava bom.
    FRASE = 32
    FRASES_ENTRE_FX = {"rare": 6, "medium": 3, "frequent": 2}
    # O MESMO EM BATIDAS, mantido para quem leia isto de fora e para não
    # partir código antigo que consultasse o intervalo. Escrito à mão de
    # propósito: uma compreensão de dicionário no corpo de uma classe tem
    # âmbito próprio e NÃO vê o `FRASE` que está duas linhas acima — dava
    # NameError no import, com a aplicação a nem chegar a abrir. Se mexeres
    # nas frases, mexe aqui também (o teste_fx_cadencia.py confirma que os
    # dois não se descolam).
    INTERVAL = {"rare": 192, "medium": 96, "frequent": 64}
    # tipos de evento estrutural permitidos, por intensidade
    _ALLOW = {"rare":     {"drop"},
              "medium":   {"drop", "breakdown"},
              "frequent": {"drop", "breakdown", "body"}}

    def __init__(self, engine: Engine, dj: AutoDJ, log, intensity="medium",
                 tr=None):
        self.eng = engine
        self.dj = dj
        self.log = log
        # tradutor de mensagens (key, **campos) -> texto; sem ele usa PT
        self.tr = tr or (lambda key, **kw: _tr("pt", key).format(**kw))
        self.intensity = intensity
        self._next_beat = 64          # primeiro FX à 2.ª frase (fallback)
        self._rot = 0
        self._cur_track = None        # (deck, faixa) ao vivo
        self._plan = []               # [(beat, kind), …] da faixa ao vivo
        self._structured = False      # a faixa atual tem plano estrutural?
        self.enabled = True

    def set_intensity(self, s):
        self.intensity = s if s in self.INTERVAL else "medium"

    def _in_transition(self):
        xf = self.eng.crossfade
        return abs(xf.value - xf.tgt) > 1e-3

    # ---- plano estrutural ---------------------------------------------------
    def _spec_of(self, deck):
        try:
            for sp in (self.dj.playlist or []):
                if sp.name == deck.track_name:
                    return sp
        except Exception:
            pass
        return None

    def _build_plan(self, deck):
        """Converte as sections (segundos da faixa ORIGINAL) em beats da
        grelha do deck. O nº do beat é invariante ao time-stretch:
        beat = (t − downbeat) × bpm_original / 60."""
        self._plan = []
        self._structured = False
        spec = self._spec_of(deck)
        secs = getattr(spec, "sections", None) if spec else None
        if not secs:
            # Silencioso ate 13/08/2026, e por isso ninguem percebia porque
            # os efeitos caiam sempre no mesmo sitio. Ver _sections_of().
            try:
                _fr = self.FRASES_ENTRE_FX.get(self.intensity, 3)
                self.log(self.tr(
                    "l_fx_sem_estrutura",
                    t=os.path.basename(
                        str(getattr(deck, "track_name", "?")))[:36],
                    f=_fr, b=_fr * self.FRASE))
            except Exception:
                pass
            return
        bpm = float(getattr(spec, "bpm", 0.0) or 0.0)
        db = float(getattr(spec, "downbeat", 0.0) or 0.0)
        if bpm <= 0:
            return
        allow = self._ALLOW.get(self.intensity, self._ALLOW["medium"])
        # A GRELHA DO DECK, não a do master. O eng.beat_len é o beat do MASTER
        # e só coincide com o do deck quando a faixa foi esticada — que é o
        # caso do automix. Na mistura MANUAL a faixa toca no BPM original
        # (load_file com stretch=False), e a contagem saía com o erro da
        # diferença entre os dois tempos. É o mesmo beat que o
        # deck.current_beat usa para disparar os eventos, portanto tem de ser
        # o mesmo aqui a decidir a zona segura.
        total_beats = deck.length / max(1, deck.grid_bl)

        def b_of(t):
            return (float(t) - db) * bpm / 60.0

        ev = []

        # ── LISTAS EXPLICITAS DO DETECTOR (13/08/2026) ────────────────────
        # O mixai_estrutura devolve `drops` e `breakdowns` a parte das
        # etiquetas, e sao mais precisos: um drop e' a frase cheia que vem
        # LOGO a seguir a uma subida ou a um vazio, e o detector ja fez essa
        # distincao. Deduzi-los das etiquetas exige que exista uma seccao
        # 'Build-up' — e nas faixas com poucas seccoes (Intro/Verse/Outro,
        # que sao muitas) nao existe, pelo que o plano saia vazio com a
        # mensagem "N seccoes mas 0 evento(s) utilizaveis".
        _meta = getattr(spec, "estrutura", None) or {}
        _explicitos = 0
        if "drop" in allow:
            for _t in (_meta.get("drops") or []):
                try:
                    ev.append((b_of(_t), "drop"))
                    _explicitos += 1
                except (TypeError, ValueError):
                    continue
        if "breakdown" in allow:
            for _t in (_meta.get("breakdowns") or []):
                try:
                    ev.append((b_of(_t), "breakdown"))
                    _explicitos += 1
                except (TypeError, ValueError):
                    continue

        for s in secs:
            try:
                lbl = str(s.get("label", "")).lower()
                b0 = b_of(s.get("start", 0.0))
                b1 = b_of(s.get("end", 0.0))
            except Exception:
                continue
            # Com listas explicitas nao se repetem pelas etiquetas: sairiam
            # eventos duplicados a poucas batidas um do outro e o
            # espacamento minimo comia o segundo.
            if _explicitos and ("build" in lbl or "chorus" in lbl
                                or "breakdown" in lbl or "bridge" in lbl):
                continue
            if ("build" in lbl or "chorus" in lbl) and "drop" in allow:
                ev.append((b1, "drop"))            # o drop é o FIM do build
            elif ("breakdown" in lbl or "bridge" in lbl) \
                    and "breakdown" in allow:
                ev.append((b0, "breakdown"))
            elif ("verse" in lbl or "body" in lbl) and "body" in allow \
                    and (b1 - b0) >= 32:
                ev.append((b0 + 16, "body"))
        # snap ao início de frase (múltiplo de 4 beats), dentro da zona
        # segura da faixa, com espaçamento mínimo de 16 beats entre eventos
        # ONDE A AGULHA JA' VAI. Um evento que ficou para tras nao e' um
        # evento: e' um efeito a disparar sobre musica que ja' passou.
        #
        # No automix isto nunca mordia porque o plano nasce com a faixa, no
        # beat 0. Em mistura MANUAL o agente liga-se a meio — e ai metade do
        # plano esta' no passado. Como o tick dispara UM evento por volta
        # (50 ms), todos os atrasados saiam de RAJADA, um atras do outro:
        # seis efeitos em 300 ms, num sitio onde nao havia nem drop nem
        # breakdown. Foi o que o log do utilizador mostrou a 16/08/2026.
        #
        # A margem de 12 batidas nao e' folga: o riser de filtro comeca 8
        # batidas ANTES do drop, e sem esse arranque o efeito perde o que
        # tem de bom — a tensao a subir.
        try:
            _agora = float(deck.current_beat)
        except Exception:
            _agora = 0.0
        _minimo = _agora + 12.0
        last = -1e9
        _passados = 0
        for b, kind in sorted(ev):
            b = round(b / 4.0) * 4.0
            if b < 24 or b > total_beats - 40:
                continue
            if b < _minimo:
                _passados += 1
                continue
            if b - last < 16:
                continue
            last = b
            self._plan.append((b, kind))
        self._structured = bool(self._plan)
        if self._structured:
            kinds = ", ".join(f"{k}@{int(b)}" for b, k in self._plan)
            self.log(self.tr("l_fx_plan", t=deck.track_name, k=kinds))
            if _passados:
                # Dizer que ficaram para tras, e quantos. Sem isto, ligar o
                # agente a meio de uma faixa dava um plano curto sem
                # explicacao — e nao se percebia se era a faixa que tinha
                # pouca estrutura ou se estava a faltar alguma coisa.
                self.log(self.tr("l_fx_passados", n=_passados))
        else:
            # Havia seccoes mas nenhum evento sobreviveu. Dizer porque: sem
            # isto o agente cai no intervalo generico sem uma palavra, e foi
            # preciso ler o codigo para perceber que estava a acontecer.
            try:
                self.log(self.tr("l_fx_poucos", s=len(secs), n=len(ev)))
            except Exception:
                pass

    def _fire_structural(self, deck, b_ev, kind):
        # MEDICAO (13/08/2026). As paragens de 0,3 s da interface aparecem
        # SEMPRE logo a seguir a um evento de FX. Duas hipoteses:
        #   A) o trabalho esta aqui dentro (agendar + escrever no log);
        #   B) isto e' barato, mas os efeitos fazem o produtor de audio gastar
        #      mais CPU por bloco e, com 2 nucleos, a interface fica sem vez.
        # Se este cronometro acusar >50 ms e' (A); se acusar 1-2 ms, e' (B) e
        # o caminho e' baratear as rampas, nao mexer aqui.
        _t_ini = time.perf_counter()
        # TEMPO DE CPU AO LADO DO TEMPO DE RELOGIO (30/08/2026).
        #
        # O cronometro aqui em baixo so' media RELOGIO, e por isso a pergunta
        # que ele proprio poe — «(A) o trabalho esta aqui dentro» ou «(B) e'
        # barato mas o produtor fica sem CPU» — nao tinha como ser respondida
        # por ele: uma espera conta na conta igual ao trabalho.
        #
        # O `paintEvent` da onda ja' aprendeu isto em 22/08 e mede as duas
        # coisas. Aqui faltava, e num caso real (73 ms, drop @ 156, seguido
        # de 3 furos no som) nao deu para dizer se foram 73 ms A FAZER ou 73
        # ms A ESPERAR — que sao dois problemas diferentes com duas
        # correccoes diferentes.
        #
        #   cpu ~= relogio  -> o trabalho E' aqui; ha' que baratea-lo.
        #   cpu << relogio  -> isto foi ESFOMEADO; o problema esta noutro
        #                      sitio (a transicao, a carga, o GIL) e mexer
        #                      aqui nao resolve nada.
        try:
            _cpu_ini = time.thread_time()
        except Exception:
            _cpu_ini = None
        name, eng = deck.name, self.eng
        try:
            if kind == "drop":
                # ── RISER + BASS DROP ─────────────────────────────────────
                # O riser de filtro ja ca estava: HP a fechar nos 8 beats
                # antes e a abrir em cheio no drop.
                #
                # Faltava o BASS DROP, que e' a tecnica standard em house e
                # afro: tirar os GRAVES no ultimo compasso antes do drop e
                # devolve-los de golpe no «1». O vazio em baixo durante 4
                # batidas e' o que faz o bombo bater a dobrar quando volta.
                # O filtro sobe a tensao; o bass drop cria o contraste.
                #
                # Quatro batidas e nao oito de proposito: tirar os graves
                # cedo demais soa a falha tecnica, nao a tensao.
                eng.schedule_at_deck_beat(
                    name, b_ev - 8,
                    lambda d=deck: d.fx_filter(
                        0.78, ramp_s=8 * eng.beat_len / eng.sr))
                eng.schedule_at_deck_beat(
                    name, b_ev - 4,
                    lambda d=deck: d.eq.set_gain(
                        "low", 0.0, ramp_s=4 * eng.beat_len / eng.sr))
                eng.schedule_at_deck_beat(
                    name, b_ev, lambda d=deck: d.filter.reset(0.5))
                # graves de volta SEM rampa: o golpe e' o efeito
                eng.schedule_at_deck_beat(
                    name, b_ev, lambda d=deck: d.eq.set_gain("low", 1.0, 0.0))
                self.log(self.tr("l_fx_riser", b=int(b_ev), d=name)
                         + " + bass drop")
            elif kind == "breakdown":
                eng.schedule_at_deck_beat(
                    name, b_ev,
                    lambda d=deck: d.fx_echo_on(wet=0.35, beats=0.75))
                eng.schedule_at_deck_beat(
                    name, b_ev + 4, lambda d=deck: d.fx_echo_out())
                self.log(self.tr("l_fx_break", b=int(b_ev), d=name))
            else:
                eng.schedule_at_deck_beat(
                    name, b_ev, lambda d=deck: d.fx_flanger_on(wet=0.5))
                eng.schedule_at_deck_beat(
                    name, b_ev + 8, lambda d=deck: d.fx_flanger_off())
                self.log(self.tr("l_fx_body", b=int(b_ev), d=name))
        except Exception as e:
            self.log(self.tr("l_fx_fail", e=e))
        _ms = (time.perf_counter() - _t_ini) * 1000.0
        if _ms > 50.0:
            _cpu = None
            if _cpu_ini is not None:
                try:
                    _cpu = (time.thread_time() - _cpu_ini) * 1000.0
                except Exception:
                    _cpu = None
            if _cpu is None:
                _veredicto = "(sem tempo de CPU nesta plataforma)"
            elif _cpu > 0.5 * _ms:
                _veredicto = ("— o trabalho E' aqui: baratear estas "
                              "chamadas resolve.")
            else:
                _veredicto = ("— isto foi ESFOMEADO, nao e' caro: os "
                              "{:.0f} ms foram quase todos a ESPERAR por "
                              "CPU. Mexer aqui nao resolve; o problema "
                              "esta' em quem estava a ocupar a "
                              "maquina.").format(_ms - (_cpu or 0.0))
            print(f"[FX] _fire_structural: {_ms:.0f} ms de relogio, "
                  f"{'?' if _cpu is None else f'{_cpu:.0f}'} ms de CPU "
                  f"({kind} @ {int(b_ev)}) {_veredicto}")

    # ---- ciclo ----------------------------------------------------------------
    def tick(self):
        """Chamado pelo timer da UI (~20x/s). Sample-accurate via scheduler."""
        if not self.enabled:
            return
        try:
            deck = self.dj.live_deck
        except Exception:
            return
        if deck.buf is None or not deck.playing:
            return
        beat = deck.current_beat
        # faixa/deck ao vivo mudou -> recomeça o agendamento na faixa nova
        key = (deck.name, deck.track_name)
        if key != self._cur_track:
            self._cur_track = key
            # DUAS FRASES DE CORTESIA, e não 16 batidas. A faixa nova entra a
            # seguir a uma mistura, que já é bastante a acontecer; disparar
            # um efeito oito segundos depois era a primeira parte do exagero.
            self._next_beat = (int(beat // self.FRASE) + 2) * self.FRASE
            self._build_plan(deck)
            return
        # não pisar as transições (crossfade ativo ou perto do fim)
        if self._in_transition() or deck.remaining < 24 * self.eng.beat_len:
            # ao sair da transição, o mesmo compasso de espera: assim que o
            # crossfade acabava, isto deixava disparar oito batidas depois
            self._next_beat = (int(beat // self.FRASE) + 2) * self.FRASE
            return
        # 1) faixa COM estrutura: efeitos só nos momentos do plano
        if self._structured:
            # DEITAR FORA O QUE JA' PASSOU, sem disparar. O plano e' filtrado
            # quando nasce, mas entre nascer e chegar a vez de um evento pode
            # haver um seek, um hot cue ou um loop — e ai o evento fica atras
            # da agulha na mesma. Disparar um riser de drop 40 batidas depois
            # do drop e' pior do que nao disparar nada.
            while self._plan and beat > self._plan[0][0] + 8:
                self._plan.pop(0)
            if self._plan and beat >= self._plan[0][0] - 12:
                b_ev, kind = self._plan.pop(0)
                self._fire_structural(deck, b_ev, kind)
            return
        # 2) fallback: rotação clássica por intervalo
        if beat < self._next_beat:
            return
        # ── O PRÓXIMO CAI NUMA FRASE, E NÃO SEMPRE NA MESMA ──────────────
        # Antes era `(beat // step + 1) * step`: relógio certo, e por isso
        # soava a máquina — o ouvido aprende a cadência ao terceiro efeito e
        # a partir daí está à espera dele.
        #
        # Salta um número VARIÁVEL de frases à volta do que a intensidade
        # pede (uma a menos, igual, ou uma a mais). Continua sempre em cima
        # de uma frase, portanto nunca cai fora do compasso; o que muda é
        # QUANDO, não ONDE. Nunca menos de duas frases seguidas, para o
        # sorteio não conseguir juntar dois efeitos.
        _fr = self.FRASES_ENTRE_FX.get(self.intensity, 3)
        _salto = max(2, _fr + _random.choice((-1, 0, 0, 1)))
        self._next_beat = (int(beat // self.FRASE) + _salto) * self.FRASE
        # NOTA: o reverb saiu da rotação automática — o custo do Schroeder
        # em tempo real no produtor engasgava o som em CPUs de 2 núcleos.
        # Continua disponível no PAD FX (pad 8, manual).
        fx = ("filter", "echo", "flanger")[self._rot % 3]
        self._rot += 1
        name, eng = deck.name, self.eng
        bl = self.eng.beat_len
        try:
            if fx == "filter":
                deck.fx_filter(0.22, ramp_s=4 * bl / eng.sr)
                eng.schedule_at_deck_beat(name, beat + 8,
                                          lambda d=deck: d.filter.reset(0.5))
                self.log(self.tr("l_fx_sweep", d=name))
            elif fx == "echo":
                deck.fx_echo_on(wet=0.4, beats=0.75)
                eng.schedule_at_deck_beat(name, beat + 4,
                                          lambda d=deck: d.fx_echo_out())
                self.log(self.tr("l_fx_echo", d=name))
            else:
                deck.fx_flanger_on(wet=0.55)
                eng.schedule_at_deck_beat(name, beat + 8,
                                          lambda d=deck: d.fx_flanger_off())
                self.log(self.tr("l_fx_flanger", d=name))
        except Exception as e:
            self.log(self.tr("l_fx_fail", e=e))


_AUDIO_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".aiff",
               ".aif", ".wma", ".opus", ".mp4", ".m4b")
_PLAYLIST_EXTS = (".m3u", ".m3u8")

# Pastas que NUNCA sao musica do utilizador, mas que estao cheias de audio.
#
# PORQUE EXISTE (13/08/2026). A pesquisa global passou a percorrer a pasta
# pessoal inteira, e o browser passou a listar tudo o que la esta. Resultado
# visto no ecra: a arvore mostrava .cache, .chatgpt, .codex, .dotnet,
# .gemini, .gnutls, .idlerc — pastas de configuracao de programas — e uma
# pesquisa por «L» devolveu 800 ficheiros, quase todos chamados `vocals`,
# que sao stems de separacao guardados em cache. A biblioteca do DJ ficou
# soterrada em lixo.
#
# Duas regras, ambas conservadoras:
#   • qualquer pasta cujo nome comece por ponto (convencao de oculto em
#     Windows e Unix) — nenhum DJ guarda musica numa dessas;
#   • uma lista curta de nomes conhecidos de cache, ambientes e sistema.
# Nao se filtra por atributo oculto do Windows: ha quem tenha a pasta de
# musica marcada como oculta, e escondia-lhe a biblioteca toda.
_PASTAS_IGNORADAS = {
    "node_modules", "__pycache__", "site-packages", "venv", ".venv",
    "appdata", "windows", "program files", "program files (x86)",
    "programdata", "$recycle.bin", "system volume information",
    "temp", "tmp", "cache", "caches", "stems", "separated",
    "onedrivetemp", "recovery",
}


# Faixas que ja passaram pelo modelo de grelha NESTA sessao. Ver a nota
# longa dentro do _ensure_grid_beats: sem isto, o mesmo ficheiro era
# reprocessado a cada nova preparacao do motor, 25 s de cada vez.
_GRIDS_FEITAS = {}          # caminho -> beats calculados (None = em curso)
_GRIDS_LOCK = threading.Lock()

# Geracao do fio de grelhas em segundo plano. Cada preparacao do motor
# incrementa-a; fios de geracao anterior desistem. Ver _bg_grids.
_BG_GRIDS_GER = 0


def parar_grelhas_em_fundo():
    """Manda desistir qualquer `_bg_grids` vivo. Nao espera por ele.

    PORQUE EXISTE (04/09/2026)
    ==========================
    A geracao so' era incrementada por quem ARRANCAVA um fio novo — nao
    havia maneira nenhuma de dizer «acabou, parem». Ao fechar a aplicacao
    o `_bg_grids` continuava a trabalhar, e o `closeEvent` largava-lhe a
    sessao do modelo por baixo dos pes. Violacao de acesso.

    NAO se espera pelo fio, de proposito: ele pode estar dentro do modelo,
    que sao 15 a 25 segundos, e esperar por isso ao fechar dava a aplicacao
    pendurada que o `os._exit` do `closeEvent` veio precisamente resolver.
    Basta que nao comece NADA de novo; o que ja' esta' a meio e' o
    `mixai_beatthis.close_session` que protege, recusando-se a largar a
    sessao enquanto la' estiver alguem.
    """
    global _BG_GRIDS_GER
    try:
        with _GRIDS_LOCK:
            _BG_GRIDS_GER += 1
    except Exception:
        pass


def _pasta_a_ignorar(nome):
    """True se esta pasta nao deve ser percorrida nem mostrada."""
    if not nome:
        return False
    if nome.startswith("."):
        return True
    return nome.lower() in _PASTAS_IGNORADAS


class _DragFileList(QListWidget):
    """Lista cujos itens (path guardado em UserRole) podem ser ARRASTADOS
    para os decks — entrega URLs de ficheiro que o DeckPanel aceita no drop.
    Também ACEITA drops: largar faixas aqui chama on_drop_paths(paths) —
    usado para gerar uma playlist automaticamente a partir das arrastadas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.on_drop_paths = None            # callback(list[str])
        # REORDENAR ARRASTANDO (13/08/2026): callback(linhas, destino).
        # Sem isto, arrastar um item DENTRO da lista caia no on_drop_paths
        # com os proprios URLs e gerava uma playlist nova — o oposto do que
        # se espera de arrastar para mudar a ordem.
        self.on_reorder = None               # callback(list[int], int)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def mimeData(self, items):
        md = QMimeData()
        urls = []
        for it in items:
            p = it.data(Qt.ItemDataRole.UserRole)
            if p:
                urls.append(QUrl.fromLocalFile(str(p)))
        if urls:
            md.setUrls(urls)
        return md

    def dragEnterEvent(self, e):
        if self.on_drop_paths and e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self.on_drop_paths and e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def _linha_destino(self, e):
        """Linha onde o item largado deve ficar, contando o indicador."""
        try:
            pos = e.position().toPoint()
        except AttributeError:                  # Qt5
            pos = e.pos()
        idx = self.indexAt(pos)
        if not idx.isValid():
            return self.count()                 # largado no vazio -> fim
        linha = idx.row()
        try:
            from PySide6.QtWidgets import QAbstractItemView as _AIV
            if self.dropIndicatorPosition() == _AIV.DropIndicatorPosition.BelowItem:
                linha += 1
        except Exception:
            pass
        return linha

    def dropEvent(self, e):
        # ARRASTOU DE DENTRO PARA DENTRO = reordenar. Tem de ser testado
        # ANTES do on_drop_paths: o mimeData de um arrasto interno tambem
        # traz URLs, e sem esta guarda a lista interpretava-o como "faixas
        # novas largadas aqui" e gerava uma playlist do zero.
        if e.source() is self and self.on_reorder:
            linhas = sorted({i.row() for i in self.selectedIndexes()})
            destino = self._linha_destino(e)
            if linhas:
                e.acceptProposedAction()
                self.on_reorder(linhas, destino)
                return
        if self.on_drop_paths and e.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in e.mimeData().urls()
                     if u.toLocalFile()]
            if paths:
                e.acceptProposedAction()
                # A LINHA ONDE SE LARGOU, para a faixa entrar ali e nao no
                # fim da lista.
                try:
                    self.on_drop_paths(paths, self._linha_destino(e))
                except TypeError:
                    self.on_drop_paths(paths)      # callback antigo
                return
        super().dropEvent(e)


def _drives():
    """Lista as drives existentes no Windows (C:\\, D:\\, …)."""
    import string
    out = []
    for c in string.ascii_uppercase:
        d = f"{c}:\\"
        if os.path.exists(d):
            out.append(d)
    return out


def _list_audio(path, md=None):
    """Devolve [(label, full_path), …] dos ficheiros de áudio de uma pasta."""
    out = []
    try:
        names = sorted(os.listdir(path), key=str.lower)
    except Exception:
        return out
    for n in names:
        if not n.lower().endswith(_AUDIO_EXTS):
            continue
        full = os.path.join(path, n)
        label = n
        try:
            info = (md.get(os.path.normpath(full)) or md.get(full)) if md else None
            if info:
                bpm = info.get("bpm")
                key = info.get("camelot") or "?"
                if isinstance(bpm, (int, float)) and bpm:
                    label = f"{n}   [{float(bpm):.0f} BPM · {key}]"
        except Exception:
            pass
        out.append((label, full))
    return out


def _dur_str(sec):
    try:
        sec = int(float(sec))
    except Exception:
        return ""
    if sec <= 0:
        return ""
    return f"{sec // 60}:{sec % 60:02d}"


# ── CACHE DAS ETIQUETAS (13/08/2026) ───────────────────────────────────────
# Medido pelo vigia da interface, com musica a tocar:
#     0,70 s em _tags_title_artist -> mutagen.File -> ... -> tokenize.open
#     0,38 s em _on_click -> _browser_select -> _populate_folder
#                         -> _audio_rows -> _tags_title_artist
#
# O `_populate_folder` le as etiquetas de TODOS os ficheiros da pasta, uma
# abertura de ficheiro por faixa, na thread da interface. Clicar noutra
# pasta — ou na mesma outra vez — repete tudo do zero.
#
# A primeira leitura e' ainda pior do que parece: o PySide6 tem um hook de
# import (`feature._mod_uses_pyside`) que faz `inspect.getsource()` no
# modulo importado, e isso arrasta linecache + tokenize a ler o ficheiro
# fonte do mutagen linha a linha. Sao os 0,70 s da primeira vez.
#
# A cache resolve o caso comum (voltar a uma pasta ja vista) sem mudar o
# comportamento: a chave inclui mtime e tamanho, por isso um ficheiro
# reetiquetado por fora e' relido.
_TAGS_CACHE = {}
_TAGS_CACHE_MAX = 4000


def _tags_title_artist(path):
    """Lê Título/Artista das ETIQUETAS (ID3, Vorbis, MP4…) via mutagen.
    Fonte autoritativa: o nome do ficheiro pode ter o artista e o título em
    qualquer ordem. Devolve (título, artista) ou (None, None).

    Resultado em cache por (caminho, mtime, tamanho) — ver a nota acima.
    """
    _chave = None
    try:
        _st = os.stat(path)
        _chave = (str(path), int(_st.st_mtime), int(_st.st_size))
        _hit = _TAGS_CACHE.get(_chave)
        if _hit is not None:
            return _hit
    except OSError:
        pass

    try:
        import mutagen
        f = mutagen.File(path, easy=True)
        if not f:
            if _chave is not None:
                if len(_TAGS_CACHE) >= _TAGS_CACHE_MAX:
                    _TAGS_CACHE.clear()
                _TAGS_CACHE[_chave] = (None, None)
            return None, None

        def _g(*keys):
            for k in keys:
                v = f.get(k)
                if v:
                    s = (str(v[0]) if isinstance(v, (list, tuple)) else str(v)).strip()
                    if s:
                        return s
            return None
        _res = (_g("title"), _g("artist", "albumartist", "performer"))
        if _chave is not None:
            if len(_TAGS_CACHE) >= _TAGS_CACHE_MAX:
                _TAGS_CACHE.clear()
            _TAGS_CACHE[_chave] = _res
        return _res
    except Exception:
        return None, None


def _parse_name(filename):
    """Fallback (só quando NÃO há etiquetas): (Título, Artista) do nome do
    ficheiro. Convenção 'Artista - Título'; remove o nº de faixa inicial
    ('1.-', '01 -', '10.') sem apanhar títulos que começam por número
    (ex.: '2 Be Real')."""
    import re
    base = os.path.splitext(filename)[0].strip()
    # nº de faixa inicial: exige pontuacao a seguir (.-)) para nao cortar
    # titulos como "2 Be Real".
    base = re.sub(r'^\s*\d+\s*[.\-)]+\s*', '', base).strip()
    if " - " in base:
        artist, title = base.split(" - ", 1)
        artist, title = artist.strip(), title.strip()
        return (title or base), artist          # (Título, Artista)
    return base, ""


def _audio_rows(path, lookup=None, so_base=False):
    """[(full, título, artista, duração, bpm, tom), …] da pasta.

    `lookup(full)` devolve o dict de metadados da base de dados (ou None).

    `so_base=True` NAO abre ficheiro nenhum: usa o nome e o que a base
    souber. E' a passagem rapida com que a lista aparece de imediato; o
    `_populate_folder` chama depois a versao completa numa thread, para as
    faixas que ainda nao estao analisadas.
    """
    rows = []
    try:
        names = sorted(os.listdir(path), key=str.lower)
    except Exception:
        return rows
    for n in names:
        if not n.lower().endswith(_AUDIO_EXTS):
            continue
        full = os.path.join(path, n)
        if so_base:
            # ── PASSAGEM RAPIDA (13/08/2026) ──────────────────────────────
            # Nome do ficheiro + o que a base ja souber, SEM abrir ficheiro
            # nenhum. E' com isto que a lista aparece de imediato; as
            # etiquetas das faixas por analisar chegam depois, numa thread.
            # Ver _populate_folder.
            _t0, _a0 = _parse_name(n)
            _d0 = _b0 = _k0 = ""
            try:
                _i0 = lookup(full) if lookup else None
            except Exception:
                _i0 = None
            if _i0:
                _d0 = _dur_str(_i0.get("duration", 0))
                _bb = _i0.get("bpm")
                if _bb:
                    try:
                        _b0 = f"{float(_bb):.0f}"
                    except (TypeError, ValueError):
                        _b0 = str(_bb)
                _k0 = str(_i0.get("camelot") or _i0.get("key") or "")
                if _i0.get("title"):
                    _t0 = str(_i0["title"])
                if _i0.get("artist") or _i0.get("albumartist"):
                    _a0 = str(_i0.get("artist") or _i0.get("albumartist"))
            rows.append((full, _t0, _a0, _d0, _b0, _k0))
            continue
        # ── A BASE DE DADOS PRIMEIRO (13/08/2026) ─────────────────────────
        # A ordem estava ao contrario: lia-se SEMPRE as etiquetas com o
        # mutagen (uma abertura de ficheiro por faixa, na thread da
        # interface) e logo a seguir o `info` da base sobrepunha-se-lhes.
        # Ou seja, nas faixas ja analisadas — a biblioteca toda — esse
        # trabalho era integralmente deitado fora.
        #
        # Medido: 0,38 s a povoar uma pasta, com musica a tocar. Agora o
        # mutagen so' e' chamado quando a base nao sabe o titulo ou o
        # artista, que e' o caso das pastas ainda por analisar.
        title, artist = _parse_name(n)
        dur = bpm = key = ""
        info = None
        try:
            info = lookup(full) if lookup else None
        except Exception:
            info = None

        t_db = a_db = None
        if info:
            try:
                dur = _dur_str(info.get("duration", 0))
                b = info.get("bpm")
                if isinstance(b, (int, float)) and b:
                    bpm = f"{float(b):.0f}"
                elif b:
                    try:
                        bpm = f"{float(b):.0f}"
                    except Exception:
                        bpm = str(b)
                key = str(info.get("camelot") or info.get("key") or "")
                a = info.get("artist") or info.get("albumartist")
                t = info.get("title")
                a_db = str(a) if a else None
                t_db = str(t) if t else None
            except Exception:
                pass

        # So se abre o ficheiro se a base nao tiver a resposta.
        if not (t_db and a_db):
            t_tag, a_tag = _tags_title_artist(full)
            if t_tag:
                title = t_tag
            if a_tag:
                artist = a_tag
        if t_db:
            title = t_db
        if a_db:
            artist = a_db
        rows.append((full, title, artist, dur, bpm, key))
    return rows


def _col_sort_key(col, s):
    """Chave de ordenação por coluna da PASTA: 0 título / 1 artista (texto),
    2 duração (segundos), 3 BPM (número), 4 Tom (roda de Camelot 1A→12B).
    Valores vazios/inválidos vão para o fim (rank 1)."""
    s = (s or "").strip()
    if col == 2:                                    # duração m:ss / h:mm:ss
        try:
            sec = 0
            for p in s.split(":"):
                sec = sec * 60 + int(p)
            return (0, sec)
        except Exception:
            return (1, 0)
    if col == 3:                                    # BPM numérico
        try:
            return (0, float(s.replace(",", ".")))
        except Exception:
            return (1, 0.0)
    if col == 4:                                    # Camelot: 1A,1B,…,12B
        import re as _re
        m = _re.match(r"^(\d{1,2})\s*([ABab])$", s)
        if m:
            return (0, int(m.group(1)), m.group(2).upper())
        return (1, 99, s.lower())
    return (0 if s else 1, s.lower())               # texto (vazios no fim)


class _SortItem(QTreeWidgetItem):
    """Item da PASTA com comparação inteligente por tipo de coluna."""

    def __lt__(self, other):
        try:
            tree = self.treeWidget()
            col = tree.sortColumn() if tree else 0
            return (_col_sort_key(col, self.text(col))
                    < _col_sort_key(col, other.text(col)))
        except Exception:
            return super().__lt__(other)


class _DragTree(QTreeWidget):
    """Tabela de ficheiros (Título/Artista/Duração/BPM/Tom) cujas linhas
    podem ser ARRASTADAS para os decks (path em UserRole da coluna 0)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAllColumnsShowFocus(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)

    def mimeData(self, items):
        md = QMimeData()
        urls = []
        for it in items:
            p = it.data(0, Qt.ItemDataRole.UserRole)
            if p:
                urls.append(QUrl.fromLocalFile(str(p)))
        if urls:
            md.setUrls(urls)
        return md


class _FolderTree(QWidget):
    """Browser lateral (estilo VirtualDJ): atalhos de topo (Música Local,
    Música, Vídeos, Discos, Ambiente de trabalho, Playlists Geradas) que se
    expandem para subpastas. Clicar numa pasta chama on_select(path)."""

    def __init__(self, roots, on_select=None, log=None, parent=None,
                 on_analyze=None, on_open=None, tr=None):
        super().__init__(parent)
        self.on_select = on_select
        self.on_analyze = on_analyze     # callback(path) — analisar a pasta
        self.on_open = on_open           # callback(path) — abrir no explorador
        # tradutor (chave -> texto no idioma da janela); sem ele fica PT
        self.tr = tr or (lambda k: _tr("pt", k))
        self.log = log or (lambda *_: None)
        self.setObjectName("browserpanel")
        self.setStyleSheet(
            "QWidget#browserpanel{background:#15171a;border:1px solid #2a2a2a;"
            "border-radius:6px;}")
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        hdr = QLabel("BROWSER")
        hdr.setStyleSheet("color:#00e5ff;font-size:12px;font-weight:800;"
                          "letter-spacing:1px;background:transparent;")
        v.addWidget(hdr)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(
            "QTreeWidget{background:#1a1a1a;border:1px solid #2a2a2a;color:#ddd;"
            "font-size:13px;border-radius:5px;} QTreeWidget::item{padding:3px;}"
            "QTreeWidget::item:selected{background:#0077A3;color:#fff;}")
        v.addWidget(self.tree, 1)
        for label, path in roots:
            self._add_root(label, path)
        self.tree.itemExpanded.connect(self._on_expand)
        self.tree.itemClicked.connect(self._on_click)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path or path == "__DRIVES__" or not os.path.isdir(path):
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self.tree)
        menu.setStyleSheet(
            "QMenu{background:#1e2127;color:#e8eaed;border:1px solid #2c313a;"
            "border-radius:6px;padding:4px;} QMenu::item{padding:7px 16px;"
            "border-radius:5px;} QMenu::item:selected{background:#0097A7;"
            "color:#06222a;}")
        act_an = menu.addAction(self.tr("m_analyze"))
        act_op = menu.addAction(self.tr("m_open_loc"))
        chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen == act_an and self.on_analyze:
            self.on_analyze(path)
        elif chosen == act_op and self.on_open:
            self.on_open(path)

    def _add_root(self, label, path):
        """Acrescenta um atalho de topo.

        `path` pode ser:
          • um caminho normal;
          • "__DRIVES__", que se expande nas unidades do sistema;
          • uma LISTA de (etiqueta, caminho), que faz deste um GRUPO — um nó
            que nao e' pasta nenhuma e so' serve para arrumar os que estao
            debaixo dele. E' assim que se faz o «Meu Computador», ao jeito
            do VirtualDJ: um cabecalho com Musica, Videos, Karaoke,
            Documentos, Ambiente de Trabalho e Discos la dentro, em vez de
            seis atalhos soltos na raiz.
        """
        top = QTreeWidgetItem([label])
        if isinstance(path, (list, tuple)):
            # Grupo: sem caminho associado, para o clique nao tentar abrir
            # uma pasta que nao existe. Ver _on_click e _on_expand, que ja
            # ignoram itens sem UserRole.
            top.setData(0, Qt.ItemDataRole.UserRole, None)
            self.tree.addTopLevelItem(top)
            for _lbl, _p in path:
                filho = QTreeWidgetItem([_lbl])
                filho.setData(0, Qt.ItemDataRole.UserRole, _p)
                top.addChild(filho)
                if _p == "__DRIVES__":
                    for d in _drives():
                        self._add_dir_item(filho, d, d)
                elif _p and os.path.isdir(_p):
                    self._add_placeholder(filho)
            top.setExpanded(True)
            return
        top.setData(0, Qt.ItemDataRole.UserRole, path)
        self.tree.addTopLevelItem(top)
        if path == "__DRIVES__":
            for d in _drives():
                self._add_dir_item(top, d, d)
        elif path and os.path.isdir(path):
            self._add_placeholder(top)

    def _add_placeholder(self, item):
        ph = QTreeWidgetItem(["…"])          # UserRole None = placeholder
        item.addChild(ph)

    def _add_dir_item(self, parent, path, label=None):
        child = QTreeWidgetItem([label or os.path.basename(path) or path])
        child.setData(0, Qt.ItemDataRole.UserRole, path)
        parent.addChild(child)
        try:
            # A seta de expansao so' aparece se houver subpastas VISIVEIS —
            # senao ficavam pastas com seta que abriam vazias.
            if any(e.is_dir() and not _pasta_a_ignorar(e.name)
                   for e in os.scandir(path)):
                self._add_placeholder(child)
        except Exception:
            pass

    def _on_expand(self, item):
        # substitui o placeholder por subpastas reais na 1ª expansão
        if (item.childCount() == 1
                and item.child(0).data(0, Qt.ItemDataRole.UserRole) is None):
            item.removeChild(item.child(0))
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path and path != "__DRIVES__" and os.path.isdir(path):
                try:
                    subs = sorted([e.path for e in os.scandir(path)
                                   if e.is_dir()
                                   and not _pasta_a_ignorar(e.name)],
                                  key=str.lower)
                except Exception:
                    subs = []
                for s in subs:
                    self._add_dir_item(item, s)

    def _on_click(self, item, _col):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if (path and path != "__DRIVES__" and os.path.isdir(path)
                and self.on_select):
            self.on_select(path)


class _VTabButton(QPushButton):
    """Separador fininho com o texto escrito na VERTICAL (de baixo p/ cima)."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._vtext = text
        self.setFixedWidth(26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Expanding)

    def setVText(self, t):
        self._vtext = t
        self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)                 # fundo/moldura do botão
        from PySide6.QtGui import QPainter
        from PySide6.QtCore import QRect
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = self.font(); f.setBold(True); f.setPointSize(10)
        p.setFont(f)
        p.setPen(QColor("#00FFFF"))
        p.translate(self.width() / 2.0, self.height() / 2.0)
        p.rotate(-90)                          # texto de baixo para cima
        p.drawText(QRect(-self.height() // 2, -self.width() // 2,
                         self.height(), self.width()),
                   Qt.AlignmentFlag.AlignCenter, self._vtext)
        p.end()

def _aviso_append_ligado():
    """True se a janela ainda avisa sobre _append fora da thread do Qt.

    Lido em TEMPO DE CHAMADA, não uma vez no import: a ponte nativa liga e
    desliga esta flag durante a sessão (ver _silenciar_aviso_append no
    mixai_motor_ponte.py). Se a cacheássemos como constante de módulo, o
    valor apanhado no arranque (True) ficava para sempre e a ponte não
    conseguia silenciar nada.
    """
    try:
        import sys as _s
        return bool(getattr(_s.modules.get("__main__"),
                            "AVISAR_APPEND_FORA_THREAD", True))
    except Exception:
        return True
    
# ═══════════════════════════════════════════════════════════════════════════
class AutoDJSoloWindow(QDialog):
    """Substituto do AutoDJWindow: mesmo fluxo, players embutidos (sem VDJ)."""

    def __init__(self, playlist, main_window_ref=None):
        super().__init__(None)
        self.parent_window = main_window_ref
        self.main_window_ref = main_window_ref
        # idioma: reflete o escolhido na app principal (pt por defeito)
        _lg = str(getattr(main_window_ref, "current_lang", "pt") or "pt")
        self._lang = _lg if _lg in ("pt", "en", "es") else "pt"
        # O DJ PLAYER SEGUE O MESMO IDIOMA (30/08/2026). Os painéis dos decks
        # e a mesa vêm do `mixai_automix_window`, que até aqui tinha os textos
        # escritos à mão em português (e dois em inglês, por distracção).
        # Agora tem o seu próprio dicionário pt/en/es e é aqui que se lhe diz
        # qual usar — no mesmo sítio onde a janela descobre o seu.
        try:
            _idioma_do_player(self._lang)
        except Exception:
            pass
        # A CONSOLA DA MANUTENÇÃO E AS SUITES (30/08/2026). O
        # `mixai_idioma` guarda a escolha no ambiente, e é assim que ela
        # atravessa a fronteira do processo: as suites correm em
        # subprocessos e não sabem nada desta janela. Ver `ambiente()`.
        try:
            import mixai_idioma as _mi
            _mi.definir(self._lang)
        except Exception:
            pass
        self.md = getattr(main_window_ref, "music_data", {}) or {}
        self.playlist = [p for p in (playlist or []) if p]
        # Mixai Fusion V.5: PRESERVA SEMPRE A ORDEM RECEBIDA. A lista que chega
        # do Set Planner / Co-Pilot é curada de propósito (referência em 1.º,
        # sequência de mixagem escolhida) — o player NÃO a reordena. A antiga
        # reordenação automática (order_set_arc quando havia saltos de BPM)
        # trocava a ordem do Set Planner ao carregar; foi desligada por
        # FUSION_PRESERVE_ORDER. Para repor o comportamento antigo, pôr False.
        FUSION_PRESERVE_ORDER = True
        if not FUSION_PRESERVE_ORDER:
            try:
                order_set_arc = _do_app("order_set_arc")
                if len(self.playlist) >= 3 and self._ordem_precisa_arranjo():
                    _o = order_set_arc(self.playlist, self.md,
                                       start_path=self.playlist[0],
                                       max_bpm_step=4.0)
                    if _o and len(_o) >= 2:
                        self.playlist = list(_o)
            except Exception:
                pass

        self.eng: Engine | None = None
        self.dj: AutoDJ | None = None
        self.fx_agent: _CreativeFX | None = None
        self._event_q = collections.deque()
        self._prep = None
        self._gen_thread = None
        self._search_ref_path = None
        self._now_row = None
        self._rem_base = 0.0
        self._rem_t0 = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowFlags(Qt.WindowType.Window |
                            Qt.WindowType.WindowMinMaxButtonsHint |
                            Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle("MixAi Player - Automix")
        self.setMinimumSize(1150, 700)
        self.setWindowState(Qt.WindowState.WindowMaximized)   # abre maximizado
        try:
            resource_path, _apply_dark_titlebar = _do_app(
                "resource_path", "_apply_dark_titlebar")
            ip = resource_path(os.path.join("icons", "mixai_logo.png"))
            if os.path.exists(ip):
                self.setWindowIcon(QIcon(ip))
            QTimer.singleShot(0, lambda: _apply_dark_titlebar(self))
        except Exception:
            pass

        self.setStyleSheet(f"""
            QDialog {{ background-color:#121212; }}
            QLabel {{ color:#f0f0f0; font-size:13px; background:transparent; }}
            QPushButton {{ background-color:#1d1f24; color:#cfd3d7;
                border:1px solid #3a3f44; border-radius:6px;
                padding:9px 12px; font-size:13px; font-weight:600; }}
            QPushButton:hover {{ background:#2a2d33; border-color:#00BCD4; }}
            QPushButton:disabled {{ color:#555; border-color:#333; }}
            QLineEdit {{ background:#1a1a1a; color:#e8e8e8;
                border:1px solid #00BCD4; border-radius:5px;
                padding:6px 10px; font-size:13px; }}
            QComboBox {{ background:#1a1a1a; color:#00FFFF;
                border:1px solid #00BCD4; border-radius:5px; padding:6px; }}
            QComboBox QAbstractItemView {{ background:#1a1a1a; color:#00FFFF;
                selection-background-color:#0077A3; }}
            QListWidget {{ background:#1a1a1a; border:1px solid #2a2a2a;
                color:#ddd; font-size:13px; border-radius:5px; }}
            QListWidget::item {{ padding:4px 8px; border-bottom:1px solid #222; }}
            QListWidget::item:selected {{ background:#0077A3; color:#fff; }}
            QCheckBox {{ color:#f0f0f0; }}
            QSlider::groove:horizontal {{ height:6px; background:#2a2a34; border-radius:3px; }}
            QSlider::handle:horizontal {{ width:18px; height:18px; margin:-7px 0;
                border-radius:9px; background:#cfcfda; }}
            QSlider::groove:vertical {{ width:6px; background:#2a2a34; border-radius:3px; }}
            QSlider::handle:vertical {{ height:16px; margin:0 -6px; border-radius:8px;
                background:#cfcfda; }}
        """)
        self._build_ui()
        _t_fl = time.monotonic()
        self._fill_list()
        _dt_fill = time.monotonic() - _t_fl
        _dt_show = 0.0
        if self.playlist:               # já abriu com um set → mostra a aba
            _t_sp = time.monotonic()
            self._show_playlist(True)
            _dt_show = time.monotonic() - _t_sp
        # ── FECHA A CONTA DO "construir" (18/09/2026) ────────────────────
        # `_build_ui` já fala das suas próprias fatias (ver os `_fatia_ui`
        # lá dentro); isto aqui é só para confirmar que não sobra tempo
        # fora dela — `_fill_list`/`_show_playlist` só mexem na playlist
        # recebida (poucas faixas), nunca na biblioteca inteira.
        try:
            if (str(os.environ.get("MIXAI_TEMPOS", "")).strip()
                    in ("1", "sim", "yes", "true")
                    or (_dt_fill + _dt_show) >= 0.5):
                print(f"[tempos] __init__ DJ Player, fora do _build_ui: "
                     f"_fill_list {_dt_fill:.2f}s · "
                     f"_show_playlist {_dt_show:.2f}s")
        except Exception:
            pass
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)
        # vigia da interface (ver _VigiaUI): escreve na consola a pilha da
        # thread principal sempre que ela ficar parada mais tempo que o
        # limite.
        # 0,20 s (era 0,35): as paragens que sobram nas transicoes do automix
        # andam nos 0,38 s e ficavam mesmo no fio do limite antigo — o vigia
        # ora as apanhava ora nao, conforme o instante em que amostrava, e sem
        # pilha nao ha' como saber onde e'. Voltar a subir quando estiverem
        # resolvidas: mais baixo do que isto comeca a acusar pausas normais.
        # ... e so' com o diagnostico ligado. Cada paragem faz o vigia
        # despejar 10 a 25 linhas na consola A PARTIR DE OUTRA THREAD; a
        # thread principal, se estiver a escrever, fica a espera do mesmo
        # handle. Um vigia que nao escreve nao serve para nada, portanto
        # nem se levanta.
        self._vigia = None
        if DIAGNOSTICO_UI:
            try:
                self._vigia = _VigiaUI(limite=0.20)
                self._vigia.start()
            except Exception as _e_vig:
                self._vigia = None
                print(f"[VigiaUI] não arrancou: {_e_vig}")
        self.ddj = None
        self.mixer.log = self._append               # log da pré-escuta
        # os decks também escrevem no log (ex.: o beat-lock a soltar-se ao
        # repor o pitch); sem isto a mensagem ia parar à consola, que quem
        # arranca pela app não vê.
        for _p in (self.deckA, self.deckB):
            try:
                _p.log = self._append
            except Exception:
                pass
        # motor ATIVO logo ao abrir (decks/mixer/controladora prontos, sem
        # ter de carregar uma música primeiro)
        QTimer.singleShot(300, self._ensure_engine)
        QTimer.singleShot(900, self._connect_ddj)   # liga a controladora

    def _ordem_precisa_arranjo(self) -> bool:
        """True se a playlist chega DESORDENADA — 2+ saltos de BPM > 8 entre
        faixas seguidas. Uma lista do gerador nunca dispara isto (vem
        encadeada); uma .m3u importada à toa pode. Sem isto, reordenar toda a
        vez destruía a sequência de mixagem que o gerador construiu."""
        try:
            _b = []
            for p in self.playlist:
                inf = self.md.get(os.path.normpath(p), {}) or {}
                try:
                    v = float(inf.get("bpm", 0) or 0)
                except (TypeError, ValueError):
                    v = 0.0
                _b.append(v)
            grandes = sum(1 for i in range(len(_b) - 1)
                          if _b[i] > 0 and _b[i + 1] > 0
                          and abs(_b[i] - _b[i + 1]) > 8.0)
            return grandes >= 2
        except Exception:
            return False

    # ── UI ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── ONDE SE VÃO OS 4s DO "construir" (18/09/2026) ────────────────
        #
        # O `[tempos] abrir o DJ Player` (mixai_fusion_automix.py) já isola
        # "construir" (o `AutoDJSoloWindow.__init__` inteiro) dos outros
        # passos, mas White reportou "construir 4.14s" sem dizer ONDE
        # dentro disso — e não vale a pena adivinhar duas vezes seguidas.
        # Marcos internos, mesmo espírito: só falam acima de meio segundo
        # (ou sempre, com MIXAI_TEMPOS=1), e dizem exactamente qual troço
        # do `_build_ui` (decks+mixer, que criam um `Engine()` cada, o
        # browser lateral, a tabela de pesquisa, ...) pesou mais.
        _t0_ui = time.monotonic()
        _passos_ui = []

        def _fatia_ui(nome):
            nonlocal _t0_ui
            _agora = time.monotonic()
            _passos_ui.append((nome, _agora - _t0_ui))
            _t0_ui = _agora

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Header (igual ao Automix antigo, sem MIDI) ----
        header = QWidget()
        header.setFixedHeight(76)
        header.setObjectName("hdr")
        header.setStyleSheet(
            "QWidget#hdr{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0e0e0e, stop:0.5 #1a1a1a, stop:1 #0e0e0e);"
            "border-bottom:2px solid #00BCD4;}")
        hh = QHBoxLayout(header)
        hh.setContentsMargins(16, 8, 16, 12)
        hh.setSpacing(10)
        logo = QLabel()
        try:
            lp = _do_app("resource_path")(os.path.join("icons",
                                                       "mixai_logo.png"))
            if os.path.exists(lp):
                pm = QPixmap(lp)
                if not pm.isNull():
                    logo.setPixmap(pm.scaledToHeight(
                        26, Qt.TransformationMode.SmoothTransformation))
        except Exception:
            pass
        logo.setStyleSheet("background:transparent;")
        hh.addWidget(logo)
        pro = QLabel("Dj Pro · Copilot")
        pro.setStyleSheet("font-size:15px;font-weight:bold;color:#00FFFF;"
                          "background:transparent;letter-spacing:1px;")
        hh.addWidget(pro)
        hh.addSpacing(14)
        lb_mt = QLabel("MASTER")
        lb_mt.setStyleSheet("color:#00BCD4;font-weight:800;background:transparent;")
        hh.addWidget(lb_mt)
        self.master_spin = QSpinBox()
        self.master_spin.setRange(59, 200)
        self.master_spin.setValue(59)                 # 59 = AUTO
        self.master_spin.setSpecialValueText("AUTO")
        self.master_spin.setSuffix(" BPM")
        self.master_spin.setFixedHeight(34)
        self.master_spin.setFixedWidth(110)
        self.master_spin.setFixedWidth(122)
        self.master_spin.setStyleSheet(
            "QSpinBox{background:#16212a;color:#00FFFF;border:2px solid #00BCD4;"
            "border-radius:6px;padding:4px 6px;font-size:13px;font-weight:bold;}"
            "QSpinBox::up-button,QSpinBox::down-button{width:16px;"
            "background:#16212a;border-left:1px solid #00BCD4;}"
            "QSpinBox::up-button{border-top-right-radius:4px;}"
            "QSpinBox::down-button{border-bottom-right-radius:4px;}")
        self.master_spin.setToolTip(self._t("master_tip"))
        hh.addWidget(self.master_spin)
        # ── REC: gravação do set em MP3 ────────────────────────────────
        # O botão é CRIADO aqui (precisa dos estilos _REC_* que se definem a
        # seguir) mas entra no cabeçalho lá mais abaixo, entre o «Parar» e o
        # «MixAi Co-Pilot» — ver o addWidget no fim deste bloco de topo.
        # Esteve ao lado do MASTER AUTO até 28/08/2026.
        # mesmo padding dos restantes botões do topo (altura igual)
        # ── REC: gravação do set em MP3 (mesmo estilo de Parar / Limpar / Remover) ──
        _REC_PAD = ("border-radius:6px;padding:9px 6px;font-size:13px;"
                    "font-weight:bold;")
        self._REC_OFF = ("QPushButton{background:#2e0d13;color:#ff4658;"
                         "border:1px solid #ff0045;" + _REC_PAD + "}"
                         "QPushButton:hover{background:#3d1019;}"
                         "QPushButton:disabled{color:#6a6a6a;border-color:#444;}")
        self._REC_ARM = ("QPushButton{background:#332b0d;color:#ffcc00;"
                         "border:1px solid #ffcc00;" + _REC_PAD + "}"
                         "QPushButton:hover{background:#403512;}")
        self._REC_ON = ("QPushButton{background:#ff0045;color:#ffffff;"
                        "border:1px solid #ff0045;" + _REC_PAD + "}"
                        "QPushButton:hover{background:#d60039;}")
        self.rec_btn = QPushButton(self._t("rec_off"))
        self.rec_btn.setFixedWidth(126)
        self.rec_btn.setStyleSheet(self._REC_OFF)
        self.rec_btn.setToolTip(self._t("rec_tip"))
        self.rec_btn.clicked.connect(self._rec_clicked)
        # (o addWidget do REC está lá em baixo, a seguir ao «Parar»)

        _BASE = "border-radius:6px;padding:10px 6px;font-size:13px;font-weight:bold;"
        _cyan = ("QPushButton{background:#16212a;color:#00FFFF;border:1px solid #00BCD4;" + _BASE + "}"
                 "QPushButton:hover{background:#0e2a33;}"
                 "QPushButton:disabled{color:#6a6a6a;border-color:#444;}")
        _red = ("QPushButton{background:#2e0d13;color:#ff4658;border:1px solid #ff0045;" + _BASE + "}"
                "QPushButton:hover{background:#3d1019;}"
                "QPushButton:disabled{color:#6a6a6a;border-color:#444;}")
        _purple = ("QPushButton{background:#512DA8;color:#ffffff;border:1px solid #673AB7;" + _BASE + "}"
                   "QPushButton:hover{background:#673AB7;}")

        # ⚙ MANUTENÇÃO. Estreito, porque não é um botão de palco — é para
        # antes e depois do set. Criado aqui, mas ENTRA NA BARRA lá em baixo,
        # entre o «Parar» e o REC (30/08/2026): estava colado ao AUTO, na
        # ponta esquerda, onde ficava no caminho dos botões que se usam a
        # tocar. Entre o «Parar» e o REC fica com os outros dois que também
        # não são de palco, e longe do «Seguinte»/«Iniciar».
        self.manut_btn = QPushButton("⚙")
        self.manut_btn.setFixedWidth(44)
        self.manut_btn.setToolTip(self._t("man_tip"))
        self.manut_btn.setStyleSheet(_cyan)
        self.manut_btn.clicked.connect(self._abrir_manutencao)

        self.history_btn = QPushButton(self._t("history"))
        self.history_btn.setStyleSheet(_cyan)
        self.history_btn.clicked.connect(self._load_history)
        hh.addWidget(self.history_btn, 1)
        # 'Seguinte' vive aqui em cima, no lugar onde estava o 'Remover'.
        # O 'Remover' passou para a barra de baixo, junto do Gerar Playlist e
        # do Limpar — sao todos accoes sobre a lista.
        self.next_btn = QPushButton(self._t("next"))
        self.next_btn.setStyleSheet(_cyan)
        self.next_btn.clicked.connect(self._next_track)
        hh.addWidget(self.next_btn, 1)
        self.start_btn = QPushButton(self._t("start"))
        self.start_btn.setStyleSheet(_cyan)
        self.start_btn.clicked.connect(self._start)
        hh.addWidget(self.start_btn, 1)
        self.stop_btn = QPushButton(self._t("stop"))
        self.stop_btn.setStyleSheet(_red)
        self.stop_btn.clicked.connect(self._stop_clicked)
        hh.addWidget(self.stop_btn, 1)
        # o ⚙ entra AQUI, entre o «Parar» e o REC. Esticamento ZERO: tem
        # largura fixa de 44 px e não deve roubar espaço aos vizinhos.
        hh.addWidget(self.manut_btn, 0)
        # REC entre o «Parar» e o «MixAi Co-Pilot» (28/08/2026). Entra com
        # esticamento ZERO de propósito: tem largura fixa de 126 px porque o
        # texto muda (OFF → ON → tempo decorrido) e sem isso o botão saltava
        # de tamanho a meio da gravação. Dar-lhe stretch 1 como aos vizinhos
        # não o faria crescer — a largura fixa manda —, mas roubava uma parte
        # do espaço que o layout tem para repartir pelos outros.
        hh.addWidget(self.rec_btn, 0)
        self.main_btn = QPushButton("↩ MixAi Co-Pilot")
        self.main_btn.setStyleSheet(_purple)
        self.main_btn.clicked.connect(self._show_main)
        hh.addWidget(self.main_btn, 1)
        outer.addWidget(header)

        # ---- Barra de pesquisa + referência + Gerar Playlist + Limpar ----
        sbar = QWidget()
        sbar.setObjectName("sbar")
        sbar.setStyleSheet(
            "QWidget#sbar{background:#0a0a0a;border-bottom:1px solid #1e1e1e;}")
        sbar.setMinimumHeight(72)
        sb = QHBoxLayout(sbar)
        sb.setContentsMargins(10, 10, 10, 16)
        sb.setSpacing(8)
        sb.setSpacing(8)
        self._ref_label = QLabel(self._t("ref_hint"))
        self._ref_label.setStyleSheet("color:#555;font-size:12px;background:transparent;")
        self._ref_label.setFixedWidth(360)
        sb.addWidget(self._ref_label)
        lupa = QLabel("🔍"); lupa.setStyleSheet("color:#00BCD4;background:transparent;")
        sb.addWidget(lupa)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(self._t("search_ph"))
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(360)
        self._search_edit.setFixedHeight(38)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._on_search_filter)
        self._search_edit.textChanged.connect(self._search_timer.start)
        sb.addWidget(self._search_edit)
        self._gen_btn = QPushButton(self._t("gen_pl"))
        self._gen_btn.setStyleSheet(
            "QPushButton{background:#512DA8;color:#ffffff;border:1px solid #673AB7;"
            "border-radius:5px;padding:6px 16px;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:#673AB7;}"
            "QPushButton:pressed{background:#311B92;}"
            "QPushButton:disabled{color:#8a8a96;border-color:#3a2f57;background:#241b3a;}")
        self._gen_btn.setEnabled(False)
        self._gen_btn.setFixedHeight(38)
        self._gen_btn.clicked.connect(self._generate_playlist)
        sb.addWidget(self._gen_btn)
        self._clear_btn = QPushButton(self._t("clear"))
        self._clear_btn.setStyleSheet(
            "QPushButton{background:#2e0d13;color:#ff4658;border:1px solid #ff0045;"
            "border-radius:5px;padding:6px 16px;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:#3d1019;}")
        self._clear_btn.setFixedHeight(38)
        self._clear_btn.clicked.connect(self._search_clear)
        sb.addWidget(self._clear_btn)
        self.remove_btn = QPushButton(self._t("remove"))
        self.remove_btn.setFixedHeight(38)
        self.remove_btn.setStyleSheet(
            "QPushButton{background:#2e0d13;color:#ff4658;border:1px solid #ff0045;"
            "border-radius:5px;padding:6px 16px;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:#3d1019;}"
            "QPushButton:disabled{color:#6a6a6a;border-color:#444;}")
        self.remove_btn.clicked.connect(self._remove_selected)
        sb.addWidget(self.remove_btn)
        sb.addSpacing(8)
        lb_ph = QLabel("PFL")
        lb_ph.setStyleSheet("color:#00BCD4;font-size:12px;font-weight:800;"
                            "background:transparent;")
        sb.addWidget(lb_ph)
        self.phones_combo = QComboBox()
        self.phones_combo.setMinimumWidth(220)
        self.phones_combo.setFixedHeight(38)
        self.phones_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.phones_combo.addItem(self._t("auto_hw"), None)
        self._th_saidas_som = _CarregarSaidasThread(self)
        self._th_saidas_som.pronto.connect(self._preencher_saidas_som)
        self._th_saidas_som.start()
        self.phones_combo.setToolTip(self._t("phones_tip"))
        self.phones_combo.currentIndexChanged.connect(self._phones_changed)
        sb.addWidget(self.phones_combo, 1)
        self._search_bar_widget = sbar

        _fatia_ui("cabecalho+barra_pesquisa")

        # ---- RHYTHM WAVE (grelha de batidas, estilo VDJ) ----
        self.rhythm = RhythmWave()
        outer.addWidget(self.rhythm)
        _fatia_ui("rhythm_wave")

        # ---- DECKS + MIXER (os players embutidos) ----
        decks_row = QHBoxLayout()
        decks_row.setContentsMargins(12, 10, 12, 4)
        decks_row.setSpacing(10)
        self._eng_tmp = Engine()
        _fatia_ui("engine_temporario")
        self.deckA = DeckPanel("A", COL_A, self._eng_tmp)
        _fatia_ui("deckpanel_A")
        self.mixer = MixerPanel(self._eng_tmp)
        _fatia_ui("mixerpanel")
        self.deckB = DeckPanel("B", COL_B, self._eng_tmp)
        _fatia_ui("deckpanel_B")
        self.deckA.on_drop = lambda p: self._manual_load("A", p)
        self.deckB.on_drop = lambda p: self._manual_load("B", p)
        decks_row.addWidget(self.deckA, 5)
        decks_row.addWidget(self.mixer, 2)
        decks_row.addWidget(self.deckB, 5)
        outer.addLayout(decks_row)

        # crossfader
        from PySide6.QtWidgets import QSlider
        xf_row = QHBoxLayout()
        xf_row.setContentsMargins(12, 0, 12, 4)
        la = QLabel("A"); la.setStyleSheet(f"color:{COL_A};font-weight:900;")
        lb = QLabel("B"); lb.setStyleSheet(f"color:{COL_B};font-weight:900;")
        self.sl_xf = QSlider(Qt.Horizontal)
        self.sl_xf.setRange(0, 1000)
        # LADOS FIXOS que pintam PROGRESSIVAMENTE ao arrastar:
        #   sub-page (à esquerda do cursor) = AZUL  → o rasto que fica atrás
        #     do cursor a caminho de B; cresce ao avançar para a direita.
        #   add-page (à direita do cursor) = VERMELHO → o que ainda falta de A;
        #     encolhe ao avançar.
        # Assim: crossfader em A mostra a barra VERMELHA (add-page grande);
        # em B mostra AZUL (sub-page grande); e a transição pinta o azul e
        # limpa o vermelho à medida que o cursor caminha. NÃO troca a cor toda
        # de repente no centro — foi esse o erro anterior.
        self.sl_xf.setStyleSheet(
            "QSlider::groove:horizontal{height:8px;border-radius:4px;"
            "background:#2a2a34;}"
            # Atencao as chavetas: a linha de cima e f-string (por isso {{ = "{"),
            # mas ESTA nao e — aqui "}}" sairia mesmo como duas chavetas e o Qt
            # rejeitava a folha inteira ("Could not parse stylesheet"). Uma so.
            f"QSlider::sub-page:horizontal{{background:{COL_B};"
            "border-top-left-radius:4px;border-bottom-left-radius:4px;}"
            f"QSlider::add-page:horizontal{{background:{COL_A};"
            "border-top-right-radius:4px;border-bottom-right-radius:4px;}"
            "QSlider::handle:horizontal{width:20px;height:20px;margin:-7px 0;"
            "border-radius:10px;background:#eaeaf2;border:2px solid #10121a;}")
        self.sl_xf.valueChanged.connect(self._xf_moved)
        # ── BOTÃO REDONDO: liga/desliga o crossfader ──────────────────────
        # Desligado, os dois decks passam inteiros e mistura-se só com os
        # faders de canal (é o "assign THRU" dos Pioneer). Serve para quem
        # não quer o crossfader no caminho, e é a rede de segurança para um
        # crossfader que ficou preso de um lado a meio de um set.
        self.bt_xf = QPushButton("ON")
        self.bt_xf.setCheckable(True)
        self.bt_xf.setChecked(True)
        self.bt_xf.setFixedSize(34, 34)
        self.bt_xf.setCursor(Qt.PointingHandCursor)
        self.bt_xf.toggled.connect(self._xf_toggled)
        self._restyle_bt_xf(True)
        xf_row.addWidget(la)
        xf_row.addWidget(self.sl_xf, 1)
        xf_row.addWidget(lb)
        xf_row.addSpacing(8)
        xf_row.addWidget(self.bt_xf)
        outer.addLayout(xf_row)
        outer.addWidget(sbar)          # pesquisa + gerar/limpar + MASTER
        _fatia_ui("crossfader+resto_da_mesa")

        # ---- conteúdo: browser | pasta + playlist | agente ----
        content = QHBoxLayout()
        content.setContentsMargins(12, 4, 12, 12)
        content.setSpacing(12)
        outer.addLayout(content, 1)
        self._content_split = QSplitter(Qt.Orientation.Horizontal)
        self._content_split.setChildrenCollapsible(False)
        content.addWidget(self._content_split)

        # 1) BROWSER de pastas (esquerda) — atalhos estilo VirtualDJ
        self.browser = _FolderTree(self._build_folder_roots(),
                                   on_select=self._browser_select,
                                   on_analyze=self._analyze_folder,
                                   on_open=self._open_folder_explorer,
                                   log=self._append,
                                   tr=self._t)
        self._content_split.addWidget(self.browser)
        _fatia_ui("browser_pastas")

        # 2) MÚSICAS DA PASTA selecionada (centro) — tabela arrastável
        fpanel = QWidget(); fpanel.setObjectName("sidepanel")
        fpanel.setStyleSheet(
            "QWidget#sidepanel{background:#15171a;border:1px solid #2a2a2a;"
            "border-radius:6px;}")
        fpv = QVBoxLayout(fpanel)
        fpv.setContentsMargins(8, 8, 8, 8); fpv.setSpacing(6)
        self._folder_lbl = QLabel(self._t("folder_hdr"))
        self._folder_lbl.setStyleSheet(
            "color:#00e5ff;font-size:12px;font-weight:800;letter-spacing:1px;"
            "background:transparent;")
        fpv.addWidget(self._folder_lbl)
        # barra de progresso da ANÁLISE da pasta (oculta até analisares)
        self._an_bar = QProgressBar()
        self._an_bar.setRange(0, 100)
        self._an_bar.setTextVisible(True)
        self._an_bar.setFixedHeight(18)
        self._an_bar.setVisible(False)
        self._an_bar.setStyleSheet(
            "QProgressBar{background:#1a1a1a;border:1px solid #2a2a2a;"
            "border-radius:4px;color:#e8eaed;font-size:11px;text-align:center;}"
            "QProgressBar::chunk{background:#00BCD4;border-radius:3px;}")
        self._an_file = ""
        fpv.addWidget(self._an_bar)
        self.folder_files = _DragTree()
        self.folder_files.setColumnCount(5)
        self.folder_files.setHeaderLabels(
            [self._t("hdr_title"), self._t("hdr_artist"),
             self._t("hdr_dur"), "BPM", self._t("hdr_key")])
        # ORDENAÇÃO por clique no cabeçalho (asc/desc); a ordem natural da
        # pasta mantém-se até ao 1.º clique (indicador a -1)
        self.folder_files.setSortingEnabled(True)
        try:
            _h = self.folder_files.header()
            _h.setSortIndicatorShown(True)
            _h.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        except Exception:
            pass
        self.folder_files.setStyleSheet(
            "QTreeWidget{background:#1a1a1a;border:1px solid #2a2a2a;color:#ddd;"
            "font-size:12px;border-radius:5px;}"
            "QHeaderView::section{background:#22262b;color:#9aa0a6;padding:4px;"
            "border:0;border-right:1px solid #2a2a2a;}"
            "QTreeWidget::item{padding:2px 4px;}"
            "QTreeWidget::item:selected{background:#0077A3;color:#fff;}")
        try:
            hdr = self.folder_files.header()
            from PySide6.QtWidgets import QHeaderView
            hdr.setStretchLastSection(False)
            # Título e Artista esticam e ocupam o espaço livre (sem folga
            # depois do 'Tom'); Duração/BPM/Tom ficam estreitas e fixas
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            for c in (2, 3, 4):
                hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.folder_files.setColumnWidth(2, 70)
            self.folder_files.setColumnWidth(3, 56)
            self.folder_files.setColumnWidth(4, 52)
        except Exception:
            pass
        self.folder_files.itemDoubleClicked.connect(
            self._on_folder_item_dclick)
        self.folder_files.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_files.customContextMenuRequested.connect(
            self._folder_ctx_menu)
        fpv.addWidget(self.folder_files, 1)
        fhint = QLabel(self._t("drag_hint"))
        # LEGIBILIDADE. Estava a #6a7075 sobre um painel quase preto — um
        # cinzento a 1.9:1 de contraste, abaixo de qualquer limiar de
        # leitura. É a linha que explica o que se pode fazer com a lista,
        # portanto quem mais precisa dela é quem ainda não sabe. Sobe para
        # #9aa3ad (≈5.5:1) e 12 px: continua discreta, mas lê-se.
        fhint.setStyleSheet(
            "color:#9aa3ad;font-size:12px;background:transparent;")
        fpv.addWidget(fhint)
        self._content_split.addWidget(fpanel)

        # 3) AGENTE (direita) — como antes
        side = QWidget()
        side.setMinimumWidth(280)
        side.setObjectName("sidepanel")
        side.setStyleSheet(
            "QWidget#sidepanel{background:#15171a;border:1px solid #2a2a2a;"
            "border-radius:6px;}")
        sv = QVBoxLayout(side)
        sv.setContentsMargins(12, 12, 12, 12)
        sv.setSpacing(8)
        self._lbl_total = QLabel("")
        self._lbl_total.setStyleSheet("color:#00e5ff;font-size:13px;font-weight:bold;")
        sv.addWidget(self._lbl_total)
        self._lbl_master = QLabel("")
        self._lbl_master.setStyleSheet("color:#9aa0a6;font-size:12px;")
        sv.addWidget(self._lbl_master)
        ar = QHBoxLayout()
        lb_ag = QLabel(self._t("agent")); lb_ag.setStyleSheet("color:#9aa0a6;font-size:12px;")
        ar.addWidget(lb_ag)
        self.fx_check = QCheckBox("Creative FX")
        self.fx_check.setChecked(True)
        self.fx_check.toggled.connect(self._fx_toggled)
        ar.addWidget(self.fx_check)
        self.fx_intensity = QComboBox()
        self.fx_intensity.addItems(["rare", "medium", "frequent"])
        self.fx_intensity.setCurrentText("medium")
        self.fx_intensity.currentTextChanged.connect(self._fx_intensity_changed)
        ar.addWidget(self.fx_intensity)
        self.ddj_btn = QPushButton(self._t("monitor_off"))
        self.ddj_btn.setCheckable(True)
        self.ddj_btn.setStyleSheet(
            "QPushButton{background:#1d1f24;color:#cfd3d7;border:1px solid "
            "#3a3f44;border-radius:5px;padding:6px 12px;font-weight:600;}"
            "QPushButton:hover{border-color:#00BCD4;}"
            "QPushButton:checked{background:#16212a;color:#00FFFF;"
            "border-color:#00BCD4;}")
        self.ddj_btn.setToolTip(self._t("ddj_tip"))
        self.ddj_btn.toggled.connect(self._ddj_toggle)
        ar.addWidget(self.ddj_btn)
        ar.addStretch()
        sv.addLayout(ar)
        lb_ac = QLabel(self._t("agent_log"))
        lb_ac.setStyleSheet("color:#9aa0a6;font-size:12px;")
        sv.addWidget(lb_ac)
        self.log_box = QTextEdit(); self.log_box.setReadOnly(True)
        # TETO no log: sem isto o documento cresce sem fim e cada append
        # relayouta um documento cada vez maior — a UI degrada com as horas
        # (bares/hotéis). 500 linhas chegam; o ficheiro ~/.mixai_cache
        # continua a guardar TUDO (via _flog).
        try:
            self.log_box.document().setMaximumBlockCount(500)
        except Exception:
            pass
        self.log_box.setStyleSheet(
            "background:#0e1013;color:#cfd3d7;font-family:Consolas,monospace;"
            "font-size:14px;border:1px solid #2a2a2a;border-radius:5px;")
        sv.addWidget(self.log_box, 1)

        # splitter esquerdo (redimensionável): browser | pasta
        self._content_split.setStretchFactor(0, 2)   # browser
        self._content_split.setStretchFactor(1, 6)   # pasta (grande)
        self._content_split.setSizes([260, 900])
        content.setStretchFactor(self._content_split, 1)
        _fatia_ui("pasta+agente+log")

        # ---- aba vertical: abre/fecha a playlist (ao centro) ----
        self._pl_tab = _VTabButton("◀  PLAYLIST")
        self._pl_tab.setStyleSheet(
            "QPushButton{background:#16212a;border:1px solid #00BCD4;"
            "border-radius:5px;} QPushButton:hover{background:#0e2a33;}")
        self._pl_tab.setToolTip(self._t("pl_tab_tip"))
        self._pl_tab.clicked.connect(self._toggle_playlist)
        content.addWidget(self._pl_tab)

        # ---- PLAYLIST GERADA (recolhível — divide o espaço das pastas) ----
        self.playlist_panel = QWidget()
        self.playlist_panel.setObjectName("sidepanel")
        self.playlist_panel.setStyleSheet(
            "QWidget#sidepanel{background:#15171a;border:1px solid #2a2a2a;"
            "border-radius:6px;}")
        self.playlist_panel.setMinimumWidth(300)
        self.playlist_panel.setMaximumWidth(560)
        ppv = QVBoxLayout(self.playlist_panel)
        ppv.setContentsMargins(8, 8, 8, 8); ppv.setSpacing(6)
        prow = QHBoxLayout()
        plbl = QLabel(self._t("gen_pl_hdr"))
        plbl.setStyleSheet(
            "color:#00e5ff;font-size:12px;font-weight:800;letter-spacing:1px;"
            "background:transparent;")
        prow.addWidget(plbl); prow.addStretch(1)
        # MIX CONTÍNUO (∞) — no topo da playlist, que é onde faz sentido:
        # é a playlist que deixa de acabar.
        # o texto vem já do dicionário: o construtor não deve ter uma
        # etiqueta em português à espera de ser substituída (era o único
        # sítio da janela onde ainda havia uma).
        self.inf_check = QCheckBox(self._t("inf_chk"))
        self.inf_check.setChecked(False)
        self.inf_check.setStyleSheet(
            "QCheckBox{color:#00e5ff;font-size:12px;font-weight:700;"
            "background:transparent;}")
        self.inf_check.setToolTip(self._t("inf_tip"))
        self.inf_check.toggled.connect(self._inf_toggled)
        prow.addWidget(self.inf_check)
        prow.addSpacing(8)
        bt_hide = QPushButton("✕")
        bt_hide.setFixedSize(22, 22)
        bt_hide.setToolTip(self._t("hide_pl"))
        bt_hide.clicked.connect(lambda: self._show_playlist(False))
        prow.addWidget(bt_hide)
        ppv.addLayout(prow)
        self.list_widget = _DragFileList()
        self.list_widget.on_drop_paths = self._playlist_dropped
        self.list_widget.on_reorder = self._playlist_reordenada
        # MENU DE CONTEXTO TAMBEM AQUI (15/08/2026). O browser tinha-o desde
        # sempre; a playlist gerada nao. Mas e' na playlist que se percebe
        # que uma grelha esta torta — e' la' que se ve' a ordem do set.
        self.list_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(
            self._playlist_ctx_menu)
        ppv.addWidget(self.list_widget, 1)
        content.addWidget(self.playlist_panel)

        # ---- AGENTE (extremo direito, como antes) ----
        side.setMaximumWidth(400)
        content.addWidget(side)

        # começa RECOLHIDA (aparece ao clicar na aba ou ao gerar playlist)
        self._show_playlist(False)

        # tabela de pesquisa flutuante (reusa o motor da app principal)
        self._search_table = None
        try:
            self._search_table = _do_app("MusicListWidget")(parent=self)
            self._search_table.main_window_ref = self.main_window_ref
            # pesquisa LOCAL ao Automix Player: não mexe na lista nem na
            # vista da interface principal (ver filterMusic)
            self._search_table.standalone_search = True

            # CABECALHOS DAS COLUNAS.
            #
            # A MusicListWidget nasce com os titulos VAZIOS — quem os preenche
            # e o update_gui_texts() da janela principal, que nunca corre para
            # esta instancia. Resultado: sete colunas de numeros sem se saber
            # o que sao.
            #
            # Usam-se os mesmos textos da janela principal quando ela existe,
            # para nao divergirem nem perderem a traducao; senao, portugues.
            try:
                _tx = {}
                _mw = self.main_window_ref
                if _mw is not None:
                    _tx = (getattr(_mw, "current_texts", None)
                           or getattr(_mw, "texts", None) or {})
                self._search_table.setHorizontalHeaderLabels([
                    _tx.get("header_track") or self._t("header_track"),
                    _tx.get("header_bpm") or self._t("header_bpm"),
                    _tx.get("header_camelot") or self._t("header_camelot"),
                    _tx.get("header_loudness") or self._t("header_loudness"),
                    _tx.get("header_energy") or self._t("header_energy"),
                    _tx.get("header_centroid") or self._t("header_centroid"),
                    _tx.get("header_cluster") or self._t("header_cluster"),
                    (_tx.get("header_compatibility")
                     or self._t("header_compatibility")),
                ])
                self._search_table.horizontalHeader().setVisible(True)
            except Exception:
                pass

            self._search_table.hide()
            self._search_table.itemDoubleClicked.connect(self._on_search_row_dclick)
        except Exception as e:
            self._append(self._tf("l_search_na", e=e))
        _fatia_ui("playlist_panel+tabela_pesquisa")

        # ── FALA SÓ SE HOUVER ALGO A DIZER (18/09/2026, mesmo espírito do
        # `_dizer_tempos` do mixai_fusion_automix): acima de meio segundo,
        # ou sempre com MIXAI_TEMPOS=1.
        try:
            _total_ui = sum(s for _, s in _passos_ui)
            _falar_sempre_ui = str(os.environ.get("MIXAI_TEMPOS", "")).strip() in (
                "1", "sim", "yes", "true")
            if _falar_sempre_ui or _total_ui >= 0.5:
                _det_ui = " · ".join(f"{n} {s:.2f}s" for n, s in _passos_ui
                                     if s >= 0.005)
                print(f"[tempos] construir DJ Player: {_total_ui:.2f}s  "
                     f"({_det_ui or 'sem passo mensuravel'})")
        except Exception:
            pass

    # ── pesquisa / gerar playlist (mesmo fluxo do antigo) ────────────────
    def _position_search_overlay(self):
        try:
            from PySide6.QtCore import QPoint
            t = self._search_table
            sb = self._search_bar_widget
            if t is None or sb is None:
                return
            top = sb.mapTo(self, QPoint(0, sb.height())).y()
            m = 8
            t.setGeometry(m, top, max(200, self.width() - 2 * m),
                          max(120, self.height() - top - m))
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._search_table is not None and self._search_table.isVisible():
            self._position_search_overlay()

    def _on_search_filter(self):
        """Pesquisa na base de dados (memória) e nos discos.

        Géneros são estritos: «disco» casa Disco / Nu-Disco / Disco House
        e nomes com disco — NÃO House/Pop nem Afro House só por
        compatibilidade harmónica (isso fica no Set Planner).
        """
        import unicodedata

        texto = self._search_edit.text().strip()
        if self._search_table is not None:
            self._search_table.hide()

        raiz = getattr(self, "_pasta_actual", None)
        if not texto:
            self._busca_token = None
            if raiz:
                self._populate_folder(raiz)
            return

        def _remover_acentos(txt):
            if not txt:
                return ""
            return unicodedata.normalize('NFKD', str(txt)).encode(
                'ASCII', 'ignore').decode('utf-8').lower()

        def _partes_genero(g):
            s = _remover_acentos(g).replace('-', ' ').replace('_', ' ')
            partes = []
            buf = []
            for ch in s:
                if ch in '/|;,&':
                    p = ''.join(buf).strip()
                    if p:
                        partes.append(p)
                    buf = []
                else:
                    buf.append(ch)
            p = ''.join(buf).strip()
            if p:
                partes.append(p)
            return partes, s

        def _genero_estrito(genero, termo):
            """Subgénero / alias. Sem grafo de compatibilidade."""
            t = _remover_acentos(termo).replace('-', ' ').replace('_', ' ').strip()
            if not t:
                return False
            partes, g_norm = _partes_genero(genero)
            if t == g_norm or t in partes:
                return True
            if len(t) >= 4:
                if t in g_norm:
                    return True
                for p in partes:
                    if t in p or p in t:
                        return True
            return False

        def _md_de(path_norm, by_lower):
            k = os.path.normpath(path_norm).lower()
            inf = by_lower.get(k) or by_lower.get(k.replace('\\', '/'))
            return inf if isinstance(inf, dict) else {}

        def _casa(path_norm, inf, nome_visivel, termos):
            inf = inf if isinstance(inf, dict) else {}
            nome_fich = _remover_acentos(os.path.basename(path_norm))
            vis = _remover_acentos(nome_visivel or '')
            titulo = _remover_acentos(inf.get('title', ''))
            artista = _remover_acentos(
                inf.get('artist', '') or inf.get('albumartist', ''))
            alvo = f'{nome_fich} {vis} {titulo} {artista}'
            genero = inf.get('genre', '') or ''
            for t in termos:
                if t in alvo or _genero_estrito(genero, t):
                    continue
                return False
            return True

        termos = [_remover_acentos(t) for t in texto.split() if t]
        if not termos:
            return

        raizes = []
        try:
            for _nome, _p in (self._build_search_roots() or []):
                if _p and os.path.isdir(str(_p)):
                    raizes.append(os.path.normpath(str(_p)))
        except Exception:
            pass

        if raiz and os.path.isdir(str(raiz)):
            r_norm = os.path.normpath(str(raiz))
            if r_norm not in raizes:
                raizes.insert(0, r_norm)

        _token = object()
        self._busca_token = _token
        LIMITE = 500

        def _bg():
            achados = []
            vistos = set()

            md = getattr(self, 'md', {}) or {}
            by_lower = {
                os.path.normpath(p).lower(): i
                for p, i in md.items() if isinstance(i, dict)
            }
            for path_db, inf in list(md.items()):
                if self._busca_token is not _token or len(achados) >= LIMITE:
                    break
                if not path_db or not isinstance(inf, dict):
                    continue
                path_norm = os.path.normpath(path_db)
                if not _casa(path_norm, inf, os.path.basename(path_norm), termos):
                    continue
                k = path_norm.lower()
                if k not in vistos:
                    vistos.add(k)
                    achados.append(path_norm)

            try:
                for _r in raizes:
                    if self._busca_token is not _token or len(achados) >= LIMITE:
                        break
                    for base, _dirs, fichs in os.walk(_r):
                        _dirs[:] = [d for d in _dirs if not _pasta_a_ignorar(d)]
                        if self._busca_token is not _token:
                            return
                        for n in fichs:
                            if not n.lower().endswith(_AUDIO_EXTS):
                                continue
                            _f = os.path.normpath(os.path.join(base, n))
                            _k = _f.lower()
                            if _k in vistos:
                                continue
                            inf = _md_de(_f, by_lower)
                            if not _casa(_f, inf, n, termos):
                                continue
                            vistos.add(_k)
                            achados.append(_f)
                            if len(achados) >= LIMITE:
                                raise StopIteration
            except StopIteration:
                pass
            except Exception:
                pass

            if self._busca_token is _token:
                self._event_q.append(('busca', (texto, achados)))

        import threading as _th
        _t = _th.Thread(target=_bg, daemon=True, name='busca-global')
        self._busca_thread = _t
        _t.start()

    def _aplicar_busca(self, texto, caminhos):
        """Renderiza os resultados instantaneamente sem travar a interface."""
        import time as _time
        _t0_bus = _time.perf_counter()
        COR_AVISO_LARANJA = QColor("#FF9800")
        COR_BRANCA = QColor("#E8EAED")

        try:
            self.folder_files.setSortingEnabled(False)
            self.folder_files.clear()

            itens = []
            faixas_sem_tags = []

            for full in caminhos:
                n = os.path.basename(full)
                title, artist = _parse_name(n)
                dur = bpm = key = ""
                inf = self._md_info(full) or {}

                if inf:
                    dur = _dur_str(inf.get("duration", 0))
                    b = inf.get("bpm")
                    if b:
                        try:
                            bpm = f"{float(b):.0f}"
                        except (TypeError, ValueError):
                            bpm = str(b)
                    key = str(inf.get("camelot") or inf.get("key") or "")
                    if inf.get("title"):
                        title = str(inf["title"])
                    if inf.get("artist") or inf.get("albumartist"):
                        artist = str(inf.get("artist") or inf.get("albumartist"))

                totalmente_analisada = bool(
                    inf and 
                    inf.get("bpm") and 
                    (inf.get("camelot") or inf.get("key")) and 
                    dur
                )

                it = _SortItem([title, artist, dur, bpm, key])
                it.setData(0, Qt.ItemDataRole.UserRole, full)
                it.setToolTip(0, full)

                # Pinta toda a linha a laranja se não estiver analisada
                cor_linha = COR_BRANCA if totalmente_analisada else COR_AVISO_LARANJA
                for col_idx in range(5):
                    it.setForeground(col_idx, cor_linha)

                itens.append(it)
                if not totalmente_analisada:
                    faixas_sem_tags.append((full, title, artist, dur, bpm, key))

            self.folder_files.addTopLevelItems(itens)
            self.folder_files.setSortingEnabled(True)
            self._folder_lbl.setText(f"{self._t('folder_hdr')} · 🔍 «{texto}»   ({len(caminhos)})")
            self._append(self._tf("l_busca_res", n=len(caminhos), q=texto))

            if faixas_sem_tags and len(faixas_sem_tags) <= 100:
                self._etiquetas_em_fundo(self._pasta_actual or "", faixas_sem_tags)

            _dt_bus = _time.perf_counter() - _t0_bus
            if _dt_bus > 0.05:
                self._append(self._tf("l_search_ms", ms=f"{_dt_bus * 1000:.0f}"))
        except Exception as e:
            self._append(f"[Pesquisa] {e}")
            
    def _on_search_row_dclick(self, item):
        if item is None:
            return
        pi = self._search_table.item(item.row(), 0)
        if pi is None:
            return
        path = pi.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        path = _norm(path)
        self._search_ref_path = path
        info = _info_of(self.md, path)
        try:
            bpm_s = f"{float(info.get('bpm') or 0):.1f}"
        except (TypeError, ValueError):
            bpm_s = "?"
        key = str(info.get("camelot") or "?")
        name = os.path.basename(path)
        short = (name[:44] + "…") if len(name) > 46 else name
        self._ref_label.setText(f"✔ {short}  [{bpm_s} BPM  {key}]")
        self._ref_label.setStyleSheet("color:#00FFFF;font-size:11px;background:transparent;")
        self._gen_btn.setEnabled(True)
        self._search_table.hide()
        self._search_edit.clear()
        self._append(self._tf("l_search_ref", name=name, bpm=bpm_s, key=key))

    def _generate_playlist(self):
        ref = self._search_ref_path
        mw = self.main_window_ref
        if not ref or mw is None:
            return
        if self._gen_thread is not None and self._gen_thread.isRunning():
            return
        try:
            # O Set Planner do player usa AGORA o mesmo diálogo e a mesma
            # thread da janela principal (mixai_fusion): "Coesão" + "Rigor
            # harmónico" em vez da antiga "Curva de energia", e a mesma
            # mecânica de geração (create_playlist_by_cluster estrito ao
            # cluster, prolongado por encadeamento até ao tempo pedido).
            # Antes eram DUAS implementações distintas — mesmo nome de classe
            # em ficheiros diferentes — e por isso o mesmo pedido dava
            # playlists diferentes conforme o sítio onde se carregava.
            # _do_app prefere o anfitrião já carregado; o _novo_api distingue
            # o diálogo do Fusion (coesão + rigor harmónico, 5 valores) do
            # antigo do dj_autodj (curva de energia, 4 valores).
            SetPlannerDialog, SetPlanThread = _do_app("SetPlannerDialog",
                                                      "SetPlanThread")
            _novo_api = getattr(SetPlannerDialog, "__module__",
                                "") == "mixai_fusion"
        except Exception as e:
            self._append(self._tf("l_sp_na", e=e))
            return
        # ---- Diálogo do SET PLANNER: duração, coesão, rigor harmónico, BPM ----
        if not hasattr(self, "current_lang"):
            self.current_lang = getattr(mw, "current_lang", "pt")
        try:
            dlg = SetPlannerDialog(self)
            # Pré-preenche o intervalo de BPM a partir da faixa de
            # referência — usando a MESMA conta do Gerenciador
            # (janela_bpm_referencia, mixai_fusion.py), e não um ±3 próprio.
            # Era exactamente esta segunda cópia, esquecida na correção de
            # 15/08, que fazia o DJ Player devolver "Sem resultados" ou
            # playlists mais pobres do que o Gerenciador para a mesma
            # referência (ex.: 155 BPM -> janela de 152–158 aqui, contra
            # 146–164 no Gerenciador).
            try:
                janela_bpm_referencia = _do_app("janela_bpm_referencia")
            except Exception:
                janela_bpm_referencia = None
            try:
                rb = float(_info_of(self.md, ref).get("bpm", 0) or 0)
                if rb > 0:
                    if janela_bpm_referencia is not None:
                        lo, hi = janela_bpm_referencia(rb)
                    else:
                        lo, hi = (int(max(40, round(rb - 3))),
                                  int(min(220, round(rb + 3))))
                    dlg.bpm_min_spin.setValue(lo)
                    dlg.bpm_max_spin.setValue(hi)
            except Exception:
                pass
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            # O diálogo do Fusion devolve 5 valores (coesão + harmónico);
            # o antigo devolve 4 (curva de energia).
            if _novo_api:
                minutes, cohesion, harmonic, bpm_min, bpm_max = \
                    dlg.get_selected_values()
                shape = f"{cohesion}/{harmonic}"      # só para o log
            else:
                minutes, shape, bpm_min, bpm_max = dlg.get_selected_values()
                cohesion, harmonic = shape, "equilibrado"
        except Exception as e:
            self._append(self._tf("l_sp_dlg_err", e=e))
            return

        _bpm_txt = (f"{bpm_min}–{bpm_max} BPM"
                    if (bpm_min and bpm_max) else "qualquer BPM")
        self._append(self._tf("l_sp_planning", min=minutes, shape=shape,
                              bpm=_bpm_txt, ref=os.path.basename(ref)))
        self._gen_btn.setEnabled(False)
        try:
            if _novo_api:
                t = SetPlanThread(mw, minutes, cohesion, harmonic, ref,
                                  bpm_min=bpm_min, bpm_max=bpm_max)
            else:
                t = SetPlanThread(mw, minutes, shape, ref,
                                  bpm_min=bpm_min, bpm_max=bpm_max)

            def _ok(ordered):
                # ── A ALMOFADA LARGA-SE NO FIM, NAO AQUI (30/08/2026) ────
                #
                # O `_pesado_fim()` estava logo aqui em cima, tres linhas
                # antes do `set_playlist()`. E o `set_playlist()` e' a parte
                # mais pesada da operacao inteira do lado da interface:
                # constroi uma linha por faixa, refaz o layout e repinta a
                # lista toda, na thread do Qt e com o GIL na mao.
                #
                # Ou seja: a almofada de proteccao caia de 2500 ms para
                # 220 ms UM INSTANTE ANTES do momento mais perigoso, e o
                # trabalho pesado acontecia desprotegido. O utilizador
                # descreveu-o assim, sem margem para duvida — «acontece no
                # momento exacto em que a lista das musicas e apresentada na
                # janela» — e o log confirma a ordem: a linha «planear o set
                # terminado» aparece ANTES da linha «Set pronto: N faixas».
                #
                # Era tambem por isto que os contadores diziam sempre «sem
                # cortes nem furos ✔»: a janela medida FECHA no
                # `_pesado_fim()`, portanto acabava antes do estalo. Os
                # numeros nunca estiveram errados — estavam a olhar para o
                # lado errado, tal como a linha de base estava a comecar
                # tarde de mais (ver a nota no `Engine.trabalho_pesado`).
                #
                # O `finally` nao e' decoracao: se o `set_playlist` rebentar,
                # a almofada TEM de voltar na mesma. Presa nos 2500 ms
                # deixava a aplicacao inteira lenta a responder e ninguem
                # perceberia porque.
                self._gen_btn.setEnabled(True)
                # _largar_thread e nao "= None": ver o comentario da funcao.
                _largar_thread(self._gen_thread)
                self._gen_thread = None
                try:
                    if ordered:
                        self.set_playlist(ordered)
                        # ── ÂNCORA PARA O MIX CONTÍNUO ──────────────────────
                        # A referência escolhida é o que define o set; guarda-se
                        # para o [∞] a usar como âncora em vez de encadear a
                        # partir da última faixa, que deriva ao fim de alguns elos.
                        # O tempo pedido NÃO limita o contínuo — serve só para
                        # avisar que o Set Planner ficou aquém e que o contínuo
                        # vai completar. Uma vez ligado, toca até ser desligado.
                        self._inf_ancora = _norm(ref)
                        _alvo_seg = float(minutes) * 60.0
                        _dur = 0.0
                        for _p in self.playlist:
                            try:
                                _dur += float((_info_of(self.md, _p)
                                               or {}).get("duration", 0.0) or 0.0)
                            except (TypeError, ValueError):
                                pass
                        self._append(self._tf("l_sp_ready",
                                              n=len(self.playlist)))
                        if _dur < _alvo_seg * 0.9:
                            self._append(self._tf(
                                "l_inf_set", m=f"{_dur/60:.0f}", k=minutes,
                                r=os.path.basename(ref)))
                            try:
                                if self.inf_check is not None:
                                    self.inf_check.setChecked(True)
                            except Exception:
                                pass
                    else:
                        self._append(self._t("l_sp_none"))
                finally:
                    self._pesado_fim()

            def _fail(err):
                self._gen_btn.setEnabled(True)
                self._pesado_fim()
                _largar_thread(self._gen_thread)
                self._gen_thread = None
                self._append(self._tf("l_sp_err", e=err))

            t.set_ready.connect(_ok)
            t.set_failed.connect(_fail)
            self._gen_thread = t
            # PLANEAR UM SET é trabalho pesado NESTE processo (percorre a
            # biblioteca, calcula distâncias, ordena). Sem a almofada de
            # protecção, o produtor de áudio ficava sem CPU no meio disso e
            # o som cortava — foi o que o utilizador relatou ao mandar gerar
            # uma playlist com música a tocar.
            try:
                if self.eng is not None:
                    self.eng.trabalho_pesado(True, "planear o set")
                    self._pesado_gen = True
            except Exception:
                self._pesado_gen = False
            t.start()
        except Exception as e:
            self._gen_btn.setEnabled(True)
            self._append(self._tf("l_sp_start_err", e=e))

    def _search_clear(self):
        self._search_edit.clear()
        if self._search_table is not None:
            self._search_table.setRowCount(0)
            self._search_table.hide()
        self._search_ref_path = None
        self._ref_label.setText(self._t("ref_hint"))
        self._ref_label.setStyleSheet("color:#555;font-size:12px;background:transparent;")
        self._gen_btn.setEnabled(False)
        self._stop()
        self.playlist = []
        self._fill_list()
        self._append(self._t("l_clear"))

    # ── playlist ──────────────────────────────────────────────────────────
    def set_playlist(self, playlist):
        pl = [p for p in (playlist or []) if p]
        # Mixai Fusion V.5: PRESERVA SEMPRE A ORDEM (ver __init__). A lista do
        # Set Planner / Co-Pilot é curada; o player não a reordena.
        FUSION_PRESERVE_ORDER = True
        self.playlist = pl               # temporário, para o helper ler
        if not FUSION_PRESERVE_ORDER:
            try:
                order_set_arc = _do_app("order_set_arc")
                if len(pl) >= 3 and self._ordem_precisa_arranjo():
                    o = order_set_arc(pl, self.md, start_path=pl[0],
                                      max_bpm_step=4.0)
                    if o and len(o) >= 2:
                        if len(o) < len(pl):
                            self._append(self._tf("l_set_out",
                                                  n=len(pl) - len(o)))
                        pl = list(o)
            except Exception:
                pass
        self.playlist = pl
        self._now_row = None
        # Âncora do [∞]: por omissão é a PRIMEIRA faixa da lista — é ela que
        # define o que o set é. O Set Planner sobrepõe-na logo a seguir com a
        # referência escolhida.
        self._inf_ancora = _norm(pl[0]) if pl else ""
        self._fill_list()
        if pl:                                   # gerou/carregou → abre a aba
            self._show_playlist(True)
        # As grelhas que faltam começam a ser calculadas JÁ, em vez de só
        # quando carregares em Iniciar (ver _GridWarmThread).
        self._arrancar_pre_grelhas()

    # ── pré-cálculo das grelhas (antes do Iniciar) ────────────────────────
    def _ha_som(self) -> bool:
        """Há algum deck a tocar ou um crossfade a meio?"""
        try:
            if self.eng is None:
                return False
            if any(self.eng.deck(n).playing for n in ("A", "B")):
                return True
            xf = self.eng.crossfade
            return abs(xf.value - xf.tgt) > 1e-3
        except Exception:
            return False

    def _arrancar_pre_grelhas(self):
        self._parar_pre_grelhas()
        if len(self.playlist) < 1:
            return
        t = _GridWarmThread(self.playlist, self.md, ha_som=self._ha_som)
        t.progress.connect(self._on_pre_grelha)
        t.done.connect(self._on_pre_grelhas_fim)
        self._warm = t
        t.start()

    def _parar_pre_grelhas(self):
        t = getattr(self, "_warm", None)
        if t is None:
            return
        try:
            t.parar()
            # NÃO se espera pelo fim: a thread pode estar dentro do modelo
            # (15-25 s) e bloquear a UI aqui era o mesmo problema que se veio
            # resolver. Ela vê a bandeira e sai sozinha; a referência fica
            # guardada para o Qt não a destruir a correr.
            _ORFAOS.append(t)
        except Exception:
            pass
        self._warm = None

    def _on_pre_grelha(self, n, total, nome):
        try:
            self._append(f"[Grelhas] {n}/{total} · {nome}")
        except Exception:
            pass

    def _on_pre_grelhas_fim(self, feitas):
        try:
            if feitas:
                self._append(self._tf("l_grelhas_ok", n=feitas))
        except Exception:
            pass

    def _fill_list(self):
        self.list_widget.clear()
        for i, p in enumerate(self.playlist):
            inf = _info_of(self.md, p)
            bpm = inf.get("bpm", "?"); key = inf.get("camelot", "?")
            bpm_txt = f"{float(bpm):.0f}" if isinstance(bpm, (int, float)) else str(bpm)
            it = QListWidgetItem(
                f"{i + 1}. {os.path.basename(str(p))}   [{bpm_txt} BPM - {key}]")
            it.setData(Qt.ItemDataRole.UserRole, _norm(str(p)))  # p/ arrastar
            self.list_widget.addItem(it)
        self._update_totals()

    def _guess_music_root(self):
        """Deteta a pasta-raiz da biblioteca a partir das faixas já indexadas;
        senão cai para ~/Music ou a pasta pessoal."""
        try:
            paths = [str(k) for k in list(self.md.keys())[:400]
                     if isinstance(k, str) and os.path.sep in str(k)]
            dirs = {os.path.dirname(p) for p in paths if p}
            dirs = {d for d in dirs if d and os.path.isdir(d)}
            if dirs:
                try:
                    common = os.path.commonpath(list(dirs))
                    if common and os.path.isdir(common):
                        return common
                except Exception:
                    pass
                # sem raiz comum: devolve a pasta mais frequente
                return sorted(dirs, key=lambda d: len(d))[0]
        except Exception:
            pass
        for cand in (os.path.join(os.path.expanduser("~"), "Music"),
                     os.path.join(os.path.expanduser("~"), "Música"),
                     os.path.expanduser("~")):
            if os.path.isdir(cand):
                return cand
        return None

    def _browser_load(self, path):
        """Duplo clique no browser: carrega a faixa no primeiro deck livre
        (que não esteja a tocar)."""
        if not path:
            return
        path = _norm(str(path))
        eng = self._ensure_engine()
        target = None
        try:
            for dk in ("A", "B"):                 # 1º: deck vazio e parado
                d = eng.deck(dk)
                if d.buf is None and not getattr(d, "playing", False):
                    target = dk
                    break
            if target is None:                    # 2º: qualquer deck parado
                for dk in ("A", "B"):
                    if not getattr(eng.deck(dk), "playing", False):
                        target = dk
                        break
        except Exception:
            target = "A"
        if target is None:
            self._append(self._t("l_br_both"))
            return
        self._manual_load(target, path)

    def _build_folder_roots(self):
        """Atalhos do browser: Música, Vídeos, Documentos, Gravações,
        Playlists Geradas e Discos.

        Pedido do White (13/08/2026): a antiga "Música Local" tentava
        adivinhar a pasta a partir da biblioteca já indexada
        (_guess_music_root, via os.path.commonpath dos ficheiros
        conhecidos). Com faixas espalhadas por várias pastas — incluindo
        soltas directamente no Ambiente de trabalho — o "ancestral comum"
        acabava a ser a pasta pessoal INTEIRA (Application Data, Contacts,
        Cookies, etc. apareciam no browser). Tirámos essa entrada e ficamos
        com atalhos fixos e previsíveis. As sub-pastas de lixo (cache,
        node_modules, pastas ocultas, etc.) continuam filtradas por
        _pasta_a_ignorar() em qualquer um destes atalhos.

        Pedido seguinte, no mesmo dia: Discos, Playlists Geradas e
        Gravações são precisos de volta. Gravações e Playlists Geradas
        usam exactamente a mesma lógica que _rec_dir() e o resto da app já
        usam (DEFAULT_MUSIC_FOLDER/<pasta>) — não se inventou um caminho
        novo, para nunca divergir de onde a app realmente grava/guarda.
        """
        home = os.path.expanduser("~")

        def first(*cands):
            for c in cands:
                if c and os.path.isdir(c):
                    return c
            return None

        # MEU COMPUTADOR (14/08/2026, a pedido do White, com o browser do
        # VirtualDJ à frente como referência).
        #
        # Só pastas de MÉDIA, e só as que existem mesmo. Nada de sistema:
        # a árvore chegou a mostrar .cache, .chatgpt, .codex, .dotnet e
        # .gemini porque listava a pasta pessoal inteira. Aqui a lista é
        # fechada — o que não estiver nesta função não aparece — e o
        # _pasta_a_ignorar trata das subpastas quando se expande.
        pc = []
        music = first(os.path.join(home, "Music"), os.path.join(home, "Música"))
        if music:
            pc.append((self._t("br_music"), music))
        videos = first(os.path.join(home, "Videos"),
                       os.path.join(home, "Vídeos"))
        if videos:
            pc.append((self._t("br_videos"), videos))
        karaoke = first(os.path.join(home, "Karaoke"),
                        os.path.join(home, "Music", "Karaoke"),
                        os.path.join(home, "Música", "Karaoke"),
                        os.path.join(home, "Videos", "Karaoke"),
                        os.path.join(home, "Vídeos", "Karaoke"))
        if karaoke:
            pc.append((self._t("br_karaoke"), karaoke))
        docs = first(os.path.join(home, "Documents"),
                     os.path.join(home, "Documentos"))
        if docs:
            pc.append((self._t("br_docs"), docs))
        desktop = first(os.path.join(home, "Desktop"),
                        os.path.join(home, "Ambiente de Trabalho"),
                        os.path.join(home, "OneDrive", "Desktop"),
                        os.path.join(home, "OneDrive", "Ambiente de Trabalho"))
        if desktop:
            pc.append((self._t("br_desktop"), desktop))
        # Discos fica DENTRO do grupo: é a porta para o resto da máquina,
        # para quem tem a música numa unidade externa — mas não convida a
        # isso, porque está arrumado em vez de solto na raiz.
        pc.append((self._t("br_drives"), "__DRIVES__"))

        roots = []
        if pc:
            roots.append((self._t("br_pc"), pc))
        # Gravações: mesmo caminho que _rec_dir() usa para gravar o set
        # (DEFAULT_MUSIC_FOLDER/Gravações). Cria-se aqui tambem se ainda
        # nao existir, para o atalho aparecer mesmo antes da 1ª gravação.
        try:
            base_music = _do_app("DEFAULT_MUSIC_FOLDER")
        except Exception:
            base_music = music or home
        rec_dir = os.path.join(base_music, self._t("rec_folder"))
        try:
            os.makedirs(rec_dir, exist_ok=True)
        except Exception:
            pass
        if os.path.isdir(rec_dir):
            roots.append((self._t("rec_folder"), rec_dir))
        # Playlists Geradas: mesmo GENERATED_PLAYLISTS_FOLDER que o resto
        # da app (histórico, exportação) já usa.
        try:
            GPF = _do_app("GENERATED_PLAYLISTS_FOLDER")
            if GPF and os.path.isdir(GPF):
                roots.append((self._t("br_genpl"), GPF))
        except Exception:
            pass
        # (O «Discos» ja vai dentro do grupo «Meu Computador» — nao se
        # repete aqui na raiz, como estava antes de 14/08/2026.)
        return roots

    def _build_search_roots(self):
        """Inclui todas as pastas de utilizador essenciais: Música, Desktop, Downloads/Transferências,
        OneDrive e Documentos."""
        home = os.path.expanduser("~")
        roots = []
        candidatos = [
            os.path.join(home, "Music"), os.path.join(home, "Música"),
            os.path.join(home, "Desktop"), os.path.join(home, "Ambiente de trabalho"),
            os.path.join(home, "Downloads"), os.path.join(home, "Transferências"),
            os.path.join(home, "Documents"), os.path.join(home, "Documentos"),
            os.path.join(home, "Videos"), os.path.join(home, "Vídeos"),
            os.path.join(home, "OneDrive", "Desktop"),
            os.path.join(home, "OneDrive", "Ambiente de trabalho"),
            os.path.join(home, "OneDrive", "Music"),
            os.path.join(home, "OneDrive", "Música"),
            os.path.join(home, "OneDrive", "Documents"),
            os.path.join(home, "OneDrive", "Documentos"),
            os.path.join(home, "OneDrive", "Downloads"),
        ]
        for c in candidatos:
            if c and os.path.isdir(c):
                c_norm = os.path.normpath(c)
                if c_norm not in [r[1] for r in roots]:
                    roots.append((os.path.basename(c_norm), c_norm))
        return roots

    def _browser_select(self, path):
        """Clique numa pasta do browser: mostra as músicas dessa pasta."""
        self._populate_folder(path)

    def _open_folder_explorer(self, path):
        """Abre a pasta no explorador de ficheiros do sistema."""
        try:
            if sys.platform == "win32":
                os.startfile(path)                          # noqa
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", path])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
            self._append(self._tf("l_br_open", p=path))
        except Exception as e:
            self._append(self._tf("l_br_open_err", e=e))

    def _analyze_folder(self, path):
        """Analisa os áudios da pasta em SEGUNDO PLANO. Não bloqueia os decks:
        a análise corre em subprocessos e o motor de áudio noutra thread.
        Limita os workers (deixa CPU livre ao som) e mostra o progresso."""
        mw = self.main_window_ref
        if mw is None:
            self._append(self._t("l_br_an_na"))
            return
        for _t in (getattr(self, "_folder_an_thread", None),
                   getattr(mw, "analysis_thread", None)):
            if _t is not None and _t.isRunning():
                self._append(self._t("l_br_an_busy"))
                return
        try:
            files = [os.path.join(path, n)
                     for n in sorted(os.listdir(path), key=str.lower)
                     if n.lower().endswith(_AUDIO_EXTS)]
        except Exception as e:
            self._append(self._tf("l_br_read_err", e=e))
            return
        if not files:
            self._append(self._t("l_br_no_audio"))
            return
        try:
            AnalysisThread = _do_app("AnalysisThread")
        except Exception as e:
            self._append(self._tf("l_br_eng_na", e=e))
            return
        self._append(self._tf(
            "l_br_analyzing", n=len(files),
            f=os.path.basename(path.rstrip(os.sep)) or path))
        th = AnalysisThread(files, mw, force_reanalyze=False)
        # PROTEGER o áudio: nunca correr in-thread (força subprocesso, fora do
        # processo do som) e limitar os workers (deixa 2 cores livres).
        th.audio_safe = True
        try:
            th.max_workers_cap = max(1, (os.cpu_count() or 4) - 2)
        except Exception:
            pass
        th.analysis_started.connect(self._on_folder_an_started)
        th.analysis_progress.connect(self._on_folder_an_progress)
        th.analysis_file_updated.connect(self._on_folder_an_file)
        th.analysis_finished.connect(
            lambda *_a, p=path: self._on_folder_an_done(p))
        th.analysis_error.connect(
            lambda msg: self._append(self._tf("l_br_an_msg", m=msg)))
        self._folder_an_thread = th
        mw.analysis_thread = th          # para o guard da app principal
        # ALMOFADA DE ÁUDIO: a fase FINAL da análise (clusters + gravação da
        # BD) corre neste processo e rouba GIL/CPU ao motor — sobe o buffer
        # da saída para ~2,5 s durante a análise (volta ao normal no fim).
        try:
            if self.eng is not None:
                self.eng.trabalho_pesado(True, "análise da pasta")
        except Exception:
            pass
        # e faz o Python alternar threads mais depressa (o motor ganha
        # prioridade efetiva contra loops apertados de serialização)
        try:
            self._old_swi = sys.getswitchinterval()
            sys.setswitchinterval(0.002)
        except Exception:
            self._old_swi = None
        th.start()

    def _on_folder_an_started(self):
        try:
            self._an_file = ""
            self._an_bar.setValue(0)
            self._an_bar.setFormat(self._t("an_prep"))
            self._an_bar.setVisible(True)
        except Exception:
            pass

    def _on_folder_an_file(self, filename):
        self._an_file = filename

    def _on_folder_an_progress(self, value):
        try:
            v = int(value)
            self._an_bar.setValue(v)
            fn = (getattr(self, "_an_file", "") or "")
            if len(fn) > 34:
                fn = fn[:33] + "…"
            self._an_bar.setFormat(f"{v}%   {fn}" if fn else f"{v}%")
        except Exception:
            pass

    def _on_folder_an_done(self, path):
        self._md_base = None             # índice por nome ficou desatualizado
        # mesmo cuidado do _gen_thread: este callback corre com a thread ainda
        # dentro do run(). Aqui há uma segunda referência (mw.analysis_thread),
        # mas ela pode ser substituída a qualquer momento e então esta seria a
        # última — não vale a pena depender disso.
        _largar_thread(self._folder_an_thread)
        self._folder_an_thread = None
        # ── A ALMOFADA LARGA-SE NO FIM (30/08/2026) ──────────────────────
        #
        # A devolução da almofada e a reposição do `setswitchinterval`
        # estavam AQUI, antes do `_populate_folder()`. E o `_populate_folder`
        # é a parte pesada desta operação — o comentário dentro dele, escrito
        # por quem o mediu, chama-lhe «o engasgo de 300-400ms» e diz que a
        # bancada sintética não o apanhava porque lá não havia «a faixa de
        # áudio a disputar o mesmo CPU apertado».
        #
        # Ou seja: a protecção era retirada exactamente antes do momento que
        # ela existe para proteger. É o mesmo defeito que o `_ok()` do Set
        # Planner tinha, e pela mesma razão.
        #
        # O `finally` garante que a almofada volta mesmo que o repovoar da
        # lista rebente: presa nos 2500 ms, a aplicação inteira ficava lenta
        # a responder e ninguém perceberia porquê.
        try:
            try:
                self._an_bar.setVisible(False)
            except Exception:
                pass
            try:
                self._populate_folder(path)
                self._append(self._t("l_br_an_done"))
            except Exception:
                pass
        finally:
            try:
                if self.eng is not None:
                    self.eng.trabalho_pesado(False, "análise da pasta")
            except Exception:
                pass
            try:
                if getattr(self, "_old_swi", None):
                    sys.setswitchinterval(self._old_swi)
            except Exception:
                pass

    def _md_info(self, full):
        """Vai à base de dados (music_data) buscar os metadados de uma faixa,
        por caminho normalizado e, em recurso, por nome de ficheiro."""
        md = self.md or {}
        info = md.get(os.path.normpath(full)) or md.get(full)
        if info:
            return info
        if getattr(self, "_md_base", None) is None:
            self._md_base = {}
            # SNAPSHOT, não iteração ao vivo: a manutenção corre numa thread
            # de fundo e tira faixas do `md`. `list(...)` é atómico em
            # CPython; iterar directamente arrisca «dictionary changed size
            # during iteration» a partir de qualquer sítio da interface.
            for k, v in list(md.items()):
                try:
                    self._md_base.setdefault(
                        os.path.basename(str(k)).lower(), v)
                except Exception:
                    pass
        return self._md_base.get(os.path.basename(full).lower())

    def _populate_folder(self, path):
        # A pasta actual e' a raiz da pesquisa por ficheiros (_on_search_filter).
        self._pasta_actual = path
        # ── MEDIR A SERIO (27/08/2026) ────────────────────────────────────
        # O "addTopLevelItems em lote" abaixo mediu-se bem numa bancada
        # sintetica (1.3x, poucos ms) mas essa bancada nao tem o tema
        # escuro, os tooltips, nem a faixa de audio a disputar o mesmo CPU
        # apertado. Em vez de adivinhar se o engasgo de 300-400ms ficou
        # resolvido, mede-se aqui a sério, na tua maquina, com a tua pasta e
        # com musica a tocar — sai no log so' quando vale a pena olhar.
        import time as _time
        _t0_pop = _time.perf_counter()
        # guarda a ordenação escolhida e desliga-a durante o repovoar
        _hdr = self.folder_files.header()
        _sc = _hdr.sortIndicatorSection()
        _so = _hdr.sortIndicatorOrder()
        self.folder_files.setSortingEnabled(False)
        self.folder_files.clear()
        try:
            name = os.path.basename(str(path).rstrip("\\/")) or str(path)
        except Exception:
            name = str(path)
        # playlists (.m3u/.m3u8) da pasta — aparecem primeiro, destacadas
        plists = []
        try:
            for n in sorted(os.listdir(path), key=str.lower):
                if n.lower().endswith(_PLAYLIST_EXTS):
                    plists.append((os.path.join(path, n), n))
        except Exception:
            pass
        # PASSAGEM RAPIDA: sem abrir ficheiros. As etiquetas das faixas que
        # a base ainda nao conhece chegam depois, pela thread mais abaixo.
        rows = _audio_rows(path, self._md_info, so_base=True)
        self._folder_lbl.setText(
            f"{self._t('folder_hdr')} · {name}   ({len(rows) + len(plists)})")
        # ── LOTE, NÃO UM A UM (27/08/2026) ────────────────────────────────
        # `addTopLevelItem` num ciclo recalcula o layout da árvore a CADA
        # chamada — com uma pasta de centenas de faixas, isto e' exactamente
        # o tipo de travagem de 300-400ms na interface principal com musica
        # a tocar (ver nota de "engasgos" nas heavy UI ops). `addTopLevelItems`
        # faz o mesmo trabalho de uma so' vez, no fim, para o lote inteiro —
        # mesma ordem, mesmo conteudo, sem recalcular a cada item.
        itens = []
        for full, n in plists:
            it = _SortItem(
                [f"▶ {os.path.splitext(n)[0]}", "(playlist)", "", "", ""])
            it.setData(0, Qt.ItemDataRole.UserRole, full)
            it.setToolTip(0, os.path.basename(full))
            it.setForeground(0, QColor("#00e5ff"))
            itens.append(it)
        for full, title, artist, dur, bpm, key in rows:
            it = _SortItem([title, artist, dur, bpm, key])
            it.setData(0, Qt.ItemDataRole.UserRole, full)
            it.setToolTip(0, os.path.basename(full))
            itens.append(it)
        self.folder_files.addTopLevelItems(itens)
        # reativa a ordenação e reaplica a escolha do utilizador
        self.folder_files.setSortingEnabled(True)
        try:
            _hdr.setSortIndicator(_sc, _so)
        except Exception:
            pass
        # só regista quando já se nota (por baixo disso ninguém repara) —
        # dá o número REAL desta máquina, com esta pasta, com música a
        # tocar, em vez de uma bancada sintética sem tema escuro nem áudio.
        _dt_pop = _time.perf_counter() - _t0_pop
        if _dt_pop > 0.05:
            self._append(self._tf("l_folder_ms", n=len(itens),
                                  ms=f"{_dt_pop * 1000:.0f}"))
        self._etiquetas_em_fundo(path, rows)

    def _etiquetas_em_fundo(self, pasta, rows):
        """Lê as etiquetas das faixas que a base não conhece, FORA da UI.

        PORQUE (13/08/2026). O `_audio_rows` abria cada ficheiro com o
        mutagen para ler título e artista — uma abertura por faixa, na
        thread da interface. Medido pelo vigia com música a tocar: 1,80 s
        de bloqueio ao entrar numa pasta. A primeira leitura é ainda pior,
        porque um hook de import do PySide6 faz `inspect.getsource()` sobre
        o módulo e arrasta o `tokenize` a ler o código-fonte linha a linha.

        Agora a lista aparece de imediato com o nome do ficheiro, e só as
        faixas SEM título na base é que são abertas — numa thread, com o
        resultado devolvido à UI pela fila de eventos.
        """
        alvos = []
        for full, title, artist, _d, _b, _k in rows:
            inf = self._md_info(full) or {}
            if inf.get("title") and (inf.get("artist") or inf.get("albumartist")):
                continue                      # a base ja sabe
            alvos.append(full)
        if not alvos:
            return

        _t_ant = getattr(self, "_tags_thread", None)
        if _t_ant is not None and _t_ant.is_alive():
            self._tags_cancelar = True        # a pasta mudou: larga a antiga
        self._tags_cancelar = False
        _token = object()
        self._tags_token = _token

        def _bg():
            achados = []
            for f in alvos:
                if self._tags_cancelar or self._tags_token is not _token:
                    return
                t, a = _tags_title_artist(f)   # com cache
                if t or a:
                    achados.append((f, t, a))
            if achados and self._tags_token is _token:
                self._event_q.append(("tags", achados))

        import threading as _th
        self._tags_thread = _th.Thread(target=_bg, daemon=True,
                                       name="tags-bg")
        self._tags_thread.start()

    def _aplicar_etiquetas(self, achados):
        """Escreve na lista da pasta as etiquetas lidas em fundo."""
        try:
            porcaminho = {f: (t, a) for f, t, a in achados}
            for i in range(self.folder_files.topLevelItemCount()):
                it = self.folder_files.topLevelItem(i)
                p = it.data(0, Qt.ItemDataRole.UserRole)
                par = porcaminho.get(p)
                if not par:
                    continue
                t, a = par
                if t:
                    it.setText(0, t)
                if a:
                    it.setText(1, a)
        except Exception:
            pass

    def _on_folder_item_dclick(self, item, _col=0):
        """Duplo clique na lista da pasta: se for uma PLAYLIST (.m3u) carrega
        as faixas dela; se for uma faixa, define-a como REFERÊNCIA para o
        Gerar Playlist (carregar no deck fica no menu de contexto/arrasto)."""
        if item is None:
            return
        p = item.data(0, Qt.ItemDataRole.UserRole)
        if not p:
            return
        if str(p).lower().endswith(_PLAYLIST_EXTS):
            self._load_playlist_file(p)
        else:
            self._set_reference(p)

    def _set_reference(self, path):
        """Define a faixa como referência do Gerar Playlist (mesmo efeito do
        duplo clique num resultado da pesquisa). Devolve True se aceitou."""
        path = _norm(str(path))
        info = _info_of(self.md, path)
        if not info:
            self._append(self._t("l_ref_na"))
            return False
        self._search_ref_path = path
        try:
            bpm_s = f"{float(info.get('bpm') or 0):.1f}"
        except (TypeError, ValueError):
            bpm_s = "?"
        key = str(info.get("camelot") or "?")
        name = os.path.basename(path)
        short = (name[:44] + "…") if len(name) > 46 else name
        self._ref_label.setText(f"✔ {short}  [{bpm_s} BPM  {key}]")
        self._ref_label.setStyleSheet(
            "color:#00FFFF;font-size:11px;background:transparent;")
        self._gen_btn.setEnabled(True)
        self._append(self._tf("l_search_ref", name=name, bpm=bpm_s, key=key))
        return True

    def _playlist_dropped(self, paths, destino=None):
        """Largar faixas na PLAYLIST GERADA.

        LARGA ONDE SE LARGOU (13/08/2026). Antes juntava sempre ao FIM,
        independentemente do sitio onde se soltava o rato. Para meter uma
        faixa a seguir a que estava a tocar era preciso arrasta-la para a
        lista e depois arrasta-la mais duas vezes la dentro — foi o que o
        utilizador teve de fazer.
        (Para o caso mais comum ha atalho melhor: botao direito na faixa ->
        "Tocar a seguir", que a mete a seguir a actual e replaneia.)

        Um .m3u largado continua a carregar a playlist inteira.
        """
        novos = []
        for p in paths:
            if str(p).lower().endswith(_PLAYLIST_EXTS):
                self._load_playlist_file(p)
                continue
            n = _norm(str(p))
            if n and n not in self.playlist and n not in novos:
                novos.append(n)
        if not novos:
            return
        if destino is None or not (0 <= int(destino) <= len(self.playlist)):
            destino = len(self.playlist)
        destino = int(destino)

        # ── NUNCA ANTES DA QUE ESTA A TOCAR (13/08/2026) ──────────────────
        # Largar perto do topo metia a faixa no indice 0, ou seja ATRAS da
        # que esta no ar — onde nunca chegaria a tocar. Quem larga uma faixa
        # com o set a decorrer quer ouvi-la, nao arquiva-la no passado.
        # Passa para logo a seguir a actual, que e' o mais proximo do que
        # foi pedido e continua a ser previsivel.
        _i_actual = None
        try:
            if self.dj is not None and 0 <= self.dj._idx < len(self.dj.playlist):
                _a_tocar = _norm(str(getattr(
                    self.dj.playlist[self.dj._idx], "path", "")))
                for _k, _p in enumerate(self.playlist):
                    if _norm(str(_p)) == _a_tocar:
                        _i_actual = _k
                        break
        except Exception:
            _i_actual = None
        if _i_actual is not None and destino <= _i_actual:
            destino = _i_actual + 1
            self._append(self._t("l_pl_drop_adiante"))

        self.playlist[destino:destino] = novos
        self._fill_list()
        self._show_playlist(True)
        self._append(self._tf("l_pl_drop", n=len(novos)))
        # O motor tem de acompanhar: se a faixa entrou ANTES do que ia tocar
        # a seguir, e' ela que passa a ser a proxima.
        self._sincronizar_ordem_motor()

    def _folder_ctx_menu(self, pos):
        """Menu de contexto da PASTA: gerar playlist, referência, deck,
        editar beatgrid e abrir localização."""
        it = self.folder_files.itemAt(pos)
        if it is None:
            return
        p = it.data(0, Qt.ItemDataRole.UserRole)
        if not p:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self.folder_files)
        menu.setStyleSheet(
            "QMenu{background:#1e2127;color:#e8eaed;border:1px solid #2c313a;"
            "border-radius:6px;padding:4px;} QMenu::item{padding:7px 16px;"
            "border-radius:5px;} QMenu::item:selected{background:#0097A7;"
            "color:#06222a;}")
        if str(p).lower().endswith(_PLAYLIST_EXTS):
            a_load = menu.addAction(self._t("m_load_pl"))
            chosen = menu.exec(self.folder_files.viewport().mapToGlobal(pos))
            if chosen == a_load:
                self._load_playlist_file(p)
            return
        # PEDIDO: so faz sentido com o automix a tocar. Fica em primeiro
        # porque, quando alguem pede uma musica, e' a accao urgente.
        a_next = None
        if self.dj is not None:
            a_next = menu.addAction(self._t("m_play_next"))
            menu.addSeparator()
        a_gen = menu.addAction(self._t("m_gen_from"))
        a_ref = menu.addAction(self._t("m_set_ref"))
        menu.addSeparator()
        a_deck = menu.addAction(self._t("m_load_deck"))
        a_grid = menu.addAction(self._t("m_edit_grid"))
        menu.addSeparator()
        a_loc = menu.addAction(self._t("m_open_loc"))
        chosen = menu.exec(self.folder_files.viewport().mapToGlobal(pos))
        if a_next is not None and chosen == a_next:
            self.tocar_a_seguir(p)
        elif chosen == a_gen:
            if self._set_reference(p):
                self._generate_playlist()
        elif chosen == a_ref:
            self._set_reference(p)
        elif chosen == a_deck:
            self._browser_load(p)
        elif chosen == a_grid:
            self._edit_grid(p)
        elif chosen == a_loc:
            self._open_folder_explorer(os.path.dirname(str(p)))

    def _playlist_ctx_menu(self, pos):
        """Menu de contexto da PLAYLIST GERADA.

        Mesmas accoes do browser, menos as que nao fazem sentido aqui: nao
        se «gera playlist a partir desta faixa» de dentro de uma playlist ja
        gerada, que a substituiria sem aviso.

        As que interessam sao a edicao da grelha e a localizacao do ficheiro:
        e' a olhar para o set em ordem que se percebe qual e' a faixa que
        anda a desalinhar, e ate' agora era preciso ir procura-la ao browser
        para lhe mexer.
        """
        it = self.list_widget.itemAt(pos)
        if it is None:
            return
        p = it.data(Qt.ItemDataRole.UserRole)
        if not p:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self.list_widget)
        menu.setStyleSheet(
            "QMenu{background:#1e2127;color:#e8eaed;border:1px solid #2c313a;"
            "border-radius:6px;padding:4px;} QMenu::item{padding:7px 16px;"
            "border-radius:5px;} QMenu::item:selected{background:#0097A7;"
            "color:#06222a;}")
        a_next = None
        if self.dj is not None:
            a_next = menu.addAction(self._t("m_play_next"))
            menu.addSeparator()
        a_ref = menu.addAction(self._t("m_set_ref"))
        menu.addSeparator()
        a_deck = menu.addAction(self._t("m_load_deck"))
        a_grid = menu.addAction(self._t("m_edit_grid"))
        menu.addSeparator()
        a_loc = menu.addAction(self._t("m_open_loc"))
        chosen = menu.exec(self.list_widget.viewport().mapToGlobal(pos))
        if a_next is not None and chosen == a_next:
            self.tocar_a_seguir(p)
        elif chosen == a_ref:
            self._set_reference(p)
        elif chosen == a_deck:
            self._browser_load(p)
        elif chosen == a_grid:
            self._edit_grid(p)
        elif chosen == a_loc:
            self._open_folder_explorer(os.path.dirname(str(p)))

    def _adoptar_deck_audivel(self, novo_live):
        """Depois de uma mistura MANUAL, o automix assume o deck que se ouve.

        O CASO (13/08/2026). O DJ carrega no A⇄B (ou puxa o crossfader) a
        meio de um set automático. O crossfader vai todo para o outro lado e
        passa a ouvir-se o deck B — mas o AutoDJ continua a achar que o deck
        ao vivo é o A. Consequências, todas observadas:

          • o deck A fica a tocar por baixo, inaudível mas a gastar CPU e a
            consumir a faixa;
          • o watchdog vê o "deck ao vivo" em silêncio, conclui que a faixa
            acabou antes do tempo e replaneia — uma vez por segundo, em
            ciclo, enchendo o log;
          • o alinhamento fica desencontrado do que se ouve.

        Aqui o automix passa o comando para o deck audível: pára e liberta o
        outro, reencontra a posição na playlist pela faixa que está no ar, e
        replaneia — o que carrega a seguinte no deck que ficou livre. É o
        que um DJ espera depois de fazer a mistura à mão.

        Em modo MANUAL (sem automix) isto não corre: aí o DJ pára e carrega
        como quiser.
        """
        dj = self.dj
        if dj is None or novo_live == getattr(dj, "_live", None):
            return
        try:
            antigo = "B" if novo_live == "A" else "A"
            d_ant = self.eng.deck(antigo)
            d_novo = self.eng.deck(novo_live)

            # 1) Largar o deck que ficou em silêncio.
            try:
                d_ant.stop()
                d_ant.loop_off()
                d_ant.fx_all_off()
                d_ant.eq.restore_low(0.01)
                d_ant.unload()
            except Exception:
                pass

            # 2) O automix passa a mandar no deck audível.
            dj._live = novo_live
            dj.finished = False
            try:
                self.eng.clear_events("transition")
            except Exception:
                pass
            try:
                d_novo.sync_follow = None
                d_novo._sync_e_filt = None
            except Exception:
                pass

            # 3) Reencontrar a posição na playlist pela faixa que está no ar.
            _nome = str(getattr(d_novo, "track_name", "") or "")
            _achou = -1
            for i, sp in enumerate(dj.playlist):
                if str(getattr(sp, "name", "")) == _nome:
                    _achou = i
                    break
            if _achou >= 0:
                dj._idx = _achou
                self._on_track_change(_nome)
            else:
                # A faixa nao pertence ao alinhamento (carga manual): -1 diz
                # ao motor para calcular o mix-out a partir do buffer.
                dj._idx = -1

            self._append(self._tf("l_xf_adoptado", d=novo_live,
                                  n=_nome[:44] or "?"))
            # 4) Carregar a seguinte no deck que ficou livre.
            self._replan_bg("mistura manual")
        except Exception as e:
            self._append(self._tf("l_am_adopt_fail", e=e))

    def _spec_de(self, caminho):
        """TrackSpec a partir do music_data. None se a faixa nao servir."""
        p = _norm(str(caminho))
        inf = _info_of(self.md or {}, p) or {}
        try:
            bpm = float(inf.get("bpm", 0) or 0)
        except (TypeError, ValueError):
            bpm = 0.0
        if not (40.0 < bpm < 300.0):
            return None
        sp = TrackSpec(
            path=p, bpm=bpm, downbeat=_downbeat_of(inf),
            mix_out=_mix_out_of(inf), name=os.path.basename(p),
            sections=_sections_of(inf),
            beats=inf.get("beats") or None,
            mix_in=inf.get("kick_in"))
        sp.estrutura = inf.get("estrutura_v2") or None
        return sp

    def _playlist_reordenada(self, linhas, destino):
        """Arrastar dentro da lista muda a ORDEM, e o motor acompanha.

        A faixa que esta a tocar nao e' afectada — continua a tocar. O que
        muda e' o que vem a seguir, e e' isso que o replan trata.
        """
        if not linhas:
            return
        n = len(self.playlist)
        linhas = [r for r in linhas if 0 <= r < n]
        if not linhas:
            return

        # Retirar de tras para a frente para os indices nao deslizarem, e
        # corrigir o destino pelo numero de itens tirados antes dele.
        movidos = [self.playlist[r] for r in linhas]
        destino = max(0, min(int(destino), n))
        antes = sum(1 for r in linhas if r < destino)
        for r in sorted(linhas, reverse=True):
            self.playlist.pop(r)
        destino -= antes
        destino = max(0, min(destino, len(self.playlist)))
        self.playlist[destino:destino] = movidos

        self._fill_list()
        self._sincronizar_ordem_motor()

    def _sincronizar_ordem_motor(self):
        """Poe a playlist do MOTOR na mesma ordem da lista da interface.

        Reaproveita os TrackSpec que ja existem — reconstrui-los perderia as
        batidas e a estrutura ja calculadas, e obrigaria a recalcular tudo.
        O `_idx` e' reencontrado pela faixa que esta a tocar, senao o set
        saltava para outra a meio.
        """
        dj = self.dj
        if dj is None:
            return
        try:
            def _cam(sp):
                return _norm(str(getattr(sp, "path", "")))

            a_tocar = None
            if 0 <= dj._idx < len(dj.playlist):
                a_tocar = _cam(dj.playlist[dj._idx])
            antigo_seguinte = None
            if 0 <= dj._idx + 1 < len(dj.playlist):
                antigo_seguinte = _cam(dj.playlist[dj._idx + 1])

            existentes = {}
            for sp in dj.playlist:
                existentes.setdefault(_cam(sp), sp)

            nova = []
            for p in self.playlist:
                pn = _norm(str(p))
                sp = existentes.get(pn) or self._spec_de(pn)
                if sp is not None:
                    nova.append(sp)
            if not nova:
                return

            dj.playlist = nova
            if a_tocar:
                for i, sp in enumerate(nova):
                    if _cam(sp) == a_tocar:
                        dj._idx = i
                        break
                else:
                    # A que toca saiu da lista (nao devia acontecer pela
                    # reordenacao, mas nao se assume). Fica onde estava,
                    # limitado ao tamanho novo.
                    dj._idx = max(0, min(dj._idx, len(nova) - 1))
            dj.finished = False

            novo_seguinte = None
            if 0 <= dj._idx + 1 < len(dj.playlist):
                novo_seguinte = _cam(dj.playlist[dj._idx + 1])

            self._append(self._tf("l_reordered",
                                  n=max(0, len(nova) - dj._idx - 1)))
            if novo_seguinte != antigo_seguinte:
                self._replan_bg("reordenacao")
        except Exception as e:
            self._append(self._tf("l_pl_sync_fail", e=e))

    def tocar_a_seguir(self, caminho):
        """PEDIDO: mete esta faixa a seguir à que está a tocar.

        Alguem pede uma musica a meio do set. O que NAO se quer e' parar,
        nem refazer o alinhamento, nem carrega-la num deck a mao e perder a
        mistura. Quer-se que ela entre no lugar seguinte e que a transicao
        seja a melhor possivel para aquele par concreto de faixas.

        E' o que isto faz: insere a faixa na posicao _idx+1 da playlist do
        motor E da lista da interface, e replaneia. O `plano_fn` do AutoDJ
        recalcula o estilo para o novo par — se o tom nao casar sai um
        passa-alto, se os BPM estiverem longe sai um echo out, e por ai
        fora. O DJ fica a saber ANTES o que vai acontecer, porque o estilo
        escolhido e' escrito no log.

        Nao toca no que esta a tocar. Se a faixa seguinte ja estava
        carregada no deck em espera, o replan trata de a substituir.
        """
        dj = self.dj
        if dj is None:
            self._append(self._t("l_next_no_dj"))
            return False

        p = _norm(str(caminho))
        inf = _info_of(self.md or {}, p) or {}
        spec = self._spec_de(p)
        if spec is None:
            self._append(self._tf("l_next_no_bpm", n=os.path.basename(p)))
            return False

        # A que esta a tocar, para se poder anunciar a transicao prevista.
        _i = int(getattr(dj, "_idx", -1) or -1)
        info_actual = None
        if 0 <= _i < len(dj.playlist):
            info_actual = _info_of(self.md or {},
                                   getattr(dj.playlist[_i], "path", "")) or None

        pos_ins = max(0, _i + 1) if _i >= 0 else 0
        dj.playlist.insert(pos_ins, spec)
        # O fim do set deixa de estar decidido: havia pedido, ha mais faixa.
        dj.finished = False

        # Lista da interface na MESMA posicao, para o realce e os totais
        # continuarem a bater certo com o motor.
        try:
            self.playlist.insert(pos_ins, p)
            self._fill_list()
            if self._now_row is not None and 0 <= _i < len(self.playlist):
                self._highlight_now(_i)
        except Exception as e:
            self._append(f"[Pedido] lista: {e}")

        self._append(self._tf("l_next_added", n=os.path.basename(p)))

        # Diz JA qual vai ser a transicao — o DJ pode preferir outra coisa.
        if info_actual:
            try:
                from mixai_core import planear_transicao, descrever_transicao
                _pl = planear_transicao(info_actual, inf,
                                        beats_omissao=self.xf_beats)
                self._append(self._tf("l_req_prev",
                                      d=descrever_transicao(_pl)))
            except Exception:
                pass

        # A faixa seguinte mudou: o deck em espera tem a antiga carregada e a
        # transicao ja esta agendada. Replanear descarta o agendamento,
        # carrega a certa e volta a agendar.
        self._replan_bg("pedido")
        return True

    def _edit_grid(self, path):
        """Editor de beatgrid (o mesmo da janela principal) e refresh da
        linha (BPM) quando guarda."""
        try:
            from mixai_grid_editor import open_grid_editor as _oge
        except Exception as e:
            self._append(self._tf("l_grid_na", e=e))
            return
        mw = self.main_window_ref
        md = getattr(mw, "music_data", None) or self.md

        def _saved(p):
            try:
                npth = os.path.normpath(str(p))
                info = md.get(npth) or {}
                bpm = info.get("bpm")
                if isinstance(bpm, (int, float)):
                    for r in range(self.folder_files.topLevelItemCount()):
                        row = self.folder_files.topLevelItem(r)
                        if _norm(str(row.data(
                                0, Qt.ItemDataRole.UserRole))) == _norm(npth):
                            row.setText(3, f"{float(bpm):.0f}")
                            break
                self._append(self._tf("l_grid_ok",
                                      n=os.path.basename(str(p))))
            except Exception as e:
                self._append(self._tf("l_grid_err", e=e))

        try:
            _oge(self, md, str(path), on_saved=_saved,
                 lang=getattr(self, "_lang", "pt"))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._append(self._tf("l_grid_err", e=e))

    def _load_playlist_file(self, path):
        """Lê um .m3u/.m3u8 e mete as faixas na PLAYLIST GERADA."""
        try:
            tracks = [t for t in (_do_app("_parse_playlist_m3u")(path) or [])
                      if t]
        except Exception as e:
            self._append(self._tf("l_br_pl_err", e=e))
            return
        if not tracks:
            self._append(self._t("l_br_pl_empty"))
            return
        self.set_playlist([_norm(t) for t in tracks])
        self._append(self._tf("l_br_pl_loaded", p=os.path.basename(path),
                              n=len(self.playlist)))

    def _show_playlist(self, show):
        """Mostra/oculta o painel da playlist gerada (ao centro)."""
        self._pl_visible = bool(show)
        try:
            self.playlist_panel.setVisible(show)
            arrow = "▶" if show else "◀"
            self._pl_tab.setVText(f"{arrow}  PLAYLIST")
        except Exception:
            pass

    def _toggle_playlist(self):
        self._show_playlist(not getattr(self, "_pl_visible", False))

    def _remove_selected(self):
        """Remove as faixas seleccionadas da playlist.

        BUG CORRIGIDO (12/08/2026) — "removi uma faixa e ela tocou na mesma".
        Havia DUAS listas: a da interface (`self.playlist`, caminhos) e a do
        motor (`dj.playlist`, TrackSpec, construida no arranque). Isto so'
        mexia na primeira. Com o set parado ninguem dava por nada, porque ao
        Iniciar a lista do motor era construida de novo — mas a tocar, a
        faixa removida continuava la' dentro e tocava na mesma.
        """
        rows = sorted({i.row() for i in self.list_widget.selectedIndexes()},
                      reverse=True)
        if not rows:
            self._append(self._t("l_am_sel_remove"))
            return

        dj = self.dj
        # A faixa que esta A TOCAR nao se remove: ja esta dentro do deck.
        # E' tambem por ela que se reencontra o indice na lista nova.
        a_tocar = None
        if dj is not None and 0 <= dj._idx < len(dj.playlist):
            a_tocar = _norm(str(getattr(dj.playlist[dj._idx], "path", "")))

        removidos = set()
        protegidas = 0
        for r in rows:
            if not (0 <= r < len(self.playlist)):
                continue
            alvo = _norm(str(self.playlist[r]))
            if a_tocar and alvo == a_tocar:
                protegidas += 1
                continue
            removidos.add(alvo)
            self.playlist.pop(r)

        self._fill_list()
        self._append(self._tf("l_am_removed", n=len(rows) - protegidas))
        if protegidas:
            self._append(self._t("l_am_protegida"))

        if dj is not None and removidos:
            try:
                self._remover_do_motor(removidos, a_tocar)
            except Exception as e:
                self._append(self._tf("l_am_rem_fail", e=e))

    def _remover_do_motor(self, removidos, a_tocar):
        """Tira as faixas removidas da lista do MOTOR e replaneia se preciso.

        Chamado pelo `_remove_selected`. Tem tres cuidados:
          • reencontra o indice da faixa em curso na lista nova, senao o
            `_idx` passa a apontar para outra e o set salta;
          • so' replaneia se a faixa SEGUINTE mudou — a meio da playlist,
            replanear sem necessidade obriga a recarregar o deck em espera
            (decode + warp da faixa inteira, segundos de trabalho);
          • se ficou sem faixas a seguir, deixa o fim acontecer normalmente.
        """
        dj = self.dj
        if dj is None or not removidos:
            return

        def _caminho(spec):
            return _norm(str(getattr(spec, "path", "")))

        antigo_seguinte = None
        if 0 <= dj._idx + 1 < len(dj.playlist):
            antigo_seguinte = _caminho(dj.playlist[dj._idx + 1])

        nova = [s for s in dj.playlist if _caminho(s) not in removidos]
        if len(nova) == len(dj.playlist):
            return                       # nada mudou do lado do motor

        novo_idx = dj._idx
        if a_tocar:
            for i, s in enumerate(nova):
                if _caminho(s) == a_tocar:
                    novo_idx = i
                    break
        dj.playlist = nova
        # _idx = -1 e' o modo manual (faixa fora da playlist): preserva-se.
        if dj._idx >= 0:
            dj._idx = max(0, min(novo_idx, len(nova) - 1))

        novo_seguinte = None
        if 0 <= dj._idx + 1 < len(dj.playlist):
            novo_seguinte = _caminho(dj.playlist[dj._idx + 1])

        self._append(self._tf("l_am_rem_ok", n=len(removidos),
                              k=len(nova)))

        if novo_seguinte != antigo_seguinte:
            # A seguinte mudou: o deck em espera tem a antiga carregada e a
            # transicao ja esta agendada. Replanear descarta o agendamento,
            # carrega a certa e volta a agendar.
            dj.finished = False
            self._replan_bg("remocao")

    def _fmt_dur(self, sec):
        sec = int(max(0, sec)); h = sec // 3600
        m = (sec % 3600) // 60; s = sec % 60
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def _update_totals(self, current_row=None):
        # CACHE das durações: isto corre a cada tick (20×/s) e antes fazia
        # um loop pela playlist inteira + setText sempre — relayout
        # constante, parte dos engasgos da UI. Agora o loop só corre quando
        # a playlist muda e o setText só quando o texto muda (~1×/s).
        key = (len(self.playlist),
               self.playlist[-1] if self.playlist else None)
        if key != getattr(self, "_tot_key", None):
            durs = []
            for p in self.playlist:
                try:
                    durs.append(float(
                        _info_of(self.md, p).get("duration", 0) or 0))
                except Exception:
                    durs.append(0.0)
            self._tot_key = key
            self._tot_durs = durs
            self._tot_sum = float(sum(durs))
        durs = self._tot_durs
        txt = f"Total {self._fmt_dur(self._tot_sum)} ({len(self.playlist)})"
        if current_row is not None and 0 <= current_row < len(durs):
            self._rem_base = float(sum(durs[current_row:]))
            self._rem_t0 = time.monotonic()
        if self._rem_base > 0:
            rem = max(0.0, self._rem_base - (time.monotonic() - self._rem_t0))
            txt += f"      {self._t('remaining')} {self._fmt_dur(rem)}"
        if txt != getattr(self, "_tot_txt", ""):
            self._tot_txt = txt
            self._lbl_total.setText(txt)

    # ── REC (gravação do master em MP3) ──────────────────────────────────
    def _rec_dir(self):
        """Pasta das gravações (criada se não existir)."""
        try:
            base = _do_app("DEFAULT_MUSIC_FOLDER")
        except Exception:
            base = os.path.join(os.path.expanduser("~"), "Music")
        d = os.path.join(base, self._t("rec_folder"))
        os.makedirs(d, exist_ok=True)
        return d

    def _rec_clicked(self):
        if getattr(self, "_rec_on", False):
            self._rec_finish()
            return
        from PySide6.QtWidgets import QInputDialog
        import datetime as _dt
        import re as _re
        sug = _dt.datetime.now().strftime("Set %Y-%m-%d %Hh%M")
        name, ok = QInputDialog.getText(self, self._t("rec_dlg_t"),
                                        self._t("rec_dlg_q"), text=sug)
        if not ok:
            return
        name = _re.sub(r'[\\/:*?"<>|]', "_", (name or "").strip()) or sug
        try:
            wav = os.path.join(self._rec_dir(), name + ".wav")
        except Exception as e:
            self._append(self._tf("rec_dir_err", e=e))
            return
        self._rec_wav = wav
        self._rec_on = True
        self._rec_ui_on = False
        self.rec_btn.setText(self._t("rec_on"))
        self.rec_btn.setStyleSheet(self._REC_ARM)
        if self.eng is not None:
            try:
                self.eng.rec_arm(wav)
                self._append(self._tf("rec_armed",
                                      f=os.path.basename(wav)))
            except Exception as e:
                self._append(self._tf("rec_fail", e=e))
                self._rec_reset_ui()
        else:
            # sem motor ainda: fica armado; arma-se no arranque do Automix
            self._append(self._t("rec_armed2"))

    def _rec_finish(self):
        """Termina e guarda (conversão MP3 em thread de fundo).

        A gravação PÁRA imediatamente (o motor deixa de alimentar o
        gravador); o que demora é a conversão WAV→MP3 — durante ela o
        botão mostra "a guardar…" para se ver que já parou."""
        t_ant = getattr(self, "_rec_stop_thread", None)
        if t_ant is not None and t_ant.is_alive():
            return                          # já está a guardar
        self._rec_on = False
        self._rec_ui_on = False
        self.rec_btn.setEnabled(False)
        self.rec_btn.setText(self._t("rec_saving"))
        self.rec_btn.setStyleSheet(self._REC_ARM)
        self._append(self._t("rec_stopped"))
        eng = self.eng

        def _bg():
            path = None
            try:
                if eng is not None:
                    path = eng.rec_stop()
            except Exception as e:
                self._event_q.append(("log", f"[REC] {e}"))
            self._event_q.append(("rec_done", path))

        import threading
        t = threading.Thread(target=_bg, daemon=True, name="rec-stop")
        self._rec_stop_thread = t
        t.start()

    def _rec_reset_ui(self):
        self._rec_on = False
        self._rec_ui_on = False
        self.rec_btn.setEnabled(True)
        self.rec_btn.setText(self._t("rec_off"))
        self.rec_btn.setStyleSheet(self._REC_OFF)

    # ── transporte ────────────────────────────────────────────────────────
    def _start(self):
        # Bloquear apenas se o AUTOMIX já está a decorrer OU se há um deck a
        # TOCAR (mistura manual em curso). Um motor manual PARADO — criado
        # automaticamente ao abrir a janela — NÃO impede o arranque: é
        # substituído em _on_prepared. (Corrige o falso "Já está a tocar".)
        _busy = self.dj is not None
        if not _busy and self.eng is not None:
            try:
                _busy = any(self.eng.deck(n).playing for n in ("A", "B"))
            except Exception:
                _busy = False
        # INICIAR e' um INTERRUPTOR do automix.
        #
        #   automix a decorrer  -> desliga (a musica continua em manual)
        #   automix desligado   -> volta a ligar sobre o que esta a tocar
        #   nada a tocar        -> arranque normal (mais abaixo)
        #
        # Nunca corta o som em nenhuma das direccoes.
        if self.dj is not None:
            self._desligar_automix()
            return

        if _busy:
            # Ha som a tocar sem automix.
            #
            # 1) Se o automix so foi desligado (guardado), volta a liga-lo
            #    sobre a faixa no ar — imediato, sem reconstruir nada.
            if self._retomar_automix():
                return

            # 2) Sem automix guardado — alinhamento novo depois de limpar,
            #    ou mistura manual de raiz. NAO se recusa: segue para a
            #    preparacao normal, e o _on_prepared trata de engatar sobre
            #    o motor que ja esta a tocar, sem cortar o som.
            self._append(self._t("l_am_align"))
        if len(self.playlist) < 2:
            self._append(self._t("l_am_min2"))
            return
        if self._prep is not None and self._prep.isRunning():
            return
        self.log_box.clear()
        self._append(self._t("l_am_prep"))
        # o pré-cálculo cede o CPU ao arranque: daqui para a frente é o
        # _PrepThread que manda, e as faixas que ele encontrar já feitas são
        # saltadas de graça.
        self._parar_pre_grelhas()
        self.start_btn.setEnabled(False)
        _mt = int(self.master_spin.value())
        self._prep = _PrepThread(self.playlist, self.md, self._event_q,
                                 master_bpm=(_mt if _mt >= 60 else None))
        # mensagens de progresso no idioma da janela
        self._prep.msg_bpm = self._t("l_prep_bpm")
        self._prep.msg_load = self._t("l_prep_load")
        self._prep.progress.connect(lambda m: self._append(f"[Automix] {m}"))
        self._prep.done.connect(self._on_prepared)
        self._prep.failed.connect(self._on_prep_failed)
        # ESTICAR E CARREGAR as primeiras faixas com música a tocar é o mesmo
        # problema: trabalho pesado no processo do áudio.
        try:
            if self.eng is not None:
                self.eng.trabalho_pesado(True, "preparar as faixas")
                self._pesado_prep = True
        except Exception:
            self._pesado_prep = False
        self._prep.start()

    def _pesado_fim_depois(self, qual="gen"):
        """Devolve a almofada SO' DEPOIS de este turno da interface acabar.

        Para quem larga a almofada no INICIO de um callback que ainda tem
        trabalho pesado pela frente e varios `return` pelo meio. Mover a
        chamada para o fim nao serve — os `return` saltavam-na e a almofada
        ficava presa nos 2500 ms para sempre, com a aplicacao inteira lenta
        a responder e ninguem a perceber porque.

        Um `singleShot(0)` resolve os dois problemas de uma vez: corre
        SEMPRE (nao ha `return` que lhe fuja) e corre DEPOIS de o callback
        ter acabado, seja por que caminho for. O trabalho pesado esta' todo
        dentro do callback, portanto fica todo protegido.
        """
        try:
            QTimer.singleShot(0, lambda: self._pesado_fim(qual))
        except Exception:
            self._pesado_fim(qual)

    def _pesado_fim(self, qual="gen"):
        """Devolve a almofada de protecção, uma vez por cada vez que foi
        pedida. A bandeira evita devolvê-la duas vezes quando o mesmo
        trabalho acaba por dois caminhos (sucesso e erro)."""
        atr = "_pesado_gen" if qual == "gen" else "_pesado_prep"
        if not getattr(self, atr, False):
            return
        setattr(self, atr, False)
        try:
            if self.eng is not None:
                self.eng.trabalho_pesado(
                    False, "planear o set" if qual == "gen"
                    else "preparar as faixas")
        except Exception:
            pass

    def _on_prepared(self, eng, dj, master):
        # DEPOIS, nao aqui: isto ainda vai engatar a musica, arrancar o
        # monitor e mexer na interface toda. Ver `_pesado_fim_depois`.
        self._pesado_fim_depois("prep")
        # ------------------------------------------------------------------
        # JA HA MUSICA A TOCAR? ENGATA-SE, NAO SE RECOMECA.
        # ------------------------------------------------------------------
        # O caso real: o DJ limpou o alinhamento, gerou outro, e carregou em
        # Iniciar — com uma faixa ainda no ar. Nao pode haver corte.
        #
        # O _PrepThread constroi sempre um motor NOVO e um AutoDJ novo. Se
        # ja ha som, o motor novo e deitado fora (ainda nem abriu a placa —
        # o start_stream() so acontece mais abaixo) e o AutoDJ novo e
        # religado ao motor que JA esta a tocar. Depois engata: espera pelo
        # ponto de mistura da faixa no ar e entra com a 1a da playlist nova
        # no deck livre.
        #
        # O master BPM do motor a tocar NAO se mexe: alterá-lo mudaria o tom
        # da musica no ar. As faixas novas sao esticadas para esse master.
        try:
            _ja_toca = self.eng is not None and any(
                self.eng.deck(n).playing for n in ("A", "B"))
        except Exception:
            _ja_toca = False

        if _ja_toca and self.eng is not eng:
            try:
                dj.eng = self.eng            # religa o automix ao motor vivo
                self.dj = dj
                self.fx_agent = _CreativeFX(self.eng, dj, self._append,
                                            self.fx_intensity.currentText(),
                                            tr=self._tf)
                self.fx_agent.enabled = self.fx_check.isChecked()
                for p in (self.deckA, self.mixer, self.deckB):
                    p.eng = self.eng
                self._lbl_master.setText(self._tf(
                    "master_auto", b=f"{self.eng.master_bpm:.1f}"))
                self.dj.engatar_em_manual(log=self._append)
                self.start_btn.setEnabled(True)
                self._append(self._t("l_am_align_ok"))
                return
            except Exception as e:
                self._append(self._tf("l_am_align_fail", e=e))

        # Havia outro motor parado? Tem de sair, senao ficavam DOIS streams a disputar a placa.
        # Garante paragem limpa do motor e do gravador anterior se houver troca de engine
        if self.eng is not None and self.eng is not eng:
            try:
                self.eng.rec_stop()
            except Exception:
                pass
            try:
                self.eng.stop_stream()
            except Exception:
                pass
            try:
                self.eng.stop_monitor()
            except Exception:
                pass

        self.eng, self.dj = eng, dj

        # Se o REC estava armado antes do 'Iniciar', re-conecta ao motor novo
        if getattr(self, "_rec_on", False) and getattr(self, "_rec_wav", None):
            try:
                eng.rec_arm(self._rec_wav)
                self._append(self._tf("rec_armed", f=os.path.basename(self._rec_wav)))
            except Exception as e:
                self._append(self._tf("rec_fail", e=e))
                self._rec_reset_ui()
        for p in (self.deckA, self.mixer, self.deckB):
            p.eng = eng
        self.deckA._track_shown = self.deckB._track_shown = None
        self._lbl_master.setText(
            self._tf("master_xfade", b=f"{master:.1f}"))
        self.fx_agent = _CreativeFX(eng, dj, self._append,
                                    self.fx_intensity.currentText(),
                                    tr=self._tf)
        self.fx_agent.enabled = self.fx_check.isChecked()
        # seek na waveform -> replaneia a transição (com debounce p/ arrasto)
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(250)
        self._seek_timer.timeout.connect(self._replan_after_seek)
        eng.on_seek = lambda deck: self._seek_timer.start()
        # A placa dos phones tem de ser conhecida ANTES de abrir a saída: com
        # saída única é ela que leva o master (canais 1/2) e o cue (3/4) na
        # mesma stream. Escolhida depois, o start_stream só podia adivinhar.
        eng.monitor_device = self.phones_combo.currentData()
        # o motor é recriado a cada arranque: leva com ele o estado do botão
        eng.crossfader_on = bool(getattr(self, "bt_xf", None) is None
                                 or self.bt_xf.isChecked())
        try:
            eng.start_stream(log=self._append)
        except Exception as e:
            self._append(self._tf("l_am_audio_err", e=e))
            self._stop()
            return
        try:
            eng.start_monitor(device=eng.monitor_device, log=self._append)
        except Exception:
            pass
        self.start_btn.setEnabled(True)
        self._append(self._tf("l_am_live", bpm=f"{master:.1f}"))

    def _on_prep_failed(self, msg):
        self._pesado_fim_depois("prep")
        self.start_btn.setEnabled(True)
        self._append(self._tf("l_am_prep_err", m=msg))

    def _stop_clicked(self):
        """ALTERNA entre AUTOMATICO e MANUAL, sem nunca parar a musica.

        Enquanto houver som a tocar, este botao NAO para nada: so troca
        quem manda.

          Automatico -> Manual : cancela as transicoes planeadas e entrega
                                 os decks ao DJ. A faixa continua a tocar.
          Manual -> Automatico : devolve o comando ao automix, que
                                 reagenda a partir de onde a musica vai.

        O motor de audio e a placa ficam SEMPRE abertos nas duas direcoes.
        Fechar e reabrir o stream para trocar de modo era o que provocava
        o estalo — e cada reabertura e uma oportunidade de nao reabrir.

        So para mesmo tudo quando ja nao ha nada a tocar (ou com o botao
        premido sem musica), para nao haver forma de calar a sala por
        engano.
        """
        try:
            playing = self.eng is not None and (
                self.eng.deck("A").playing or self.eng.deck("B").playing)
        except Exception:
            playing = False

        # 1o CLIQUE — tira o automix do comando, a musica continua.
        if self.dj is not None and playing:
            self._desligar_automix()
            self._append(self._t("l_pl_stopped"))
            self._append(self._t("l_am_stop_again"))
            return

        # 2o CLIQUE (ou sem automix) — limpa tudo.
        self._stop()

    def _retomar_automix(self):
        """Devolve o comando ao automix sobre o que ja esta a tocar."""
        if getattr(self, "_dj_pausado", None) is not None and self.eng is not None:
            self.dj = self._dj_pausado
            self.fx_agent = getattr(self, "_fx_pausado", None)
            self._dj_pausado = None
            self._fx_pausado = None
            try:
                # A faixa que esta no ar pertence ao alinhamento do automix?
                nome_vivo = None
                for _d in ("A", "B"):
                    try:
                        _dk = self.eng.deck(_d)
                        if getattr(_dk, "playing", False):
                            nome_vivo = getattr(_dk, "track_name", None)
                            break
                    except Exception:
                        pass
                _na_lista = any(
                    getattr(sp, "name", None) == nome_vivo
                    for sp in (getattr(self.dj, "playlist", None) or []))

                if nome_vivo and not _na_lista:
                    # Faixa de fora (o DJ trocou de alinhamento em manual):
                    # ENGATA — espera pelo ponto de mistura desta faixa e
                    # entra com a 1a do alinhamento no deck livre.
                    self.dj.engatar_em_manual(log=self._append)
                else:
                    # Mesma playlist: realinha com o estado real (deck e
                    # faixa podem ter mudado) e reagenda de onde vai.
                    try:
                        self.dj.resync_from_engine(log=self._append)
                    except AttributeError:
                        pass      # versao antiga do motor, sem resync
                    self.dj.replan()
            except Exception as e:
                self._append(self._tf("l_am_replan_fail", e=e))
            try:
                self._lbl_master.setText(self._tf(
                    "master_auto", b=f"{self.eng.master_bpm:.1f}"))
            except Exception:
                pass
            self._append(self._t("l_am_auto_back"))
            return True
        return False

    def _desligar_motor(self):
        """PARAGEM A SERIO — so para fechar a aplicacao.

        O _stop() deixa o motor vivo de proposito, para se poder limpar e
        carregar outro alinhamento sem cortar o som. Isso e certo enquanto a
        janela esta aberta — e errado ao fechar: a musica continuava a tocar
        com a janela fechada, sem forma de a calar.

        Aqui deita-se tudo abaixo: decks, gravacao, pre-escuta e placa.
        """
        if getattr(self, "_rec_on", False):
            try:
                self._rec_finish()
            except Exception:
                pass
        if self.eng is not None:
            for _d in ("A", "B"):
                try:
                    self.eng.deck(_d).stop()
                except Exception:
                    pass
            try:
                self.eng.stop_monitor()
            except Exception:
                pass
            try:
                self.eng.stop_stream()
            except Exception:
                pass
        self.eng = None
        self.dj = None
        self.fx_agent = None
        self._dj_pausado = None
        self._fx_pausado = None
        self._rem_base = 0.0

    def _desligar_automix(self):
        """Tira o automix do comando, deixando a musica a tocar em manual."""
        try:
            self.eng.clear_events("transition")
        except Exception:
            pass
        self._dj_pausado = self.dj
        self._fx_pausado = self.fx_agent
        self.dj = None
        self.fx_agent = None
        self._rem_base = 0.0
        self._clear_now_highlight()
        try:
            self._lbl_master.setText(
                f"MASTER {self.eng.master_bpm:.1f} BPM · "
                f"{self._t('manual_mix')}")
        except Exception:
            pass
        self._append(self._t("l_am_off_manual"))

    def _stop(self):
        """Para a REPRODUCAO e limpa o automix — mas deixa o MOTOR VIVO.

        O motor de audio e a placa ficam abertos. Isto e deliberado e e como
        funciona qualquer software de DJ: a placa abre uma vez e fica. Fechar
        e reabrir a cada mudanca de playlist da estalos, custa quase um
        segundo de interface presa, e cada reabertura e uma oportunidade de
        NAO reabrir — num casamento isso e o fim da noite.

        Assim, depois de parar podes carregar ou gerar outra playlist e
        arrancar de novo sem que a placa alguma vez feche.

        Para desligar o motor a serio (fechar a janela) ha o _desligar_motor.
        """
        # REC ligado: termina e guarda antes de parar
        if getattr(self, "_rec_on", False):
            self._rec_finish()
        if self.eng is not None:
            # A MUSICA NAO PARA AQUI.
            #
            # Este botao limpa o AUTOMIX e a playlist — nao e um botao de
            # silencio. A faixa que estiver no ar continua a tocar, em
            # manual, enquanto montas o alinhamento seguinte. E assim que
            # se trabalha: nunca ha silencio na sala por causa de uma
            # operacao de organizacao.
            #
            # Para calar mesmo, ha os botoes de cada deck.
            try:
                a_on = self.eng.deck("A").playing
                b_on = self.eng.deck("B").playing
            except Exception:
                a_on = b_on = False

            # Cancela transicoes agendadas: sem automix, ninguem as executa.
            try:
                self.eng.clear_events("transition")
            except Exception:
                pass

            self._append(self._t("l_am_stopped"))
            if a_on or b_on:
                self._append(self._t("l_am_clear_playing"))
            else:
                self._append(self._t("l_am_clear_engine"))
        # ATENCAO: self.eng NAO e posto a None. E isso que mantem a placa
        # aberta para a proxima playlist.
        self.dj = None
        self.fx_agent = None
        # limpa tambem o automix que estivesse guardado em modo manual,
        # senao ficava agarrado a um motor ja morto
        self._dj_pausado = None
        self._fx_pausado = None
        self._rem_base = 0.0
        self._clear_now_highlight()

    def _replan_after_seek(self):
        if self.dj is None or self.eng is None:
            return
        # o replan pode carregar a faixa seguinte (segundos) — fora da UI
        self._replan_bg("seek")
        self._append(self._t("l_am_replan"))

    def _ensure_engine(self):
        """Cria o motor para MISTURA MANUAL (sem Automix) se ainda não
        existir: decks vazios, stream ligada, pré-escuta se houver DDJ."""
        if self.eng is not None:
            return self.eng
        mt = int(self.master_spin.value())
        master = float(mt) if mt >= 60 else 124.0
        eng = Engine(master_bpm=master)
        self.eng = eng
        for pnl in (self.deckA, self.mixer, self.deckB):
            pnl.eng = eng
        self.deckA._track_shown = self.deckB._track_shown = None
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(250)
        self._seek_timer.timeout.connect(self._replan_after_seek)
        eng.on_seek = lambda deck: (self.dj is not None
                                    and self._seek_timer.start())
        # ver nota acima: a saída única precisa de saber a placa antes.
        eng.monitor_device = self.phones_combo.currentData()
        # o motor é recriado a cada arranque: leva com ele o estado do botão
        eng.crossfader_on = bool(getattr(self, "bt_xf", None) is None
                                 or self.bt_xf.isChecked())
        try:
            eng.start_stream(log=self._append)
        except Exception as e:
            self._append(self._tf("l_man_audio_err", e=e))
        try:
            eng.start_monitor(device=eng.monitor_device, log=self._append)
        except Exception:
            pass
        self._lbl_master.setText(
            f"MASTER {master:.1f} BPM · {self._t('manual_mix')}")
        self._append(self._tf("l_man_ready", bpm=f"{master:.0f}"))
        return eng

    def _manual_load(self, deck_name, path):
        """Drop de uma música num deck (ou LOAD do DDJ-400)."""
        eng = self._ensure_engine()
        # DECK A TOCAR: PERGUNTA, NAO RECUSA (13/08/2026).
        # Antes recusava em silencio (uma linha no log que passa
        # despercebida a meio de um set) e o DJ ficava sem perceber porque
        # nada acontecia. Agora diz o que esta a tocar e pergunta se quer
        # parar — a decisao e' de quem esta ao comando, mas ninguem corta
        # uma faixa por acidente.
        try:
            _d = eng.deck(deck_name)
            if getattr(_d, "playing", False):
                _nome = str(getattr(_d, "track_name", "") or "?")
                from PySide6.QtWidgets import QMessageBox
                _r = QMessageBox.question(
                    self, self._t("l_deck_titulo"),
                    self._tf("l_deck_a_tocar", d=deck_name,
                             n=(_nome[:60] + "…") if len(_nome) > 62 else _nome),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if _r != QMessageBox.StandardButton.Yes:
                    self._append(self._tf("l_man_playing", d=deck_name))
                    return
                try:
                    _d.stop()
                    _d.loop_off()
                    _d.fx_all_off()
                except Exception:
                    pass
        except Exception:
            pass
        th = getattr(self, "_mload_" + deck_name, None)
        if th is not None and th.isRunning():
            self._append(self._tf("l_man_busy", d=deck_name))
            return
        self._append(self._tf("l_man_loading", d=deck_name,
                              n=os.path.basename(path)))
        t = _ManualLoadThread(eng, deck_name, path, self.md)
        t.regrid.connect(lambda m: self._append(f"[Grid] {m}"))
        # FAIXA LONGA: o que se decidiu e porque. Sem isto, uma carga de
        # varios minutos e' indistinguivel de uma aplicacao pendurada — foi
        # exactamente o que aconteceu a 05/09 com o DARIO REMIX 2.wav.
        t.aviso.connect(lambda m: self._append(f"[Manual] {m}"))
        t.done.connect(lambda dk, nm: self._append(
            self._tf("l_man_ok", d=dk, n=nm)))
        t.failed.connect(lambda dk, er: self._append(
            self._tf("l_man_fail", d=dk, e=er)))
        setattr(self, "_mload_" + deck_name, t)
        t.start()

    def _ddj_browse(self, delta):
        """Encoder de BROWSE da controladora: move a seleção na lista ativa
        da biblioteca (pesquisa se visível → pasta → playlist). `delta` é o
        passo relativo do encoder (negativo = subir, positivo = descer).
        Corre na thread da UI (chamado do _tick)."""
        try:
            step = int(delta)
        except (TypeError, ValueError):
            return
        if step == 0:
            return
        # limita o passo: a maioria dos encoders manda ±1 por entalhe; um valor
        # grande (leitura de volta rápida) não deve saltar dezenas de linhas.
        step = max(-10, min(10, step))

        # 1) tabela de PESQUISA, se estiver visível
        st = getattr(self, "_search_table", None)
        if st is not None and st.isVisible() and st.rowCount() > 0:
            row = st.currentRow()
            if row < 0:
                row = 0
            row = max(0, min(st.rowCount() - 1, row + step))
            st.setCurrentCell(row, 0)
            try:
                st.scrollToItem(st.item(row, 0))
            except Exception:
                pass
            return

        # 2) árvore da PASTA (conteúdo da pasta selecionada)
        ff = getattr(self, "folder_files", None)
        if ff is not None and ff.topLevelItemCount() > 0:
            n = ff.topLevelItemCount()
            cur = ff.currentItem()
            idx = ff.indexOfTopLevelItem(cur) if cur is not None else -1
            if idx < 0:
                idx = 0
            idx = max(0, min(n - 1, idx + step))
            it = ff.topLevelItem(idx)
            if it is not None:
                ff.setCurrentItem(it)
                try:
                    ff.scrollToItem(it)
                except Exception:
                    pass
            return

        # 3) PLAYLIST gerada (lista central)
        lw = getattr(self, "list_widget", None)
        if lw is not None and lw.count() > 0:
            row = lw.currentRow()
            if row < 0:
                row = 0
            row = max(0, min(lw.count() - 1, row + step))
            lw.setCurrentRow(row)
            try:
                lw.scrollToItem(lw.item(row))
            except Exception:
                pass

    def _ddj_load(self, deck_name):
        """Botão LOAD do DDJ-400: carrega a faixa selecionada no browser
        (resultados da pesquisa; senão, a selecionada na playlist)."""
        path = None
        try:
            if (self._search_table is not None
                    and self._search_table.isVisible()
                    and self._search_table.currentRow() >= 0):
                it = self._search_table.item(
                    self._search_table.currentRow(), 0)
                if it is not None:
                    path = it.data(Qt.ItemDataRole.UserRole)
            # senão: a faixa selecionada na PASTA (onde o browse navega)
            if path is None:
                ff = getattr(self, "folder_files", None)
                if ff is not None and ff.currentItem() is not None:
                    _p = ff.currentItem().data(0, Qt.ItemDataRole.UserRole)
                    if _p and not str(_p).lower().endswith(_PLAYLIST_EXTS):
                        path = _p
            if path is None:
                r = self.list_widget.currentRow()
                if 0 <= r < len(self.playlist):
                    path = self.playlist[r]
        except Exception:
            path = None
        if path:
            self._event_q.append(("log", f"[DDJ-400] LOAD deck {deck_name}"))
            self._manual_load(deck_name, _norm(path))
        else:
            self._event_q.append(("log", "[DDJ-400] LOAD: seleciona uma "
                                  "faixa na pesquisa ou na playlist."))

    def _preencher_saidas_som(self, saidas):
        """Recebe a lista da `_CarregarSaidasThread` e preenche a combo.

        Corre na thread da interface (é para aqui que o `pronto.emit`
        entrega, via ligação Qt normal) — só aqui é seguro mexer no
        `QComboBox`.
        """
        try:
            detected_ctrl = None
            ctrl_keywords = [
                "ddj", "pioneer", "hercules", "djcontrol", "denon",
                "traktor", "numark", "reloop", "roland", "allen & heath",
                "xone", "behringer"
            ]
            for nome, idx in saidas:
                self.phones_combo.addItem(nome, idx)
                if not detected_ctrl:
                    nome_low = nome.lower()
                    for kw in ctrl_keywords:
                        if kw in nome_low:
                            clean_name = nome.split("  [")[0].strip()
                            detected_ctrl = clean_name
                            break

            if detected_ctrl:
                self.phones_combo.setItemText(0, f"AUTO ({detected_ctrl})")
            else:
                self.phones_combo.setItemText(0, self._t("auto_hw"))
        except Exception:
            pass

    def _phones_changed(self, _idx):
        dev = self.phones_combo.currentData()
        if self.eng is None:
            self._append(self._t("l_pfl_later"))
            return
        self.eng.monitor_device = dev
        try:
            self.eng.stop_monitor()
            ok = self.eng.start_monitor(device=dev, log=self._append)
            if not ok and dev is None:
                self._append(self._t("l_pfl_none"))
        except Exception as e:
            self._append(self._tf("l_pfl_err", e=e))

    def _deck_panel(self, deck):
        return self.deckA if str(deck).upper() == "A" else self.deckB

    def _connect_ddj(self):
        try:
            from mixai_ddj400 import DDJ400
        except Exception as e:
            self._append(self._tf("l_ddj_na", e=e))
            return
        if self.ddj is None:
            self.ddj = DDJ400(
                lambda: self.eng,
                lambda msg: self._event_q.append(("log", msg)),
                lang=self._lang,
                actions={
                    "load": self._ddj_load,
                    # pads/modos: enfileiram para correr na thread da UI
                    "pad_mode": lambda dk, md: self._event_q.append(
                        ("padmode", dk, md)),
                    "pad": lambda dk, i: self._event_q.append(("pad", dk, i)),
                    # botão de FX da controladora -> checkbox Creative FX
                    # (tem de correr na thread da UI: mexe num widget)
                    "fx_toggle": lambda: self._event_q.append(("fx_btn",)),
                    # QUE EFEITO ESTÁ ARMADO, para a etiqueta do mixer. Sem
                    # isto a etiqueta existia mas nunca era alimentada, e
                    # ficava no travessão para sempre — saber qual dos quatro
                    # efeitos estava escolhido obrigava a decorar a posição de
                    # dois selectores da controladora.
                    "fx_estado": lambda txt, on: self._event_q.append(
                        ("fx_estado", txt, on)),
                    "pad_release": lambda dk, i: self._event_q.append(
                        ("padrel", dk, i)),
                    # BROWSE/SCROLL: encoder da controladora → move a seleção
                    # na lista da biblioteca (corre na thread da UI).
                    "browse": lambda delta: self._event_q.append(
                        ("browse", delta)),
                })
        if not self.ddj.connected:
            self.ddj.start()
        if self.ddj.connected:
            curr_text = self.phones_combo.itemText(0)
            if "AUTO" in curr_text and "DDJ" not in curr_text:
                ctrl_name = getattr(self.ddj, "device_name", "Pioneer DDJ-400") or "Pioneer DDJ-400"
                self.phones_combo.setItemText(0, f"AUTO ({ctrl_name})")

    def _ddj_toggle(self, on):
        self._connect_ddj()
        self.ddj_btn.setText(self._t("monitor_on") if on
                             else self._t("monitor_off"))
        if self.ddj is not None:
            self.ddj.learn = bool(on)
            self._append(self._t("l_ddj_mon_on") if on
                         else self._t("l_ddj_mon_off"))

    def _next_track(self):
        """NEXT: inicia imediatamente a transição para a faixa seguinte.

        Corre em thread de fundo: o skip_to_next pode ter de CARREGAR a
        faixa seguinte (decode + warp da faixa inteira = segundos) e na
        thread da UI isso congelava a janela ("Não responde")."""
        if self.dj is None or self.eng is None:
            self._append(self._t("l_am_nothing"))
            return
        t_ant = getattr(self, "_next_thread", None)
        if t_ant is not None and t_ant.is_alive():
            return                          # NEXT já em curso
        dj = self.dj

        def _bg():
            try:
                ok = dj.skip_to_next()
            except Exception as e:
                self._event_q.append(
                    ("log", self._tf("l_am_next_err", e=e)))
                return
            self._event_q.append(
                ("log", self._t("l_next_go") if ok
                 else self._t("l_am_next_skip")))

        import threading
        t = threading.Thread(target=_bg, daemon=True, name="next-bg")
        self._next_thread = t
        t.start()

    # ── crossfader / mixer / FX ───────────────────────────────────────────
    def _restyle_bt_xf(self, ligado):
        # AZUL, NAO VERDE (28/08/2026). Mesma razao do Agent FX: o verde nao
        # pertence a esta paleta. O contraste com o estado desligado nao vem
        # do tom — vem do brilho: ligado e' um azul aceso sobre fundo azul
        # escuro, desligado e' cinzento morto sobre cinzento.
        cor = "#2f9bff" if ligado else "#6a6a76"
        fundo = "#0f2338" if ligado else "#1b1b21"
        self.bt_xf.setStyleSheet(
            "QPushButton{border-radius:17px;font-size:10px;font-weight:900;"
            f"color:{cor};background:{fundo};border:2px solid {cor};" + "}"
            "QPushButton:hover{border-color:#eaeaf2;}")
        self.bt_xf.setText("ON" if ligado else "OFF")
        self.bt_xf.setToolTip(
            self._t("xf_on_tip" if ligado else "xf_off_tip"))

    def _xf_toggled(self, ligado):
        ligado = bool(ligado)
        self._restyle_bt_xf(ligado)
        self.sl_xf.setEnabled(ligado)
        for e in (self.eng, getattr(self, "_eng_tmp", None)):
            if e is not None:
                e.crossfader_on = ligado
        self._append(self._t("l_xf_on" if ligado else "l_xf_off"))

    def _xf_moved(self, v):
        if not self.eng:
            return
        # A rampa acompanha o ritmo a que o slider dispara — ver a nota
        # grande no `rampa_adaptativa`. Era 50 ms fixos, e 50 ms fixos ficam
        # sempre atras do dedo enquanto se arrasta.
        _agora = time.perf_counter()
        _ant = getattr(self, "_xf_t_ant", None)
        self._xf_t_ant = _agora
        self.eng.set_crossfade(
            v / 1000.0,
            rampa_adaptativa(None if _ant is None else (_agora - _ant),
                             self.eng.sr))

    # ── manutenção ───────────────────────────────────────────────────────
    def _guardar_biblioteca(self, apagar=None, tocadas=None):
        """Grava na base o que a manutenção mexeu.

        Sem isto as correcções viviam só em memória e desapareciam no fecho
        — o utilizador via «37 corrigidas» e no arranque seguinte estavam lá
        as 37 outra vez. Um agente de manutenção que não persiste é pior do
        que nenhum, porque dá confiança falsa.

        ── APAGAR É DIFERENTE DE GRAVAR (28/08/2026) ──────────────────────
        Esta função só sabia fazer `upsert_track` sobre o que estava no
        dicionário. Para as grelhas e a estrutura chegava — mudam o valor de
        uma chave que continua lá. Para as ÓRFÃS não chegava: o `_limpar`
        tirava-as do dicionário, isto regravava o que sobrava, e a linha na
        SQLite ficava intacta. O dicionário volta a nascer da base no
        arranque, portanto as órfãs voltavam todas — exactamente o defeito
        que o parágrafo acima diz querer evitar, resolvido para dois dos
        três casos. Daí o `apagar`, que passa pelo `delete_tracks`.

        ── E SÓ O QUE MUDOU ──────────────────────────────────────────────
        `tocadas` limita a gravação aos caminhos que a correcção mexeu. Sem
        isso eram as ~1150 faixas serializadas e reescritas em CADA uma das
        três correcções, para actualizar algumas dezenas. Sem argumento
        nenhum mantém-se o comportamento antigo — grava tudo —, que é o que
        um chamador antigo espera.
        """
        md = getattr(self, "md", None)
        if not isinstance(md, dict):
            return
        try:
            up = _do_app("upsert_track")
        except Exception:
            up = None
        try:
            rm = _do_app("delete_tracks")
        except Exception:
            rm = None

        # ── remoções ────────────────────────────────────────────────────
        if apagar:
            alvos = [c for c in apagar if c]
            for c in alvos:
                md.pop(c, None)          # rede: o chamador já o fez
            if rm is not None and alvos:
                try:
                    rm(alvos)
                except Exception:
                    pass
            # o índice por nome de ficheiro tem de ser deitado fora: senão
            # continuava a devolver metadados de faixas que já não existem
            self._md_base = None

        # ── gravações ───────────────────────────────────────────────────
        if up is None:
            return
        if tocadas is not None:
            itens = [(c, md.get(c)) for c in tocadas if c in md]
        elif apagar is not None:
            itens = []               # pediram só remoção; nada a regravar
        else:
            itens = list(md.items())
        for cam, info in itens:
            if info is None:
                continue
            try:
                up(cam, info)
            except Exception:
                continue

    def _abrir_manutencao(self):
        """Consola de manutenção: MODAL, e corre tudo à vista.

        Modal de propósito. Isto não é um painel de palco — é para antes e
        depois do set. Enquanto está aberta, o resto da aplicação não aceita
        cliques: recalcular grelhas e mexer na base ao mesmo tempo que
        alguém carrega uma faixa é a receita para uma corrida de dados com o
        pior desfecho possível, que é ficar sem saber o que aconteceu.

        A música NÃO pára — quem está a tocar continua a tocar. O que se
        recusa a correr com música no ar são as correcções (ver
        MAN.ha_musica_a_tocar).
        """
        from PySide6.QtCore import QThread, Signal, Qt as _Qt
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                       QPlainTextEdit, QPushButton, QLabel)
        try:
            import mixai_manutencao as MAN
        except Exception as e:
            self._append(self._tf("man_na", e=e))
            return

        # Threads que ficaram a terminar depois de a janela fechar. Existe
        # só para as manter vivas — um QThread recolhido pelo Python com a
        # thread ainda a correr rebenta o processo. Ver `_fechar`.
        if not hasattr(self, "_manut_pendentes"):
            self._manut_pendentes = []

        janela = self

        class _Obreiro(QThread):
            """Faz o trabalho todo FORA da thread da interface, para a consola
            ir escrevendo em vez de congelar e despejar tudo no fim."""
            linha = Signal(str)
            terminou = Signal(int, int)      # problemas, corrigidos

            def __init__(self, corrigir):
                super().__init__()
                self.corrigir = bool(corrigir)
                self._parar = False

            def parar(self):
                self._parar = True

            def run(self):
                em = self.linha.emit
                eng = getattr(janela, "eng", None)
                md = getattr(janela, "md", None)
                em("═" * 62)
                em(janela._t("man_cab"))
                em("═" * 62)

                em(janela._t("man_p1"))
                ach = MAN.diagnosticar(eng=eng, md=md,
                                       guardar=janela._guardar_biblioteca)
                for l in MAN.relatorio(ach).splitlines():
                    em(l)
                maus = MAN.problemas(ach)

                em(janela._t("man_p2"))
                if self._parar:
                    self.terminou.emit(len(maus), 0)
                    return
                p, f, s = MAN.correr_suites(em, parar=lambda: self._parar)
                # ── SEM PLACAR DE ZEROS NO .EXE (03/09/2026) ───────────
                # No exe as suites nao existem (sao .py da arvore de
                # codigo, e o proprio `correr_suites` ja' o explica). Mas
                # a seguir a' explicacao aparecia sempre
                #
                #     0 suite(s) passaram · 0 falharam · 38 saltadas
                #
                # que se le' como uma derrota. Quem olha de relance ve' o
                # «0 passaram» e nao o paragrafo por cima. Numa
                # demonstracao isso e' a aplicacao a parecer que falhou o
                # seu proprio auto-teste, quando o que ela fez foi saltar
                # uma fase que nao se aplica. O placar so' aparece quando
                # ha' mesmo suites contadas.
                if (p + f) > 0:
                    em(janela._tf("man_resumo", p=p, f=f, s=s))

                em(janela._t("man_p3"))
                corrigidos = 0
                if not self.corrigir:
                    em(janela._t("man_nao_ped"))
                elif MAN.ha_musica_a_tocar(eng):
                    em(janela._t("man_musica1"))
                    em(janela._t("man_musica2"))
                    em(janela._t("man_musica3"))
                    em(janela._t("man_musica4"))
                else:
                    alvos = [a for a in ach
                             if a.corrigivel and a.autonomia == MAN.AUTO]
                    if not alvos:
                        em(janela._t("man_nada"))
                    else:
                        for a in alvos:
                            em(f"  • {a.titulo}…")
                        # o «Parar» também vale aqui: uma correcção de
                        # grelhas sobre 300 faixas são 55 minutos
                        corrigidos, _sal, msg = MAN.corrigir(
                            ach, eng=eng, log=em,
                            parar=lambda: self._parar)
                        em(f"  {msg}")
                em("\n" + "═" * 62)
                self.terminou.emit(len(maus), corrigidos)

        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("man_titulo"))
        dlg.setModal(True)
        dlg.setWindowModality(_Qt.WindowModality.ApplicationModal)
        dlg.resize(880, 620)
        v = QVBoxLayout(dlg)
        cab = QLabel(self._t("man_pronto"))
        cab.setStyleSheet("font-size:13px;font-weight:800;color:#dfe4ea;")
        v.addWidget(cab)
        # CONSOLA A SÉRIO: monoespaçada, fundo preto, só de leitura e sem
        # limite de linhas apagadas a meio (o relatório todo tem de caber).
        con = QPlainTextEdit()
        con.setReadOnly(True)
        con.setMaximumBlockCount(0)
        con.setStyleSheet(
            "background:#07090d;color:#c8f7d0;border:1px solid #2a2f3a;"
            "font-family:Consolas,'Courier New',monospace;font-size:12px;")
        v.addWidget(con, 1)
        linha = QHBoxLayout()
        bt_diag = QPushButton(self._t("man_bt_diag"))
        bt_fix = QPushButton(self._t("man_bt_fix"))
        bt_parar = QPushButton(self._t("man_bt_parar"))
        bt_zip = QPushButton(self._t("man_bt_zip"))
        bt_fechar = QPushButton(self._t("man_bt_fechar"))
        for b in (bt_diag, bt_fix, bt_parar, bt_zip, bt_fechar):
            b.setMinimumHeight(30)
        bt_parar.setEnabled(False)
        linha.addWidget(bt_diag, 1)
        linha.addWidget(bt_fix, 1)
        linha.addWidget(bt_parar)
        linha.addWidget(bt_zip)
        linha.addWidget(bt_fechar)
        v.addLayout(linha)

        # ── GUARDAR O DIAGNOSTICO (04/09/2026) ────────────────────────────
        # O registo de falhas do utilizador foi o que permitiu encontrar a
        # violacao de acesso do `closeEvent`. O de um cliente fica no disco
        # dele e ninguem o ve'. Este botao junta-o num zip no Ambiente de
        # Trabalho, para ele anexar a um email.
        #
        # Corre na thread da interface de proposito: sao uns centesimos a
        # copiar tres ficheiros de texto, e por-lhe uma thread em cima numa
        # janela que ja' tem uma a correr era arranjar a corrida que esta
        # janela e' modal para evitar.
        def _guardar_zip():
            con.appendPlainText(self._t("man_zip_a_fazer"))
            try:
                import mixai_manutencao as _MAN
                caminho, levou, faltou = _MAN.juntar_diagnostico(
                    md=getattr(self, "md", None),
                    eng=getattr(self, "eng", None))
            except Exception as e:
                con.appendPlainText(self._tf("man_zip_erro", e=e))
                return
            con.appendPlainText(self._tf("man_zip_ok", p=caminho))
            con.appendPlainText(self._tf("man_zip_leva", q=", ".join(levou)))
            if faltou:
                con.appendPlainText(
                    self._tf("man_zip_falta", q=", ".join(faltou)))
            con.appendPlainText(self._t("man_zip_aviso"))
            con.ensureCursorVisible()
            try:
                self._open_folder_explorer(os.path.dirname(caminho))
            except Exception:
                pass

        bt_zip.clicked.connect(_guardar_zip)

        est = {"th": None}

        def _fim(n_maus, n_fix):
            bt_diag.setEnabled(True)
            bt_fix.setEnabled(True)
            bt_parar.setEnabled(False)
            bt_fechar.setEnabled(True)
            cab.setText(
                (self._t("man_ordem") if not n_maus
                 else self._tf("man_atencao", n=n_maus))
                + (self._tf("man_corrig", n=n_fix) if n_fix else ""))
            est["th"] = None

        def _arrancar(corrigir):
            if est["th"] is not None:
                return
            # Uma corrida anterior pode ter ficado a terminar em segundo
            # plano depois de a janela ter sido fechada. Duas a mexer no
            # `md` ao mesmo tempo é a corrida de dados que esta janela é
            # modal precisamente para evitar.
            try:
                if any(t.isRunning() for t in self._manut_pendentes):
                    cab.setText(self._t("man_anterior"))
                    return
            except Exception:
                pass
            con.clear()
            cab.setText(self._t("man_correr"))
            for b in (bt_diag, bt_fix, bt_fechar):
                b.setEnabled(False)
            bt_parar.setEnabled(True)
            th = _Obreiro(corrigir)
            th.linha.connect(lambda t: (con.appendPlainText(t),
                                        con.ensureCursorVisible()))
            th.terminou.connect(_fim)
            est["th"] = th
            th.start()

        bt_diag.clicked.connect(lambda: _arrancar(False))
        bt_fix.clicked.connect(lambda: _arrancar(True))
        bt_parar.clicked.connect(
            lambda: est["th"] and est["th"].parar())

        def _fechar():
            """Fechar sem levar a aplicação atrás.

            ── O QUE ESTAVA ERRADO (28/08/2026) ──────────────────────────
            Era `th.parar()` seguido de `th.wait(4000)` e `dlg.accept()`
            aconteça o que acontecer. Mas o `parar` só é lido ENTRE tarefas,
            e uma grelha do modelo leva 11 a 18 s por faixa: quatro segundos
            não chegam nem para uma. O `wait` devolvia False, fechava-se na
            mesma, o `dlg` — que é uma variável local — era recolhido ao
            sair do `exec()`, e os widgets C++ por baixo dele desapareciam.
            A thread continuava viva e continuava a emitir `linha` para uma
            lambda que escreve no `con` e `terminou` para o `_fim` que
            escreve no `cab`. Escrever num QPlainTextEdit já destruído é um
            «Internal C++ object already deleted» na melhor das hipóteses e
            uma falha de segmentação na pior — a aplicação inteira abaixo,
            possivelmente a meio de um set.

            ── O QUE SE FAZ AGORA ────────────────────────────────────────
            Desliga-se PRIMEIRO os sinais: a partir daí a thread pode
            trabalhar à vontade que não toca em nenhum widget. Depois
            espera-se um pouco pela cortesia de ela acabar; se não acabar,
            guarda-se a referência numa lista da janela — sem isso o Python
            recolhia o objecto QThread com a thread ainda a correr, que é a
            outra maneira de rebentar — e ela termina em segundo plano. O
            trabalho que já estava feito fica gravado de qualquer forma,
            porque cada correcção grava no fim de si própria.
            """
            th = est["th"]
            est["th"] = None
            if th is not None:
                th.parar()
                try:
                    th.linha.disconnect()
                except Exception:
                    pass
                try:
                    th.terminou.disconnect()
                except Exception:
                    pass
                if not th.wait(1500):
                    self._manut_pendentes.append(th)

                    def _arrumar(_t=th):
                        try:
                            self._manut_pendentes.remove(_t)
                        except Exception:
                            pass
                    try:
                        th.finished.connect(_arrumar)
                    except Exception:
                        pass
                    try:
                        self._append(self._t("man_fundo"))
                    except Exception:
                        pass
            dlg.accept()
        bt_fechar.clicked.connect(_fechar)
        dlg.rejected.connect(_fechar)

        _arrancar(False)          # abre já a diagnosticar
        dlg.exec()

    def _fx_toggled(self, on):
        if self.fx_agent:
            self.fx_agent.enabled = bool(on)
        self._append(self._tf("l_fx_toggle", s='ON' if on else 'OFF'))

    def _fx_intensity_changed(self, s):
        if self.fx_agent:
            self.fx_agent.set_intensity(s)
        self._append(self._tf("l_fx_int", s=s))

    # ── MIX CONTÍNUO (∞) ─────────────────────────────────────────────────
    def _inf_toggled(self, on):
        self._append(self._t("inf_on") if on else self._t("inf_off"))
        if on:
            self._inf_falhas = 0
            self._inf_tocadas = set(
                os.path.normpath(str(getattr(sp, "path", "")))
                for sp in (getattr(self.dj, "playlist", None) or []))

    @staticmethod
    def _inf_snapshot(mw):
        """Fotografia dos pesos da UI em atributos simples, para a thread de
        fundo nunca tocar em widgets Qt (não é thread-safe)."""
        class _Val:
            def __init__(self, v): self._v = v
            def value(self): return self._v

        class _Snap:
            pass
        s = _Snap()
        for a in ("bpm_weight", "camelot_weight", "energy_weight",
                  "rhythm_weight", "transition_od_weight",
                  "transition_rv_weight", "transition_sr_weight",
                  "transition_sf_weight", "transition_pm_weight"):
            w = getattr(mw, a, None)
            if w is not None:
                try:
                    setattr(s, a, _Val(float(w.value())))
                except Exception:
                    pass
        for a in ("max_intro_onset_density", "min_intro_onset_density",
                  "max_intro_rhythm_variance", "min_intro_rhythm_variance",
                  "max_intro_perceptual_loudness_slew_rate",
                  "min_intro_perceptual_loudness_slew_rate",
                  "max_intro_spectral_flatness", "min_intro_spectral_flatness",
                  "max_energy", "min_energy"):
            v = getattr(mw, a, None)
            if v is not None:
                try:
                    setattr(s, a, float(v))
                except Exception:
                    pass
        return s

    def _inf_estender(self):
        """Junta mais faixas ao fim da playlist, sem parar o som.

        Degrada por camadas em vez de parar: mesmo cluster -> clusters
        VIZINHOS -> biblioteca (Med) -> biblioteca ±12 BPM (Low). Só entram
        faixas com grelha já calculada — a análise não pode correr durante a
        reprodução (rouba CPU ao áudio), por isso a biblioteca tem de estar
        preparada de antemão, que é o cenário de um bar ou hotel.

        A seleção corre numa THREAD DE FUNDO: sobre bibliotecas grandes o
        scoring bloqueava a UI ("Não responde") e causava underflow no áudio.
        O resultado volta pela _event_q e é aplicado no _tick (thread da UI).
        """
        dj = self.dj
        if dj is None or not getattr(dj, "playlist", None):
            return
        t_ant = getattr(self, "_inf_thread", None)
        if t_ant is not None and t_ant.is_alive():
            return                          # já há uma extensão em curso
        md = self.md or {}
        tocadas = getattr(self, "_inf_tocadas", None)
        if tocadas is None:
            tocadas = self._inf_tocadas = set()
        for sp in dj.playlist:
            tocadas.add(os.path.normpath(str(getattr(sp, "path", ""))))
        ultimo = os.path.normpath(str(getattr(dj.playlist[-1], "path", "")))
        if not ultimo or ultimo not in md:
            return
        # ── O SET INTEIRO, FOTOGRAFADO AQUI ──────────────────────────────
        # Para a última rede do `_worker` (voltar ao princípio e repetir).
        # Tirada NESTA thread, que é a da interface e a única que mexe na
        # `dj.playlist`: o `_worker` corre em fundo e não a pode percorrer
        # enquanto alguém lhe acrescenta faixas.
        _set_inteiro = [os.path.normpath(str(getattr(sp, "path", "")))
                        for sp in dj.playlist]
        _set_inteiro = [p for p in _set_inteiro if p and p in md]

        def _voltar_ao_principio():
            """As próximas seis faixas do set que já está a tocar.

            A REDE QUE NÃO PODE FALHAR. Não procura nada: pega no set que
            está na playlist e volta ao princípio dele. São faixas que já
            passaram pelo motor, já têm grelha e já provaram que tocam — não
            há busca, não há piso, não há como vir vazio enquanto houver
            duas faixas.

            O ponteiro (`_inf_volta`) avança de chamada para chamada, para o
            set INTEIRO voltar a tocar em vez de ficar um ciclo das seis
            primeiras. Num set de vinte faixas a diferença ouve-se ao fim de
            meia hora.
            """
            if len(_set_inteiro) < 2:
                return []
            _i = int(getattr(self, "_inf_volta", 0) or 0)
            _fila = []
            for _k in range(len(_set_inteiro)):
                _p = _set_inteiro[(_i + _k) % len(_set_inteiro)]
                if _p != ultimo and _p not in _fila:
                    _fila.append(_p)
                if len(_fila) >= 6:
                    break
            self._inf_volta = (_i + len(_fila)) % len(_set_inteiro)
            return _fila

        # NOTA: o [∞] NÃO tem alvo de duração — contínuo é contínuo, toca até
        # ser desligado. O tempo pedido (30/90/120 min) é do Set Planner, que
        # o usa para decidir quantas faixas escolher. Cheguei a pôr aqui uma
        # paragem por duração e estava errado: transformava o modo contínuo
        # num modo "até dar o tempo", que é outra coisa.

        # ── ÂNCORA ───────────────────────────────────────────────────────
        # A extensão encadeava a partir da ÚLTIMA faixa (anchor_mode="chain").
        # Cada elo fica parecido com o anterior, mas ao fim de dez elos já se
        # está noutro estilo — é a mesma deriva que se corrigiu no Set
        # Planner. Passa a ancorar na faixa de REFERÊNCIA do set, que é a que
        # define o que o set é, e usa o caminho "reference" — o único que tem
        # as correcções de hoje (embedding centrado, corte por dispersão,
        # bónus de pasta).
        # A âncora é deduzida AQUI e não guardada por quem cria a playlist.
        # Tentei o contrário — pô-la no set_playlist e no Set Planner — e
        # falhou: quando o DJ Player abre já com uma lista vinda da janela
        # principal, o construtor atribui self.playlist directamente e nunca
        # passa pelo set_playlist. A âncora ficava vazia e caía no "chain",
        # sem sintoma visível a não ser os candidatos serem os mesmos de
        # antes. Deduzir do estado em vez de depender de alguém a ter
        # gravado remove a classe inteira desse erro.
        _anc = os.path.normpath(str(getattr(self, "_inf_ancora", "") or ""))
        if not _anc or _anc not in md:
            # a primeira faixa do set é o que o define
            _anc = os.path.normpath(str(getattr(dj.playlist[0], "path", "")))
        if _anc and _anc in md:
            semente, modo = _anc, "reference"
        else:
            semente, modo = ultimo, "chain"
        try:
            import mixai_fusion as _mf
        except Exception as e:
            self._append(self._tf("inf_na", e=e))
            return
        # só faixas prontas a tocar (grelha feita) — nada de análise ao vivo
        # snapshot: ver a nota do `_md_info` — a manutenção pode estar a
        # mexer no `md` numa thread de fundo
        prontas = {p: i for p, i in list(md.items())
                   if isinstance(i, dict) and i.get("beats")
                   and (i.get("_grid_engine") or i.get("grid_manual"))
                   and os.path.normpath(p) not in tocadas}
        if not prontas:
            # ── A BIBLIOTECA ACABOU MESMO (16/09/2026) ───────────────────
            # Toda a faixa com grelha já está na playlist. Aqui fazia-se
            # `return` depois de um aviso, e mais nada — nem sequer se punha
            # um evento na fila, por isso o `_inf_falhas` nem chegava a
            # contar. Resultado: com o set terminado, o ciclo dos eventos
            # voltava a chamar isto de 5 em 5 segundos, isto voltava a sair
            # por aqui, e o espaço ficava calado para sempre sem uma única
            # linha a explicar porquê.
            #
            # É EXACTAMENTE O CENÁRIO QUE ESTE MODO EXISTE PARA COBRIR: um
            # bar ao fim de muitas horas, com a biblioteca toda já tocada.
            # Volta-se ao princípio do set, que é o que o utilizador pediu.
            _fila = _voltar_ao_principio()
            tocadas.clear()
            if _fila:
                self._event_q.append(("inf", _fila, [
                    f"[∞] toda a biblioteca já tocou — a recomeçar o set do "
                    f"princípio ({len(_set_inteiro)} faixas)."]))
            else:
                self._append(self._t("inf_lib_end"))
            return
        prontas[semente] = md[semente]        # a semente tem de estar no pool
        # Mesmo conjunto mas SEM tirar as já tocadas — só para o último
        # recurso lá em baixo, quando não houver mais nada inédito.
        prontas_todas = {p: i for p, i in list(md.items())
                         if isinstance(i, dict) and i.get("beats")
                         and (i.get("_grid_engine") or i.get("grid_manual"))}

        # ── VIAGEM POR CLUSTERS (02/08/2026) ─────────────────────────────
        # Antes a âncora ficava presa à faixa de referência e a busca só ia
        # ALARGANDO em torno dela: cluster -> vizinhos -> biblioteca -> ±12
        # BPM. Ao fim de algumas horas isso dá candidatos cada vez piores em
        # volta do mesmo ponto, porque o ponto nunca muda.
        #
        # Agora o modo contínuo VIAJA: esgota o cluster onde está, salta para
        # o cluster compatível seguinte, esgota esse, e assim por diante até
        # ter passado por todos — e só então recomeça. A âncora acompanha a
        # viagem, por isso dentro de cada cluster os candidatos são sempre
        # medidos contra material desse cluster, não contra uma referência
        # que ficou três estilos atrás.
        #
        # A ponte entre clusters é a faixa do cluster novo MAIS PARECIDA com
        # a que acabou de tocar. É o que um DJ faz ao mudar de ambiente:
        # escolhe a porta de entrada, não uma faixa qualquer lá dentro.
        # ── O QUE MUDOU AQUI, E O QUE ISSO VALE (29/08/2026) ─────────────
        # A docstring desta função diz «a seleção corre numa THREAD DE
        # FUNDO», e isso só era verdade a partir do `_worker`: a viagem por
        # clusters — o `clusters_por_ritmo` e o `reference_similarity_batch`
        # sobre o cluster inteiro — ficava no ciclo de eventos. A nota de
        # 24/08/2026 lá dentro já dizia isto, escrita e por corrigir.
        #
        # HONESTIDADE SOBRE O GANHO: hoje isto não corrige nada que se ouça,
        # porque O BLOCO DE VIAGEM NUNCA CORRE — ver a nota grande no
        # `_viajar`. Justifiquei a mudança com «86 a 511 ms de janela
        # parada» antes de verificar se o bloco era sequer alcançável. Não
        # é. O que fica é código que passa a fazer o que a docstring dele
        # promete, e uma armadilha desarmada para o dia em que a
        # alcançabilidade for corrigida.
        #
        # O `snap` é o único que TEM de ficar aqui: lê os widgets de pesos, e
        # widgets só se tocam na thread da interface. Não depende da viagem,
        # por isso sobe para cima dela e o resto desce para o `_worker`.
        mw = getattr(self, "main_window_ref", None) or self
        snap = self._inf_snapshot(mw)
        excl = list(tocadas)
        toc_snap = set(tocadas)

        _gastos = getattr(self, "_inf_clusters_gastos", None)
        if _gastos is None:
            _gastos = self._inf_clusters_gastos = set()

        # Lido aqui e não dentro do `_viajar`: assim o valor é o mesmo do
        # princípio ao fim de um tique, e o import falhado (versão antiga do
        # mixai_core) não deixa a viagem meio ligada.
        try:
            from mixai_core import VIAGEM_CLUSTERS
        except Exception:
            VIAGEM_CLUSTERS = False

        def _do_cluster(cid):
            return {p: i for p, i in prontas.items()
                    if i.get("cluster") == cid}

        def _buscar(sem, mod, ambito, preset, msgs):
            """Um degrau da escada de busca. Devolve as faixas inéditas.

            Extraído para fora do `_worker` a 15/09/2026 porque passou a ser
            preciso em DOIS sítios: o `_viajar` faz a busca de casa para
            saber se o cluster ainda dá alguma coisa, e o `_worker` usa o
            resultado dessa mesma busca em vez de a repetir. Sem isto, ligar
            a viagem custava uma chamada a mais por tique.
            """
            _ant = getattr(_mf, "REFERENCE_SEARCH_SCOPE", "cluster")
            try:
                _mf.REFERENCE_SEARCH_SCOPE = ambito
                # max_size=8: só precisamos de 6 faixas — o default do
                # preset (12/50) multiplicava o custo sem ganho nenhum.
                r = _mf.create_playlist_by_cluster(
                    snap, sem, prontas, preset, max_size=8,
                    exclude_paths=excl, anchor_mode=mod) or []
            except Exception as e:
                msgs.append(self._tf("inf_err", a=f"{ambito}/{preset}", e=e))
                r = []
            finally:
                _mf.REFERENCE_SEARCH_SCOPE = _ant
            return [p for p in r if os.path.normpath(p) not in toc_snap][:6]

        def _viajar(semente, modo, msgs):
            """Escolhe o cluster onde ir buscar as próximas faixas.

            CORRE NA THREAD DE FUNDO. Daí não chamar `self._append` — as
            mensagens vão no `msgs` e são escritas pelo `_inf_aplicar`, na
            thread da interface, como o resto do `_worker` já fazia.

            Devolve `(semente, modo, cluster, casa)`, ou None quando a
            viagem deu a volta completa e é preciso recomeçar do princípio.
            O `casa` são as faixas que a busca no cluster de origem já
            encontrou — o `_worker` usa-as em vez de repetir a busca. Vem
            vazio quando se viajou (o cluster é outro) ou None quando a
            viagem está desligada.

            ═══════════════════════════════════════════════════════════════
            LIGADA A 15/09/2026, E O DEFEITO NÃO ERA O QUE ESTAVA ESCRITO.

            Até aqui esta função nunca corria, e a nota antiga explicava
            porquê: o `prontas` é construído SEM as tocadas mas leva
            `prontas[semente] = md[semente]` na linha a seguir, e o teste
            `not _do_cluster(_cid)` corre sobre esse mesmo `prontas`, já com
            a semente lá dentro. A semente pertence ao cluster `_cid` por
            definição. O conjunto nunca é vazio.

            Isso está certo, mas CORRIGIR SÓ ISSO NÃO LIGA A VIAGEM. Medido
            hoje sobre a base real (763 faixas, 12 arranques, 40 tiques
            cada): excluir as tocadas do teste dá 0,2 viagens por set — ou
            seja, continua a não acontecer. O cluster de casa nunca se
            esvazia porque a escada de âmbitos JÁ TINHA saltado para os
            vizinhos e para a biblioteca e andava a servir faixas de fora,
            deixando lá dentro material que ninguém foi buscar. O cluster
            não estava vazio: estava ABANDONADO.

            A pergunta certa é a operacional — «ainda tenho alguma coisa em
            casa que sirva?» — e quem a responde é a própria busca de casa.
            Se o âmbito "cluster" volta vazio, é PARA ISSO que se alarga
            para os vizinhos, e é exactamente aí que a viagem devia entrar.
            Passa a ser esse o teste.

            MEDIDO (12 arranques, 40 tiques, base de 763):

              regra de esgotamento   coesão  semelhança  p10   viagens  rep.
              antes (nunca corre)    45,0%     0,792    0,673    0,0    0,2
              só excluir as tocadas  44,3%     0,794    0,673    0,2    0,2
              a busca de casa vazia  56,5%     0,821    0,717    7,0    0,0

            O p10 é o que responde à queixa: são as PIORES transições do
            set, e sobem 0,673 -> 0,717. A escada passa a servir de casa em
            40 tiques de 40 (antes servia da biblioteca em ~25 deles), e as
            repetições desaparecem. Não custa tempo — 1,7 s contra 1,8 s
            pelos mesmos 40 tiques, porque o `_buscar` reaproveita a busca.

            MIXAI_VIAGEM=0 volta ao que havia. Vale a pena ouvir um set
            inteiro antes de a deixar ligada: o que muda ouve-se ao fim de
            horas, não ao fim de três faixas.
            ═══════════════════════════════════════════════════════════════
            """
            _cid = (md.get(semente) or {}).get("cluster")
            if not VIAGEM_CLUSTERS:
                return semente, modo, _cid, None
            if _cid is None:
                return semente, modo, _cid, None
            # «este cluster está esgotado» = a busca de casa não deu nada.
            # Ver a nota acima: contar as faixas que lá restam responde a
            # outra pergunta, e a resposta dessa é sempre "ainda há".
            _casa = _buscar(semente, modo, "cluster", "Med", msgs)
            if _casa:
                return semente, modo, _cid, _casa
            _gastos.add(_cid)
            # ── A PONTE ESCOLHE-SE PELO RITMO (24/08/2026) ────────────────
            # O `get_neighboring_clusters` ordena por BPM, energia e
            # centroide — tres escalares, nenhum deles ritmo. Quando um
            # cluster se esgota, o que se procura e' outra FAMILIA que se
            # misture, e isso e' uma pergunta de ritmo.
            #
            # Ver `clusters_por_ritmo` no mixai_fusion: o BPM entra como
            # filtro (o perfil ritmico nao sabe nada de velocidade) e o
            # ritmo ordena o que sobra. Devolve None quando nao ha dados que
            # cheguem, e ai fica o criterio antigo — uma biblioteca por
            # reanalisar continua a funcionar como sempre.
            _viz = []
            try:
                from mixai_core import PONTE_RITMO
            except Exception:
                PONTE_RITMO = False
            if PONTE_RITMO:
                try:
                    # `log=msgs.append` e não `self._append`: o log da janela
                    # toca num widget, e isto já não corre na thread dela.
                    _viz = list(_mf.clusters_por_ritmo(
                        md, _cid, top_k=50, log=msgs.append) or [])
                except Exception as _e_pr:
                    msgs.append(f"[∞] ponte ritmica indisponivel: {_e_pr}")
                    _viz = []
            if not _viz:
                try:
                    _viz = list(_mf.get_neighboring_clusters(md, _cid, top_k=50) or [])
                except Exception:
                    _viz = []
            _todos = sorted({i.get("cluster") for i in prontas.values()
                             if i.get("cluster") is not None},
                            key=lambda c: str(c))
            _seguinte = None
            for _c in list(_viz) + _todos:      # vizinhos primeiro, por ordem
                if _c in _gastos or _c == _cid:
                    continue
                if _do_cluster(_c):
                    _seguinte = _c
                    break
            if _seguinte is None:
                # passámos por todos: recomeça a viagem
                msgs.append("[∞] percorri todos os clusters — a recomeçar.")
                _gastos.clear()
                tocadas.clear()
                return None                     # próximo tick recomeça limpo
            # faixa-ponte: a do cluster novo mais parecida com a última
            _pool_novo = _do_cluster(_seguinte)
            # pesos fixos e ritmo em cima: a ponte é uma questão de a batida
            # encaixar, não de agradar aos deslizadores da janela
            _w_ponte = {"bpm": 5.0, "camelot": 6.0, "energy": 3.0,
                        "rhythm": 9.0, "genre": 1.5, "embedding": 8.0}
            _inf_ult = md.get(ultimo, {})
            # ESTA ESCOLHA CORRIA NA THREAD DA UI ATE' 29/08/2026 — a nota
            # antiga estava aqui, escrita e por corrigir. Agora todo o
            # `_viajar` e' chamado de dentro do `_worker`, que e' onde a
            # docstring da funcao sempre disse que o trabalho acontecia.
            #
            # O `reference_similarity_batch` e' a mesma conta vectorizada:
            # medido aqui, da' diferenca maxima de 2e-16 contra o ciclo (ou
            # seja, o mesmo numero em virgula flutuante) e custa 3 a 5 vezes
            # menos. O `argmax` fica com o PRIMEIRO maximo, tal como o
            # `>` estrito do ciclo -- o desempate nao muda.
            _chaves = list(_pool_novo.keys())
            _ponte, _melhor = None, -1.0
            try:
                _sc = _mf.reference_similarity_batch(
                    _inf_ult, [_pool_novo[_k] for _k in _chaves], _w_ponte)
                if len(_sc):
                    _j = int(np.argmax(_sc))
                    _ponte, _melhor = _chaves[_j], float(_sc[_j])
            except Exception:
                # sem vectorizado (versao antiga do mixai_fusion) -> ciclo
                for _p in _chaves:
                    try:
                        _s = _mf.reference_similarity(_inf_ult,
                                                      _pool_novo[_p], _w_ponte)
                    except Exception:
                        _s = 0.0
                    if _s > _melhor:
                        _ponte, _melhor = _p, _s
            if _ponte:
                semente = os.path.normpath(_ponte)
                # atribuição simples a um atributo: só esta thread lá escreve
                # (o guarda do `_inf_thread` impede duas extensões ao mesmo
                # tempo) e a interface só o lê no início da próxima extensão.
                self._inf_ancora = semente
                modo = "reference"
                msgs.append(f"[∞] cluster {_cid} esgotado -> {_seguinte} "
                            f"(ponte: {os.path.basename(semente)})")
                _cid = _seguinte
            # `[]` e não None: viajou-se, o cluster é outro, e a busca de
            # casa que foi feita lá em cima era do cluster ANTIGO. O
            # `_worker` tem de fazer a escada toda a partir da ponte.
            return semente, modo, _cid, []

        def _worker():
            novos, msgs = [], []
            _via = _viajar(semente, modo, msgs)
            if _via is None:
                # ── A VOLTA COMPLETA NÃO PODE SERVIR ZERO (16/09/2026) ───
                # Aqui fazia-se `return`: as mensagens iam para o log e o
                # tique acabava sem acrescentar faixa nenhuma. A nota antiga
                # dizia que isso era de propósito, «para não contar como
                # falha em encontrar faixas».
                #
                # Era inofensivo enquanto o bloco da viagem nunca corria —
                # e nunca correu, até hoje de manhã. Ao ligá-la, ABRI ESTE
                # CAMINHO: agora a viagem dá mesmo a volta a todos os
                # clusters, e quando dá, o contínuo ficava um tique sem
                # servir nada. Num bar isso é o princípio do silêncio.
                #
                # Passa a cair para as redes lá em baixo — repetir por
                # semelhança e, se nem isso, voltar ao princípio do set. O
                # `tocadas` já foi limpo pelo `_viajar`, por isso o que vem
                # a seguir tem a biblioteca inteira outra vez à frente.
                _sem, _modo, _cid, _casa = semente, modo, None, []
                _volta_completa = True
            else:
                _sem, _modo, _cid, _casa = _via
                _volta_completa = False
            print(f"[∞] âncora: {os.path.basename(_sem)} · modo {_modo} "
                  f"· cluster {_cid}")
            # O `_viajar` já fez a busca de casa para decidir se o cluster
            # estava esgotado. Se ela deu faixas, são estas — repetir a
            # chamada dava exactamente o mesmo resultado e custava o dobro.
            _escada = (("cluster", "Med"), ("neighbors", "Med"),
                       ("library", "Med"), ("library", "Low"))
            if _casa:
                novos = _casa
                _escada = ()
            elif _volta_completa:
                # Acabou de se dar a volta a todos os clusters. O `prontas`
                # foi construído no princípio deste tique, ainda a excluir as
                # tocadas que o `_viajar` entretanto limpou — correr a escada
                # sobre ele era procurar no conjunto errado. Vai-se direito
                # às redes, que trabalham sobre a biblioteca inteira.
                _escada = ()
            for ambito, preset in _escada:
                novos = _buscar(_sem, _modo, ambito, preset, msgs)
                if novos:
                    if (ambito, preset) != ("cluster", "Med"):
                        _amb = {"neighbors": self._t("inf_neigh"),
                                "library": self._t("inf_lib")}.get(ambito,
                                                                   ambito)
                        _ext = " ±12 BPM" if preset == "Low" else ""
                        msgs.append(self._tf("inf_widen", a=f"{_amb}{_ext}"))
                    break

            # ── ÚLTIMO RECURSO: repetir (02/08/2026) ─────────────────────
            # Se as quatro camadas voltarem vazias, a versão anterior punha
            # `novos = []` na fila SEM MENSAGEM: nada era acrescentado e o
            # som acabava por parar sem explicação. Num bar ou num hotel,
            # que é o cenário deste modo, parar em silêncio é o pior
            # desfecho — pior do que repetir uma faixa.
            #
            # Ficou mais provável com os pisos de qualidade apertados hoje:
            # numa biblioteca pequena, ou com uma referência muito
            # particular, chega-se depressa ao ponto em que já não há nada
            # inédito acima do piso.
            #
            # Contínuo é contínuo: volta a permitir as já tocadas, com o
            # preset mais largo, e AVISA. A repetição é uma decisão
            # deliberada e visível, não uma falha.
            if not novos:
                try:
                    _mf.REFERENCE_SEARCH_SCOPE = "library"
                    r = _mf.create_playlist_by_cluster(
                        snap, _sem, prontas_todas, "Low", max_size=8,
                        exclude_paths=[], anchor_mode=_modo) or []
                except Exception as e:
                    msgs.append(self._tf("inf_err", a="repetir", e=e))
                    r = []
                finally:
                    _mf.REFERENCE_SEARCH_SCOPE = "cluster"
                novos = [p for p in r
                         if os.path.normpath(p) != os.path.normpath(
                             str(getattr(dj.playlist[-1], "path", "")))][:6]
                if novos:
                    msgs.append("[∞] sem faixas novas parecidas — a repetir "
                                "do repertório já tocado.")
                    self._event_q.append(("inf_reset_tocadas", None, []))

            # ── A VOLTA AO PRINCÍPIO (16/09/2026) ────────────────────────
            # PARA QUE SERVE ESTE MODO, dito pelo utilizador: sonorizar um
            # bar, uma loja, um hotel, muitas horas seguidas, com coesão de
            # género e transições cuidadas. Nesse cenário PARAR É O PIOR
            # DESFECHO QUE HÁ — pior do que repetir. Um espaço em silêncio
            # nota-se; a mesma música outra vez ao fim de três horas, não.
            #
            # E até hoje parava. Com duas extensões vazias seguidas o
            # `_inf_falhas` chegava a 2 e o ciclo dos eventos chamava o
            # `_stop()`. As duas redes acima — alargar o âmbito, e repetir
            # por semelhança — são buscas, e uma busca pode não devolver
            # nada: um piso apertado, uma referência muito particular, uma
            # biblioteca pequena. Faltava a rede que não pode falhar.
            #
            # Esta não procura nada: pega no SET QUE JÁ ESTÁ A TOCAR e
            # volta ao princípio dele. São faixas que já passaram pelo
            # motor, já têm grelha e já provaram que tocam — não há busca,
            # não há piso, não há como vir vazio.
            #
            # E percorre o set INTEIRO, com um ponteiro que avança de
            # chamada para chamada, em vez de repor sempre as primeiras
            # seis. A diferença ouve-se: um set de vinte faixas volta a
            # tocar as vinte, e não as seis do princípio em ciclo.
            if not novos:
                novos = _voltar_ao_principio()
                if novos:
                    msgs.append(
                        f"[∞] biblioteca esgotada — a recomeçar o set do "
                        f"princípio ({len(_set_inteiro)} faixas). O espaço "
                        f"não fica em silêncio.")
                    self._event_q.append(("inf_reset_tocadas", None, []))

            if not novos:
                msgs.append("[∞] não encontrei mais nada para tocar. "
                            "Verifica se a biblioteca tem grelhas "
                            "calculadas.")

            self._event_q.append(("inf", novos, msgs))

        import threading
        t = threading.Thread(target=_worker, daemon=True, name="inf-extend")
        self._inf_thread = t
        t.start()

    def _replan_bg(self, ctx="replan"):
        """dj.replan() em thread de fundo. O replan pode disparar a carga da
        faixa seguinte (decode librosa + time-stretch da faixa INTEIRA — ver
        AutoDJ._plan_next), que demora segundos; feita na thread da UI era um
        dos "Não responde"."""
        dj = self.dj
        if dj is None:
            return
        t_ant = getattr(self, "_replan_thread", None)
        if t_ant is not None and t_ant.is_alive():
            return                          # já há um replan em curso

        def _bg():
            try:
                dj.replan()
            except Exception as e:
                self._event_q.append(("log", f"[{ctx}] {e}"))

        import threading
        t = threading.Thread(target=_bg, daemon=True, name="replan-bg")
        self._replan_thread = t
        t.start()

    def _inf_aplicar(self, novos, msgs):
        """Aplica o resultado da extensão [∞] (corre na thread da UI)."""
        for m in msgs:
            self._append(m)
        dj = self.dj
        if dj is None:
            return
        md = self.md or {}
        tocadas = getattr(self, "_inf_tocadas", None)
        if tocadas is None:
            tocadas = self._inf_tocadas = set()
        if not novos:
            self._inf_falhas = getattr(self, "_inf_falhas", 0) + 1
            self._append(self._t("inf_none"))
            tocadas.clear()
            return
        self._inf_falhas = 0
        # antes de acrescentar: estávamos na última faixa? (nesse caso o
        # "plano" era _mark_finished e é preciso replanear com as novas)
        era_ultima = dj._idx >= len(dj.playlist) - 1
        added = 0
        for p in novos:
            inf = md.get(os.path.normpath(p)) or {}
            try:
                bpm = float(inf.get("bpm", 0) or 0)
            except (TypeError, ValueError):
                bpm = 0.0
            if not (40.0 < bpm < 300.0):
                continue
            _sp = TrackSpec(
                path=p, bpm=bpm, downbeat=_downbeat_of(inf),
                mix_out=_mix_out_of(inf), name=os.path.basename(str(p)),
                sections=_sections_of(inf),
                beats=inf.get("beats") or None,
                mix_in=inf.get("kick_in"))
            _sp.estrutura = inf.get("estrutura_v2") or None
            dj.playlist.append(_sp)
            tocadas.add(os.path.normpath(p))
            added += 1
            self._append(self._tf("inf_add", n=os.path.basename(str(p))))
            # Também na PLAYLIST GERADA (UI): assim o set completo fica
            # visível, o realce da faixa atual funciona, e o Histórico →
            # "Guardar atual" grava a playlist INTEIRA (incluindo o que o
            # ∞ acrescentou), no fim ou quando se desliga o contínuo.
            try:
                inf2 = _info_of(self.md, p)
                bpm2 = inf2.get("bpm", "?")
                key2 = inf2.get("camelot", "?")
                bpm_txt = (f"{float(bpm2):.0f}"
                           if isinstance(bpm2, (int, float)) else str(bpm2))
                it = QListWidgetItem(
                    f"{len(self.playlist) + 1}. "
                    f"{os.path.basename(str(p))}   [{bpm_txt} BPM - {key2}]")
                it.setData(Qt.ItemDataRole.UserRole, _norm(str(p)))
                self.list_widget.addItem(it)
                self.playlist.append(p)
            except Exception as _e_ui:
                self._append(f"[∞] lista: {_e_ui}")
        if added:
            try:
                self._update_totals()
            except Exception:
                pass
        if added and (era_ultima or dj.finished):
            # O replan pode ter de CARREGAR a faixa seguinte (decode + warp
            # da faixa inteira = segundos) — nunca na thread da UI. Só é
            # preciso se o plano atual era "acabar" (última faixa/finished);
            # a meio da playlist a transição agendada continua válida.
            dj.finished = False
            self._replan_bg("[∞] replan")

    # ── refresh ──────────────────────────────────────────────────────────
    def _tick(self):
        """Mede o CORPO do tick e delega. MEDICAO TEMPORARIA.

        O salto ENTRE ticks ja' era medido, mas sozinho nao distingue duas
        coisas muito diferentes:
          • o corpo do tick demorou      -> a culpa e' de codigo nosso, aqui;
          • o corpo foi rapido mas o tick nem chegou a ser chamado a horas
            -> o Qt esteve ocupado noutra coisa (pintura, folhas de estilo)
               ou a thread principal nao apanhou o GIL.
        Sem esta separacao andamos a adivinhar qual das duas e'. Tirar quando
        o congelamento das transicoes estiver resolvido.
        """
        _t0 = time.monotonic()
        self._tick_partes = []
        try:
            self._tick_corpo()
        finally:
            _d = time.monotonic() - _t0
            self._tick_dur = _d
            if _d > 0.05 and DIAGNOSTICO_UI:
                # A REPARTICAO E' O QUE FALTAVA (24/08/2026).
                # "corpo demorou 380 ms" diz que a culpa e' nossa mas nao
                # diz de quem. Sem isto andei a adivinhar entre a pintura da
                # onda, o [∞] e o watchdog — tres sitios plausiveis, zero
                # medidas. Cada seccao carimba-se a si propria; so' se
                # imprime quando o tick ja' foi lento, portanto nao ha' custo
                # nenhum no caso normal.
                _p = getattr(self, "_tick_partes", None) or []
                _det = "  ".join(f"{n} {ms:.0f}" for n, ms in _p if ms >= 1.0)
                print(f"[tick] corpo demorou {_d * 1000:.0f} ms"
                      + (f"  ·  {_det}" if _det else "  ·  (nada com >1 ms)"))

    def _marco(self, nome, t_ini):
        """Carimba quanto custou uma seccao do tick. Devolve o relogio novo,
        para encadear marcos sem ter de repetir o `time.monotonic()`."""
        _agora = time.monotonic()
        if DIAGNOSTICO_UI:
            try:
                self._tick_partes.append((nome, (_agora - t_ini) * 1000.0))
            except Exception:
                pass
        return _agora

    def _tick_corpo(self):
        # ── DETECTOR DE TRAVAMENTO DA INTERFACE ──────────────────────────
        # Este temporizador dispara a cada 50 ms. Se passou muito mais do que
        # isso, a thread da interface esteve bloqueada — e o que interessa
        # saber é O QUÊ a bloqueou, não que bloqueou. O motor publica a fase
        # da carga em mixai_engine.FASE_CARGA; se estiver vazia no momento do
        # salto, o travamento não veio da carga da faixa seguinte e temos de
        # procurar noutro sítio (desenho da waveform, tags, base de dados).
        _agora = time.monotonic()
        _PULSO_UI[0] = _agora            # relógio de pulso lido pelo _VigiaUI
        _ant = getattr(self, "_tick_ant", None)
        self._tick_ant = _agora
        if _ant is not None:
            _salto = _agora - _ant
            # 0,30 s. Esteve temporariamente a 0,12 s a cacar a "tremura nas
            # transicoes", e o resultado dessa caca foi que o ciclo de eventos
            # NUNCA bloqueia nas transicoes: o maior salto medido foi 0,12 s.
            # O que parecia paragem era a posicao mostrada nos decks a nao
            # avancar enquanto a almofada escoava. Voltou ao limiar normal —
            # a 0,12 s isto escreve uma linha por qualquer soluco do sistema.
            if _salto > 0.30 and DIAGNOSTICO_UI:
                try:
                    import mixai_engine as _me
                    _fase = getattr(_me, "FASE_CARGA", "") or "(sem carga a decorrer)"
                except Exception:
                    _fase = "(?)"
                # CONSOLA, não só o log da janela: o log da janela é escrito
                # PELA thread que travou, portanto a linha só lá aparece
                # depois de tudo passar — e a ordem em relação às outras
                # mensagens perde-se, que é justamente o que interessa ver.
                # o tempo do tick ANTERIOR diz se o salto foi trabalho nosso
                # ou espera: corpo curto + salto longo = o Qt esteve noutra
                # coisa, nao aqui
                _dur = getattr(self, "_tick_dur", 0.0) * 1000.0
                print(f"[UI] parou {_salto:.2f}s · {_fase} "
                      f"· tick anterior {_dur:.0f} ms")
                self._append(self._tf("l_ui_parou",
                                      s=f"{_salto:.2f}", f=_fase))
        _tm = time.monotonic()
        # LINHAS QUE O MOTOR DISSE NUMA THREAD DE FUNDO. Ele já não toca no
        # widget a partir de lá (ver `Engine._dizer`): põe-nas numa fila e
        # somos nós, aqui, do lado certo, que as escrevemos.
        try:
            if self.eng is not None:
                self.eng.escoar_log()
        except Exception:
            pass
        # eventos vindos do thread de áudio (track change / transição)
        while self._event_q:
            ev = self._event_q.popleft()
            if ev[0] == "track":
                self._on_track_change(ev[1])
            elif ev[0] == "mix":
                self._append(self._tf("l_mixing", a=ev[1], b=ev[2]))
            elif ev[0] == "log":
                self._append(ev[1])
            elif ev[0] == "tags":
                self._aplicar_etiquetas(ev[1])
            elif ev[0] == "busca":
                self._aplicar_busca(ev[1][0], ev[1][1])
            elif ev[0] == "padmode":
                try:
                    self._deck_panel(ev[1])._set_mode(ev[2])
                except Exception:
                    pass
            elif ev[0] == "pad":
                try:
                    self._deck_panel(ev[1])._pad_pressed(ev[2])
                except Exception:
                    pass
            elif ev[0] == "padrel":
                try:
                    self._deck_panel(ev[1])._pad_released(ev[2])
                except Exception:
                    pass
            elif ev[0] == "fx_estado":
                # Widget -> tem de correr na thread da UI, daí passar pela
                # fila. O mostrar_fx já ignora repetições, e este evento
                # chega a cada volta do knob de profundidade.
                try:
                    self.mixer.mostrar_fx(ev[1], ev[2])
                except Exception:
                    pass
            elif ev[0] == "fx_btn":
                novo = not self.fx_check.isChecked()
                self.fx_check.setChecked(novo)     # dispara o _fx_toggled
                self._append("[DDJ-400] Creative FX "
                             + ("ON ✨" if novo else "OFF"))
            elif ev[0] == "browse":
                try:
                    self._ddj_browse(ev[1])
                except Exception:
                    pass
            elif ev[0] == "inf":
                try:
                    self._inf_aplicar(ev[1], ev[2])
                except Exception as _e_ia:
                    self._append(f"[∞] aplicar: {_e_ia}")
            elif ev[0] == "inf_reset_tocadas":
                # A extensão esgotou o repertório inédito e vai repetir. O
                # conjunto das já tocadas tem de ser limpo AQUI, na thread da
                # UI — é ela a dona do _inf_tocadas, e mexer-lhe a partir da
                # thread de fundo era uma corrida à espera de acontecer.
                try:
                    if getattr(self, "_inf_tocadas", None) is not None:
                        self._inf_tocadas.clear()
                except Exception:
                    pass
            elif ev[0] == "rec_done":
                self._rec_reset_ui()
                if ev[1]:
                    _p = str(ev[1])
                    self._append(self._tf("rec_saved", p=_p))
                    try:
                        r = QMessageBox.question(
                            self, self._t("rec_ok_t"),
                            self._tf("rec_ok_q", p=_p),
                            QMessageBox.StandardButton.Yes
                            | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.Yes)
                        if r == QMessageBox.StandardButton.Yes:
                            self._open_folder_explorer(
                                os.path.dirname(_p))
                    except Exception:
                        pass
                else:
                    self._append(self._t("rec_nothing"))
        _tm = self._marco("eventos", _tm)
        if self.eng is None:
            return
        # REC: mostra o tempo gravado no botão quando o som já disparou
        if getattr(self, "_rec_on", False):
            _rec = getattr(self.eng, "_rec", None)
            if _rec is not None and _rec.triggered:
                if not getattr(self, "_rec_ui_on", False):
                    self.rec_btn.setStyleSheet(self._REC_ON)
                    self._rec_ui_on = True
                _s = int(_rec.samples / max(1, self.eng.sr))
                self.rec_btn.setText(
                    f"■ ON {_s // 60:02d}:{_s % 60:02d}")
        self.deckA.refresh(); self.deckB.refresh(); self.mixer.refresh()
        _tm = self._marco("decks", _tm)
        self._rw_flip = not getattr(self, "_rw_flip", False)
        if self._rw_flip:                      # rhythm wave a 10 fps
            self.rhythm.render(self.eng)
            _tm = self._marco("rhythm", _tm)
        v = int(self.eng.crossfade.value * 1000)
        if abs(self.sl_xf.value() - v) > 5:
            self.sl_xf.blockSignals(True)
            self.sl_xf.setValue(v)
            self.sl_xf.blockSignals(False)
            # os lados têm cor fixa (sub-page azul, add-page vermelho); o Qt
            # pinta-os sozinho conforme a posição, não é preciso repintar.
        if self.fx_agent:
            self.fx_agent.tick()
            _tm = self._marco("fx", _tm)
        self._update_totals()
        _tm = self._marco("totais", _tm)
        # watchdog: se a faixa ao vivo acabou e a transição planeada nunca
        # chegou (ex.: seek para a frente), dispara a mistura imediatamente
        if self.dj is not None and not self.dj.finished:
            now = time.monotonic()
            # ∞: alimenta a playlist antes de ela acabar
            if getattr(self, "inf_check", None) is not None \
                    and self.inf_check.isChecked() \
                    and now - getattr(self, "_inf_last", 0.0) > 5.0:
                self._inf_last = now
                try:
                    if self.dj._idx >= len(self.dj.playlist) - 2:
                        # corre em thread de fundo; o resultado chega pela
                        # _event_q ("inf") e o replan é feito em _inf_aplicar
                        self._inf_estender()
                except Exception as _e_inf:
                    print(f"[∞] {_e_inf}")
                _tm = self._marco("infinito", _tm)
            if now - getattr(self, "_wd_last", 0.0) > 1.0:
                self._wd_last = now
                try:
                    d = self.dj.live_deck
                    xf = self.eng.crossfade
                    # NA ULTIMA FAIXA NAO SE REPLANEIA (correcao 12/08/2026).
                    # O watchdog existe para apanhar transicoes que nunca
                    # chegaram (ex.: seek para a frente). Na ultima faixa nao
                    # ha transicao nenhuma para apanhar — e replanear ali
                    # reagendava o fim do set para dali a uma faixa inteira,
                    # de segundo a segundo. Era metade do "fica no fim aos
                    # saltos"; a outra metade era o deck nao parar.
                    ha_seguinte = self.dj._idx + 1 < len(self.dj.playlist)
                    # MISTURA MANUAL NAO E' FIM DE FAIXA (13/08/2026).
                    # Mexer no crossfader a mao (o A⇄B, ou o cursor) muda o
                    # deck que se OUVE, mas o AutoDJ continua a achar que o
                    # deck ao vivo e' o outro. Esse fica em silencio, o
                    # watchdog le isso como "a faixa acabou antes do tempo",
                    # replaneia — e volta a fazer o mesmo um segundo depois,
                    # em ciclo. Era a enxurrada de "Faixa terminou antes do
                    # planeado" com a musica a continuar a tocar.
                    #
                    # Se o OUTRO deck esta a tocar, nao acabou nada: houve
                    # uma mistura manual. Nao se replaneia.
                    _outro_nome = "B" if self.dj._live == "A" else "A"
                    try:
                        _outro_toca = bool(self.eng.deck(_outro_nome).playing)
                    except Exception:
                        _outro_toca = False
                    # PAUSA A MAO NAO E' FIM DE FAIXA (15/08/2026).
                    #
                    # Faltava esta. O watchdog dava "faixa terminou" a
                    # qualquer deck parado com o crossfader assente — e uma
                    # pausa manual cumpre isso a letra. Carregar em pausa
                    # punha o automix a avancar em ciclo, uma vez por
                    # segundo. Relatado assim: "se eu parar a reproducao no
                    # deck o automix fica mal, tenho que tocar o parar".
                    #
                    # O watchdog existe para apanhar transicoes que NUNCA
                    # chegaram — o caso do seek para a frente, em que a faixa
                    # corre ate ao fim e para sozinha. Nesse caso nao sobra
                    # audio nenhum. Numa pausa a mao sobram minutos.
                    #
                    # Dois segundos de folga porque o fim exacto depende do
                    # escoamento da almofada de saida.
                    try:
                        _quase_no_fim = (d.remaining <= 2.0 * self.eng.sr)
                    except Exception:
                        _quase_no_fim = True     # sem dados, comporta-se como antes
                    if (ha_seguinte and d.buf is not None and not d.playing
                            and not _outro_toca and _quase_no_fim
                            and abs(xf.value - xf.tgt) < 1e-3):
                        self._append(self._t("l_end_early"))
                        self._replan_bg("watchdog")   # carga pesada fora da UI
                    elif _outro_toca and abs(xf.value - xf.tgt) < 1e-3:
                        # O crossfader assentou do outro lado e esse deck
                        # esta a tocar: o automix ADOPTA-O. Ver o metodo.
                        _alvo = 1.0 if _outro_nome == "B" else 0.0
                        if abs(xf.value - _alvo) < 0.02:
                            self._adoptar_deck_audivel(_outro_nome)
                except Exception:
                    pass
                _tm = self._marco("watchdog", _tm)
        if self.dj is not None and self.dj.finished:
            # ── O CONTÍNUO NÃO PÁRA (16/09/2026) ─────────────────────────
            # O limite era 2 tentativas vazias seguidas e depois `_stop()`.
            # Para o que este modo é — sonorizar um bar, uma loja, um hotel
            # durante horas — parar é o pior desfecho que há, e era o único
            # que o utilizador não podia aceitar.
            #
            # A extensão ganhou hoje uma rede que não pode vir vazia: volta
            # ao princípio do set que já está a tocar (ver `_inf_estender`).
            # Com ela, chegar aqui com falhas quer dizer que nem isso deu —
            # ou seja, playlist com menos de duas faixas. Aí parar é a única
            # coisa que sobra, mas passa a dizer-se PORQUÊ em vez de sair
            # com o «set terminado» de sempre, que num hotel não explica
            # nada a quem vai ver o que aconteceu.
            #
            # 6 e não 2: as tentativas são de 5 em 5 segundos e não custam
            # nada; desistir depressa é que custa.
            _inf_on = (getattr(self, "inf_check", None) is not None
                       and self.inf_check.isChecked())
            if _inf_on and getattr(self, "_inf_falhas", 0) < 6:
                self._inf_estender()
                _tm = self._marco("infinito-fim", _tm)
            else:
                if _inf_on:
                    self._append(self._t("inf_stopped_fail"))
                self._stop()

    def _on_track_change(self, name):
        self._append(self._tf("l_now_playing", n=name))
        row = -1
        for i, p in enumerate(self.playlist):
            if os.path.basename(str(p)) == name:
                row = i
                break
        if row >= 0:
            self._highlight_now(row)
            self._update_totals(row)

    def _highlight_now(self, row):
        self._clear_now_highlight()
        if 0 <= row < self.list_widget.count():
            self.list_widget.setCurrentRow(row)
            it = self.list_widget.item(row)
            if it:
                f = it.font(); f.setBold(True); it.setFont(f)
                it.setForeground(QColor("#00E5FF"))
                self.list_widget.scrollToItem(it)
        self._now_row = row

    def _clear_now_highlight(self):
        prev = self._now_row
        if prev is not None and 0 <= prev < self.list_widget.count():
            it = self.list_widget.item(prev)
            if it:
                f = it.font(); f.setBold(False); it.setFont(f)
                it.setForeground(QColor("#dddddd"))
        self._now_row = None

    # ── histórico (Generated Playlists, como o antigo) ────────────────────
    def _load_history(self):
        """Histórico: carregar, guardar a playlist atual e remover sets."""
        try:
            GENERATED_PLAYLISTS_FOLDER, _parse_playlist_m3u = _do_app(
                "GENERATED_PLAYLISTS_FOLDER", "_parse_playlist_m3u")
        except Exception as e:
            self._append(self._tf("l_hist_na", e=e))
            return
        import glob
        import re

        def _scan():
            fs = (glob.glob(os.path.join(GENERATED_PLAYLISTS_FOLDER, "*.m3u")) +
                  glob.glob(os.path.join(GENERATED_PLAYLISTS_FOLDER, "*.m3u8")))
            return sorted(fs, key=lambda p: os.path.basename(p).lower(),
                          reverse=True)

        files = _scan()
        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("saved_pls"))
        dlg.setMinimumSize(620, 460)
        dlg.setStyleSheet(self.styleSheet())
        v = QVBoxLayout(dlg)
        lw = QListWidget()

        def _fill():
            lw.clear()
            for p in files:
                try:
                    n = len([t for t in (_parse_playlist_m3u(p) or []) if t])
                    lw.addItem(f"{os.path.splitext(os.path.basename(p))[0]}"
                               f"  ({n} {self._t('tracks_w')})")
                except Exception:
                    lw.addItem(os.path.splitext(os.path.basename(p))[0])
            if lw.count():
                lw.setCurrentRow(0)
        _fill()
        v.addWidget(lw, 1)

        bt_load = QPushButton(self._t("load_sel"))
        bt_save = QPushButton(self._t("save_cur"))
        bt_del = QPushButton(self._t("remove_pl"))
        bt_del.setStyleSheet(
            "QPushButton{background:#2e0d13;color:#ff4658;border:1px solid #ff0045;"
            "border-radius:6px;padding:9px;font-weight:bold;}"
            "QPushButton:hover{background:#3d1019;}")
        v.addWidget(bt_load)
        h = QHBoxLayout()
        h.addWidget(bt_save)
        h.addWidget(bt_del)
        v.addLayout(h)

        def _do_save():
            if not self.playlist:
                QMessageBox.information(dlg, self._t("save_t"),
                                        self._t("no_pl_save"))
                return
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(dlg, self._t("save_pl_t"),
                                            self._t("set_name"))
            if not ok:
                return
            name = re.sub(r'[\\/:*?"<>|]', "_", name.strip()) or "Set"
            mx = 0
            for f in files:
                m = re.match(r"(\d{4})", os.path.basename(f))
                if m:
                    mx = max(mx, int(m.group(1)))
            os.makedirs(GENERATED_PLAYLISTS_FOLDER, exist_ok=True)
            path = os.path.join(GENERATED_PLAYLISTS_FOLDER,
                                f"{mx + 1:04d} - {name}.m3u")
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("#EXTM3U\n")
                    for p in self.playlist:
                        fh.write(_norm(p) + "\n")
            except Exception as e:
                QMessageBox.warning(dlg, self._t("l_hist_save_t"),
                                    self._tf("l_fail", e=e))
                return
            self._append(self._tf("l_hist_saved", n=os.path.basename(path),
                                  k=len(self.playlist)))
            files[:] = _scan()
            _fill()

        def _do_del():
            row = lw.currentRow()
            if row < 0 or row >= len(files):
                return
            p = files[row]
            if QMessageBox.question(
                    dlg, self._t("remove_t"),
                    f"{self._t('del_disk')}\n\n{os.path.basename(p)}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            try:
                os.remove(p)
            except Exception as e:
                QMessageBox.warning(dlg, self._t("l_hist_del_t"),
                                    self._tf("l_fail", e=e))
            files[:] = _scan()
            _fill()

        bt_save.clicked.connect(_do_save)
        bt_del.clicked.connect(_do_del)
        bt_load.clicked.connect(dlg.accept)
        lw.itemDoubleClicked.connect(lambda *_: dlg.accept())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        row = lw.currentRow()
        if row < 0 or row >= len(files):
            return
        tracks = [t for t in (_parse_playlist_m3u(files[row]) or []) if t]
        if tracks:
            self.set_playlist([_norm(t) for t in tracks])
            self._append(self._tf("l_hist_loaded",
                                  n=os.path.basename(files[row]),
                                  k=len(self.playlist)))

    # ── navegação ─────────────────────────────────────────────────────────
    def _show_main(self):
        mw = self.parent_window
        try:
            self.showMinimized()
            if mw is not None:
                mw.showMaximized(); mw.activateWindow(); mw.raise_()
        except Exception:
            pass

    def _t(self, key):
        """Texto da UI no idioma da app principal (pt/en/es)."""
        return _tr(self._lang, key)

    def _tf(self, tf_key, **kw):
        """Template traduzido com campos ({e}, {n}, …) preenchidos."""
        try:
            return _tr(self._lang, tf_key).format(**kw)
        except Exception:
            return _tr(self._lang, tf_key)
     

    def _append(self, text):
        try:
            import html
            t = str(text).rstrip("\n")
            _flog(t)                       # espelha para ~/.mixai_cache
            tl = t.lower()
            # cores por tipo de mensagem — cobre pt/en/es
            if (">> a tocar" in tl or ">> now playing" in tl
                    or ">> sonando" in tl):
                col, bold = "#ffffff", True
            elif (">> a misturar" in tl or ">> mixing" in tl
                    or ">> mezclando" in tl or tl.startswith(">> next")):
                col, bold = "#ff9d3b", True
            elif tl.startswith("fx:"):
                col, bold = "#00e5ff", False
            elif ("erro" in tl or "falha" in tl or "error" in tl
                    or "failed" in tl or "falló" in tl):
                col, bold = "#ff6b6b", False
            else:
                col, bold = "#cfd3d7", False
            esc = html.escape(t)
            if bold:
                esc = f"<b>{esc}</b>"
            # ── SÓ A THREAD DO QT PODE TOCAR NUM WIDGET (30/08/2026) ──────
            # [long comment]
            try:
                _app = QApplication.instance()
                _fora = (_app is not None
                         and QThread.currentThread() is not _app.thread())
            except Exception:
                _fora = False
            if _fora:
                try:
                    import threading as _th
                    import traceback as _tb
                    _n = getattr(self, "_append_fora", 0) + 1
                    self._append_fora = _n
                    if (_n in (1, 2, 3, 10, 100)
                            and _aviso_append_ligado()):
                        print(f"[UI] _append fora da thread do Qt x{_n} "
                              f"(thread '{_th.current_thread().name}') — "
                              f"reencaminhado. Quem chamou:")
                        for _l in _tb.format_stack()[-6:-1]:
                            print("     " + _l.rstrip())
                except Exception:
                    pass
                # reencaminhar...
                try:
                    _html = f'<span style="color:{col}">{esc}</span>'
                    QTimer.singleShot(
                        0, self, lambda _h=_html: self.log_box.append(_h))
                except Exception:
                    pass
                return
            self.log_box.append(f'<span style="color:{col}">{esc}</span>')
        except Exception:
            pass

    def closeEvent(self, event):
        # se algum deck estiver a TOCAR, pedir confirmação antes de fechar
        try:
            playing = self.eng is not None and (
                getattr(self.eng.deck("A"), "playing", False)
                or getattr(self.eng.deck("B"), "playing", False))
        except Exception:
            playing = False
        if playing:
            if QMessageBox.question(
                    self, self._t("close_t"),
                    self._t("close_q"),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        try:
            self.timer.stop()
        except Exception:
            pass
        try:
            if self.ddj is not None:
                self.ddj.stop()
        except Exception:
            pass
        # AO FECHAR e paragem TOTAL — nao o _stop(), que deixa o motor vivo
        # de proposito para se poder trocar de alinhamento sem cortar o som.
        # Com o _stop() aqui, a musica continuava a tocar de janela fechada.
        self._desligar_motor()
        # o pré-cálculo pode estar dentro do modelo; manda-se parar e a
        # referência fica em _ORFAOS para o Qt não a destruir a correr
        # (era assim que aparecia o depurador Just-In-Time ao fechar).
        try:
            self._parar_pre_grelhas()
        except Exception:
            pass
        try:
            if getattr(self, "_vigia", None) is not None:
                self._vigia.parar()
        except Exception:
            pass
        # ── VARRIMENTO DE TODAS AS QThreads DESTA JANELA ─────────────────
        # Isto é a causa do "quer depurar com o VS Code?" ao fechar.
        #
        # Só o _warm e o _prep é que estavam tratados. Ficavam de fora, entre
        # outras, as _ManualLoadThread guardadas em _mload_A/_mload_B — e uma
        # carga manual a meio dura segundos. Ao fechar a janela, o último
        # ponteiro Python para essa QThread desaparecia com a janela, o Qt
        # via-se a destruir uma thread ainda viva e chamava qFatal(), que no
        # Windows é abort() — e o abort() é que abre o depurador
        # Just-In-Time. Não era um erro de Python, por isso nunca aparecia
        # nos excepthooks; só ficava a linha "[Qt FATAL] QThread: Destroyed
        # while thread is still running" no mixai_crash.log.
        #
        # Varrer vars(self) em vez de listar nomes à mão é deliberado: cada
        # QThread nova que alguém acrescente fica coberta sem se lembrar
        # disto. Espera-se um pouco por cada uma e, se não morrer, guarda-se
        # a referência em _ORFAOS — manter o objecto vivo é o que impede o
        # aborto. NÃO se usa terminate(): matar uma thread a meio de uma
        # gravação na base deixa-a corrompida, e fechar a janela não vale
        # isso. Elas veem a bandeira e saem sozinhas.
        try:
            from PySide6.QtCore import QThread as _QT
            for _nome, _obj in list(vars(self).items()):
                try:
                    if not isinstance(_obj, _QT) or not _obj.isRunning():
                        continue
                    for _m in ("parar", "stop"):
                        _f = getattr(_obj, _m, None)
                        if callable(_f):
                            try:
                                _f()
                            except Exception:
                                pass
                            break
                    _obj.wait(1500)
                    if _obj.isRunning():
                        print(f"[MixAi] '{_nome}' ainda a correr no fecho — "
                              f"guardada para nao abortar o processo")
                        _ORFAOS.append(_obj)
                except Exception:
                    pass
        except Exception:
            pass
        mw = self.parent_window
        try:
            if mw is not None:
                mw._automix_window = None
                mw.showMaximized(); mw.activateWindow(); mw.raise_()
        except Exception:
            pass
        super().closeEvent(event)


# ═════════════════════════════════════════════════════════════════════
# AGENT FX NA MISTURA MANUAL, E AS LETRAS DO BROWSER
# ═════════════════════════════════════════════════════════════════════
#
# VEIO DO `mixai_dj_autodj.py` A 05/09/2026, E PORQUE
# ---------------------------------------------------
# Este bloco vivia no `mixai_dj_autodj.py` — 19 044 linhas que o cabecalho
# do `mixai_core.py` declara ABANDONADAS desde 12/08/2026. So' que nao
# estava abandonado de facto: o `mixai_fusion` e o `mixai_fusion_automix`
# importavam DE LA' estas funcoes, e UMA importacao basta para o
# PyInstaller levar o modulo inteiro. Eram 876 KB dentro do exe para ir
# buscar 244 linhas.
#
# E o sitio certo e' aqui, nao la': tudo o que este codigo usa —
# `_CreativeFX`, `_info_of`, `_sections_of`, `_downbeat_of` — ja' vive
# neste ficheiro, e a janela onde ele cola o botao e' a desta casa.
# Estava do outro lado por acidente historico, e pagava-se caro por isso.
#
# Os dois `from mixai_autodj_solo import ...` que este codigo fazia
# desapareceram na mudanca: agora e' o proprio modulo.
# ═════════════════════════════════════════════════════════════════════


_MANUAL_FX_OFF = (
    "QPushButton{background:#16212a;color:#00FFFF;border:1px solid #00BCD4;"
    "border-radius:6px;padding:10px 6px;font-size:13px;font-weight:bold;}"
    "QPushButton:hover{background:#0e2a33;}"
)


_MANUAL_FX_ON = (
    "QPushButton{background:#12336b;color:#bcd8ff;border:2px solid #2f81f7;"
    "border-radius:6px;padding:9px 5px;font-size:13px;font-weight:bold;}"
    "QPushButton:hover{background:#17408a;}"
)


class _ManualDJShim:
    """Faz de 'dj' para o _CreativeFX no modo manual: o 'live_deck' e o deck
    audivel segundo o crossfader, e a 'playlist' sao as faixas que estao nos
    decks — com a ESTRUTURA da base de dados.

    PORQUE E' QUE O MANUAL NAO TINHA EFEITOS NOS SITIOS CERTOS (16/08/2026).

    O _CreativeFX tem dois modos: o ESTRUTURAL, que poe o riser a abrir
    exactamente no drop e o echo a entrar no breakdown, e um recurso por
    intervalo de batidas, que dispara de 32 em 32 sem saber o que esta a
    tocar. Qual deles corre depende de _spec_of(deck) encontrar a faixa na
    `playlist` do dj.

    Aqui a playlist era uma lista VAZIA, fixa. Nunca encontrava nada, logo
    o modo estrutural nunca chegou a correr em mistura manual — e o log
    dizia-o em cada faixa ("sem estrutura ... efeitos por intervalo"), so'
    que parecia um problema da faixa e nao do modo.

    A estrutura existe: e' a mesma que o automix usa, esta' na base de dados
    (`sections_v2` + `estrutura_v2`, com os drops e breakdowns ja detectados).
    So' faltava ir busca-la. Constroi-se aqui, a pedido, com o caminho da
    faixa que esta' no deck.
    """
    def __init__(self, win):
        self._win = win
        self._cache = {}          # caminho -> spec (ou None se nao houver)

    # ---- estrutura das faixas que estao nos decks --------------------------
    def _spec_da_bd(self, caminho):
        """Um 'spec' minimo com o que o _CreativeFX._build_plan le: nome,
        bpm ORIGINAL, downbeat em segundos, sections e a meta com as listas
        explicitas de drops/breakdowns."""
        md = getattr(self._win, "md", None) or {}
        info = _info_of(md, caminho)
        if not info:
            return None
        secs = _sections_of(info)
        est = info.get("estrutura_v2") or None
        if not secs and not est:
            return None                     # sem estrutura: recurso e' honesto
        try:
            bpm = float(info.get("bpm", 0) or 0)
        except (TypeError, ValueError):
            bpm = 0.0
        if not (40.0 < bpm < 300.0):
            return None                     # sem BPM nao ha' conversao t->beat

        class _Spec:
            pass

        sp = _Spec()
        # TEM de ser o mesmo texto que o deck tem em track_name, senao o
        # _spec_of nao casa. Na carga manual o load_file guarda o CAMINHO
        # COMPLETO em track_name (mixai_engine.load_file -> load_buffer,
        # name=str(path)), ao contrario do automix que guarda o nome do
        # ficheiro. E' por isso que aqui se usa o caminho tal e qual.
        sp.name = caminho
        sp.bpm = bpm
        sp.downbeat = _downbeat_of(info)
        sp.sections = secs
        sp.estrutura = est
        return sp

    @property
    def playlist(self):
        eng = getattr(self._win, "eng", None)
        if eng is None:
            return []
        out = []
        for nm in ("A", "B"):
            try:
                d = eng.deck(nm)
            except Exception:
                continue
            cam = str(getattr(d, "track_name", "") or "")
            if not cam:
                continue
            if cam not in self._cache:
                try:
                    self._cache[cam] = self._spec_da_bd(cam)
                except Exception:
                    self._cache[cam] = None
                if len(self._cache) > 32:      # nao cresce sem fim num set
                    self._cache.pop(next(iter(self._cache)))
            sp = self._cache.get(cam)
            if sp is not None:
                out.append(sp)
        return out

    @property
    def live_deck(self):
        eng = getattr(self._win, "eng", None)
        if eng is None:
            raise RuntimeError("sem motor manual")
        a = eng.deck("A")
        b = eng.deck("B")
        a_on = getattr(a, "playing", False) and getattr(a, "buf", None) is not None
        b_on = getattr(b, "playing", False) and getattr(b, "buf", None) is not None
        try:
            xf = float(eng.crossfade.value)
        except Exception:
            xf = 0.0
        if a_on and b_on:
            return b if xf >= 0.5 else a
        if b_on:
            return b
        return a


class _ManualFXAgent:
    """Liga o agente de efeitos criativos (_CreativeFX) a MISTURA MANUAL do
    player Automix, comandado por um botao on/off no topo. So atua quando NAO
    ha Automix a decorrer (ai e o agente do Automix que trata dos FX)."""
    def __init__(self, win):
        from PySide6.QtCore import QTimer
        self.win = win
        self.enabled = False
        self.agent = None
        self._eng = None
        self._dj = _ManualDJShim(win)
        self.timer = QTimer(win)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)
        self.btn = None

    def _intensity(self):
        try:
            return self.win.fx_intensity.currentText()
        except Exception:
            return "medium"

    def _log(self, msg):
        try:
            self.win._append(msg)
        except Exception:
            print(msg)

    def install_button(self):
        from PySide6.QtWidgets import QPushButton
        btn = QPushButton("Agent FX: OFF")
        btn.setStyleSheet(_MANUAL_FX_OFF)
        btn.setToolTip("Toggle the DJ agent effects during manual mixing "
                       "(echo / filter / flanger on the beat).")
        btn.clicked.connect(self.toggle)
        self.btn = btn
        try:
            layout = self.win.start_btn.parentWidget().layout()
            layout.insertWidget(layout.indexOf(self.win.history_btn), btn, 1)
        except Exception:
            try:
                self.win.start_btn.parentWidget().layout().addWidget(btn)
            except Exception:
                pass
        return btn

    def toggle(self):
        self.enabled = not self.enabled
        if self.enabled:
            if self.btn:
                self.btn.setText("Agent FX: ON")
                self.btn.setStyleSheet(_MANUAL_FX_ON)
            self.timer.start()
            self._log("[Agent] Manual-mix effects: ON")
        else:
            self.timer.stop()
            if self.agent is not None:
                self.agent.enabled = False
            if self.btn:
                self.btn.setText("Agent FX: OFF")
                self.btn.setStyleSheet(_MANUAL_FX_OFF)
            self._log("[Agent] Manual-mix effects: OFF")

    def _tick(self):
        if not self.enabled:
            return
        win = self.win
        eng = getattr(win, "eng", None)
        if eng is None:
            return
        if getattr(win, "dj", None) is not None:
            return
        if self.agent is None or self._eng is not eng:
            self._eng = eng
            self.agent = _CreativeFX(eng, self._dj, win._append,
                                     self._intensity(),
                                     tr=getattr(win, "_tf", None))
            self.agent.enabled = True
        try:
            self.agent.set_intensity(self._intensity())
        except Exception:
            pass
        try:
            self.agent.tick()
        except Exception:
            pass


def _attach_manual_fx_button(win):
    """Acrescenta o botao 'Agent FX' (efeitos na mistura manual) ao player
    Automix. Sem painel Co-Pilot. Falha em silencio se a janela nao suportar."""
    try:
        win._manual_fx = _ManualFXAgent(win)
        win._manual_fx.install_button()
    except Exception as e:
        print(f"[Automix] Agent FX indisponivel: {e}")


_AMX_BROWSER_QSS = (
    "QTreeWidget{background:#1a1a1a;border:1px solid #2a2a2a;color:#ddd;"
    "font-size:16px;border-radius:5px;} QTreeWidget::item{padding:6px 3px;}"
    "QTreeWidget::item:selected{background:#0077A3;color:#fff;}"
)


_AMX_FOLDER_QSS = (
    "QTreeWidget{background:#1a1a1a;border:1px solid #2a2a2a;color:#ddd;"
    "font-size:16px;border-radius:5px;}"
    "QHeaderView::section{background:#22262b;color:#9aa0a6;padding:6px;"
    "border:0;border-right:1px solid #2a2a2a;font-size:13px;}"
    "QTreeWidget::item{padding:5px 4px;}"
    "QTreeWidget::item:selected{background:#0077A3;color:#fff;}"
)


def _bump_automix_fonts(win):
    """Aumenta o tipo de letra da arvore BROWSER e da tabela de musicas
    (FOLDER) do player Automix."""
    try:
        win.browser.tree.setStyleSheet(_AMX_BROWSER_QSS)
    except Exception as e:
        print(f"[Automix] fonte do browser indisponivel: {e}")
    try:
        win.folder_files.setStyleSheet(_AMX_FOLDER_QSS)
    except Exception as e:
        print(f"[Automix] fonte da tabela indisponivel: {e}")


# alias para compatibilidade com o open_automix_player
AutoDJWindow = AutoDJSoloWindow
# v5.0.1: i18n pt/en/es completo (UI + operações do agente DJ)




