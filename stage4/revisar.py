"""Revisão cega à condição pelo agente Code Reviewer (métrica secundária).

Cada solução é copiada para um diretório neutro com identificador aleatório; o revisor
recebe apenas esse diretório, sem saber se o código veio de C1 ou C2, de que caso ou de
que geração. O mapeamento fica em `reviews/mapa.json`, que nunca é mostrado ao revisor.

Uso:
    py revisar.py preparar --por-celula 2     # sorteia e anonimiza as amostras
    py revisar.py revisar                     # roda o code-reviewer em cada amostra
    py revisar.py consolidar                  # reassocia e conta achados por severidade
"""

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
RUNS = BASE / "runs"
REVIEWS = BASE / "reviews"
RESULTS = BASE / "results"
REPO = BASE.parent

MODELO = "claude-sonnet-5"
SEVERIDADES = ["CRÍTICO", "ALTO", "MÉDIO", "BAIXO", "ELOGIO"]

PROMPT = (
    "Revise o código em `{alvo}/solucao.py` usando o subagente `code-reviewer`. "
    "Contexto: Python 3.12, módulo utilitário isolado, sem framework, sem acesso a rede "
    "ou banco. Grave o relatório em `{alvo}/review.md`. "
    "Não tente descobrir a origem do arquivo nem procurar outros diretórios do projeto."
)


def cmd_preparar(args):
    REVIEWS.mkdir(exist_ok=True)
    rng = random.Random(args.semente)
    mapa = {}
    for caso_dir in sorted(RUNS.glob("UC-*")):
        for cond in ("c1", "c2"):
            gers = sorted(p for p in (caso_dir / cond).glob("g*")
                          if (p / "solucao.py").exists())
            for ger in rng.sample(gers, min(args.por_celula, len(gers))):
                ident = f"amostra-{uuid.UUID(int=rng.getrandbits(128)).hex[:8]}"
                destino = REVIEWS / ident
                destino.mkdir(parents=True, exist_ok=True)
                shutil.copy(ger / "solucao.py", destino / "solucao.py")
                mapa[ident] = {"caso": caso_dir.name, "cond": cond, "ger": ger.name}
    ordem = list(mapa)
    rng.shuffle(ordem)                      # ordem de apresentação aleatorizada
    (REVIEWS / "mapa.json").write_text(
        json.dumps({"mapa": mapa, "ordem": ordem}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"{len(mapa)} amostras anonimizadas em {REVIEWS}")


def cmd_revisar(args):
    dados = json.loads((REVIEWS / "mapa.json").read_text(encoding="utf-8"))
    pendentes = [i for i in dados["ordem"]
                 if not (REVIEWS / i / "review.md").exists()]
    print(f"{len(pendentes)} amostras pendentes de revisão")
    for ident in pendentes:
        alvo = f"stage4/reviews/{ident}"
        cmd = ["claude", "-p", "--model", MODELO, "--dangerously-skip-permissions",
               PROMPT.format(alvo=alvo)]
        try:
            subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1200,
                           shell=(sys.platform == "win32"))
        except subprocess.TimeoutExpired:
            print(f"[{ident}] TIMEOUT")
            continue
        ok = (REVIEWS / ident / "review.md").exists()
        print(f"[{ident}] {'OK' if ok else 'FALHOU'}")


def contar_severidades(texto: str) -> dict:
    """Conta as tags de severidade nos títulos de achado do relatório."""
    contagem = Counter()
    for sev in SEVERIDADES:
        contagem[sev] = len(re.findall(rf"\[{re.escape(sev)}\]", texto))
    return dict(contagem)


def cmd_consolidar(args):
    dados = json.loads((REVIEWS / "mapa.json").read_text(encoding="utf-8"))
    mapa = dados["mapa"]
    linhas = []
    for ident, origem in mapa.items():
        arq = REVIEWS / ident / "review.md"
        if not arq.exists():
            continue
        contagem = contar_severidades(arq.read_text(encoding="utf-8", errors="replace"))
        linhas.append({"amostra": ident, **origem, **contagem,
                       "bloqueantes": contagem["CRÍTICO"] + contagem["ALTO"]})

    por_cond = {}
    for linha in linhas:
        por_cond.setdefault(linha["cond"], []).append(linha)

    print(f"{'cond':5} {'n':>3} " + " ".join(f"{s:>9}" for s in SEVERIDADES)
          + f" {'bloq/amostra':>13}")
    resumo = {}
    for cond in ("c1", "c2"):
        grupo = por_cond.get(cond, [])
        if not grupo:
            continue
        medias = {s: round(sum(x[s] for x in grupo) / len(grupo), 2) for s in SEVERIDADES}
        bloq = round(sum(x["bloqueantes"] for x in grupo) / len(grupo), 2)
        resumo[cond] = {"n": len(grupo), **medias, "bloqueantes_por_amostra": bloq}
        print(f"{cond:5} {len(grupo):>3} "
              + " ".join(f"{medias[s]:>9.2f}" for s in SEVERIDADES) + f" {bloq:>13.2f}")

    # pareado por caso: média de bloqueantes por condição em cada caso
    por_caso = {}
    for linha in linhas:
        por_caso.setdefault(linha["caso"], {}).setdefault(linha["cond"], []).append(
            linha["bloqueantes"])
    pares = []
    for caso, conds in sorted(por_caso.items()):
        if "c1" in conds and "c2" in conds:
            pares.append({"caso": caso,
                          "c1": round(sum(conds["c1"]) / len(conds["c1"]), 3),
                          "c2": round(sum(conds["c2"]) / len(conds["c2"]), 3)})

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "revisao_cega.json").write_text(
        json.dumps({"por_amostra": linhas, "por_condicao": resumo,
                    "pareado_por_caso": pares}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n{len(linhas)} revisões consolidadas em {RESULTS / 'revisao_cega.json'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preparar")
    p.add_argument("--por-celula", type=int, default=2)
    p.add_argument("--semente", type=int, default=7)
    p.set_defaults(func=cmd_preparar)
    r = sub.add_parser("revisar"); r.set_defaults(func=cmd_revisar)
    c = sub.add_parser("consolidar"); c.set_defaults(func=cmd_consolidar)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
