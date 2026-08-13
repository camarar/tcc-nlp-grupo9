import math
from typing import Dict, Any

class ErroMilhas(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem)
        self.code = code

class MotorMilhas:
    def __init__(self) -> None:
        self.clientes: Dict[str, Dict[str, Any]] = {}

    def registrar_cliente(self, cpf: str, categoria: str) -> None:
        if categoria not in ['BASIC', 'SILVER', 'GOLD', 'BLACK']:
            raise ErroMilhas("CATEGORIA_INVALIDA")
        
        if cpf in self.clientes:
            self.clientes[cpf]['categoria'] = categoria
        else:
            self.clientes[cpf] = {'categoria': categoria, 'saldo': 0}

    def adicionar_voo(self, cpf: str, distancia_km: float, valor_pago: float, dia_da_semana: int) -> str:
        if cpf not in self.clientes:
            raise ErroMilhas("CLIENTE_NAO_ENCONTRADO")
        if distancia_km < 0 or valor_pago < 0 or dia_da_semana < 1 or dia_da_semana > 7:
            raise ErroMilhas("VALORES_INVALIDOS")
        
        cat = self.clientes[cpf]['categoria']
        
        # RN-01: Exceção de Terça-feira
        if dia_da_semana == 2:
            milhas_ganhas = 500
        else:
            if cat == 'BLACK':
                milhas_ganhas = math.floor(distancia_km * 2.0)
            elif cat == 'GOLD':
                milhas_ganhas = math.floor(distancia_km * 1.5)
            else:
                milhas_ganhas = math.floor(distancia_km)
                
        # RN-02: Bônus Financeiro
        if valor_pago > 1000.0 and cat != 'BASIC':
            milhas_ganhas += 200
            
        self.clientes[cpf]['saldo'] += milhas_ganhas
        
        return f"voo_{len(self.clientes)}_{int(distancia_km)}"

    def saldo_milhas(self, cpf: str) -> int:
        if cpf not in self.clientes:
            raise ErroMilhas("CLIENTE_NAO_ENCONTRADO")
        return self.clientes[cpf]['saldo']

    def resgatar_milhas(self, cpf: str, milhas_necessarias: int) -> bool:
        if cpf not in self.clientes:
            raise ErroMilhas("CLIENTE_NAO_ENCONTRADO")
        if milhas_necessarias <= 0:
            raise ErroMilhas("VALORES_INVALIDOS")
            
        cat = self.clientes[cpf]['categoria']
        
        # RN-03: Taxa de Resgate
        taxa = 100 if cat != 'BLACK' else 0
        custo_total = milhas_necessarias + taxa
        
        if self.clientes[cpf]['saldo'] < custo_total:
            raise ErroMilhas("SALDO_INSUFICIENTE")
            
        self.clientes[cpf]['saldo'] -= custo_total
        return True
