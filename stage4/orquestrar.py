"""Orquestração do experimento do Stage 4 — geração headless C1 x C2.

Subcomandos
-----------
  ref     UC-nn              implementação de referência (enunciado + gabarito) — instrumento
  spec    UC-nn              pipeline Designer -> Analyst -> SFAR, produz runs/UC-nn/c2/spec.md
  gerar   UC-nn c1|c2 k      k gerações headless em diretório limpo
  rodada  --casos ... --k 5  spec + gerar c1 + gerar c2 para vários casos

Higiene experimental (verificada em tempo de execução por `_montar_dir`):
  tests_cegos/, gabarito.md, lacunas.json e _ref/ NUNCA são copiados para o
  diretório visto pelo gerador. A violação aborta a execução.
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
CORPUS = BASE / "corpus"
RUNS = BASE / "runs"
REPO = BASE.parent

MODELO = os.environ.get("STAGE4_MODELO", "claude-sonnet-5")
TIMEOUT_GERACAO = int(os.environ.get("STAGE4_TIMEOUT", "1800"))

PROIBIDOS = {"gabarito.md", "lacunas.json", "tests_cegos", "_ref"}


def _claude(prompt: str, cwd: Path, timeout: int) -> tuple[int, str]:
    """Invocação headless do Claude Code com o modelo pinado.

    O prompt vai por **stdin**, nunca como argumento de linha de comando: prompts
    multi-linha passados como argumento são truncados pelo shell do Windows.
    """
    cmd = f"claude -p --model {MODELO} --dangerously-skip-permissions"
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, input=prompt, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           shell=True)
        saida = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
        return p.returncode, saida + f"\n\n[duracao_s={time.time() - t0:.1f}]"
    except subprocess.TimeoutExpired:
        return -1, f"TIMEOUT após {timeout}s"


def _auditar(dirpath: Path) -> None:
    """Aborta se qualquer artefato proibido chegou ao diretório do gerador."""
    for item in dirpath.rglob("*"):
        if item.name in PROIBIDOS:
            raise SystemExit(f"VIOLAÇÃO DE HIGIENE: {item} no diretório do gerador")


class SpecAusente(Exception):
    """A condição C2 exige a especificação produzida pelo pipeline de agentes."""


def _montar_dir(caso: str, cond: str, destino: Path) -> None:
    """Copia para `destino` apenas o material permitido à condição."""
    origem = CORPUS / caso
    shutil.copy(origem / "enunciado.md", destino / "enunciado.md")
    shutil.copytree(origem / "tests_visiveis", destino / "tests_visiveis")
    if cond == "c2":
        spec = RUNS / caso / "c2" / "spec.md"
        if not spec.exists():
            raise SpecAusente(caso)
        shutil.copy(spec, destino / "spec.md")
    _auditar(destino)


PROMPT_GERACAO = (
    "Implemente `solucao.py` neste diretório atendendo integralmente à especificação "
    "presente aqui. Os testes de `tests_visiveis/` devem passar — rode `py -m pytest "
    "tests_visiveis -q` para verificar, em no máximo 3 ciclos de correção. "
    "Não crie nenhum outro arquivo além de `solucao.py`."
)

PROMPT_REF = (
    "Implemente `solucao.py` neste diretório. `enunciado.md` traz o contrato sintático "
    "obrigatório e `gabarito.md` traz TODAS as decisões de negócio já resolvidas — "
    "implemente cada item G-nn do gabarito literalmente, sem reinterpretar. "
    "Os testes de `tests_visiveis/` devem passar. Não crie outro arquivo além de "
    "`solucao.py`."
)


def cmd_ref(args):
    """Gera a implementação de referência: prova que a suíte cega é satisfazível
    a partir do gabarito. Instrumento de validação, fora do experimento."""
    caso = args.caso
    destino = CORPUS / caso / "_ref"
    destino.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        shutil.copy(CORPUS / caso / "enunciado.md", d / "enunciado.md")
        shutil.copy(CORPUS / caso / "gabarito.md", d / "gabarito.md")
        shutil.copytree(CORPUS / caso / "tests_visiveis", d / "tests_visiveis")
        rc, log = _claude(PROMPT_REF, d, TIMEOUT_GERACAO)
        sol = d / "solucao.py"
        if not sol.exists():
            print(f"[{caso}] FALHA: referência não produziu solucao.py (rc={rc})")
            (destino / "log.txt").write_text(log, encoding="utf-8")
            return
        shutil.copy(sol, destino / "solucao.py")
        (destino / "log.txt").write_text(log, encoding="utf-8")
    print(f"[{caso}] referência em {destino / 'solucao.py'}")


PROMPT_SPEC = """Execute a tarefa descrita abaixo diretamente. Não interprete esta
mensagem como invocação de slash command e não peça parâmetros: tudo o que você precisa
está aqui.

