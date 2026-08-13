"""
Gerador de artefatos dos agentes (Senior Functional Analyst Reviewer e Code Reviewer).

FONTE ÚNICA DA VERDADE, por agente:
    - Prompt (corpo):   "<Agente ...>.md"
    - Metadados:        <name>.meta.json

A partir dessas duas fontes, este script gera os artefatos derivados de cada agente:
    - <name>.yaml                         (definição canônica + system:)
    - .claude/agents/<name>.md            (subagente do Claude Code) — quando aplicável

Os runners "*_reviewer.py" NÃO são gerados: leem o prompt `.md` diretamente e o
modelo do `<name>.meta.json`, então permanecem sempre em sincronia sem passar aqui.

Uso:
    py build_agent.py            # regenera os artefatos de todos os agentes
    py build_agent.py --check    # falha (exit 1) se algum artefato está desatualizado

Sem dependências externas (somente biblioteca padrão).
"""

import argparse
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).parent
WRAP_WIDTH = 74

# ── Configuração dos agentes ──────────────────────────────────────────────────
# Cada agente aponta para o prompt-fonte, o meta e os alvos gerados. `subagent`
# é opcional: agentes sem subagente do Claude Code deixam como None.
AGENTS = [
    {
        "prompt": "Agente Senior Functional Analyst Reviewer.md",
        "meta": "senior-functional-analyst-reviewer.meta.json",
        "yaml": "senior-functional-analyst-reviewer.yaml",
        "subagent": ".claude/agents/senior-functional-analyst-reviewer.md",
    },
    {
        "prompt": "Agente Code Reviewer.md",
        "meta": "code-reviewer.meta.json",
        "yaml": "code-reviewer.yaml",
        "subagent": ".claude/agents/code-reviewer.md",
    },
    {
        "prompt": "Agente Working Backwards Designer.md",
        "meta": "working-backwards-designer.meta.json",
        "yaml": "working-backwards-designer.yaml",
        "subagent": ".claude/agents/working-backwards-designer.md",
    },
    {
        "prompt": "Agente Working Backwards Analyst.md",
        "meta": "working-backwards-analyst.meta.json",
        "yaml": "working-backwards-analyst.yaml",
        "subagent": ".claude/agents/working-backwards-analyst.md",
    },
]

LICENSE_HEADER = """# Copyright 2026 Raphael Amaral
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License."""


def comment_lines(text: str) -> str:
    """Quebra um texto em linhas de comentário YAML (`# ...`)."""
    lines = textwrap.wrap(text, width=WRAP_WIDTH,
                          break_on_hyphens=False, break_long_words=False)
    return "\n".join("# " + ln for ln in lines)


def _banner(prompt_name: str, meta_name: str, comment: str) -> str:
    text = (
        f'GENERATED por build_agent.py a partir de "{prompt_name}" + {meta_name}. '
        "NÃO EDITE À MÃO — altere a fonte e rode `py build_agent.py`."
    )
    if comment == "md":
        return "<!-- " + text + " -->"
    return comment_lines(text)  # comentário YAML multi-linha


def folded_description(desc: str, indent: str = "  ") -> str:
    """Emite um bloco YAML `description: >` com a descrição quebrada em linhas."""
    lines = textwrap.wrap(desc, width=WRAP_WIDTH)
    body = "\n".join(indent + ln for ln in lines)
    return "description: >\n" + body


def indent_block(text: str, prefix: str = "  ") -> str:
    """Indenta cada linha não vazia; mantém linhas em branco realmente vazias."""
    out = []
    for line in text.split("\n"):
        out.append(prefix + line if line.strip() else "")
    return "\n".join(out)


def build_yaml(prompt: str, meta: dict, prompt_name: str, meta_name: str) -> str:
    parts = [
        LICENSE_HEADER,
        "",
        _banner(prompt_name, meta_name, comment="yaml"),
        "",
        f"name: {meta['name']}",
        f"author: {meta['author']}",
        f"license: {meta['license']}",
        folded_description(meta["description"]),
    ]
    if meta.get("model_note"):
        parts.append(comment_lines(meta["model_note"]))
    parts.append(f"model: {meta['model']['api']}")
    if meta.get("tools_note"):
        parts.append(comment_lines(meta["tools_note"]))
    parts.append("tools:")
    parts += [f"  - {t}" for t in meta["tools"]]
    parts.append("system: |")
    parts.append(indent_block(prompt))
    return "\n".join(parts) + "\n"


def build_subagent(prompt: str, meta: dict, prompt_name: str, meta_name: str) -> str:
    parts = [
        "---",
        f"name: {meta['name']}",
        folded_description(meta["description"]),
        f"tools: {', '.join(meta['tools'])}",
        f"model: {meta['model']['claude_code']}",
        "---",
        _banner(prompt_name, meta_name, comment="md"),
        "",
        prompt,
    ]
    return "\n".join(parts) + "\n"


def write_lf(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def targets_for(agent: dict) -> dict:
    """Mapa {Path -> conteúdo esperado} para um agente."""
    prompt_path = ROOT / agent["prompt"]
    meta_path = ROOT / agent["meta"]
    prompt = prompt_path.read_text(encoding="utf-8").strip("\n")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    out = {
        ROOT / agent["yaml"]: build_yaml(prompt, meta, agent["prompt"], agent["meta"]),
    }
    if agent["subagent"]:
        out[ROOT / agent["subagent"]] = build_subagent(
            prompt, meta, agent["prompt"], agent["meta"]
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera os artefatos derivados dos agentes.")
    ap.add_argument("--check", action="store_true",
                    help="Não escreve; retorna 1 se algum artefato estiver desatualizado.")
    args = ap.parse_args()

    # Valida as fontes antes de qualquer escrita.
    for agent in AGENTS:
        for key in ("prompt", "meta"):
            p = ROOT / agent[key]
            if not p.exists():
                print(f"Erro: fonte não encontrada — {p}")
                return 2

    all_targets: dict = {}
    for agent in AGENTS:
        all_targets.update(targets_for(agent))

    if args.check:
        stale = [p for p, expected in all_targets.items()
                 if (p.read_text(encoding="utf-8") if p.exists() else None) != expected]
        if stale:
            print("Artefatos desatualizados (rode `py build_agent.py`):")
            for p in stale:
                print(f"  - {p.relative_to(ROOT)}")
            return 1
        print("OK — todos os artefatos estão em sincronia com as fontes.")
        return 0

    for path, content in all_targets.items():
        write_lf(path, content)
        print(f"Gerado: {path.relative_to(ROOT)}")
    print("Pronto. Fontes: '<Agente ...>.md' + '<name>.meta.json' por agente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
