#!/usr/bin/env python3
"""Anima gráficos de posição e trajetória do pêndulo usando Manim Community."""

import argparse
from bisect import bisect_right
import csv
from dataclasses import dataclass
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap

from amortecimento import AmortecimentoIndisponivel, estimar_amortecimento, validar_parametros


@dataclass
class Dados:
    tempos: list[float]
    x: list[float]
    y: list[float]
    frames: int
    detectados: int


def ler_dados(caminho):
    """Preserva falhas de detecção como NaN para interromper as curvas."""
    tempos, xs, ys = [], [], []
    anterior_frame = anterior_tempo = None
    total = detectados = 0
    with Path(caminho).open(newline="", encoding="utf-8-sig") as arquivo:
        leitor = csv.DictReader(arquivo)
        obrigatorias = {"frame", "tempo_s", "detectado", "x_px", "y_px"}
        faltantes = obrigatorias - set(leitor.fieldnames or [])
        if faltantes:
            raise ValueError(f"Colunas ausentes no CSV: {', '.join(sorted(faltantes))}.")
        for linha in leitor:
            numero = leitor.line_num
            try:
                frame = int(linha["frame"])
                tempo = float(linha["tempo_s"])
                flag = linha["detectado"]
                if frame < 0 or not math.isfinite(tempo) or tempo < 0:
                    raise ValueError("frame e tempo devem ser não negativos e finitos")
                if anterior_frame is not None and (
                    frame <= anterior_frame or tempo <= anterior_tempo
                ):
                    raise ValueError("frames e tempos devem estar em ordem crescente")
                if flag not in ("0", "1"):
                    raise ValueError("detectado deve ser 0 ou 1")
                x = float(linha["x_px"]) if flag == "1" else math.nan
                y = float(linha["y_px"]) if flag == "1" else math.nan
                if flag == "1" and not (math.isfinite(x) and math.isfinite(y)):
                    raise ValueError("posição detectada deve ter X e Y finitos")
            except (TypeError, ValueError) as erro:
                raise ValueError(f"Dados inválidos na linha {numero}: {erro}.") from erro
            # Também interrompe as linhas quando frames foram removidos do CSV.
            if anterior_frame is not None and frame > anterior_frame + 1:
                tempos.append(math.nan)
                xs.append(math.nan)
                ys.append(math.nan)
            tempos.append(tempo)
            xs.append(x)
            ys.append(y)
            total += 1
            detectados += flag == "1"
            anterior_frame, anterior_tempo = frame, tempo

    if total == 0:
        raise ValueError("O CSV não contém dados.")
    if detectados == 0:
        raise ValueError("O CSV não contém nenhuma posição detectada para construir o gráfico.")
    return Dados(tempos, xs, ys, total, detectados)


def segmentar(dados):
    """Separa detecções consecutivas, sem ligar curvas através de falhas."""
    trechos, trecho = [], []
    for ponto in zip(dados.tempos, dados.x, dados.y):
        if all(math.isfinite(valor) for valor in ponto):
            trecho.append(ponto)
        elif trecho:
            trechos.append(trecho)
            trecho = []
    if trecho:
        trechos.append(trecho)
    return trechos


def limites(valores):
    """Limites com margem e passos legíveis, inclusive para séries constantes."""
    validos = [valor for valor in valores if math.isfinite(valor)]
    minimo, maximo = min(validos), max(validos)
    margem = (maximo - minimo) * 0.05 or max(1, abs(minimo) * 0.05)
    minimo, maximo = minimo - margem, maximo + margem
    desejado = (maximo - minimo) / 5
    potencia = 10 ** math.floor(math.log10(desejado))
    passo = next(fator * potencia for fator in (1, 2, 5, 10) if fator * potencia >= desejado)
    return (math.floor(minimo / passo) * passo, math.ceil(maximo / passo) * passo, passo)


