# PIDIM SMART Dashboard — React + FastAPI + Scheduler (v2)

- Fixed Reports: Loan, Poultry, Grants
- NEW: Loan custom Month filter (uses AP column as Date of Disbursement)

## Deploy
- **Backend (Render)**: build `pip install -r backend/requirements.txt`, start `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- **Cron**: POST `https://<your-backend>/tasks/refresh` every 10m
- **Frontend (Vercel)**: Root = `frontend`, env `VITE_API_BASE=https://<your-backend>`

## Local
```
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
cd frontend
npm i
npm run dev
```
