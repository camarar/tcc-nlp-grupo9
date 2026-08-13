"""Roda spec + geração C2 (k configurável) para uma lista de casos, sequencialmente.

Uso: py rodar_c2.py UC-01 UC-05 UC-09 --k 1
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).parent

ap = argparse.ArgumentParser()
ap.add_argument("casos", nargs="+")
ap.add_argument("--k", type=int, default=1)
args = ap.parse_args()

for caso in args.casos:
    spec = BASE / "runs" / caso / "c2" / "spec.md"
    if not spec.exists():
        print(f"\n=== {caso}: spec ===", flush=True)
        for tentativa in range(1, 4):
            r = subprocess.run([sys.executable, str(BASE / "orquestrar.py"), "spec", caso],
                               check=False)
            if spec.exists():
                break
            log = (BASE / "runs" / caso / "c2" / "spec_log.txt")
            texto = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            if "session limit" in texto.lower() or "limite" in texto.lower():
                print(f"[{caso}] limite de sessão — aguardando 120s antes de tentar de novo")
                time.sleep(120)
            else:
                print(f"[{caso}] tentativa {tentativa} falhou, tentando de novo em 10s")
                time.sleep(10)
    else:
        print(f"\n=== {caso}: spec já existe ===", flush=True)

    print(f"=== {caso}: gerar c2 k={args.k} ===", flush=True)
    subprocess.run([sys.executable, str(BASE / "orquestrar.py"), "gerar", caso, "c2",
                    str(args.k)], check=False)
