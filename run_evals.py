"""
Script de avaliação automática (Evals) para os agentes Working Backwards.
Executa os agentes contra os cenários de teste e salva os resultados.
"""

import os
import sys
import json
from pathlib import Path
import anthropic

# Forcar UTF-8 no stdout do Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
CASES_DIR = SCRIPT_DIR / "tests" / "cases"
RESULTS_DIR = SCRIPT_DIR / "tests" / "results"

def load_agent_config(meta_name: str, prompt_name: str) -> tuple[str, str]:
    meta_path = SCRIPT_DIR / meta_name
    prompt_path = SCRIPT_DIR / prompt_name
    
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    model = meta["model"]["api"]
    system_prompt = prompt_path.read_text(encoding="utf-8")
    return model, system_prompt

def run_evaluation():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Erro: A variável de ambiente ANTHROPIC_API_KEY não está configurada.")
        sys.exit(1)
        
    client = anthropic.Anthropic(api_key=api_key)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("INICIANDO EXECUÇÃO DE EVALS - AGENTES WORKING BACKWARDS")
    print("=" * 70)
    
    # ── Teste 1: Designer (Gerador) ───────────────────────────────────────────
    print("\n[EVAL 1] Executando Working Backwards Designer...")
    designer_model, designer_system = load_agent_config(
        "working-backwards-designer.meta.json", 
        "Agente Working Backwards Designer.md"
    )
    
    case_1_path = CASES_DIR / "caso_01_notificacoes_push.md"
    case_1_input = case_1_path.read_text(encoding="utf-8")
    
    try:
        response = client.messages.create(
            model=designer_model,
            max_tokens=4000,
            system=designer_system,
            messages=[
                {"role": "user", "content": f"Use esta ideia para criar o PR/FAQ inicial:\n\n{case_1_input}"}
            ]
        )
        output_text = response.content[0].text
        output_file = RESULTS_DIR / "designer_notificacoes_push.md"
        output_file.write_text(output_text, encoding="utf-8")
        print(f"-> Sucesso! Resultado salvo em: {output_file.relative_to(SCRIPT_DIR)}")
    except Exception as e:
        print(f"-> Erro ao executar Eval 1: {e}")

    # ── Teste 2: Analyst (Revisor) ────────────────────────────────────────────
    print("\n[EVAL 2] Executando Working Backwards Analyst...")
    analyst_model, analyst_system = load_agent_config(
        "working-backwards-analyst.meta.json", 
        "Agente Working Backwards Analyst.md"
    )
    
    case_2_path = CASES_DIR / "caso_02_checkout_incompleto.md"
    case_2_input = case_2_path.read_text(encoding="utf-8")
    
    try:
        response = client.messages.create(
            model=analyst_model,
            max_tokens=4000,
            system=analyst_system,
            messages=[
                {"role": "user", "content": f"Revise a proposta de PR/FAQ abaixo:\n\n{case_2_input}"}
            ]
        )
        output_text = response.content[0].text
        output_file = RESULTS_DIR / "analyst_checkout_incompleto.md"
        output_file.write_text(output_text, encoding="utf-8")
        print(f"-> Sucesso! Resultado salvo em: {output_file.relative_to(SCRIPT_DIR)}")
    except Exception as e:
        print(f"-> Erro ao executar Eval 2: {e}")

    print("\n" + "=" * 70)
    print("EVALS CONCLUÍDOS COM SUCESSO.")
    print("=" * 70)

if __name__ == "__main__":
    run_evaluation()