def abrir_video(caminho):
    if sys.platform == "win32":
        os.startfile(str(caminho))
    else:
        comando = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([comando, str(caminho)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def gerar_grafico(csv_path, saida=None, mostrar=False, duracao=12, qualidade="media", massa=None, comprimento=None):
    csv_path = Path(csv_path)
    saida = Path(saida) if saida is not None else csv_path.with_name("grafico_pendulo.mp4")
    if saida.suffix.lower() != ".mp4":
        raise ValueError("A saída da animação deve ter extensão .mp4.")
    if saida.resolve() == csv_path.resolve():
        raise ValueError("A saída deve ser diferente do CSV de entrada.")
    if not math.isfinite(duracao) or duracao <= 0:
        raise ValueError("A duração deve ser positiva e finita.")
    qualidades = {"baixa": (854, 480, 15), "media": (1280, 720, 30), "alta": (1920, 1080, 60)}
    if qualidade not in qualidades:
        raise ValueError("A qualidade deve ser baixa, media ou alta.")
    validar_parametros(massa, comprimento)
    dados = ler_dados(csv_path)
    trechos = segmentar(dados)
    resultado, motivo = None, ""
    try:
        resultado = estimar_amortecimento(trechos, massa, comprimento)
    except AmortecimentoIndisponivel as erro:
        motivo = str(erro)
    try:
        import manim as mn
        import numpy as np
    except ImportError as erro:
        raise RuntimeError(
            "Instale Manim e as dependências: python -m pip install -r requirements.txt"
        ) from erro

    tempos = [t for t in dados.tempos if math.isfinite(t)]
    inicio, fim = tempos[0], tempos[-1]
    faixa_t = limites(tempos)
    faixa_x, faixa_y = limites(dados.x), limites(dados.y)

    class GraficosPendulo(mn.Scene):
        def construct(self):
            titulo = mn.Text("Movimento do pêndulo", font_size=32).move_to([0, 3.55, 0])
            resumo = mn.Text(
                f"{dados.detectados}/{dados.frames} frames com detecção · posições em pixels",
                font_size=18, color=mn.GREY_B,
            ).move_to([0, 3.1, 0])
            self.play(mn.FadeIn(titulo), mn.FadeIn(resumo), run_time=0.6)

            def painel(faixa_h, faixa_v, largura, altura, centro, nome, rotulo_h, rotulo_v, inverter=False):
                eixo_v = (-faixa_v[1], -faixa_v[0], faixa_v[2]) if inverter else faixa_v
                eixos = mn.Axes(
                    x_range=faixa_h, y_range=eixo_v,
                    x_length=largura, y_length=altura, tips=False,
                    axis_config={"include_numbers": False, "include_ticks": False, "color": mn.GREY_B},
                ).move_to(centro)
                grade, numeros = mn.VGroup(), mn.VGroup()
                for valor in np.arange(faixa_h[0], faixa_h[1] + faixa_h[2] * 0.5, faixa_h[2]):
                    base = eixos.c2p(valor, eixo_v[0])
                    grade.add(mn.Line(base, eixos.c2p(valor, eixo_v[1]), color=mn.GREY_D, stroke_width=0.5))
                    numeros.add(mn.Text(f"{valor:g}", font_size=12).next_to(base, mn.DOWN, buff=0.08))
                for valor in np.arange(eixo_v[0], eixo_v[1] + eixo_v[2] * 0.5, eixo_v[2]):
                    base = eixos.c2p(faixa_h[0], valor)
                    grade.add(mn.Line(base, eixos.c2p(faixa_h[1], valor), color=mn.GREY_D, stroke_width=0.5))
                    numero = -valor if inverter else valor
                    numeros.add(mn.Text(f"{numero:g}", font_size=12).next_to(base, mn.LEFT, buff=0.08))
                textos = mn.VGroup(
                    mn.Text(nome, font_size=21).next_to(eixos, mn.UP, buff=0.2),
                    mn.Text(rotulo_h, font_size=15).next_to(eixos, mn.DOWN, buff=0.4),
                    mn.Text(rotulo_v, font_size=15).rotate(mn.PI / 2).next_to(eixos, mn.LEFT, buff=0.65),
                )
                return eixos, mn.VGroup(grade, eixos, numeros, textos)

            eixo_x, grupo_x = painel(faixa_t, faixa_x, 5.1, 1.65, [-3.1, 1.55, 0], "Posição horizontal", "Tempo (s)", "X (px)")
            eixo_y, grupo_y = painel(faixa_t, faixa_y, 5.1, 1.65, [-3.1, -1.35, 0], "Posição vertical", "Tempo (s)", "Y (px)")
            # Mesma escala em X e Y para preservar a forma da trajetória.
            escala = min(4.5 / (faixa_x[1] - faixa_x[0]), 4.5 / (faixa_y[1] - faixa_y[0]))
            eixo_xy, grupo_xy = painel(
                faixa_x, faixa_y, escala * (faixa_x[1] - faixa_x[0]),
                escala * (faixa_y[1] - faixa_y[0]), [3.5, 0, 0],
                "Trajetória na imagem", "X (px)", "Y (px; aumenta para baixo)", inverter=True,
            )
            self.play(mn.FadeIn(grupo_x), mn.FadeIn(grupo_y), mn.FadeIn(grupo_xy), run_time=0.6)

            relogio = mn.ValueTracker(inicio)
            numero = mn.DecimalNumber(inicio, num_decimal_places=2, font_size=20, mob_class=mn.Text)
            legenda_tempo = mn.Text("Tempo do vídeo (s):", font_size=19).move_to([-1, -3.3, 0])
            numero.next_to(legenda_tempo, mn.RIGHT, buff=0.15)
            numero.add_updater(lambda mob: mob.set_value(relogio.get_value()))
            self.add(legenda_tempo, numero)

            def curva(trecho, eixos, coordenadas, cor):
                instantes = [p[0] for p in trecho]
                pontos = np.array([eixos.c2p(*coordenadas(*p)) for p in trecho])
                linha = mn.VMobject(color=cor, stroke_width=2)
                ponta = mn.Dot(pontos[0], radius=0.04, color=cor).set_opacity(0)
                grupo = mn.VGroup(linha, ponta)
                completo = False

                def atualizar(_):
                    nonlocal completo
                    tempo = relogio.get_value()
                    quantidade = bisect_right(instantes, tempo)
                    if quantidade == 0:
                        return
                    visiveis = pontos[:quantidade]
                    if quantidade < len(pontos):
                        anterior = quantidade - 1
                        fracao = (tempo - instantes[anterior]) / (instantes[quantidade] - instantes[anterior])
                        atual = pontos[anterior] + fracao * (pontos[quantidade] - pontos[anterior])
                        visiveis = np.vstack([visiveis, atual])
                    if not completo:
                        if len(visiveis) > 1:
                            linha.set_points_as_corners(visiveis)
                        completo = quantidade == len(pontos)
                    # Uma detecção isolada permanece visível como um ponto.
                    visivel = len(pontos) == 1 or tempo <= instantes[-1]
                    ponta.move_to(visiveis[-1]).set_opacity(1 if visivel else 0)

                grupo.add_updater(atualizar)
                grupo.update(0)
                self.add(grupo)

            for trecho in trechos:
                curva(trecho, eixo_x, lambda t, x, y: (t, x), mn.BLUE_C)
                curva(trecho, eixo_y, lambda t, x, y: (t, y), mn.ORANGE)
                curva(trecho, eixo_xy, lambda t, x, y: (x, -y), mn.TEAL_C)
            if fim > inicio:
                self.play(relogio.animate.set_value(fim), run_time=duracao, rate_func=mn.linear)
            else:
                self.wait(duracao)
            self.wait(1)
            # Remove atualizadores antes da transição para a tela de resultados.
            for objeto in self.mobjects:
                objeto.clear_updaters(recursive=True)
            self.play(*[mn.FadeOut(objeto) for objeto in list(self.mobjects)], run_time=0.6)
            cabecalho = mn.Text("Resultados da análise", font_size=32)
            parametros = mn.Text(f"Massa: {massa:g} kg  ·  Comprimento efetivo: {comprimento:g} m", font_size=21)
            if resultado is not None:
                linhas = [
                    cabecalho, parametros,
                    mn.Text(f"Fator de qualidade: Q = {resultado.fator_qualidade:.5g}", font_size=28, color=mn.GOLD),
                    mn.Text(f"Ajuste exponencial: R² = {resultado.r2:.4f}", font_size=24, color=mn.TEAL_C),
                ]
            else:
                linhas = [
                    cabecalho, parametros,
                    mn.Text("Ajuste exponencial e Q indisponíveis", font_size=28, color=mn.YELLOW),
                    mn.Text(textwrap.fill(motivo, width=70), font_size=21),
                    mn.Text("Confira a detecção e use um vídeo com mais oscilações e decaimento visível.", font_size=18, color=mn.GREY_B),
                ]
            cartao = mn.VGroup(*linhas).arrange(mn.DOWN, buff=0.3)
            if cartao.width > 13:
                cartao.scale_to_fit_width(13)
            if cartao.height > 7:
                cartao.scale_to_fit_height(7)
            cartao.move_to(mn.ORIGIN)
            self.play(mn.FadeIn(cartao), run_time=0.6)
            self.wait(6)

    saida = saida.resolve()
    saida.parent.mkdir(parents=True, exist_ok=True)
    largura, altura, fps = qualidades[qualidade]
    # Mantém caches e segmentos intermediários fora da pasta dos resultados.
    with tempfile.TemporaryDirectory(prefix="pendulo_manim_") as pasta:
        with mn.tempconfig({
            "renderer": "cairo", "pixel_width": largura, "pixel_height": altura,
            "frame_width": 14.222222, "frame_height": 8, "frame_rate": fps,
            "background_color": "#0f172a", "format": "mp4", "write_to_movie": True,
            "save_last_frame": False, "preview": False, "disable_caching": True,
            "media_dir": pasta, "video_dir": str(saida.parent),
            "partial_movie_dir": str(Path(pasta) / "parciais"),
            "output_file": saida.stem,
        }):
            GraficosPendulo().render()
    renderizado = saida.with_suffix(".mp4")
    if renderizado != saida and renderizado.is_file():
        renderizado.replace(saida)
    if not saida.is_file():
        raise RuntimeError(f"O Manim não gerou o vídeo esperado: {saida}")
    if resultado is not None:
        print(f"Amortecimento: c={resultado.coeficiente_torque:.6g} N·m·s; b={resultado.coeficiente_forca:.6g} kg/s; beta={resultado.beta:.6g} s^-1; Q={resultado.fator_qualidade:.6g}; R²={resultado.r2:.4f}")
    else:
        print(f"Amortecimento indisponível: {motivo}")
    if mostrar:
        try:
            abrir_video(saida)
        except OSError as erro:
            print(f"Vídeo salvo, mas não foi possível abri-lo automaticamente: {erro}", file=sys.stderr)
    return saida


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="posicoes.csv gerado por analisar_pendulo.py.")
    parser.add_argument("--saida", type=Path, help="Arquivo .mp4; padrão: grafico_pendulo.mp4 ao lado do CSV.")
    parser.add_argument("--mostrar", action="store_true", help="Abre o vídeo depois da renderização.")
    parser.add_argument("--duracao", type=float, default=12, help="Duração do desenho das curvas em segundos; padrão: 12 (mais cerca de 9,4 s de apresentação, transições e resultado).")
    parser.add_argument("--qualidade", choices=("baixa", "media", "alta"), default="media", help="baixa: 480p/15 FPS; media: 720p/30 FPS; alta: 1080p/60 FPS.")
    parser.add_argument("--massa", type=float, required=True, help="Massa do peso do pêndulo em kg; exemplo: 0.100 para 100 g.")
    parser.add_argument("--comprimento", type=float, required=True, help="Comprimento efetivo em metros, do ponto de suspensão ao centro do peso.")
    args = parser.parse_args(argv)
    try:
        saida = gerar_grafico(args.csv, args.saida, args.mostrar, args.duracao, args.qualidade, args.massa, args.comprimento)
    except (OSError, RuntimeError, ValueError, csv.Error) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    print(f"Animação salva em: {saida.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
