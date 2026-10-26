#!/usr/bin/env python3
"""Localiza o peso preto de um pêndulo filmado contra uma parede branca."""

import argparse
import csv
from dataclasses import dataclass
import math
from pathlib import Path
import sys

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None


@dataclass
class Deteccao:
    x: float
    y: float
    area: float
    contorno: object


def detectar(frame, limiar=50, kernel=7, area_minima=100, roi=None):
    """Retorna máscara de pixels escuros e centro do maior corpo após abertura.

    O fio aparece na máscara original, mas a abertura com um elemento elíptico
    remove estruturas finas antes do cálculo do centro do peso.
    """
    altura, largura = frame.shape[:2]
    x, y, w, h = roi if roi is not None else (0, 0, largura, altura)
    cinza = cv2.cvtColor(frame[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
    _, recorte = cv2.threshold(cinza, limiar, 255, cv2.THRESH_BINARY_INV)
    mascara = np.zeros((altura, largura), dtype=np.uint8)
    mascara[y:y + h, x:x + w] = recorte

    elemento = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel, kernel))
    corpos = cv2.morphologyEx(recorte, cv2.MORPH_OPEN, elemento)
    contornos, _ = cv2.findContours(
        corpos, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    candidatos = [c for c in contornos if cv2.contourArea(c) >= area_minima]
    if not candidatos:
        return mascara, None

    contorno = max(candidatos, key=cv2.contourArea)
    momentos = cv2.moments(contorno)
    if momentos["m00"] == 0:
        return mascara, None
    contorno = contorno + np.array([[[x, y]]], dtype=np.int32)
    return mascara, Deteccao(
        x=x + momentos["m10"] / momentos["m00"],
        y=y + momentos["m01"] / momentos["m00"],
        area=cv2.contourArea(contorno),
        contorno=contorno,
    )


def argumentos(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Arquivo de vídeo de entrada.")
    parser.add_argument("--saida", type=Path, help="Pasta de saída (padrão: resultados/NOME_DO_VIDEO).")
    parser.add_argument("--limiar", type=int, default=50, help="Pixels com intensidade <= limiar são pretos (0 a 255; padrão: 50).")
    parser.add_argument("--kernel", type=int, default=7, help="Diâmetro ímpar do filtro que remove o fio, em pixels (padrão: 7).")
    parser.add_argument("--area-minima", type=float, default=100, help="Área mínima do peso após filtragem, em px² (padrão: 100).")
    parser.add_argument("--roi", type=int, nargs=4, metavar=("X", "Y", "LARGURA", "ALTURA"), help="Restringe a busca a um retângulo; coordenadas de saída continuam relativas ao frame inteiro.")
    parser.add_argument("--fps", type=float, help="Substitui o FPS do vídeo para calcular o tempo e gravar os vídeos de saída.")
    parser.add_argument("--salvar-videos", action="store_true", help="Grava mascara.mp4 e rastreamento.mp4.")
    parser.add_argument("--mostrar", action="store_true", help="Exibe a análise; pressione Q ou Esc para interromper.")
    args = parser.parse_args(argv)
    if not 0 <= args.limiar <= 255:
        parser.error("--limiar deve estar entre 0 e 255.")
    if args.kernel < 3 or args.kernel % 2 == 0:
        parser.error("--kernel deve ser ímpar e >= 3.")
    if not math.isfinite(args.area_minima) or args.area_minima <= 0:
        parser.error("--area-minima deve ser positiva e finita.")
    if args.fps is not None and (not math.isfinite(args.fps) or args.fps <= 0):
        parser.error("--fps deve ser positivo e finito.")
    if args.roi is not None:
        x, y, w, h = args.roi
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            parser.error("--roi exige X e Y >= 0 e largura e altura > 0.")
    return args


def analisar(args):
    if cv2 is None or np is None:
        raise RuntimeError("Instale as dependências: python -m pip install -r requirements.txt")
    if not args.video.is_file():
        raise ValueError(f"Vídeo não encontrado: {args.video}")

    captura = cv2.VideoCapture(str(args.video))
    gravadores = []
    try:
        if not captura.isOpened():
            raise ValueError("Não foi possível abrir o vídeo. Verifique o arquivo e o codec.")
        ok, frame = captura.read()
        if not ok:
            raise ValueError("O vídeo não contém frames decodificáveis.")
        altura, largura = frame.shape[:2]
        if args.roi is not None:
            x, y, w, h = args.roi
            if x + w > largura or y + h > altura:
                raise ValueError(f"A ROI ultrapassa o frame de {largura} x {altura} pixels.")
        fps = args.fps if args.fps is not None else captura.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("FPS inválido no arquivo. Informe o valor com --fps, por exemplo --fps 30.")

        saida = args.saida or Path("resultados") / args.video.stem
        csv_path = saida / "posicoes.csv"
        destinos = [csv_path]
        if args.salvar_videos:
            destinos.extend([saida / "mascara.mp4", saida / "rastreamento.mp4"])
            if largura % 2 or altura % 2:
                raise ValueError("A gravação MP4 exige largura e altura pares. Execute sem --salvar-videos para gerar o CSV.")
        for destino in destinos:
            if destino.resolve() == args.video.resolve() or destino.exists():
                raise ValueError(f"Arquivo já existe: {destino}. Escolha outra pasta com --saida.")
        saida.mkdir(parents=True, exist_ok=True)

        if args.salvar_videos:
            for destino in destinos[1:]:
                gravador = cv2.VideoWriter(
                    str(destino), cv2.VideoWriter_fourcc(*"mp4v"), fps, (largura, altura)
                )
                gravadores.append(gravador)
                if not gravador.isOpened():
                    raise RuntimeError(f"Não foi possível criar {destino}; verifique o suporte ao codec MP4.")

        total = encontrados = 0
        interrompido = False
        with csv_path.open("x", newline="", encoding="utf-8") as arquivo:
            writer = csv.writer(arquivo)
            writer.writerow(["frame", "tempo_s", "detectado", "x_px", "y_px", "area_px2"])
            while ok:
                if frame.shape[:2] != (altura, largura):
                    raise ValueError("O vídeo mudou de resolução durante a leitura.")
                mascara, deteccao = detectar(
                    frame, args.limiar, args.kernel, args.area_minima, args.roi
                )
                tempo = total / fps
                writer.writerow([
                    total, f"{tempo:.6f}", int(deteccao is not None),
                    f"{deteccao.x:.3f}" if deteccao else "",
                    f"{deteccao.y:.3f}" if deteccao else "",
                    f"{deteccao.area:.3f}" if deteccao else "",
                ])
                total += 1
                encontrados += deteccao is not None

                if args.salvar_videos or args.mostrar:
                    anotado = frame.copy()
                    if args.roi is not None:
                        x, y, w, h = args.roi
                        cv2.rectangle(anotado, (x, y), (x + w - 1, y + h - 1), (255, 150, 0), 1)
                    if deteccao:
                        centro = (round(deteccao.x), round(deteccao.y))
                        cv2.drawContours(anotado, [deteccao.contorno], -1, (0, 200, 0), 2)
                        cv2.drawMarker(anotado, centro, (0, 0, 255), cv2.MARKER_CROSS, 16, 2)
                    status = "detectado" if deteccao else "sem deteccao"
                    cv2.putText(anotado, f"frame={total - 1} t={tempo:.3f}s {status}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                    if args.salvar_videos:
                        gravadores[0].write(cv2.cvtColor(mascara, cv2.COLOR_GRAY2BGR))
                        gravadores[1].write(anotado)
                    if args.mostrar:
                        cv2.imshow("Pendulo - Q ou Esc para sair", anotado)
                        cv2.imshow("Mascara: branco = objeto escuro", mascara)
                        if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                            interrompido = True
                            break
                ok, frame = captura.read()

        print(f"{'Interrompido' if interrompido else 'Concluído'}: {total} frames processados; {encontrados} com detecção; {total - encontrados} sem detecção.")
        print(f"CSV: {csv_path.resolve()}")
        if args.salvar_videos:
            print(f"Vídeos: {saida.resolve()}")
        return total, encontrados
    finally:
        captura.release()
        for gravador in gravadores:
            gravador.release()
        if args.mostrar:
            cv2.destroyAllWindows()


def main(argv=None):
    args = argumentos(argv)
    try:
        analisar(args)
    except (OSError, RuntimeError, ValueError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    except Exception as erro:
        if cv2 is not None and isinstance(erro, cv2.error):
            print(f"Erro do OpenCV: {erro}", file=sys.stderr)
            return 1
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
