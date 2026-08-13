"""Análise estatística do experimento pareado C1 x C2 do Stage 4.

Sem dependências externas: Wilcoxon dos postos sinalizados com distribuição **exata**
por enumeração (viável para n <= 20), Cliff's delta, correção de Holm para múltiplas
métricas e estimativa de poder por reamostragem.

Uso:
    py analise.py                  # lê results/resumo.json
    py analise.py --alfa 0.05 --bootstrap 2000
"""

import argparse
import json
import random
import sys
from itertools import product
from math import comb, sqrt
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
RESULTS = BASE / "results"

# métricas pareadas por tarefa: (chave, rótulo, direção desejada)
METRICAS = [
    ("pass_at_1", "pass@1 (média por geração)", "maior"),
    ("pass_at_5", "pass@5 (estimador não enviesado)", "maior"),
    ("taxa_testes_media", "taxa de testes cegos aprovados", "maior"),
    ("lacunas_cobertas_media", "taxa de captura de lacunas plantadas", "maior"),
    ("flake8_por_100_linhas_media", "violações flake8 por 100 linhas", "menor"),
    ("cc_media", "complexidade ciclomática média", "menor"),
    ("mi_media", "índice de manutenibilidade", "maior"),
    ("loc_media", "linhas de código", "neutro"),
]


def postos_medios(valores):
    """Postos de 1..n com média nos empates."""
    ordenado = sorted(range(len(valores)), key=lambda i: valores[i])
    postos = [0.0] * len(valores)
    i = 0
    while i < len(ordenado):
        j = i
        while j + 1 < len(ordenado) and valores[ordenado[j + 1]] == valores[ordenado[i]]:
            j += 1
        media = (i + j) / 2 + 1
        for k in range(i, j + 1):
            postos[ordenado[k]] = media
        i = j + 1
    return postos


def wilcoxon_pareado(diferencas, max_exato=20):
    """Wilcoxon dos postos sinalizados, bilateral.

    Descarta os zeros (correção de Wilcoxon). Usa a distribuição exata por
    enumeração dos 2**n padrões de sinal quando n <= max_exato; acima disso,
    aproximação normal com correção de continuidade.
    """
    d = [x for x in diferencas if x != 0]
    n = len(d)
    if n == 0:
        return {"n_efetivo": 0, "W_mais": 0.0, "W_menos": 0.0,
                "p": 1.0, "metodo": "sem variação"}

    postos = postos_medios([abs(x) for x in d])
    w_mais = sum(p for p, x in zip(postos, d) if x > 0)
    w_menos = sum(p for p, x in zip(postos, d) if x < 0)
    observado = min(w_mais, w_menos)

    if n <= max_exato:
        total = 0
        favoraveis = 0
        for sinais in product((0, 1), repeat=n):
            s = sum(p for p, b in zip(postos, sinais) if b)
            total += 1
            if min(s, sum(postos) - s) <= observado + 1e-9:
                favoraveis += 1
        p = favoraveis / total
        metodo = f"exato ({total} padrões)"
    else:
        media = n * (n + 1) / 4
        desvio = sqrt(n * (n + 1) * (2 * n + 1) / 24)
        z = (abs(observado - media) - 0.5) / desvio if desvio else 0.0
        p = 2 * (1 - _phi(z))
        metodo = "aproximação normal"

    return {"n_efetivo": n, "W_mais": round(w_mais, 1), "W_menos": round(w_menos, 1),
            "p": min(1.0, round(p, 6)), "metodo": metodo}


def _phi(z):
    """CDF da normal padrão via função erro de Abramowitz-Stegun."""
    from math import erf
    return 0.5 * (1 + erf(z / sqrt(2)))


def cliffs_delta(a, b):
    """Cliff's delta de `a` sobre `b`: P(a>b) - P(a<b)."""
    maior = sum(1 for x in a for y in b if x > y)
    menor = sum(1 for x in a for y in b if x < y)
    n = len(a) * len(b)
    if n == 0:
        return 0.0, "indefinido"
    d = (maior - menor) / n
    m = abs(d)
    if m < 0.147:
        rotulo = "desprezível"
    elif m < 0.33:
        rotulo = "pequeno"
    elif m < 0.474:
        rotulo = "médio"
    else:
        rotulo = "grande"
    return round(d, 4), rotulo


