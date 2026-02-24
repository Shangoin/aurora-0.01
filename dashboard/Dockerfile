FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir streamlit supabase pandas plotly requests python-dotenv

COPY dashboard.py .

EXPOSE 8501

CMD streamlit run dashboard.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true
