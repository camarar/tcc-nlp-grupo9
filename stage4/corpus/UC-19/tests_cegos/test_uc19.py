"""Suíte cega UC-19 — trilha de auditoria à prova de adulteração."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from solucao import ErroAuditoria, TrilhaAuditoria

T0 = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
GENESIS = "0" * 64


class Relogio:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t

    def avancar(self, **kw):
        self.t += timedelta(**kw)


def montar(config=None):
    r = Relogio()
    t = TrilhaAuditoria(relogio=r)
    if config:
        t.configurar(config)
    return t, r


def evento(**kw):
    e = {"actor_id": "u1", "action": "LOGIN", "resource": "sessao",
         "result": "SUCESSO", "payload": {"ip": "1.1.1.1"}}
    e.update(kw)
    return e


def hash_esperado(registro, anterior):
    corpo = {k: v for k, v in registro.items() if k not in ("hash", "hash_anterior")}
    s = json.dumps(corpo, sort_keys=True, separators=(",", ":"),
                   default=str, ensure_ascii=False)
    return hashlib.sha256((anterior + s).encode()).hexdigest()


# ------------------------------------------------------ G-01 obrigatórios

@pytest.mark.parametrize("campo", ["actor_id", "action", "resource", "result"])
def test_campo_obrigatorio_ausente(campo):
    t, _ = montar()
    e = evento()
    del e[campo]
    with pytest.raises(ErroAuditoria) as exc:
        t.registrar(e)
    assert exc.value.code == "REGISTRO_INVALIDO"


def test_result_fora_do_vocabulario():
    t, _ = montar()
    with pytest.raises(ErroAuditoria) as exc:
        t.registrar(evento(result="TALVEZ"))
    assert exc.value.code == "REGISTRO_INVALIDO"


def test_payload_ausente_vira_dicionario_vazio():
    t, _ = montar()
    e = evento()
    del e["payload"]
    t.registrar(e)
    assert t.exportar()[0]["payload"] == {}


def test_timestamp_vem_do_relogio_do_servico():
    t, r = montar()
    t.registrar(evento())
    r.avancar(hours=1)
    t.registrar(evento())
    ts = [x["timestamp_utc"] for x in t.exportar()]
    assert ts == [T0, T0 + timedelta(hours=1)]


def test_timestamp_do_chamador_e_aceito_falsificando_data():
    t, _ = montar()
    falso_ts = datetime(2000, 1, 1, tzinfo=timezone.utc)
    t.registrar(evento(timestamp_utc=falso_ts))
    assert t.exportar()[0]["timestamp_utc"] == falso_ts


# --------------------------------------------------------- G-02/G-03 payload

def test_denylist_remove_no_primeiro_nivel():
    t, _ = montar()
    t.registrar(evento(payload={"cpf": "111", "ip": "1.1.1.1"}))
    assert t.exportar()[0]["payload"] == {"ip": "1.1.1.1"}


def test_denylist_remove_em_qualquer_profundidade():
    t, _ = montar()
    t.registrar(evento(payload={"dados": {"senha": "x", "ok": 1},
                                "lista": [{"email": "a@b.c", "n": 2}]}))
    assert t.exportar()[0]["payload"] == {"dados": {"ok": 1}, "lista": [{"n": 2}]}


def test_denylist_ignora_maiusculas():
    t, _ = montar()
    t.registrar(evento(payload={"CPF": "111", "Senha": "x", "ok": 1}))
    assert t.exportar()[0]["payload"] == {"ok": 1}


def test_payload_do_chamador_nao_e_modificado():
    t, _ = montar()
    p = {"cpf": "111", "ip": "1.1.1.1"}
    t.registrar(evento(payload=p))
    assert p == {"cpf": "111", "ip": "1.1.1.1"}


def test_denylist_configuravel():
    t, _ = montar({"denylist": ["segredo"]})
    t.registrar(evento(payload={"cpf": "111", "segredo": "x"}))
    assert t.exportar()[0]["payload"] == {"cpf": "111"}


def test_denylist_vazia_preserva_tudo():
    t, _ = montar({"denylist": []})
    t.registrar(evento(payload={"cpf": "111"}))
    assert t.exportar()[0]["payload"] == {"cpf": "111"}


def test_reconfiguracao_nao_altera_o_ja_gravado():
    t, _ = montar()
    t.registrar(evento(payload={"cpf": "111", "ok": 1}))
    t.configurar({"denylist": []})
    t.registrar(evento(payload={"cpf": "222"}))
    payloads = [x["payload"] for x in t.exportar()]
    assert payloads == [{"ok": 1}, {"cpf": "222"}]


# ------------------------------------------------------- G-04/G-05 cadeia

def test_primeiro_registro_ancora_no_genesis():
    t, _ = montar()
    t.registrar(evento())
    assert t.exportar()[0]["hash_anterior"] == GENESIS


def test_hash_encadeia_o_anterior():
    t, _ = montar()
    t.registrar(evento())
    t.registrar(evento(action="LOGOUT"))
    regs = t.exportar()
    assert regs[1]["hash_anterior"] == regs[0]["hash"]


def test_hash_segue_a_formula():
    t, _ = montar()
    h = t.registrar(evento())
    reg = t.exportar()[0]
    assert h == reg["hash"] == hash_esperado(reg, GENESIS)


def test_indice_comeca_em_zero_e_e_sequencial():
    t, _ = montar()
    for _ in range(3):
        t.registrar(evento())
    assert [x["indice"] for x in t.exportar()] == [0, 1, 2]


# ------------------------------------------------ G-06/G-07 integridade

def test_trilha_vazia_e_integra():
    t, _ = montar()
    assert t.verificar_integridade() == {"integra": True, "total": 0,
                                         "primeiro_divergente": None}


def test_cadeia_valida():
    t, _ = montar()
    for _ in range(3):
        t.registrar(evento())
    v = t.verificar_integridade()
    assert v["integra"] is True and v["total"] == 3
    assert v["primeiro_divergente"] is None


def test_exportar_devolve_copias():
    t, _ = montar()
    t.registrar(evento())
    regs = t.exportar()
    regs[0]["actor_id"] = "invasor"
    regs[0]["payload"]["ip"] = "9.9.9.9"
    assert t.verificar_integridade()["integra"] is True
    assert t.exportar()[0]["actor_id"] == "u1"


# ------------------------------------------------------- G-08/G-09 expurgo

def test_expurgo_descarta_os_antigos():
    t, r = montar({"retencao_dias": 30})
    t.registrar(evento())
    r.avancar(days=40)
    t.registrar(evento(action="NOVO"))
    assert t.expurgar(r.t) == 1
    assert [x["action"] for x in t.exportar()] == ["NOVO"]


def test_expurgo_quebra_a_cadeia_e_invalida_integridade():
    t, r = montar({"retencao_dias": 30})
    t.registrar(evento())
    r.avancar(days=40)
    t.registrar(evento(action="A"))
    t.registrar(evento(action="B"))
    t.expurgar(r.t)
    
    regs = t.exportar()
    assert [x["indice"] for x in regs] == [0, 1]
    assert regs[0]["hash_anterior"] != GENESIS
    assert regs[1]["hash_anterior"] == regs[0]["hash"]
    
    v = t.verificar_integridade()
    assert v["integra"] is False
    assert v["primeiro_divergente"] == 0


def test_expurgo_sem_candidatos():
    t, r = montar({"retencao_dias": 30})
    t.registrar(evento())
    antes = t.exportar()[0]["hash"]
    assert t.expurgar(r.t) == 0
    assert t.exportar()[0]["hash"] == antes


def test_registro_na_fronteira_da_retencao_sobrevive():
    t, r = montar({"retencao_dias": 30})
    t.registrar(evento())
    r.avancar(days=30)
    assert t.expurgar(r.t) == 0


# ----------------------------------------------------------- G-10 consulta

def test_consulta_sem_filtro_traz_tudo():
    t, _ = montar()
    t.registrar(evento())
    t.registrar(evento(action="LOGOUT"))
    assert len(t.consultar({})) == 2


def test_filtros_combinam_por_e_logico():
    t, _ = montar()
    t.registrar(evento(actor_id="u1", action="LOGIN"))
    t.registrar(evento(actor_id="u2", action="LOGIN"))
    t.registrar(evento(actor_id="u1", action="LOGOUT"))
    r = t.consultar({"actor_id": "u1", "action": "LOGIN"})
    assert len(r) == 1 and r[0]["actor_id"] == "u1"


def test_janela_temporal_inclusiva():
    t, r = montar()
    t.registrar(evento(action="A"))
    r.avancar(hours=2)
    t.registrar(evento(action="B"))
    achados = t.consultar({"desde": T0, "ate": T0 + timedelta(hours=2)})
    assert [x["action"] for x in achados] == ["A", "B"]


def test_janela_temporal_exclui_fora():
    t, r = montar()
    t.registrar(evento(action="A"))
    r.avancar(hours=2)
    t.registrar(evento(action="B"))
    achados = t.consultar({"desde": T0 + timedelta(hours=1)})
    assert [x["action"] for x in achados] == ["B"]


def test_consulta_ordenada_cronologicamente():
    t, r = montar()
    for i in range(3):
        t.registrar(evento(action=f"A{i}"))
        r.avancar(minutes=1)
    achados = t.consultar({})
    assert [x["timestamp_utc"] for x in achados] == sorted(
        x["timestamp_utc"] for x in achados)


def test_filtro_desconhecido():
    t, _ = montar()
    with pytest.raises(ErroAuditoria) as exc:
        t.consultar({"ip": "1.1.1.1"})
    assert exc.value.code == "CONSULTA_INVALIDA"


def test_janela_invertida():
    t, _ = montar()
    with pytest.raises(ErroAuditoria) as exc:
        t.consultar({"desde": T0, "ate": T0 - timedelta(days=1)})
    assert exc.value.code == "CONSULTA_INVALIDA"


def test_consulta_devolve_copias():
    t, _ = montar()
    t.registrar(evento())
    t.consultar({})[0]["actor_id"] = "invasor"
    assert t.consultar({})[0]["actor_id"] == "u1"


# ------------------------------------------------------- G-11 configuração

@pytest.mark.parametrize("cfg", [
    {"retencao_dias": 0}, {"retencao_dias": -1},
    {"denylist": "cpf"}, {"denylist": [1, 2]},
])
def test_configuracao_invalida(cfg):
    t, _ = montar()
    with pytest.raises(ErroAuditoria) as exc:
        t.configurar(cfg)
    assert exc.value.code == "POLITICA_INVALIDA"


def test_exportar_expoe_as_chaves_do_contrato():
    t, _ = montar()
    t.registrar(evento())
    assert set(t.exportar()[0]) == {
        "indice", "timestamp_utc", "actor_id", "action", "resource",
        "result", "payload", "hash_anterior", "hash"}
