"""
Harness de avaliação do Stage 4 — experimento pareado C1 x C2.

Avalia soluções geradas (runs/UC-nn/{c1,c2}/g<k>/solucao.py) contra a suíte
cega do corpus, além de flake8 e radon (CC e MI). Consolida em results/.

Uso:
    py run_stage4.py avaliar --caso UC-01 --cond c1 --ger 1
    py run_stage4.py avaliar --all
    py run_stage4.py consolidar

A suíte cega NUNCA deve ser copiada para o diretório visto pelo gerador.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
CORPUS = BASE / "corpus"
RUNS = BASE / "runs"
RESULTS = BASE / "results"


def _run(cmd, cwd=None, timeout=120):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"


def avaliar_solucao(caso: str, solucao: Path) -> dict:
    """Roda a suíte cega + flake8 + radon sobre uma solucao.py."""
    cegos = CORPUS / caso / "tests_cegos"
    res = {"caso": caso, "solucao": str(solucao), "erro": None}
    if not solucao.exists():
        res["erro"] = "solucao.py não encontrado"
        return res
    if not cegos.exists() or not any(cegos.glob("test_*.py")):
        res["erro"] = "suíte cega ausente para este caso"
        return res

    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        shutil.copy(solucao, tmpd / "solucao.py")
        for t in cegos.glob("test_*.py"):
            shutil.copy(t, tmpd / t.name)

        # importabilidade
        rc, _, err = _run([sys.executable, "-c", "import solucao"], cwd=tmpd, timeout=30)
        res["importavel"] = rc == 0
        if rc != 0:
            res["erro_import"] = err.strip()[-500:]

        # pytest (suíte cega)
        import re
        rc, out, err = _run([sys.executable, "-m", "pytest", "-q", "--tb=no",
                             "-p", "no:cacheprovider"], cwd=tmpd)
        last = out.strip().splitlines()[-1] if out.strip() else ""
        res["pytest_resumo"] = last
        m_p = re.search(r"(\d+) passed", last)
        m_f = re.search(r"(\d+) failed", last)
        m_e = re.search(r"(\d+) error", last)
        res["testes_passaram"] = int(m_p.group(1)) if m_p else 0
        res["testes_falharam"] = (int(m_f.group(1)) if m_f else 0) + (int(m_e.group(1)) if m_e else 0)
        res["testes_total"] = res["testes_passaram"] + res["testes_falharam"]
        res["suite_ok"] = res.get("testes_total", 0) > 0 and res.get("testes_falharam", 1) == 0

        # flake8 (contagem de violações)
        rc, out, _ = _run([sys.executable, "-m", "flake8", "--max-line-length", "120",
                           "--count", "solucao.py"], cwd=tmpd)
        try:
            res["flake8_violacoes"] = int(out.strip().splitlines()[-1]) if out.strip() else 0
        except ValueError:
            res["flake8_violacoes"] = None

        # radon: complexidade ciclomática média e índice de manutenibilidade
        rc, out, _ = _run([sys.executable, "-m", "radon", "cc", "-s", "-j", "solucao.py"], cwd=tmpd)
        try:
            blocos = json.loads(out).get("solucao.py", [])
            ccs = [b["complexity"] for b in blocos]
            res["cc_media"] = round(sum(ccs) / len(ccs), 2) if ccs else 0.0
        except Exception:
            res["cc_media"] = None
        rc, out, _ = _run([sys.executable, "-m", "radon", "mi", "-j", "solucao.py"], cwd=tmpd)
        try:
            res["mi"] = round(json.loads(out)["solucao.py"]["mi"], 2)
        except Exception:
            res["mi"] = None
    return res


def descobrir_runs():
    for caso_dir in sorted(RUNS.glob("UC-*")):
        for cond in ("c1", "c2"):
            for ger in sorted((caso_dir / cond).glob("g*")):
                sol = ger / "solucao.py"
                if sol.exists():
                    yield caso_dir.name, cond, ger.name, sol


def cmd_avaliar(args):
    RESULTS.mkdir(exist_ok=True)
    alvos = []
    if args.all:
        alvos = list(descobrir_runs())
    else:
        sol = RUNS / args.caso / args.cond / f"g{args.ger}" / "solucao.py"
        alvos = [(args.caso, args.cond, f"g{args.ger}", sol)]
    linhas = []
    for caso, cond, ger, sol in alvos:
        r = avaliar_solucao(caso, sol)
        r.update({"cond": cond, "ger": ger})
        linhas.append(r)
        status = "OK " if r.get("suite_ok") else "FAIL"
        print(f"[{status}] {caso}/{cond}/{ger}: "
              f"{r.get('testes_passaram', '?')}/{r.get('testes_total', '?')} testes, "
              f"flake8={r.get('flake8_violacoes')}, cc={r.get('cc_media')}, mi={r.get('mi')}"
              + (f"  ERRO: {r['erro']}" if r.get("erro") else ""))
    out = RESULTS / "avaliacoes.jsonl"
    with out.open("a", encoding="utf-8") as f:
        for r in linhas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nResultados anexados em {out}")


def cmd_consolidar(args):
    src = RESULTS / "avaliacoes.jsonl"
    if not src.exists():
        print("Nada a consolidar (results/avaliacoes.jsonl ausente).")
        return
    regs = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    # pass@k por caso/condição: fração de casos com >=1 geração aprovada, e taxa bruta
    por_chave = {}
    for r in regs:
        por_chave.setdefault((r["caso"], r["cond"]), []).append(bool(r.get("suite_ok")))
    print(f"{'caso':8} {'cond':4} {'k':>2} {'aprovadas':>9} {'pass@k':>7}")
    resumo = []
    for (caso, cond), oks in sorted(por_chave.items()):
        k = len(oks)
        aprov = sum(oks)
        passk = 1.0 if aprov > 0 else 0.0
        print(f"{caso:8} {cond:4} {k:>2} {aprov:>9} {passk:>7.2f}")
        resumo.append({"caso": caso, "cond": cond, "k": k,
                       "aprovadas": aprov, "pass_at_k": passk})
    (RESULTS / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResumo em {RESULTS / 'resumo.json'} — use-o como entrada do teste de Wilcoxon.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("avaliar", help="avalia soluções geradas contra a suíte cega")
    a.add_argument("--caso")
    a.add_argument("--cond", choices=["c1", "c2"])
    a.add_argument("--ger", type=int, default=1)
    a.add_argument("--all", action="store_true")
    a.set_defaults(func=cmd_avaliar)
    c = sub.add_parser("consolidar", help="consolida results/avaliacoes.jsonl")
    c.set_defaults(func=cmd_consolidar)
    args = ap.parse_args()
    if args.cmd == "avaliar" and not args.all and not (args.caso and args.cond):
        ap.error("informe --caso e --cond, ou use --all")
    args.func(args)


if __name__ == "__main__":
    main()
