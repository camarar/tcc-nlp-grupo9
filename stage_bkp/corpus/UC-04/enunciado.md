    # UC-04 — Rate limiter de API

    ## Tarefa

    Implemente um limitador de requisições por cliente para proteger uma API.

    ## Interface obrigatória

    - Arquivo: `solucao.py`
- Classe: `RateLimiter(limite=100, janela_s=60, relogio=None)`
- Método: `verificar(client_id) -> tuple[bool, float]`  (allowed, retry_after)
- `relogio` é um callable que retorna o tempo em segundos (float); quando None, usar `time.monotonic`.

    ## Entrega

    - Implementar em `solucao.py`, Python 3.12, sem dependências externas.
    - Os testes em `tests_visiveis/` devem passar.
