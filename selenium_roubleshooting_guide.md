
## Troubleshooting

### Issue: "chromedriver not found"
**Solution:** Use webdriver-manager (Step 2) which handles this automatically

### Issue: "Chrome version mismatch"
**Solution:** Update Chrome browser to latest version, then run:
```bash
pip install --upgrade webdriver-manager
```

### Issue: "Permission denied" on Mac/Linux
**Solution:** Run with sudo:
```bash
sudo pip install selenium
```

### Issue: Browser opens but doesn't navigate
**Solution:** Check your internet connection and firewall settings

