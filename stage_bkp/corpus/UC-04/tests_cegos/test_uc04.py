import threading
import pytest
from solucao import RateLimiter

class Clock:
    def __init__(self):
        self.t = 0.0
    def __call__(self):
        return self.t

def test_permite_exatamente_o_limite():
    clk = Clock()
    rl = RateLimiter(limite=100, janela_s=60, relogio=clk)
    resultados = [rl.verificar("c1")[0] for _ in range(100)]
    assert all(resultados)
    assert rl.verificar("c1")[0] is False

def test_retry_after_do_mais_antigo():
    clk = Clock()
    rl = RateLimiter(limite=100, janela_s=60, relogio=clk)
    for _ in range(100):
        rl.verificar("c1")          # todas em t=0
    clk.t = 30.0
    allowed, retry = rl.verificar("c1")
    assert allowed is False
    assert retry == pytest.approx(30.0, abs=0.1)

def test_janela_deslizante_expira():
    clk = Clock()
    rl = RateLimiter(limite=100, janela_s=60, relogio=clk)
    for _ in range(100):
        rl.verificar("c1")          # todas em t=0
    clk.t = 59.5
    assert rl.verificar("c1")[0] is False
    clk.t = 60.01                    # janela (0.01, 60.01] — as de t=0 sairam
    assert rl.verificar("c1")[0] is True

def test_isolamento_entre_clientes():
    clk = Clock()
    rl = RateLimiter(limite=1, janela_s=60, relogio=clk)
    assert rl.verificar("a")[0] is True
    assert rl.verificar("a")[0] is False
    assert rl.verificar("b")[0] is True

def test_thread_safety_nao_excede_limite():
    clk = Clock()                    # relogio fixo: nada expira
    rl = RateLimiter(limite=50, janela_s=60, relogio=clk)
    aprovadas = []
    def worker():
        for _ in range(25):
            if rl.verificar("c1")[0]:
                aprovadas.append(1)
    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(aprovadas) == 50
