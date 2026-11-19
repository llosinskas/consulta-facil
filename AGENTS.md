# AGENTS.md

As instruções para assistentes de IA (arquitetura, fluxo de dados, contratos entre módulos,
armadilhas e checklist) estão em [`CLAUDE.md`](CLAUDE.md). Leia-o antes de modificar o código.

Resumo mínimo:
- Camadas: `app.py`/`pages/` → `ui/` → `services/` → `domain/`. `domain` e `services` não importam Streamlit nem `ui`.
- Testes: `python -m pytest -q` (inclui `tests/test_arquitetura.py`, que valida as camadas e as assinaturas públicas).
