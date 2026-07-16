name: Daily OI Scan

on:
  schedule:
    - cron: '15 10 * * 1-5'
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install nsepython pandas numpy

      - name: Run scanner
        run: python institutional_scanner.py

      - name: Commit and push results
        run: |
          git config user.name "OI Pulse Bot"
          git config user.email "bot@users.noreply.github.com"
          git add scan_result.json oi_history.csv
          git commit -m "Auto scan: $(date +'%Y-%m-%d %H:%M')" || echo "No changes to commit"
          git push
