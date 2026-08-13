"""
Agente Working Backwards Analyst — Revisão e Maturação de PR/FAQ interativo via terminal.

Uso:
    py working_backwards_analyst.py
    py working_backwards_analyst.py --file caminho/para/pr_faq.md
"""

import anthropic
import json
import os
import sys
import argparse
from pathlib import Path

# Forcar UTF-8 no stdout do Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Configuração ──────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
PROMPT_FILE = SCRIPT_DIR / "Agente Working Backwards Analyst.md"
META_FILE = SCRIPT_DIR / "working-backwards-analyst.meta.json"

FALLBACK_MODEL = "claude-sonnet-5"


def load_model() -> str:
    try:
        meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        return meta["model"]["api"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return FALLBACK_MODEL


MODEL = load_model()

SEPARATOR = "-" * 70

# ── Cores ANSI ────────────────────────────────────────────────────────────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    YELLOW  = "\033[93m"
    GREEN   = "\033[92m"
    BLUE    = "\033[94m"
    CYAN    = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE   = "\033[97m"

def color_enabled() -> bool:
    return sys.stdout.isatty() and os.name != "nt" or os.environ.get("TERM") == "xterm-256color"

def fmt(text: str, *codes: str) -> str:
    if not color_enabled():
        return text
    return "".join(codes) + text + C.RESET

# ── Ferramentas disponíveis para o agente ─────────────────────────────────────

TOOLS = [
    {
        "name": "read_file",
        "description": (
            "Lê o conteúdo de um arquivo do sistema de arquivos local para validação "
            "do PR/FAQ. Use quando o usuário fornecer um caminho de arquivo de PR/FAQ."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Caminho absoluto ou relativo do arquivo a ser lido."
                },
                "start_line": {
                    "type": "integer",
                    "description": "Linha inicial (1-based). Omita para ler desde o início."
                },
                "end_line": {
                    "type": "integer",
                    "description": "Linha final (1-based). Omita para ler até o fim."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "list_directory",
        "description": "Lista documentos em um diretório para ajudar o usuário a escolher o PR/FAQ para revisar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Caminho do diretório a listar."
                },
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Extensões para filtrar, ex: ['.md']. Omita para listar tudo."
                }
            },
            "required": ["path"]
        }
    }
]

# ── Implementação das ferramentas ─────────────────────────────────────────────

def tool_read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return f"Erro: arquivo não encontrado — {path}"
        if not p.is_file():
            return f"Erro: o caminho não é um arquivo — {path}"

        lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        total = len(lines)

        sl = (start_line - 1) if start_line else 0
        el = end_line if end_line else total
        selected = lines[sl:el]

        numbered = [f"{sl + i + 1:4d} | {line}" for i, line in enumerate(selected)]
        header = f"// Arquivo: {p} ({total} linhas)"
        if start_line or end_line:
            header += f" — exibindo linhas {sl+1}–{min(el, total)}"

        return header + "\n" + "".join(numbered)
    except Exception as e:
        return f"Erro ao ler arquivo: {e}"


def tool_list_directory(path: str, extensions: list[str] | None = None) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return f"Erro: diretório não encontrado — {path}"
        if not p.is_dir():
            return f"Erro: o caminho não é um diretório — {path}"

        DOC_EXTS = {".md", ".txt", ".json", ".yaml", ".yml"}
        filter_exts = {e.lower() for e in extensions} if extensions else DOC_EXTS

        entries = sorted(p.rglob("*"))
        files = [
            e.relative_to(p)
            for e in entries
            if e.is_file() and e.suffix.lower() in filter_exts
            and not any(part.startswith(".") or part in {"node_modules", "__pycache__", ".git", "dist", "build"}
                        for part in e.parts)
        ]

        if not files:
            return f"Nenhum arquivo de documento encontrado em {path}"

        lines = [f"Arquivos em {path}:", ""]
        for f in files[:100]:
            lines.append(f"  {f}")
        if len(files) > 100:
            lines.append(f"  ... e mais {len(files) - 100} arquivos")
        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao listar diretório: {e}"


def dispatch_tool(name: str, inputs: dict) -> str:
    if name == "read_file":
        return tool_read_file(**inputs)
    if name == "list_directory":
        return tool_list_directory(**inputs)
    return f"Ferramenta desconhecida: {name}"

# ── Carregamento do system prompt ─────────────────────────────────────────────

def load_system_prompt() -> str:
    if not PROMPT_FILE.exists():
        print(fmt(f"Aviso: arquivo de prompt não encontrado em {PROMPT_FILE}", C.YELLOW))
        return "Você é um revisor de soluções de arquitetura que avalia PR/FAQs."
    return PROMPT_FILE.read_text(encoding="utf-8")

# ── Entrada multi-linha ───────────────────────────────────────────────────────

