import contextlib
import csv
import io
from pathlib import Path
import tempfile
import unittest

import analisar_pendulo as app


class ArgumentosTest(unittest.TestCase):
    def test_rejeita_parametros_invalidos(self):
        casos = [
            ["--kernel", "2"], ["--kernel", "0"],
            ["--limiar", "256"], ["--limiar", "-1"],
            ["--area-minima", "nan"], ["--area-minima", "0"],
            ["--fps", "0"], ["--fps", "inf"],
            ["--roi", "0", "0", "-1", "100"],
        ]
        for caso in casos:
            with self.subTest(caso=caso), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as erro:
                    app.argumentos(["video.mp4", *caso])
                self.assertEqual(erro.exception.code, 2)


@unittest.skipIf(app.cv2 is None or app.np is None, "Instale OpenCV e NumPy para testar a detecção.")
class DeteccaoTest(unittest.TestCase):
    def frame(self, centro=(90, 120)):
        frame = app.np.full((180, 240, 3), 255, dtype=app.np.uint8)
        app.cv2.line(frame, (120, 5), centro, (0, 0, 0), 2)
        app.cv2.circle(frame, centro, 15, (0, 0, 0), -1)
        return frame

    def test_centro_do_peso_nao_do_fio(self):
        mascara, deteccao = app.detectar(self.frame())
        self.assertIsNotNone(deteccao)
        self.assertAlmostEqual(deteccao.x, 90, delta=1)
        self.assertAlmostEqual(deteccao.y, 120, delta=1)
        self.assertEqual(mascara[5, 120], 255)  # Fio permanece na máscara bruta.
        self.assertEqual(mascara[170, 230], 0)

    def test_roi_mantem_coordenadas_globais_e_exclui_outro_objeto(self):
        frame = self.frame()
        app.cv2.rectangle(frame, (170, 40), (230, 160), (0, 0, 0), -1)
        mascara, deteccao = app.detectar(frame, roi=(30, 40, 110, 120))
        self.assertIsNotNone(deteccao)
        self.assertAlmostEqual(deteccao.x, 90, delta=1)
        self.assertAlmostEqual(deteccao.y, 120, delta=1)
        self.assertEqual(mascara[100, 200], 0)

    def test_fundo_branco_sem_deteccao(self):
        frame = app.np.full((100, 100, 3), 255, dtype=app.np.uint8)
        mascara, deteccao = app.detectar(frame)
        self.assertIsNone(deteccao)
        self.assertEqual(app.np.count_nonzero(mascara), 0)

    def test_fio_isolado_nao_e_peso(self):
        frame = app.np.full((100, 100, 3), 255, dtype=app.np.uint8)
        app.cv2.line(frame, (50, 5), (50, 95), (0, 0, 0), 2)
        _, deteccao = app.detectar(frame)
        self.assertIsNone(deteccao)

    def test_ruido_pequeno_nao_e_peso(self):
        frame = app.np.full((100, 100, 3), 255, dtype=app.np.uint8)
        app.cv2.circle(frame, (50, 50), 4, (0, 0, 0), -1)
        _, deteccao = app.detectar(frame, area_minima=100)
        self.assertIsNone(deteccao)

    def test_video_csv_e_videos_de_saida(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            video = raiz / "entrada.avi"
            gravador = app.cv2.VideoWriter(
                str(video), app.cv2.VideoWriter_fourcc(*"MJPG"), 25, (240, 180)
            )
            self.assertTrue(gravador.isOpened(), "Codec MJPG indisponível.")
            try:
                for indice in range(12):
                    frame = self.frame((70 + indice * 5, 120))
                    if indice == 5:
                        frame[:] = 255
                    gravador.write(frame)
            finally:
                gravador.release()

            args = app.argumentos([
                str(video), "--saida", str(raiz / "saida"), "--salvar-videos"
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(app.analisar(args), (12, 11))
            csv_path = raiz / "saida" / "posicoes.csv"
            with csv_path.open(newline="", encoding="utf-8") as arquivo:
                linhas = list(csv.DictReader(arquivo))
            self.assertEqual(len(linhas), 12)
            for indice, linha in enumerate(linhas):
                self.assertEqual(int(linha["frame"]), indice)
                self.assertAlmostEqual(float(linha["tempo_s"]), indice / 25)
                self.assertEqual(linha["detectado"], "0" if indice == 5 else "1")
                if indice == 5:
                    self.assertEqual([linha["x_px"], linha["y_px"], linha["area_px2"]], ["", "", ""])
                else:
                    self.assertAlmostEqual(float(linha["x_px"]), 70 + indice * 5, delta=1.5)
                    self.assertAlmostEqual(float(linha["y_px"]), 120, delta=1.5)
            for nome in ("mascara.mp4", "rastreamento.mp4"):
                captura = app.cv2.VideoCapture(str(raiz / "saida" / nome))
                try:
                    total = 0
                    while True:
                        ok, frame = captura.read()
                        if not ok:
                            break
                        total += 1
                        self.assertEqual(frame.shape[:2], (180, 240))
                    self.assertEqual(total, 12)
                finally:
                    captura.release()
            original = csv_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "já existe"):
                app.analisar(args)
            self.assertEqual(csv_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
