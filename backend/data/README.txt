Shop database (backend/data/shop.db)
====================================

Your app reads shop.db from this folder. seed.sql is a full SQLite dump used when the DB
file is missing or empty (e.g. fresh clone / Railway first boot).

Option A — Official course shop.db (best if you still have the ~2 MB file)
---------------------------------------------------------------------------
  1. Copy your real shop.db from class materials to this folder as shop.db (replace).
  2. From the backend/ directory:
       python data/export_seed.py
  3. Commit shop.db and seed.sql if you want the same data everywhere.

  Or in one step:
       python data/import_course_database.py /path/to/your/original/shop.db

Option B — Large synthetic dataset (no "Demo Customer"; for local dev only)
----------------------------------------------------------------------------
  From backend/:
       python data/populate_full_sample.py
       python data/export_seed.py

  This rebuilds shop.db with hundreds of customers and orders (random names).

After changing shop.db, run export_seed.py so seed.sql stays in sync.
