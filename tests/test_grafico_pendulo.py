import importlib.util
import math
from pathlib import Path
import tempfile
import unittest

import grafico_pendulo as app


class GraficoTest(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.csv = Path(self.pasta.name) / "posicoes.csv"

    def escrever(self, linhas):
        self.csv.write_text(
            "frame,tempo_s,detectado,x_px,y_px,area_px2\n" + linhas,
            encoding="utf-8-sig",
        )

    def test_preserva_falhas_e_coordenadas_zero(self):
        self.escrever("0,0,1,0,100,200\n1,0.1,0,,,\n2,0.2,1,20,110,200\n")
        dados = app.ler_dados(self.csv)
        self.assertEqual((dados.frames, dados.detectados), (3, 2))
        self.assertEqual(dados.tempos, [0, 0.1, 0.2])
        self.assertEqual(dados.x[0], 0)
        self.assertTrue(math.isnan(dados.x[1]))
        self.assertTrue(math.isnan(dados.y[1]))
        self.assertEqual(dados.y[2], 110)

    def test_interrompe_curva_quando_faltam_frames(self):
        self.escrever("0,0,1,10,100,200\n3,0.3,1,20,110,200\n")
        dados = app.ler_dados(self.csv)
        self.assertEqual((dados.frames, dados.detectados), (2, 2))
        self.assertTrue(math.isnan(dados.x[1]))
        self.assertEqual(len(dados.x), 3)

    def test_rejeita_dados_inconsistentes(self):
        casos = [
            "0,0,1,,100,200\n", "0,0,1,nan,100,200\n",
            "0,inf,1,10,100,200\n", "0,0,2,10,100,200\n",
            "0,0,1,10,100,200\n0,0.1,1,10,100,200\n",
            "0,0.2,1,10,100,200\n1,0.1,1,10,100,200\n",
        ]
        for linhas in casos:
            with self.subTest(linhas=linhas):
                self.escrever(linhas)
                with self.assertRaisesRegex(ValueError, "linha"):
                    app.ler_dados(self.csv)

    def test_rejeita_csv_vazio_ou_sem_deteccoes(self):
        for linhas in ("", "0,0,0,,,\n"):
            with self.subTest(linhas=linhas):
                self.escrever(linhas)
                with self.assertRaises(ValueError):
                    app.ler_dados(self.csv)

    def test_rejeita_colunas_ausentes(self):
        self.csv.write_text("x,y\n10,20\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Colunas ausentes"):
            app.ler_dados(self.csv)

    def test_saida_nao_pode_ser_csv(self):
        self.escrever("0,0,1,10,100,200\n")
        original = self.csv.read_bytes()
        with self.assertRaises(ValueError):
            app.gerar_grafico(self.csv, self.csv)
        self.assertEqual(self.csv.read_bytes(), original)

    def test_segmenta_falhas_sem_unir_trajetorias(self):
        self.escrever("0,0,1,0,100,200\n1,0.1,0,,,\n2,0.2,1,20,110,200\n3,0.3,1,30,120,200\n")
        trechos = app.segmentar(app.ler_dados(self.csv))
        self.assertEqual(trechos, [[(0, 0, 100)], [(0.2, 20, 110), (0.3, 30, 120)]])

    def test_segmenta_frames_removidos(self):
        self.escrever("0,0,1,10,100,200\n3,0.3,1,20,110,200\n")
        trechos = app.segmentar(app.ler_dados(self.csv))
        self.assertEqual([len(trecho) for trecho in trechos], [1, 1])

    def test_limites_incluem_dados_constantes_e_variados(self):
        for valores in ([100, 100], [0], [-20, 300, math.nan], [0.01, 0.015]):
            with self.subTest(valores=valores):
                minimo, maximo, passo = app.limites(valores)
                self.assertGreater(passo, 0)
                for valor in valores:
                    if math.isfinite(valor):
                        self.assertLess(minimo, valor)
                        self.assertGreater(maximo, valor)

    def test_rejeita_duracao_e_qualidade_invalidas(self):
        self.escrever("0,0,1,10,100,200\n")
        for duracao in (0, -1, math.nan, math.inf):
            with self.subTest(duracao=duracao), self.assertRaises(ValueError):
                app.gerar_grafico(self.csv, duracao=duracao)
        with self.assertRaises(ValueError):
            app.gerar_grafico(self.csv, qualidade="invalida")

    def test_exige_massa_e_comprimento(self):
        self.escrever("0,0,1,10,100,200\n")
        with self.assertRaisesRegex(ValueError, "massa"):
            app.gerar_grafico(self.csv)
        with self.assertRaisesRegex(ValueError, "comprimento"):
            app.gerar_grafico(self.csv, massa=0.1)

    @unittest.skipIf(importlib.util.find_spec("manim") is None, "Instale Manim para testar a renderização.")
    def test_gera_mp4_sem_janela(self):
        omega = math.sqrt(9.80665 / 0.5 - 0.05 ** 2)
        self.escrever("".join(
            f"{i},{i / 30},1,{320 + 100 * math.exp(-0.05 * i / 30) * math.cos(omega * i / 30)},100,200\n"
            for i in range(601)
        ))
        saida = app.gerar_grafico(self.csv, duracao=0.3, qualidade="baixa", massa=0.1, comprimento=0.5)
        self.assertEqual(saida.name, "grafico_pendulo.mp4")
        import av
        with av.open(str(saida)) as video:
            stream = video.streams.video[0]
            self.assertEqual((stream.width, stream.height), (854, 480))
            self.assertGreaterEqual(sum(1 for _ in video.decode(video=0)), 140)


if __name__ == "__main__":
    unittest.main()
