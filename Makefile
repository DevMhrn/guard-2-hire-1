.PHONY: install demo eval migrate seed ui clean

# ─── Setup ────────────────────────────────────────────────────────────────────
install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -U pip && pip install -e ".[dev]"
	@echo "✓ deps installed. Copy .env.example → .env and fill in keys."

# ─── Database ─────────────────────────────────────────────────────────────────
migrate:
	@. .venv/bin/activate && python -c "\
import os, psycopg; \
from dotenv import load_dotenv; load_dotenv(override=True); \
url=os.environ['SUPABASE_DB_URL']; \
sql=open('hireguard/rag/migrations.sql').read(); \
conn=psycopg.connect(url, prepare_threshold=None); \
cur=conn.cursor(); cur.execute(sql); conn.commit(); conn.close(); \
print('✓ migration applied')"

seed:
	@. .venv/bin/activate && python -m hireguard.rag.seed
	@echo "✓ rules seeded into Supabase (Member B owns this)"

# ─── Run ──────────────────────────────────────────────────────────────────────
# The real demo — what graders see.
demo:
	@. .venv/bin/activate && streamlit run hireguard/ui/streamlit_app.py

# Headless CLI — for dev debugging and as a fallback if Streamlit breaks.
cli:
	@. .venv/bin/activate && python run_demo.py --sample acme_se_role

cli-clean:
	@. .venv/bin/activate && python run_demo.py --sample northwind_pm_role

cli-auto:
	@. .venv/bin/activate && python run_demo.py --sample acme_se_role --auto-approve

# ─── Tests / Evals ────────────────────────────────────────────────────────────
eval:
	@. .venv/bin/activate && pytest tests/ -v

# ─── Housekeeping ─────────────────────────────────────────────────────────────
clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ */__pycache__ */*/__pycache__
	rm -rf *.egg-info build dist
