"""UC-16 — Serviço de consulta paginada com escopo por perfil."""

import base64
import json
from functools import cmp_to_key

_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"}
_DIRECOES = {"asc", "desc"}


class ErroConsulta(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


def _comparar_valores(a, b):
    if a is None and b is None:
        return 0
    if a is None:
        return -1
    if b is None:
        return 1
    try:
        if a < b:
            return -1
        if a > b:
            return 1
        return 0
    except TypeError:
        ta, tb = str(type(a)), str(type(b))
        if ta != tb:
            return -1 if ta < tb else 1
        sa, sb = repr(a), repr(b)
        return -1 if sa < sb else (1 if sa > sb else 0)


def _comparar_registros(r1, r2, ordenar_por_efetivo):
    for campo, direcao in ordenar_por_efetivo:
        c = _comparar_valores(r1.get(campo), r2.get(campo))
        if c != 0:
            return -c if direcao == "desc" else c
    return 0


def _avalia_filtro(valor_registro, op, valor_filtro):
    if op == "eq":
        return valor_registro == valor_filtro
    if op == "ne":
        return valor_registro != valor_filtro
    if op in ("gt", "gte", "lt", "lte"):
        if valor_registro is None:
            return False
        try:
            if op == "gt":
                return valor_registro > valor_filtro
            if op == "gte":
                return valor_registro >= valor_filtro
            if op == "lt":
                return valor_registro < valor_filtro
            return valor_registro <= valor_filtro
        except TypeError:
            return False
    if op == "in":
        return valor_registro in valor_filtro
    if op == "contains":
        if valor_registro is None:
            return False
        if not isinstance(valor_registro, str):
            raise ErroConsulta("FILTRO_INVALIDO")
        return valor_filtro in valor_registro
    raise ErroConsulta("FILTRO_INVALIDO")


class ServicoConsulta:
    def __init__(self, registros: list) -> None:
        self._registros = [dict(r) for r in registros]
        self._perfis: dict = {}

    def definir_perfil(self, perfil, campos_visiveis, filtro_fixo=None) -> None:
        if not isinstance(perfil, str) or perfil == "":
            raise ErroConsulta("PARAMETRO_INVALIDO")
        if not isinstance(campos_visiveis, list) or len(campos_visiveis) == 0:
            raise ErroConsulta("PARAMETRO_INVALIDO")
        if not all(isinstance(c, str) for c in campos_visiveis):
            raise ErroConsulta("PARAMETRO_INVALIDO")
        if filtro_fixo is not None and not isinstance(filtro_fixo, dict):
            raise ErroConsulta("PARAMETRO_INVALIDO")
        self._perfis[perfil] = (set(campos_visiveis), dict(filtro_fixo) if filtro_fixo else {})

    def inserir(self, registro: dict) -> None:
        self._registros.append(dict(registro))

    def consultar(self, perfil: str, params: dict) -> dict:
        if perfil not in self._perfis:
            raise ErroConsulta("PERFIL_DESCONHECIDO")
        campos_visiveis, filtro_fixo = self._perfis[perfil]

        params = params or {}
        cursor = params.get("cursor")
        tamanho = params.get("tamanho")
        ordenar_por_in = params.get("ordenar_por")
        filtros_in = params.get("filtros")

        if tamanho is None:
            tamanho = 20
        else:
            if isinstance(tamanho, bool) or not isinstance(tamanho, int) or not (1 <= tamanho <= 100):
                raise ErroConsulta("PARAMETRO_INVALIDO")

        if cursor is not None and not isinstance(cursor, str):
            raise ErroConsulta("PARAMETRO_INVALIDO")

        if ordenar_por_in is not None:
            if not isinstance(ordenar_por_in, list) or len(ordenar_por_in) == 0:
                raise ErroConsulta("PARAMETRO_INVALIDO")
            for par in ordenar_por_in:
                if (not isinstance(par, (list, tuple)) or len(par) != 2
                        or not isinstance(par[0], str) or par[1] not in _DIRECOES):
                    raise ErroConsulta("PARAMETRO_INVALIDO")

        if filtros_in is not None:
            if not isinstance(filtros_in, dict):
                raise ErroConsulta("PARAMETRO_INVALIDO")
            for campo, cond in filtros_in.items():
                if (not isinstance(campo, str) or not isinstance(cond, dict)
                        or "op" not in cond or "valor" not in cond):
                    raise ErroConsulta("PARAMETRO_INVALIDO")

        if ordenar_por_in is not None:
            for campo, _direcao in ordenar_por_in:
                if campo not in campos_visiveis:
                    raise ErroConsulta("CAMPO_INVALIDO")
        if filtros_in:
            for campo in filtros_in:
                if campo not in campos_visiveis:
                    raise ErroConsulta("CAMPO_INVALIDO")

        if ordenar_por_in is None:
            ordenar_por_efetivo = [["id", "asc"]]
        else:
            ordenar_por_efetivo = [[p[0], p[1]] for p in ordenar_por_in]
            if not any(c == "id" for c, _ in ordenar_por_efetivo):
                ordenar_por_efetivo.append(["id", "asc"])

        filtros_usuario = []
        if filtros_in:
            for campo, cond in filtros_in.items():
                op = cond["op"]
                valor = cond["valor"]
                if op not in _OPS:
                    raise ErroConsulta("FILTRO_INVALIDO")
                if op == "in" and not isinstance(valor, list):
                    raise ErroConsulta("FILTRO_INVALIDO")
                if op == "contains" and not isinstance(valor, str):
                    raise ErroConsulta("FILTRO_INVALIDO")
                filtros_usuario.append((campo, op, valor))

        combinados = []
        for campo, cond in filtro_fixo.items():
            combinados.append((campo, cond["op"], cond["valor"]))
        combinados.extend(filtros_usuario)

        cursor_pseudo = None
        if cursor is not None:
            cursor_pseudo = self._decodificar_cursor(cursor, ordenar_por_efetivo)

        elegiveis = []
        for r in self._registros:
            ok = True
            for campo, op, valor in combinados:
                if not _avalia_filtro(r.get(campo), op, valor):
                    ok = False
                    break
            if ok:
                elegiveis.append(r)

        elegiveis.sort(key=cmp_to_key(lambda a, b: _comparar_registros(a, b, ordenar_por_efetivo)))

        if cursor_pseudo is not None:
            inicio = len(elegiveis)
            for i, r in enumerate(elegiveis):
                if _comparar_registros(r, cursor_pseudo, ordenar_por_efetivo) > 0:
                    inicio = i
                    break
        else:
            inicio = 0

        total = len(elegiveis)
        janela = elegiveis[inicio:]
        pagina = janela[:tamanho]
        tem_proxima = len(janela) > tamanho

        proximo_cursor = None
        if tem_proxima:
            proximo_cursor = self._codificar_cursor(pagina[-1], ordenar_por_efetivo)

        itens = [{k: v for k, v in r.items() if k in campos_visiveis} for r in pagina]

        return {
            "itens": itens,
            "proximo_cursor": proximo_cursor,
            "tem_proxima": tem_proxima,
            "total": total,
        }

    def _codificar_cursor(self, registro, ordenar_por_efetivo):
        campos = [c for c, _ in ordenar_por_efetivo]
        valores = [registro.get(c) for c in campos]
        payload = json.dumps({"campos": campos, "valores": valores})
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")

    def _decodificar_cursor(self, cursor, ordenar_por_efetivo):
        try:
            bruto = base64.urlsafe_b64decode(cursor.encode("ascii"))
            payload = json.loads(bruto.decode("utf-8"))
        except Exception:
            raise ErroConsulta("CURSOR_INVALIDO")

        if not isinstance(payload, dict) or "campos" not in payload or "valores" not in payload:
            raise ErroConsulta("CURSOR_INVALIDO")

        campos = payload["campos"]
        valores = payload["valores"]
        esperado = [c for c, _ in ordenar_por_efetivo]
        if campos != esperado or not isinstance(valores, list) or len(valores) != len(campos):
            raise ErroConsulta("CURSOR_INVALIDO")

        return dict(zip(campos, valores))
