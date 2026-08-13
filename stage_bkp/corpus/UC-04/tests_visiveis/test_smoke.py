from solucao import RateLimiter

def test_permite_ate_o_limite():
    rl = RateLimiter(limite=3, janela_s=60, relogio=lambda: 0.0)
    assert rl.verificar("a")[0] is True
    assert rl.verificar("a")[0] is True
    assert rl.verificar("a")[0] is True

def test_nega_acima_do_limite():
    rl = RateLimiter(limite=1, janela_s=60, relogio=lambda: 0.0)
    rl.verificar("a")
    allowed, retry = rl.verificar("a")
    assert allowed is False
