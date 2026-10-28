# APS — Pêndulo

Analisa um vídeo de um pêndulo preto diante de uma parede branca, salva sua
posição frame a frame e gera gráficos animados com Manim. Ao final da animação,
mostra a massa, o comprimento, o ajuste exponencial (R²) e o fator de qualidade Q.

## Instalação

Requer Python 3.10 ou superior. Na pasta do projeto, execute no PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Nos comandos abaixo, usuários de Linux/macOS devem substituir
`.\.venv\Scripts\python.exe` por `python`, com o ambiente ativado.

## Analisar o vídeo

```powershell
.\.venv\Scripts\python.exe analisar_pendulo.py "meu_video.mp4" --salvar-videos
```

Substitua `meu_video.mp4` pelo seu arquivo. Os resultados ficam em
`resultados/meu_video/`:

- `posicoes.csv`: frame, tempo e posição X/Y em pixels.
- `mascara.mp4`: máscara dos pixels escuros, incluindo o fio.
- `rastreamento.mp4`: vídeo com o centro do peso marcado.

O fio é removido por filtragem na máscara interna usada para medir o peso.
Sem `--salvar-videos`, o programa gera apenas o CSV.

## Gerar os gráficos

```powershell
.\.venv\Scripts\python.exe grafico_pendulo.py "resultados/meu_video/posicoes.csv" --massa 0.100 --comprimento 0.50 --qualidade baixa --mostrar
```

Use sua massa em **kg** e o comprimento em **metros**, da suspensão ao centro
de massa do peso. Os valores acima são exemplos de 100 g e 50 cm.

O vídeo `grafico_pendulo.mp4` é salvo ao lado do CSV. Ele mostra X(t), Y(t),
a trajetória e uma tela final com massa, comprimento, ajuste exponencial (R²) e Q.
A estimativa pressupõe pequenas oscilações e amortecimento viscoso; filme pelo
menos quatro oscilações completas com decaimento visível da amplitude.

## Ajustes úteis

- `--limiar 40`: reduz a detecção de sombras; o padrão é 50.
- `--kernel 7`: filtro para separar o fio do peso. Deve ser mais largo que o fio
  e mais estreito que o peso na imagem.
- `--saida resultados/tentativa2`: escolhe outra pasta para a análise, preservando
  resultados existentes. Use o novo caminho do CSV ao gerar os gráficos.
- `--duracao 20`: desenha as curvas em 20 segundos; o padrão é 12, além da
  apresentação e da tela final.
- `--qualidade alta`: renderiza a animação em 1080p.

## Scripts

- `analisar_pendulo.py`: detecção e geração do CSV.
- `grafico_pendulo.py`: gráficos animados e tela de resultados.
- `amortecimento.py`: cálculos físicos.

