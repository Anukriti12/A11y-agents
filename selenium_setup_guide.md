# Selenium Installation Guide for Accessibility Agents Project

## Prerequisites

- Python 3.8 or higher installed
- pip package manager
- Code editor (VS Code recommended)

## Step 1: Install Selenium

Open your terminal/command prompt and run:
```bash
pip install selenium
```

## Step 2: Install WebDriver Manager (Easier than manual driver setup)
```bash
pip install webdriver-manager
```
This automatically handles Chrome/Firefox driver downloads.

## Step 3: Install Additional Libraries
```bash
pip install beautifulsoup4
pip install textstat
pip install pillow
```
- beautifulsoup4: For HTML parsing
- textstat: For readability analysis (Sophie)
- pillow: For screenshot analysis (Elias)

## Step 4: Test Your Setup

Create a file called `test_selenium.py`:
```python
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# Setup Chrome driver
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

# Navigate to a test page
driver.get("https://www.w3.org/WAI/demos/bad/before/home.html")

# Print page title
print(f"Page title: {driver.title}")

# Find all images
images = driver.find_elements(By.TAG_NAME, "img")
print(f"Found {len(images)} images on page")

# Close browser
driver.quit()

print("\nSelenium is working correctly!")
```

Run it:
```bash
python test_selenium.py
```
If you see the page title and image count, you're all set!

## Step 5: Test Zoom Functionality (for Elias agent)

Create `test_zoom.py`:
```python
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
driver.get("https://www.washington.edu")
driver.maximize_window()

# Take screenshot at 100%
driver.save_screenshot("test_100.png")
print("Screenshot at 100% saved")

# Zoom to 200%
driver.execute_script("document.body.style.zoom='200%'")
time.sleep(2)

# Check for horizontal scroll
has_h_scroll = driver.execute_script(
    "return document.documentElement.scrollWidth > window.innerWidth"
)
print(f"Horizontal scroll at 200%: {has_h_scroll}")

# Take screenshot at 200%
driver.save_screenshot("test_200.png")
print("Screenshot at 200% saved")

driver.quit()
print("\nZoom testing works!")
```

## Step 6: Test Keyboard Navigation (for Ade agent)

Create `test_keyboard.py`:
```python
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
driver.get("https://www.washington.edu")

body = driver.find_element(By.TAG_NAME, "body")

print("Tabbing through first 10 focusable elements:\n")

for i in range(10):
    body.send_keys(Keys.TAB)
    focused = driver.switch_to.active_element
    
    # Get element info
    tag = focused.tag_name
    text = focused.text[:30] if focused.text else ""
    
    # Check focus indicator
    outline = focused.value_of_css_property('outline')
    has_outline = outline != 'none'
    
    status = "✓" if has_outline else "✗"
    print(f"{i+1}. {tag}: {text} - Focus visible: {status}")

driver.quit()
print("\nKeyboard navigation testing works!")
```

## Quick Reference

### Common Selenium Commands:
```python
# Navigate
driver.get("https://example.com")

# Find elements
element = driver.find_element(By.ID, "submit")
elements = driver.find_elements(By.TAG_NAME, "img")

# Send keys
element.send_keys("text to type")
element.send_keys(Keys.TAB)
element.send_keys(Keys.ENTER)

# Execute JavaScript
result = driver.execute_script("return document.title")

# Screenshots
driver.save_screenshot("page.png")

# Get CSS properties
color = element.value_of_css_property('color')

# Element size/position
size = element.size  # {'width': 100, 'height': 50}
location = element.location  # {'x': 10, 'y': 20}

# Close
driver.quit()
```