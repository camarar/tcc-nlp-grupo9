"""UC-16 — Serviço de consulta paginada com escopo por perfil."""

from __future__ import annotations

import base64
import json
from functools import cmp_to_key
from typing import Any


class ErroConsulta(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


_DIRECOES_VALIDAS = ("asc", "desc")
_OPS_VALIDOS = ("eq", "ne", "gt", "gte", "lt", "lte", "in", "contains")


def _comparar_valores(v1: Any, v2: Any, direcao: str) -> int:
    if v1 is None and v2 is None:
        return 0
    if v1 is None:
        return 1 if direcao == "asc" else -1
    if v2 is None:
        return -1 if direcao == "asc" else 1
    if v1 == v2:
        return 0
    if direcao == "asc":
        return -1 if v1 < v2 else 1
    return -1 if v1 > v2 else 1


def _aplicar_op(op: str, valor_reg: Any, valor_filtro: Any) -> bool:
    if op == "eq":
        return valor_reg == valor_filtro
    if op == "ne":
        return valor_reg != valor_filtro
    if op in ("gt", "gte", "lt", "lte"):
        if valor_reg is None:
            return False
        try:
            if op == "gt":
                return valor_reg > valor_filtro
            if op == "gte":
                return valor_reg >= valor_filtro
            if op == "lt":
                return valor_reg < valor_filtro
            return valor_reg <= valor_filtro
        except TypeError:
            return False
    if op == "in":
        return valor_reg in valor_filtro
    if op == "contains":
        if not isinstance(valor_reg, str) or not isinstance(valor_filtro, str):
            return False
        return valor_filtro in valor_reg
    return False


class ServicoConsulta:
    def __init__(self, registros: list[dict]) -> None:
        self._registros: list[dict] = [dict(r) for r in registros]
        self._perfis: dict[str, dict] = {}

    def definir_perfil(self, perfil: str, campos_visiveis: list[str],
                        filtro_fixo: dict | None = None) -> None:
        if not perfil or not campos_visiveis:
            raise ErroConsulta("PARAMETRO_INVALIDO")
        self._perfis[perfil] = {
            "campos_visiveis": set(campos_visiveis),
            "filtro_fixo": dict(filtro_fixo) if filtro_fixo else {},
        }

    def inserir(self, registro: dict) -> None:
        self._registros.append(dict(registro))

    def _campos_existentes(self) -> set:
        campos = set()
        for r in self._registros:
            campos.update(r.keys())
        return campos

    def consultar(self, perfil: str, params: dict) -> dict:
        if perfil not in self._perfis:
            raise ErroConsulta("PERFIL_DESCONHECIDO")

        perfil_cfg = self._perfis[perfil]
        campos_visiveis = perfil_cfg["campos_visiveis"]
        filtro_fixo = perfil_cfg["filtro_fixo"]

        cursor = params.get("cursor")
        tamanho = params.get("tamanho")
        ordenar_por = params.get("ordenar_por")
        filtros = params.get("filtros")

        # --- PARAMETRO_INVALIDO ---
        if tamanho is None:
            tamanho = 20
        else:
            if isinstance(tamanho, bool) or not isinstance(tamanho, int) or \
                    tamanho < 1 or tamanho > 100:
                raise ErroConsulta("PARAMETRO_INVALIDO")

        if ordenar_por is None:
            ordenar_por_efetivo = [["id", "asc"]]
        else:
            for par in ordenar_por:
                if not isinstance(par, list) or len(par) != 2:
                    raise ErroConsulta("PARAMETRO_INVALIDO")
                _campo, direcao = par
                if direcao not in _DIRECOES_VALIDAS:
                    raise ErroConsulta("PARAMETRO_INVALIDO")
            campos_ordenados = [p[0] for p in ordenar_por]
            if "id" in campos_ordenados:
                ordenar_por_efetivo = [list(p) for p in ordenar_por]
            else:
                ordenar_por_efetivo = [list(p) for p in ordenar_por] + [["id", "asc"]]

        if filtros is None:
            filtros = {}
        else:
            if not isinstance(filtros, dict):
                raise ErroConsulta("PARAMETRO_INVALIDO")
            for _campo, spec in filtros.items():
                if not isinstance(spec, dict) or "op" not in spec:
                    raise ErroConsulta("PARAMETRO_INVALIDO")

        # --- CAMPO_INVALIDO ---
        campos_existentes = self._campos_existentes()

        def validar_campo(campo: str) -> None:
            if campo == "id":
                return
            if campo not in campos_existentes or campo not in campos_visiveis:
                raise ErroConsulta("CAMPO_INVALIDO")

        for campo, _direcao in ordenar_por_efetivo:
            validar_campo(campo)
        for campo in filtros:
            validar_campo(campo)

        # --- FILTRO_INVALIDO ---
        for _campo, spec in filtros.items():
            op = spec.get("op")
            valor = spec.get("valor")
            if op not in _OPS_VALIDOS:
                raise ErroConsulta("FILTRO_INVALIDO")
            if op == "in" and not isinstance(valor, list):
                raise ErroConsulta("FILTRO_INVALIDO")
            if op == "contains" and not isinstance(valor, str):
                raise ErroConsulta("FILTRO_INVALIDO")

        specs_combinadas = list(filtro_fixo.items()) + list(filtros.items())

        def registro_satisfaz(registro: dict) -> bool:
            for campo, spec in specs_combinadas:
                if not _aplicar_op(spec["op"], registro.get(campo), spec.get("valor")):
                    return False
            return True

        filtrados = [r for r in self._registros if registro_satisfaz(r)]
        total = len(filtrados)

        campos_ordenacao = [c for c, _ in ordenar_por_efetivo]

        def comparar(r1: dict, r2: dict) -> int:
            for campo, direcao in ordenar_por_efetivo:
                c = _comparar_valores(r1.get(campo), r2.get(campo), direcao)
                if c != 0:
                    return c
            return 0

        filtrados.sort(key=cmp_to_key(comparar))

        # --- CURSOR_INVALIDO ---
        start_index = 0
        if cursor is not None:
            try:
                bruto = base64.urlsafe_b64decode(cursor.encode("utf-8"))
                dados = json.loads(bruto.decode("utf-8"))
            except Exception:
                raise ErroConsulta("CURSOR_INVALIDO")

            if not isinstance(dados, list) or \
                    not all(isinstance(item, list) and len(item) == 2 for item in dados):
                raise ErroConsulta("CURSOR_INVALIDO")

            campos_cursor = [item[0] for item in dados]
            if campos_cursor != campos_ordenacao:
                raise ErroConsulta("CURSOR_INVALIDO")

            valores_cursor = [item[1] for item in dados]

            start_index = len(filtrados)
            for i, r in enumerate(filtrados):
                chave_r = [r.get(c) for c in campos_ordenacao]
                depois = False
                empatado = True
                for (campo, direcao), va, vb in zip(ordenar_por_efetivo, chave_r, valores_cursor):
                    c = _comparar_valores(va, vb, direcao)
                    if c != 0:
                        depois = c > 0
                        empatado = False
                        break
                if not empatado and depois:
                    start_index = i
                    break

        pagina = filtrados[start_index:start_index + tamanho]
        tem_proxima = (start_index + tamanho) < len(filtrados)

        if pagina and tem_proxima:
            ultimo = pagina[-1]
            chave_ultimo = [[c, ultimo.get(c)] for c in campos_ordenacao]
            cursor_bytes = json.dumps(chave_ultimo).encode("utf-8")
            proximo_cursor = base64.urlsafe_b64encode(cursor_bytes).decode("ascii")
        else:
            proximo_cursor = None
            tem_proxima = False

        itens = []
        for r in pagina:
            item = {"id": r.get("id")}
            for campo in campos_visiveis:
                if campo != "id" and campo in r:
                    item[campo] = r[campo]
            itens.append(item)

        return {
            "itens": itens,
            "proximo_cursor": proximo_cursor,
            "tem_proxima": tem_proxima,
            "total": total,
        }