def holm(pvalores, alfa=0.05):
    """Correção de Holm-Bonferroni. Devolve a lista de (p_ajustado, rejeita)."""
    indexados = sorted(range(len(pvalores)), key=lambda i: pvalores[i])
    m = len(pvalores)
    ajustados = [0.0] * m
    anterior = 0.0
    for posicao, i in enumerate(indexados):
        aj = min(1.0, (m - posicao) * pvalores[i])
        aj = max(aj, anterior)
        ajustados[i] = aj
        anterior = aj
    return [(round(ajustados[i], 6), ajustados[i] < alfa) for i in range(m)]


def poder_observado(diferencas, alfa=0.05, b=2000, semente=42):
    """Estimativa de poder por reamostragem: fração de reamostras em que o teste
    rejeita, dado o efeito observado. Usa aproximação normal por desempenho."""
    d = [x for x in diferencas if x != 0]
    n = len(d)
    if n < 3:
        return None
    rng = random.Random(semente)
    rejeicoes = 0
    for _ in range(b):
        amostra = [d[rng.randrange(n)] for _ in range(n)]
        r = wilcoxon_pareado(amostra, max_exato=0)   # força aproximação normal
        if r["p"] < alfa:
            rejeicoes += 1
    return round(rejeicoes / b, 3)


def carregar(caminho):
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    por_caso = {}
    for linha in dados:
        por_caso.setdefault(linha["caso"], {})[linha["cond"]] = linha
    pares = {c: v for c, v in por_caso.items() if "c1" in v and "c2" in v}
    return dict(sorted(pares.items()))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--resumo", default=str(RESULTS / "resumo.json"))
    ap.add_argument("--alfa", type=float, default=0.05)
    ap.add_argument("--bootstrap", type=int, default=2000)
    args = ap.parse_args()

    pares = carregar(args.resumo)
    if not pares:
        print("Nenhum par C1/C2 completo em", args.resumo)
        return
    casos = list(pares)
    print(f"Pares completos (tarefas): n = {len(casos)}\n")

    saida = {"n_pares": len(casos), "casos": casos, "alfa": args.alfa, "metricas": []}
    brutos = []

    for chave, rotulo, direcao in METRICAS:
        c1 = [pares[c]["c1"].get(chave) for c in casos]
        c2 = [pares[c]["c2"].get(chave) for c in casos]
        if any(v is None for v in c1 + c2):
            continue
        dif = [b - a for a, b in zip(c1, c2)]
        w = wilcoxon_pareado(dif)
        delta, magnitude = cliffs_delta(c2, c1)
        favor_c2 = sum(1 for x in dif if x > 0)
        favor_c1 = sum(1 for x in dif if x < 0)
        item = {
            "metrica": chave, "rotulo": rotulo, "direcao_desejada": direcao,
            "media_c1": round(sum(c1) / len(c1), 4),
            "media_c2": round(sum(c2) / len(c2), 4),
            "mediana_c1": round(sorted(c1)[len(c1) // 2], 4),
            "mediana_c2": round(sorted(c2)[len(c2) // 2], 4),
            "tarefas_favor_c2": favor_c2, "tarefas_favor_c1": favor_c1,
            "empates": len(casos) - favor_c1 - favor_c2,
            "wilcoxon": w, "cliffs_delta": delta, "magnitude": magnitude,
            "poder_observado": poder_observado(dif, args.alfa, args.bootstrap),
        }
        saida["metricas"].append(item)
        brutos.append(w["p"])

    for item, (p_aj, rejeita) in zip(saida["metricas"], holm(brutos, args.alfa)):
        item["p_holm"] = p_aj
        item["significativo_holm"] = rejeita

    print(f"{'métrica':38} {'C1':>8} {'C2':>8} {'C2>C1':>6} {'p':>9} "
          f"{'p_holm':>9} {'delta':>7} {'efeito':>12}")
    for m in saida["metricas"]:
        print(f"{m['rotulo'][:38]:38} {m['media_c1']:>8.3f} {m['media_c2']:>8.3f} "
              f"{m['tarefas_favor_c2']:>3}/{len(casos):<2} {m['wilcoxon']['p']:>9.4f} "
              f"{m['p_holm']:>9.4f} {m['cliffs_delta']:>7.3f} {m['magnitude']:>12}")

    destino = RESULTS / "analise.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAnálise completa em {destino}")
    print(f"Método do Wilcoxon: {saida['metricas'][0]['wilcoxon']['metodo']}"
          if saida["metricas"] else "")


if __name__ == "__main__":
    main()
