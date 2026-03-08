# Tesouro Direto Pricing Engine

A production-ready microservice that calculates exact mark-to-market prices (Preço Unitário - PU) for Brazilian government bonds from the **Tesouro Direto** program. 

The engine fetches live market data daily and uses the Brazilian 252 business-day convention to price all available retail government bonds.

## Documentation

Full project documentation is available in the [`docs/`](docs/) directory:
- [English Documentation](docs/README_en.md)
- [Documentação em Português](docs/README_pt.md)

You can also read the rendered HTML documentation directly from the running API at:
- `GET /docs/readme`

## Quick Start

```bash
# Requires Python 3.12+ and Make
make run
```
*Starts the API on [http://localhost:8000](http://localhost:8000).*

To run the robust 34+ unit test suite:
```bash
make test
```
