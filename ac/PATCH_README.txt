AgentCarbon update: roles, monthly request, auditor requests, credit buyer, calendar months
=========================================================================================

HOW TO APPLY (project folder = the folder that contains run.py)
1. Stop the app (Ctrl+C).
2. Delete these 3 files (they are replaced by new pages/routes):
      backend/app/api/claims.py
      frontend/src/pages/Claims.jsx
      frontend/src/pages/Evidence.jsx
3. Delete the whole old folder  frontend/dist   (the new build is in this zip).
4. Copy everything from this zip over your project folder, accepting "replace"
   (the folder layout inside the zip matches the project exactly).
5. IMPORTANT - reset the database (the data model changed):
      delete everything inside the data/ folder      (agentcarbon.db, agentcarbon.db-shm, agentcarbon.db-wal)
      delete the folder datasets/generated/company_bundles   (rebuilt automatically on next start)
   (optional) empty uploads/ and reports/
6. Start:  python run.py      (first start ~30 s)  ->  http://localhost:8000
   Your .env (GROQ_API_KEY) is NOT touched. No new Python packages are needed.
   If you edit the UI later:  cd frontend && npm install && npm run build

WHAT IS IN THIS ZIP
  46 replaced files, 13 new files, 3 files to delete (see steps), and a rebuilt frontend/dist.
   Backend tests:  cd backend && python -m pytest      (21 pass)

NEW LOGINS (password Demo@12345)
  admin@agentcarbon.demo    -> only approves/rejects registrations and maintains accounts
  buyer@agentcarbon.demo    -> credit buyer: sees only auditor-approved, registered credits
  northstar@ / ironwood@ / crestline@ / redwood@ / summit@agentcarbon.demo -> plant operators
  auditor@agentcarbon.demo  -> auditor
