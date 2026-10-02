name: Europe Conflict Radar - Manual Test

on:
  workflow_dispatch:

jobs:
  radar-test:
    runs-on: ubuntu-latest

    steps:
      - name: Get repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Test Supabase connection
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SECRET_KEY: ${{ secrets.SUPABASE_SECRET_KEY }}
        run: python test_supabase.py
