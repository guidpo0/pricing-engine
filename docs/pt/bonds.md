# Títulos Suportados

O serviço cobre os 5 principais títulos do Tesouro Direto disponíveis para negociação:

| Tipo do Título | Identificador da API | Metodologia |
|-----------|----------------|-------------|
| Tesouro Prefixado | `PREFIXADO` | Desconto do valor nominal pela curva de juros nominal (Pré). |
| Tesouro Prefixado com juros | `PREFIXADO_JUROS`| VPL de cupons semestrais de 10% + valor de face na curva pré. |
| Tesouro IPCA+ | `IPCA` | Desconto do VNA pela curva de juros real (IPCA+). |
| Tesouro IPCA+ com juros | `IPCA_JUROS` | VPL de cupons semestrais de 6% sobre o VNA + retorno do VNA na curva real. |
| Tesouro Selic | `SELIC` | VNA SELIC atualizado diariamente desde 2000, descontado pelo spread de mercado. |
