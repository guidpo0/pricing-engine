# Guia de Integração

O Pricing Engine foi desenhado como um **microsserviço de retardo zero** focado em isolar regras de negócio complexas (matemática financeira) das aplicações *Client* (como seu sistema principal de gestão de carteiras, seu banco de dados ou seu App mobile).

## O Paradigma de Responsabilidade Única (Microservices)

1. **A sua Aplicação Principal:**
   A sua aplicação (o *Client*) não precisa e nem deve saber como interpolar uma curva forward da ANBIMA ou calcular cupons semestrais. A única responsabilidade da sua aplicação é saber "O que" o cliente possui. Exemplo: "O Roberto tem 10.51 cotas do Tesouro IPCA+ 2035".

2. **O Pricing Engine (Este projeto):**
   A responsabilidade dele é centralizar todas as regras mutáveis do governo e as taxas do mercado financeiro brasileiro. Ele calcula "Quanto" o ativo do Roberto vale hoje.

Toda a infraestrutura de Pricing pode e deve escalar independentemente do seu sistema de gestão num cluster Kubernetes/Docker.

---

## Como Consumir na Prática

Sempre que a sua aplicação precisar do valor financeiro de um cliente para exibir um Dashboard ou Saldo do dia, ela deve realizar uma chamada HTTP `POST` "por debaixo dos panos" (Server-to-Server) para a nossa Engine de Precificação.

### A Requisição (Your App ➔ Pricing Engine):
Você envia apenas o identificador daquele título e quantas cotas o cliente possui.
**Endpoint:** `POST /portfolio/value`
```json
{
    "bond_type": "IPCA",
    "maturity_date": "2035-05-15",
    "quantity": 10.51
}
```

### A Resposta (Pricing Engine ➔ Your App):
Nossa engine hidrata o preço usando a curva `IPCA+` em memória e devolve a resposta completa e *mastigada* para você em milissegundos.
```json
{
    "bond_type": "IPCA",
    "maturity_date": "2035-05-15",
    "pu": 4150.25,
    "quantity": 10.51,
    "position_value": 43619.13,
    "yield_rate": 0.0612,
    "vna": 4212.18,
    "calculation_date": "2026-03-08"
}
```

A sua aplicação então apenas lê o nó `"position_value": 43619.13` (R$ 43.619,13) e o envia diretamente para a tela do Front-End. O seu banco de dados e a sua equipe de _backend principal_ nunca precisaram saber como se calcula um título Pós Fixado Brasileiro.