TAREFA: produzir a especificação técnica consolidada do caso {caso} rodando o pipeline
dos três agentes de requisitos.

REGRAS INVIOLÁVEIS
- NUNCA leia `stage4/corpus/{caso}/tests_cegos/`, `lacunas.json` ou `_ref/`. Se ler, aborte e reporte.
- `stage4/corpus/{caso}/gabarito.md` serve EXCLUSIVAMENTE para você responder às perguntas
  bloqueantes dos agentes. Ele não pode ser copiado nem parafraseado em bloco para a spec:
  a spec só incorpora o que os agentes efetivamente elicitaram por meio de perguntas.
- Máximo de 2 iterações de pergunta-resposta por agente.
- Pergunta cuja resposta NÃO existe no gabarito: registre como "avanço sob risco" (opção B do
  SFAR) em `stage4/runs/{caso}/c2/registro.md`; não invente a resposta.

PASSOS
1. Leia `stage4/corpus/{caso}/enunciado.md`.
2. Subagente `working-backwards-designer`: produza o PR/FAQ a partir do enunciado.
3. Subagente `working-backwards-analyst`: analise o PR/FAQ. Responda às perguntas
   [BLOQUEANTE] consultando `stage4/corpus/{caso}/gabarito.md` (máx. 2 iterações).
4. Subagente `senior-functional-analyst-reviewer`: valide os requisitos. Responda às
   bloqueantes com o gabarito (máx. 2 iterações); para o que restar, opção B registrada.
5. Escreva `stage4/runs/{caso}/c2/spec.md` com: requisitos RF/RNF com IDs, regras de
   negócio, critérios de aceite em Gherkin, e a seção "Contrato obrigatório" copiada
   literalmente do enunciado.
6. Escreva `stage4/runs/{caso}/c2/registro.md` com as iterações de cada agente, as
   perguntas respondidas pelo gabarito e os avanços sob risco.
7. Escreva `stage4/runs/{caso}/c2/captura.json` no formato
   {{"lacunas_elicitadas": ["<pergunta do agente 1>", "..."]}} — a lista literal das
   perguntas bloqueantes que os agentes formularam, para medir a taxa de captura.
