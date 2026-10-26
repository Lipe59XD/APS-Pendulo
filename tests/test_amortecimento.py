import math
import random
import unittest

from amortecimento import (
    AmortecimentoIndisponivel,
    GRAVIDADE,
    estimar_amortecimento,
    validar_parametros,
)


def sinal(beta=0.05, comprimento=0.5, duracao=20, ruido=0, escala=1, centro=320):
    omega = math.sqrt(GRAVIDADE / comprimento - beta ** 2)
    rng = random.Random(42)
    return [
        (i / 60, centro + escala * 100 * math.exp(-beta * i / 60) * math.cos(omega * i / 60 + 0.4) + rng.uniform(-ruido, ruido), 100)
        for i in range(int(duracao * 60) + 1)
    ]


class AmortecimentoTest(unittest.TestCase):
    def test_recupera_coeficientes_conhecidos(self):
        resultado = estimar_amortecimento([sinal()], massa=0.1, comprimento=0.5)
        self.assertAlmostEqual(resultado.beta, 0.05, delta=0.0001)
        self.assertAlmostEqual(resultado.coeficiente_forca, 0.01, delta=0.0001)
        self.assertAlmostEqual(resultado.coeficiente_torque, 0.0025, delta=0.00001)
        self.assertAlmostEqual(resultado.razao_amortecimento, 0.05 / math.sqrt(GRAVIDADE / 0.5), delta=0.0001)
        self.assertAlmostEqual(resultado.fator_qualidade, math.sqrt(GRAVIDADE / 0.5) / (2 * 0.05), delta=0.01)
        self.assertGreater(resultado.r2, 0.999)

    def test_massa_e_comprimento_entram_no_coeficiente_de_torque(self):
        base = estimar_amortecimento([sinal()], massa=0.1, comprimento=0.5)
        massa_dupla = estimar_amortecimento([sinal()], massa=0.2, comprimento=0.5)
        fio_duplo = estimar_amortecimento([sinal(comprimento=1)], massa=0.1, comprimento=1)
        self.assertAlmostEqual(massa_dupla.coeficiente_torque / base.coeficiente_torque, 2)
        self.assertAlmostEqual(massa_dupla.fator_qualidade, base.fator_qualidade)
        self.assertAlmostEqual(fio_duplo.coeficiente_torque / base.coeficiente_torque, 4, delta=0.01)

    def test_independe_da_origem_e_da_escala_em_pixels(self):
        for centro, escala in ((0, 1), (1200, 0.5), (320, 2)):
            with self.subTest(centro=centro, escala=escala):
                resultado = estimar_amortecimento([sinal(centro=centro, escala=escala)], 0.1, 0.5)
                self.assertAlmostEqual(resultado.beta, 0.05, delta=0.0001)

    def test_tolera_ruido_pequeno(self):
        resultado = estimar_amortecimento([sinal(ruido=0.7)], 0.1, 0.5)
        self.assertAlmostEqual(resultado.beta, 0.05, delta=0.002)

    def test_nao_usa_pares_que_cruzam_falhas(self):
        pontos = sinal()
        resultado = estimar_amortecimento([pontos[:360], pontos[480:]], 0.1, 0.5)
        self.assertAlmostEqual(resultado.beta, 0.05, delta=0.001)
        self.assertTrue(all(t < 6 or t >= 8 for t, _ in resultado.amplitudes))

    def test_rejeita_amplitude_constante_crescente_e_video_curto(self):
        for pontos in (sinal(beta=0), sinal(beta=-0.05), sinal(duracao=1), [(i / 60, 320, 100) for i in range(1000)]):
            with self.subTest(inicio=pontos[:1], tamanho=len(pontos)):
                with self.assertRaises(AmortecimentoIndisponivel):
                    estimar_amortecimento([pontos], 0.1, 0.5)

    def test_rejeita_periodo_incompativel_com_comprimento(self):
        with self.assertRaises(AmortecimentoIndisponivel):
            estimar_amortecimento([sinal(comprimento=0.5)], 0.1, 1.5)

    def test_parametros_fisicos_devem_ser_positivos_e_finitos(self):
        for valor in (None, 0, -1, math.nan, math.inf):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    validar_parametros(valor, 0.5)
                with self.assertRaises(ValueError):
                    validar_parametros(0.1, valor)


if __name__ == "__main__":
    unittest.main()
