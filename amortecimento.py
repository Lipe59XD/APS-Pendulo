"""Estima amortecimento viscoso equivalente de um pêndulo simples.

Modelo: m L² theta'' + c theta' + m g L theta = 0 (pequenos ângulos).
O decaimento medido no vídeo fornece beta; c = 2 m L² beta.
"""

from dataclasses import dataclass
import math
from statistics import median


GRAVIDADE = 9.80665


class AmortecimentoIndisponivel(ValueError):
    """Os dados não sustentam uma estimativa pelo modelo exponencial."""


@dataclass
class ResultadoAmortecimento:
    beta: float
    coeficiente_torque: float
    coeficiente_forca: float
    razao_amortecimento: float
    r2: float
    periodo_medido: float
    amplitudes: list[tuple[float, float]]

    @property
    def fator_qualidade(self):
        """Q = omega0 / (2 beta) = 1 / (2 zeta), adimensional."""
        return 1 / (2 * self.razao_amortecimento)


def validar_parametros(massa, comprimento):
    for nome, valor in (("massa em kg", massa), ("comprimento em metros", comprimento)):
        if valor is None or not math.isfinite(valor) or valor <= 0:
            raise ValueError(f"Informe {nome} com um valor positivo e finito.")
    try:
        inercia = massa * comprimento ** 2
        omega0 = math.sqrt(GRAVIDADE / comprimento)
    except (OverflowError, ZeroDivisionError) as erro:
        raise ValueError("Massa ou comprimento fora do intervalo numérico suportado.") from erro
    if not math.isfinite(inercia) or inercia <= 0 or not math.isfinite(omega0):
        raise ValueError("Massa ou comprimento fora do intervalo numérico suportado.")


def _suavizar(trecho, periodo):
    """Média móvel centrada apenas dentro de cada trecho sem falhas."""
    if len(trecho) < 5:
        return []
    dt = median(b[0] - a[0] for a, b in zip(trecho, trecho[1:]))
    if dt <= 0 or periodo / dt < 8:
        return []
    janela = min(31, max(3, round(0.04 * periodo / dt) | 1))
    meio = janela // 2
    soma = [0.0]
    for _, x, _ in trecho:
        soma.append(soma[-1] + x)
    return [
        (trecho[i][0], (soma[i + meio + 1] - soma[i - meio]) / janela)
        for i in range(meio, len(trecho) - meio)
    ]


def _extremos(pontos, proeminencia):
    """Detecta inversões significativas; não trata as bordas como picos."""
    if not pontos:
        return []
    alto = baixo = 0
    sentido = 0
    extremos = []
    for i, (_, valor) in enumerate(pontos):
        if sentido == 0:
            if valor >= pontos[alto][1]:
                alto = i
            if valor <= pontos[baixo][1]:
                baixo = i
            if valor - pontos[baixo][1] >= proeminencia:
                sentido, alto = 1, i
            elif pontos[alto][1] - valor >= proeminencia:
                sentido, baixo = -1, i
        elif sentido == 1:
            if valor >= pontos[alto][1]:
                alto = i
            elif pontos[alto][1] - valor >= proeminencia:
                extremos.append(pontos[alto])
                sentido, baixo = -1, i
        else:
            if valor <= pontos[baixo][1]:
                baixo = i
            elif valor - pontos[baixo][1] >= proeminencia:
                extremos.append(pontos[baixo])
                sentido, alto = 1, i
    return extremos


def estimar_amortecimento(trechos, massa, comprimento):
    """Ajusta ln(A/Aref) = constante - beta*t às semiamplitudes pico a pico.

    Para extremos alternados consecutivos, A=|x_max-x_min|/2 é associado ao
    instante médio dos dois extremos. Isso dispensa estimar a posição central.
    Nenhum par cruza falhas de detecção. A escala constante em pixels cancela.
    """
    validar_parametros(massa, comprimento)
    omega0 = math.sqrt(GRAVIDADE / comprimento)
    periodo0 = 2 * math.pi / omega0
    suaves = [_suavizar(trecho, periodo0) for trecho in trechos]
    valores = [x for trecho in suaves for _, x in trecho]
    if not valores or max(valores) - min(valores) < 2:
        raise AmortecimentoIndisponivel("Pouca variação horizontal ou poucos frames válidos.")
    proeminencia = max(1.0, 0.03 * (max(valores) - min(valores)))
    amplitudes, meios_periodos = [], []
    for trecho in suaves:
        extremos = _extremos(trecho, proeminencia)
        for (ta, xa), (tb, xb) in zip(extremos, extremos[1:]):
            intervalo = tb - ta
            if 0.25 * periodo0 <= intervalo <= 1.25 * periodo0:
                amplitudes.append(((ta + tb) / 2, abs(xa - xb) / 2))
                meios_periodos.append(intervalo)
    if len(amplitudes) < 5:
        raise AmortecimentoIndisponivel("Picos insuficientes: filme ao menos quatro oscilações completas.")
    amplitudes.sort()
    ts = [t for t, _ in amplitudes]
    if ts[-1] - ts[0] < 1.5 * periodo0:
        raise AmortecimentoIndisponivel("Intervalo de observação muito curto para estimar o decaimento.")
    logs = [math.log(a / amplitudes[0][1]) for _, a in amplitudes]
    media_t, media_log = sum(ts) / len(ts), sum(logs) / len(logs)
    sxx = sum((t - media_t) ** 2 for t in ts)
    inclinacao = sum((t - media_t) * (a - media_log) for t, a in zip(ts, logs)) / sxx
    beta = -inclinacao
    variacao = sum((a - media_log) ** 2 for a in logs)
    residuos = sum((a - media_log - inclinacao * (t - media_t)) ** 2 for t, a in zip(ts, logs))
    r2 = 1 - residuos / variacao if variacao > 1e-15 else 0.0
    if beta <= 0 or beta * (ts[-1] - ts[0]) < 0.02:
        raise AmortecimentoIndisponivel("Não há decaimento mensurável suficiente da amplitude.")
    if r2 < 0.8:
        raise AmortecimentoIndisponivel("As amplitudes não seguem bem o modelo exponencial (R² < 0,80).")
    if beta >= omega0:
        raise AmortecimentoIndisponivel("Decaimento incompatível com o modelo oscilatório e o comprimento informado.")
    periodo_medido = 2 * median(meios_periodos)
    periodo_previsto = 2 * math.pi / math.sqrt(omega0 ** 2 - beta ** 2)
    if abs(periodo_medido / periodo_previsto - 1) > 0.25:
        raise AmortecimentoIndisponivel("Período incompatível com o comprimento; verifique o FPS e o comprimento efetivo.")
    return ResultadoAmortecimento(
        beta=beta,
        coeficiente_torque=2 * massa * comprimento ** 2 * beta,
        coeficiente_forca=2 * massa * beta,
        razao_amortecimento=beta / omega0,
        r2=r2,
        periodo_medido=periodo_medido,
        amplitudes=amplitudes,
    )