def read_multiline(prompt_text: str) -> str:
    print(fmt(prompt_text, C.BOLD + C.CYAN))
    print(fmt("  (para textos longos, termine com END em uma linha vazia)", C.DIM))
    print()

    lines: list[str] = []
    try:
        first = input()
    except EOFError:
        return ""

    if not first.strip():
        return ""

    lines.append(first)

    if len(first) < 200:
        if not sys.stdin.isatty():
            for line in sys.stdin:
                if line.strip() == "END":
                    break
                lines.append(line.rstrip("\n"))
        return "\n".join(lines)

    print(fmt("  [modo multi-linha ativado — digite END para enviar]", C.DIM))
    try:
        while True:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
    except EOFError:
        pass

    return "\n".join(lines)

# ── Loop principal do agente ──────────────────────────────────────────────────

def agent_loop(client: anthropic.Anthropic, system: str, messages: list, user_input: str) -> str:
    messages.append({"role": "user", "content": user_input})

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8096,
            system=system,
            tools=TOOLS,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            assistant_content = response.content

            for block in response.content:
                if block.type == "tool_use":
                    print(fmt(f"\n  Ferramenta: {block.name}({json.dumps(block.input, ensure_ascii=False)})", C.DIM + C.MAGENTA))
                    result = dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

        else:
            final = next(
                (block.text for block in response.content if hasattr(block, "text")),
                ""
            )
            messages.append({"role": "assistant", "content": final})
            return final

# ── Renderização da resposta ──────────────────────────────────────────────────

def print_response(text: str) -> None:
    print()
    print(fmt(SEPARATOR, C.DIM))
    print(fmt("  REVISÃO DA SOLUÇÃO", C.BOLD + C.GREEN))
    print(fmt(SEPARATOR, C.DIM))
    print()

    tag_colors = {
        "[BLOQUEANTE]": C.RED + C.BOLD,
        "[NÃO-BLOQUEANTE]": C.YELLOW + C.BOLD,
        "[SUGESTÃO — requer aprovação]": C.CYAN + C.BOLD,
    }

    for line in text.splitlines():
        colored = line
        for tag, style in tag_colors.items():
            if tag in colored:
                colored = colored.replace(tag, fmt(tag, style))
        print(colored)

    print()
    print(fmt(SEPARATOR, C.DIM))

# ── CLI ───────────────────────────────────────────────────────────────────────

HELP_TEXT = """
Comandos disponíveis:
  exit / quit   Encerra o agente
  clear         Limpa o histórico da conversa (nova sessão)
  help          Exibe esta ajuda

Dicas de uso:
  • Cole o documento PR/FAQ completo e termine com END em uma linha vazia
  • Informe o caminho de um arquivo: "Revise a proposta pr_faq.md"
  • Faça perguntas de follow-up para sanar as dúvidas levantadas pelo revisor
"""

def print_banner(system_prompt_path: Path) -> None:
    print()
    print(fmt(SEPARATOR, C.DIM))
    print(fmt("  AGENTE WORKING BACKWARDS ANALYST", C.BOLD + C.CYAN))
    print(fmt(f"  Modelo: {MODEL}", C.DIM))
    print(fmt(f"  Prompt: {system_prompt_path}", C.DIM))
    print(fmt(SEPARATOR, C.DIM))
    print(fmt(HELP_TEXT, C.DIM))


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente Working Backwards Analyst interativo")
    parser.add_argument("--file", "-f", help="Arquivo PR/FAQ para revisar diretamente ao iniciar")
    parser.add_argument("--api-key", help="Chave da API Anthropic (ou defina ANTHROPIC_API_KEY)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(fmt("Erro: defina a variável ANTHROPIC_API_KEY ou use --api-key", C.RED))
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = load_system_prompt()
    messages: list = []

    print_banner(PROMPT_FILE)

    if args.file:
        file_path = Path(args.file)
        user_input = f"Por favor, revise o PR/FAQ do arquivo: {file_path.resolve()}"
        print(fmt(f"\n> {user_input}", C.BOLD))
        print(fmt("\n  Processando...", C.DIM))
        response = agent_loop(client, system_prompt, messages, user_input)
        print_response(response)

    while True:
        print()
        try:
            user_input = read_multiline("PR/FAQ ›")
        except KeyboardInterrupt:
            print(fmt("\n\nUse 'exit' para sair.", C.DIM))
            continue

        if not user_input.strip():
            continue

        cmd = user_input.strip().lower()
        if cmd in ("exit", "quit", "sair"):
            print(fmt("\nEncerrando o agente. Até logo!\n", C.DIM))
            break
        if cmd == "clear":
            messages.clear()
            print(fmt("  Histórico limpo. Nova sessão iniciada.", C.DIM + C.GREEN))
            continue
        if cmd == "help":
            print(fmt(HELP_TEXT, C.DIM))
            continue

        print(fmt("\n  Processando...", C.DIM))
        try:
            response = agent_loop(client, system_prompt, messages, user_input)
            print_response(response)
        except anthropic.APIError as e:
            print(fmt(f"\nErro da API: {e}", C.RED))
        except Exception as e:
            print(fmt(f"\nErro inesperado: {e}", C.RED))


if __name__ == "__main__":
    main()
