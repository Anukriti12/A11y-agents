## For NVDA Users (Rohan - Lakshmi)

### Install NVDA:

1. Download from: https://www.nvaccess.org/download/
2. Run installer (free, no license needed)
3. During installation, select "Create desktop icon"

### Find NVDA Logs:

NVDA creates log files at:
```
C:\Users\[YourUsername]\AppData\Roaming\nvda\nvda.log
```

### Enable Detailed Logging:

1. Open NVDA (Insert+N)
2. Preferences → Settings
3. General category
4. Set "Logging level" to "Debug"
5. Click OK

### Test NVDA Log Capture:

Create `test_nvda_log.py`:
```python
import os
import time

# Path to NVDA log
nvda_log_path = os.path.expanduser(r"~\AppData\Roaming\nvda\nvda.log")

print(f"NVDA log location: {nvda_log_path}")

if os.path.exists(nvda_log_path):
    print("✓ NVDA log found!")
    
    # Read last 10 lines
    with open(nvda_log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        print("\nLast 10 log entries:")
        for line in lines[-10:]:
            print(line.strip())
else:
    print("NVDA log not found. Make sure NVDA is installed and has been run at least once.")
```


