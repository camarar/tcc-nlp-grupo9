"""Harness de medição do Stage 4 — experimento pareado C1 x C2.

Mede cada `solucao.py` contra a suíte cega do corpus, além de flake8 e radon, e
consolida por caso/condição. Corrige o defeito D3 da 1ª geração: `pass@k` não é mais
"alguma geração passou", e sim o estimador não enviesado de Chen et al. (2021).

Uso:
    py run_stage4.py validar  --all            # referência x suíte cega (instrumento)
    py run_stage4.py avaliar  --all            # soluções de runs/
    py run_stage4.py consolidar
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from math import comb
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
CORPUS = BASE / "corpus"
RUNS = BASE / "runs"
RESULTS = BASE / "results"


def _run(cmd, cwd=None, timeout=180):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"


def pass_at_k(n: int, c: int, k: int) -> float:
    """Estimador não enviesado de pass@k (Chen et al., 2021):
    1 - C(n-c, k) / C(n, k), com n amostras e c corretas."""
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def avaliar_solucao(caso: str, solucao: Path) -> dict:
    """Roda a suíte cega + flake8 + radon sobre uma solucao.py, em diretório isolado."""
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

        res["loc"] = len(solucao.read_text(encoding="utf-8", errors="replace").splitlines())

        rc, _, err = _run([sys.executable, "-c", "import solucao"], cwd=tmpd, timeout=60)
        res["importavel"] = rc == 0
        if rc != 0:
            res["erro_import"] = err.strip()[-500:]

        # pytest com relatório por teste, para medir cobertura de lacunas
        rc, out, _ = _run([sys.executable, "-m", "pytest", "-q", "--tb=no",
                           "-rA", "-p", "no:cacheprovider"], cwd=tmpd)
        linhas = out.strip().splitlines()
        res["pytest_resumo"] = linhas[-1] if linhas else ""
        aprovados = set()
        for ln in linhas:
            mm = re.match(r"PASSED\s+(?:.*::)?([A-Za-z0-9_]+)", ln.strip())
            if mm:
                aprovados.add(mm.group(1))
        res["testes_aprovados_nomes"] = sorted(aprovados)
        m_p = re.search(r"(\d+) passed", res["pytest_resumo"])
        m_f = re.search(r"(\d+) failed", res["pytest_resumo"])
        m_e = re.search(r"(\d+) error", res["pytest_resumo"])
        res["testes_passaram"] = int(m_p.group(1)) if m_p else 0
        res["testes_falharam"] = (int(m_f.group(1)) if m_f else 0) + \
                                 (int(m_e.group(1)) if m_e else 0)
        res["testes_total"] = res["testes_passaram"] + res["testes_falharam"]
        res["taxa_testes"] = round(res["testes_passaram"] / res["testes_total"], 4) \
            if res["testes_total"] else 0.0
        res["suite_ok"] = res["testes_total"] > 0 and res["testes_falharam"] == 0

        res["lacunas_cobertas"] = _lacunas_cobertas(caso, aprovados)

        rc, out, _ = _run([sys.executable, "-m", "flake8", "--max-line-length", "120",
                           "--count", "solucao.py"], cwd=tmpd)
        try:
            res["flake8_violacoes"] = int(out.strip().splitlines()[-1]) if out.strip() else 0
        except ValueError:
            res["flake8_violacoes"] = None
        if res.get("flake8_violacoes") is not None and res.get("loc"):
            res["flake8_por_100_linhas"] = round(
                100 * res["flake8_violacoes"] / res["loc"], 2)

        rc, out, _ = _run([sys.executable, "-m", "radon", "cc", "-s", "-j", "solucao.py"],
                          cwd=tmpd)
        try:
            blocos = json.loads(out).get("solucao.py", [])
            ccs = [b["complexity"] for b in blocos]
            res["cc_media"] = round(sum(ccs) / len(ccs), 2) if ccs else 0.0
            res["cc_max"] = max(ccs) if ccs else 0
        except Exception:
            res["cc_media"] = res["cc_max"] = None
        rc, out, _ = _run([sys.executable, "-m", "radon", "mi", "-j", "solucao.py"], cwd=tmpd)
        try:
            res["mi"] = round(json.loads(out)["solucao.py"]["mi"], 2)
        except Exception:
            res["mi"] = None
    return res


def _lacunas_cobertas(caso: str, aprovados: set) -> dict:
    """Fração dos testes de cada lacuna plantada que a solução satisfaz."""
    arq = CORPUS / caso / "lacunas.json"
    if not arq.exists():
        return {}
    spec = json.loads(arq.read_text(encoding="utf-8"))
    out = {}
    for lac in spec.get("lacunas", []):
        ts = lac.get("testes", [])
        if not ts:
            continue
        ok = sum(1 for t in ts if t in aprovados)
        out[lac["id"]] = {"total": len(ts), "aprovados": ok,
                          "coberta": ok == len(ts)}
    return out


def cmd_validar(args):
    """Valida o instrumento: a referência de cada caso deve passar 100% da suíte cega."""
    casos = args.casos or [p.name for p in sorted(CORPUS.glob("UC-*"))]
    linhas, falhas = [], 0
    for caso in casos:
        ref = CORPUS / caso / "_ref" / "solucao.py"
        if not ref.exists():
            print(f"[{caso}] SEM REFERÊNCIA")
            falhas += 1
            continue
        r = avaliar_solucao(caso, ref)
        ok = r.get("suite_ok")
        falhas += 0 if ok else 1
        print(f"[{'OK  ' if ok else 'FALHA'}] {caso}: "
              f"{r.get('testes_passaram')}/{r.get('testes_total')} testes cegos, "
              f"{r.get('loc')} linhas, cc={r.get('cc_media')}, mi={r.get('mi')}")
        linhas.append({"caso": caso, **{k: r.get(k) for k in
                       ("testes_passaram", "testes_total", "suite_ok", "loc",
                        "cc_media", "cc_max", "mi", "flake8_violacoes")}})
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "validacao_instrumento.json").write_text(
        json.dumps(linhas, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(linhas) - falhas}/{len(casos)} casos com instrumento válido.")


def descobrir_runs():
    for caso_dir in sorted(RUNS.glob("UC-*")):
        for cond in ("c1", "c2"):
            for ger in sorted((caso_dir / cond).glob("g*")):
                sol = ger / "solucao.py"
                if sol.exists():
                    yield caso_dir.name, cond, ger.name, sol


def cmd_avaliar(args):
    RESULTS.mkdir(exist_ok=True)
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
        print(f"[{'OK  ' if r.get('suite_ok') else 'FALHA'}] {caso}/{cond}/{ger}: "
              f"{r.get('testes_passaram')}/{r.get('testes_total')} "
              f"({100 * (r.get('taxa_testes') or 0):.0f}%), {r.get('loc')} linhas, "
              f"flake8={r.get('flake8_violacoes')}, cc={r.get('cc_media')}, mi={r.get('mi')}"
              + (f"  ERRO: {r['erro']}" if r.get("erro") else ""))
    out = RESULTS / "avaliacoes.jsonl"
    with out.open("a", encoding="utf-8") as f:
        for r in linhas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n{len(linhas)} avaliações anexadas em {out}")


def cmd_consolidar(args):
    src = RESULTS / "avaliacoes.jsonl"
    if not src.exists():
        print("Nada a consolidar (results/avaliacoes.jsonl ausente).")
        return
    regs = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    # dedup: última avaliação de cada (caso, cond, ger) prevalece
    unico = {(r["caso"], r["cond"], r["ger"]): r for r in regs}

    por_chave = {}
    for r in unico.values():
        por_chave.setdefault((r["caso"], r["cond"]), []).append(r)

    print(f"{'caso':8} {'cond':4} {'n':>2} {'ok':>2} {'pass@1':>7} {'pass@5':>7} "
          f"{'testes':>7} {'lacunas':>8} {'loc':>5} {'fl/100':>7} {'cc':>5} {'mi':>6}")
    resumo = []
    for (caso, cond), rs in sorted(por_chave.items()):
        n = len(rs)
        c = sum(1 for r in rs if r.get("suite_ok"))
        taxas = [r.get("taxa_testes") or 0 for r in rs]
        lac = [_frac_lacunas(r) for r in rs]
        item = {
            "caso": caso, "cond": cond, "n": n, "aprovadas": c,
            "pass_at_1": round(c / n, 4),
            "pass_at_5": round(pass_at_k(n, c, min(5, n)), 4),
            "taxa_testes_media": round(sum(taxas) / n, 4),
            "lacunas_cobertas_media": round(sum(lac) / n, 4),
            "loc_media": round(_media(rs, "loc"), 1),
            "flake8_por_100_linhas_media": round(_media(rs, "flake8_por_100_linhas"), 2),
            "cc_media": round(_media(rs, "cc_media"), 2),
            "mi_media": round(_media(rs, "mi"), 2),
        }
        resumo.append(item)
        print(f"{caso:8} {cond:4} {n:>2} {c:>2} {item['pass_at_1']:>7.2f} "
              f"{item['pass_at_5']:>7.2f} {item['taxa_testes_media']:>7.2f} "
              f"{item['lacunas_cobertas_media']:>8.2f} {item['loc_media']:>5.0f} "
              f"{item['flake8_por_100_linhas_media']:>7.2f} {item['cc_media']:>5.2f} "
              f"{item['mi_media']:>6.1f}")
    (RESULTS / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResumo em {RESULTS / 'resumo.json'} — entrada de analise.py")


def _media(rs, campo):
    vals = [r.get(campo) for r in rs if isinstance(r.get(campo), (int, float))]
    return sum(vals) / len(vals) if vals else 0.0


def _frac_lacunas(r):
    lc = r.get("lacunas_cobertas") or {}
    return sum(1 for v in lc.values() if v.get("coberta")) / len(lc) if lc else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validar", help="valida o instrumento (referência x suíte cega)")
    v.add_argument("--casos", nargs="*"); v.add_argument("--all", action="store_true")
    v.set_defaults(func=cmd_validar)

    a = sub.add_parser("avaliar", help="avalia soluções geradas")
    a.add_argument("--caso"); a.add_argument("--cond", choices=["c1", "c2"])
    a.add_argument("--ger", type=int, default=1); a.add_argument("--all", action="store_true")
    a.set_defaults(func=cmd_avaliar)

    c = sub.add_parser("consolidar"); c.set_defaults(func=cmd_consolidar)

    args = ap.parse_args()
    if args.cmd == "avaliar" and not args.all and not (args.caso and args.cond):
        ap.error("informe --caso e --cond, ou use --all")
    args.func(args)


if __name__ == "__main__":
    main()
