from playwright.sync_api import sync_playwright

url = "https://dequeuniversity.com/demo/dream"

with sync_playwright() as p:
    # Launch a headless browser
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Navigate to the page and wait for it to load
    page.goto(url)
    page.wait_for_load_state("networkidle") # Wait for all network requests to finish

    # Retrieve the fully rendered HTML
    html_content = page.content()
    print(html_content)

    # (Optional) Save it to a file
    with open("rendered_page.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    browser.close()