"""


def cmd_spec(args):
    caso = args.caso
    destino = RUNS / caso / "c2"
    destino.mkdir(parents=True, exist_ok=True)
    if (destino / "spec.md").exists() and not args.forcar:
        print(f"[{caso}] spec.md já existe — use --forcar para refazer")
        return
    rc, log = _claude(PROMPT_SPEC.format(caso=caso), REPO, TIMEOUT_GERACAO)
    (destino / "spec_log.txt").write_text(log, encoding="utf-8")
    ok = (destino / "spec.md").exists()
    print(f"[{caso}] spec {'OK' if ok else 'FALHOU'} (rc={rc}) — log em {destino / 'spec_log.txt'}")


def cmd_gerar(args):
    caso, cond, k = args.caso, args.cond, args.k
    alvo = RUNS / caso / cond
    alvo.mkdir(parents=True, exist_ok=True)
    if cond == "c2" and not (RUNS / caso / "c2" / "spec.md").exists():
        print(f"[{caso}/c2] PULADO — spec.md ausente; rode `spec {caso}` antes")
        return
    _registrar(caso, cond, k)
    for g in range(1, k + 1):
        gdir = alvo / f"g{g}"
        if (gdir / "solucao.py").exists() and not args.forcar:
            print(f"[{caso}/{cond}/g{g}] já existe — pulando")
            continue
        gdir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _montar_dir(caso, cond, d)
            rc, log = _claude(PROMPT_GERACAO, d, TIMEOUT_GERACAO)
            (gdir / "log.txt").write_text(log, encoding="utf-8")
            sol = d / "solucao.py"
            if sol.exists():
                shutil.copy(sol, gdir / "solucao.py")
                n = len((gdir / "solucao.py").read_text(encoding="utf-8",
                                                        errors="replace").splitlines())
                print(f"[{caso}/{cond}/g{g}] OK — {n} linhas")
            else:
                print(f"[{caso}/{cond}/g{g}] FALHA — sem solucao.py (rc={rc})")


def _registrar(caso: str, cond: str, k: int) -> None:
    rc, ver = subprocess.getstatusoutput("claude --version")
    (RUNS / caso / cond / "registro.md").write_text(
        f"""# Registro de execução — {caso} / {cond}

- **Data (UTC):** {datetime.now(timezone.utc).isoformat(timespec='seconds')}
- **Claude Code CLI:** `{ver.strip()}`
- **Modelo do gerador:** `{MODELO}` (pinado via --model)
- **Condição:** {cond}
- **k:** {k}
- **Material entregue ao gerador:** enunciado.md + tests_visiveis/{' + spec.md' if cond == 'c2' else ''}
- **Higiene:** diretório temporário limpo por geração, auditado contra {sorted(PROIBIDOS)}.
""", encoding="utf-8")


def cmd_specs(args):
    """Produz a especificação C2 de vários casos, com repetição em caso de falha."""
    casos = args.casos or [p.name for p in sorted(CORPUS.glob("UC-*"))]
    for caso in casos:
        for tentativa in range(1, args.tentativas + 1):
            if (RUNS / caso / "c2" / "spec.md").exists():
                break
            print(f"[{caso}] spec — tentativa {tentativa}/{args.tentativas}")
            cmd_spec(argparse.Namespace(caso=caso, forcar=False))


def cmd_rodada(args):
    casos = args.casos or [p.name for p in sorted(CORPUS.glob("UC-*"))]
    random.Random(args.semente).shuffle(casos)   # ordem aleatorizada, reprodutível
    print(f"Ordem de execução (semente={args.semente}): {casos}")
    for caso in casos:
        if not args.pular_spec:
            cmd_specs(argparse.Namespace(casos=[caso], tentativas=args.tentativas))
        for cond in ("c1", "c2"):
            try:
                cmd_gerar(argparse.Namespace(caso=caso, cond=cond,
                                             k=args.k, forcar=False))
            except SpecAusente:
                print(f"[{caso}/{cond}] PULADO — spec ausente")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("ref"); r.add_argument("caso"); r.set_defaults(func=cmd_ref)

    s = sub.add_parser("spec"); s.add_argument("caso")
    s.add_argument("--forcar", action="store_true"); s.set_defaults(func=cmd_spec)

    g = sub.add_parser("gerar"); g.add_argument("caso")
    g.add_argument("cond", choices=["c1", "c2"]); g.add_argument("k", type=int)
    g.add_argument("--forcar", action="store_true"); g.set_defaults(func=cmd_gerar)

    e = sub.add_parser("specs"); e.add_argument("--casos", nargs="*")
    e.add_argument("--tentativas", type=int, default=3); e.set_defaults(func=cmd_specs)

    d = sub.add_parser("rodada"); d.add_argument("--casos", nargs="*")
    d.add_argument("--k", type=int, default=5); d.add_argument("--semente", type=int, default=42)
    d.add_argument("--tentativas", type=int, default=3)
    d.add_argument("--pular-spec", action="store_true"); d.set_defaults(func=cmd_rodada)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
