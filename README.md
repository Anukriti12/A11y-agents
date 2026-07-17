# A11y-agents

prompts1/ - Where persona system prompts live

tools1/ - Where tool agents live

corpus1/ - Where test cases with ground truth live

results/ - Where results live

docs/ - Architecture and design decisions


## 0. Prerequisites (install once, forget)

### Python 3.11 or 3.12

Download from https://www.python.org/downloads/. Get the **Windows installer (64-bit)** for Python 3.11.9 or 3.12.x. Not Python 3.13 — some of your dependencies aren't updated for it yet.

During install:
- **Check "Add python.exe to PATH"** at the bottom of the first screen. Non-negotiable.
- Click "Install Now"
- After install, click "Disable path length limit" if it appears

Verify in a **new PowerShell window** (existing ones don't see the PATH change):

```powershell
python --version
pip --version
```

Should print Python 3.11.x or 3.12.x and pip 24.x. If either fails, PATH didn't get updated. Reboot and try again.

### Git

Download from https://git-scm.com/download/win. Install with defaults. Verify:

```powershell
git --version
```

### Google Chrome

Selenium tools (axe_core, timing_checker, form_validator) use Chrome. Install from https://www.google.com/chrome/. Verify by launching it.

### Tesseract OCR (for NVDA tool)

1. Download `tesseract-ocr-w64-setup-5.x.x.exe` from https://github.com/UB-Mannheim/tesseract/wiki
2. Run installer. Keep default install path (`C:\Program Files\Tesseract-OCR`).
3. **Check "Add to PATH"** when the installer offers it. If it doesn't offer it, add it manually via System Properties → Environment Variables → Path → New → `C:\Program Files\Tesseract-OCR`.
4. Restart PowerShell.
5. Verify:

```powershell
tesseract --version
```

Should print `tesseract v5.x.x`. If not, PATH is wrong; add it manually.

### NVDA screen reader

Only needed for Lakshmi's persona (which uses `nvda_agent.py`).

1. Download NVDA from https://www.nvaccess.org/download/
2. Install with defaults. Skip "start on Windows startup" if you don't want it always running.
3. NVDA needs to be RUNNING when the experiment executes Lakshmi rows. Launch it (Ctrl+Alt+N) before starting the experiment.

## 1. Clone the repo

```powershell
cd $HOME
git clone https://github.com/Anukriti12/A11y-agents.git
cd A11y-agents
```


## 2. Create a virtual environment

Do this. It isolates your project's dependencies and avoids the "which Python got the packages" confusion you had before.

```powershell
python -m venv venv
```

Activate it:

```powershell
.\venv\Scripts\Activate.ps1
```

Your prompt should now show `(venv)` at the start. Every command after this runs in the venv.

**If PowerShell blocks the activation script** with an execution-policy error:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then re-run the activate command.

Verify you're in the venv:

```powershell
python -c "import sys; print(sys.executable)"
```

Should print a path ending in `venv\Scripts\python.exe`. If it shows `AppData\Local\Programs\Python\...` instead, the venv isn't active.

## 3. Install Python dependencies

Inside the activated venv:

```powershell
python -m pip install --upgrade pip

# Core dependencies your persona agents and tools import
pip install openai python-dotenv beautifulsoup4 lxml

# Selenium tools (axe, timing_checker, form_validator, target_size, etc.)
pip install selenium webdriver-manager

# Playwright tools (check_keyboard_navigation, check_aaa_color_contrast, check_text_formatting, check_wcag_text_spacing_and_reflow)
pip install playwright

# NVDA tool
pip install pywinauto pytesseract pillow

# Readability tool
pip install textstat pyenchant nltk

# Utility
pip install requests tqdm
```

After the above, install Playwright's browser binaries:

```powershell
playwright install chromium
```

That downloads the Chromium build Playwright expects. 

Optional: freeze the exact versions installed so the environment is reproducible.

```powershell
pip freeze > requirements.txt
git add requirements.txt
git commit -m "Freeze Python dependencies for reproducibility"
```

## 4. Set your OpenAI API key

Create a file called `.env` in the repo root (same folder as `run_experiment.py`):

```powershell
Set-Content -Path .env -Value "OPENAI_API_KEY=sk-your-key-here"
```

Confirm it loads:

```powershell
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Key loaded:', bool(os.environ.get('OPENAI_API_KEY')))"
```
Should print `Key loaded: True`.

## 5. Verify each tool dependency independently

Before running the whole experiment, confirm each piece works. 

```powershell
# Playwright can launch a browser
python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); print('Playwright OK'); b.close(); p.stop()"

# Selenium can launch Chrome
python -c "from selenium import webdriver; from selenium.webdriver.chrome.options import Options; o=Options(); o.add_argument('--headless=new'); d=webdriver.Chrome(options=o); d.get('about:blank'); print('Selenium OK'); d.quit()"

# Tesseract is reachable
python -c "import pytesseract; print('Tesseract OK:', pytesseract.get_tesseract_version())"

# pywinauto imports
python -c "from pywinauto.application import Application; print('pywinauto OK')"

# NLTK words corpus (readability tool uses this)
python -c "import nltk; nltk.download('words', quiet=True); from nltk.corpus import words; print('NLTK words OK:', len(words.words()), 'words')"

# openai client
python -c "import openai; print('openai OK:', openai.__version__)"
```

Each should print `OK`. If any fails, that specific dependency needs attention before proceeding.

## 6. Verify the repo structure and imports

```powershell
# Confirm canonical folders exist
dir personas1, tools1, corpus1, conditions

# Confirm base_agent lives in personas/
dir personas\base_agent.py

# Confirm every condition can be imported
python -c "from conditions.condition_a_axe import AxeCondition; from conditions.condition_b_persona_llm import PersonaLLMCondition; from conditions.condition_c_persona_agent import PersonaAgentCondition; print('All imports OK')"
```


## 7. Smoke test with 2 snippets

Before committing to a full run, prove it works on 2 snippets. 6 evaluations total (2 snippets x 3 conditions x 1 rep). Takes about 5 minutes.

```powershell
Remove-Item results\smoke.jsonl -ErrorAction SilentlyContinue
python run_experiment.py --corpus corpus1 --limit 2 --repetitions 1 --output results\smoke.jsonl
```

Watch the console. You should see:
- Both snippets loaded
- All 3 conditions run for each
- No `ModuleNotFoundError`
- No `BrowserType.launch: Executable doesn't exist` (Playwright working)
- No `No module named 'pytesseract'` (NVDA tool working)


## 8. Check the smoke test tool traces


```powershell
python -c "
import json
with open('results/smoke.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r.get('condition') != 'persona_agent': continue
        for c in r.get('metadata', {}).get('tool_trace', []):
            print(f\"{c['name']:<40} status={c['status']:<10} elapsed={c['elapsed_seconds']:.2f}s\")
"
```

Every line should show `status=ok` (or `status=ok_inapplicable` for legit no-work returns) and `elapsed_seconds` matching the tool type:
- Selenium tools: 3-8s
- Playwright tools: 5-15s
- NVDA tool: 20-60s
- Static analyzers: 0.01-2s

Any `status=tool_error` or Playwright/NVDA tool completing in under a second means that tool is still broken. Debug that ONE tool before running the full experiment.

## 9. Run the full experiment

Once smoke passes clean:
# Backup the broken old results (optional)
Copy-Item results\experiment_results.jsonl results\experiment_results_v1_broken.jsonl -ErrorAction SilentlyContinue

# Full run to fresh output file
python run_experiment.py --corpus corpus1 --repetitions 3 --output results\experiment_results_v2_fixed.jsonl


**Keep NVDA running the entire time** if the corpus includes Lakshmi snippets. If NVDA closes mid-run, Lakshmi's tool will start failing.

In a second PowerShell window, watch the log live:

```powershell
Get-Content results\logs\base_agent_*.log -Wait -Tail 20
```

Look for any `status=tool_error` lines. If they start piling up, kill the run (Ctrl+C), fix the tool, and restart. `--resume` is on by default so you won't lose completed rows.

## 10. After the experiment finishes

Two commands, in order:

```powershell
python reclassify_traces.py results\experiment_results.jsonl
python analyze_results.py results\experiment_results_reclassified.jsonl
```

This produces `results\analysis\verdicts.csv` and `results\analysis\tool_calls.csv`, plus a summary in the console showing per-persona agreement rates and per-tool statistics.

## 11. Snapshot for reproducibility

```powershell
mkdir snapshots\v1_final
Copy-Item -Recurse personas, personas1, tools1, corpus1, conditions, run_experiment.py, requirements.txt, .env.example snapshots\v1_final\
git add snapshots\
git commit -m "Freeze v1 configuration for A11yAgents study"
```

(Include `.env.example` with the key stripped, not `.env` — contains API key.)
