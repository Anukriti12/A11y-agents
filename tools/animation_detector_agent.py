"""
Animation Detector Tool Agent
Detects CSS animations and autoplay media
Used by: Stefan, Elias
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

class AnimationDetectorAgent:
    """Detects animations that could distract or overwhelm users"""
    
    def execute(self, html):
        """
        Detect CSS animations and autoplay media.
        
        Args:
            html: HTML string to analyze
        
        Returns:
            {
                "css_animations": [...],
                "css_animations_count": int,
                "autoplay_media": [...],
                "autoplay_count": int,
                "total_motion_count": int,
                "tool_name": "AnimationDetectorAgent"
            }
        """
        
        driver = self._start_browser()
        
        try:
            # Load HTML
            driver.get(f"data:text/html;charset=utf-8,{html}")
            time.sleep(1)  # Let page render and animations start
            
            # Detect CSS animations (will never return None)
            css_animations = self._detect_css_animations(driver)
            
            # Detect autoplay media (will never return None)
            autoplay_media = self._detect_autoplay_media(driver)
            
            return {
                "css_animations": css_animations,
                "css_animations_count": len(css_animations),
                "autoplay_media": autoplay_media,
                "autoplay_count": len(autoplay_media),
                "total_motion_count": len(css_animations) + len(autoplay_media),
                "tool_name": "AnimationDetectorAgent"
            }
        
        finally:
            driver.quit()
    
    def _start_browser(self):
        """Start headless Chrome browser"""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        
        return webdriver.Chrome(options=options)
    
    def _detect_css_animations(self, driver):
        """
        Detect elements with CSS animations.
        
        Returns:
            list: List of dictionaries containing animation details
        """
        
        script = """
        const elements = document.querySelectorAll('*');
        const animated = [];
        
        elements.forEach((elem, idx) => {
            const style = window.getComputedStyle(elem);
            
            // Check for CSS animations
            if (style.animationName && style.animationName !== 'none') {
                animated.push({
                    element_index: idx,
                    tag: elem.tagName.toLowerCase(),
                    class: elem.className || '',
                    id: elem.id || '',
                    animation_name: style.animationName,
                    animation_duration: style.animationDuration,
                    animation_iteration_count: style.animationIterationCount
                });
            }
        });
        
        return animated;
        """
        
        try:
            result = driver.execute_script(script)
            return result if result else []
        except Exception as e:
            print(f"Error detecting CSS animations: {e}")
            return []  # Always return list, never None
    
    def _detect_autoplay_media(self, driver):
        """
        Detect video/audio elements with autoplay attribute.
        
        Returns:
            list: List of dictionaries containing autoplay media details
        """
        
        autoplay_elements = []
        
        # Find all video elements with autoplay
        try:
            videos = driver.find_elements(By.TAG_NAME, 'video')
            for video in videos:
                if video.get_attribute('autoplay') is not None:
                    autoplay_elements.append({
                        "type": "video",
                        "src": video.get_attribute('src') or '',
                        "has_controls": video.get_attribute('controls') is not None,
                        "is_muted": video.get_attribute('muted') is not None,
                        "is_looping": video.get_attribute('loop') is not None
                    })
        except Exception as e:
            print(f"Error detecting videos: {e}")
        
        # Find all audio elements with autoplay
        try:
            audios = driver.find_elements(By.TAG_NAME, 'audio')
            for audio in audios:
                if audio.get_attribute('autoplay') is not None:
                    autoplay_elements.append({
                        "type": "audio",
                        "src": audio.get_attribute('src') or '',
                        "has_controls": audio.get_attribute('controls') is not None,
                        "is_muted": audio.get_attribute('muted') is not None
                    })
        except Exception as e:
            print(f"Error detecting audio: {e}")
        
        return autoplay_elements  # Always return list, never None


# Test
if __name__ == "__main__":
    agent = AnimationDetectorAgent()
    
    # Test 1: Simple test from original
    print("=" * 50)
    print("TEST 1: Original simple test")
    print("=" * 50)
    
    test_html = """
    <div style="animation: spin 1s infinite">Spinning</div>
    <video autoplay loop src="ad.mp4"></video>
    """
    
    result = agent.execute(test_html)
    print("Result:", result)
    print(f"Expected: 1 CSS animation, 1 autoplay video")
    print(f"Got: {result['css_animations_count']} animation(s), {result['autoplay_count']} autoplay")
    assert result['css_animations_count'] == 1, "Should detect 1 animation"
    assert result['autoplay_count'] == 1, "Should detect 1 autoplay video"
    print("✓ PASS")
    print()
    
    # Test 2: More complex example
    print("=" * 50)
    print("TEST 2: Multiple animations")
    print("=" * 50)
    
    test_html_2 = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                50% { transform: translateX(-10px); }
            }
            @keyframes fade {
                from { opacity: 1; }
                to { opacity: 0; }
            }
            .ad { animation: shake 0.5s infinite; }
            .banner { animation: fade 2s infinite; }
        </style>
    </head>
    <body>
        <div class="ad">SALE!</div>
        <div class="banner">Limited Time</div>
        <video autoplay loop src="ad.mp4"></video>
    </body>
    </html>
    """
    
    result = agent.execute(test_html_2)
    print("Result:", result)
    print(f"Expected: 2 CSS animations, 1 autoplay video (total: 3)")
    print(f"Got: {result['css_animations_count']} animations, {result['autoplay_count']} autoplay, total: {result['total_motion_count']}")
    assert result['total_motion_count'] == 3, "Should detect 3 total motion sources"
    print("✓ PASS")
    print()
    
    # Test 3: No animations (control)
    print("=" * 50)
    print("TEST 3: No animations")
    print("=" * 50)
    
    test_html_3 = """
    <html>
    <body>
        <h1>Static Page</h1>
        <p>No animations here.</p>
    </body>
    </html>
    """
    
    result = agent.execute(test_html_3)
    print("Result:", result)
    print(f"Expected: 0 animations")
    print(f"Got: {result['total_motion_count']} total motion")
    assert result['total_motion_count'] == 0, "Should detect 0 motion"
    print("✓ PASS")
    print()
    
    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)

# """
# Animation Detector Tool Agent
# Detects CSS animations, transitions, autoplay media, and animated GIFs.
# Verifies prefers-reduced-motion suppression and pause/stop/hide mechanism existence.

# Used by: Stefan (2.2.2), Elias (2.2.2)
# Elias-specific: also checks pause-control target size (hand tremor consideration)

# Replaces Selenium with Playwright for consistency with the rest of the pipeline.
# """

# import asyncio
# import base64
# import re
# import struct
# import zlib
# from pathlib import Path
# from playwright.async_api import async_playwright


# # WCAG 2.2.2: motion lasting ≤ 5 seconds is exempt (blink/pause rule only applies to longer motion)
# DURATION_THRESHOLD_SECONDS = 5.0

# # WCAG 2.5.5: minimum target size for interactive controls (also practical for Elias's tremor)
# MIN_TARGET_SIZE_PX = 44

# # CSS properties that indicate a pause/stop/hide mechanism
# PAUSE_CONTROL_ARIA_LABELS = [
#     "pause", "stop", "hide", "freeze", "disable animation",
#     "reduce motion", "stop animation", "pause animation"
# ]

# # Known JS animation library globals to detect
# JS_ANIMATION_GLOBALS = ["gsap", "TweenMax", "TweenLite", "anime", "velocity", "lottie", "rive"]


# class AnimationDetectorAgent:
#     """
#     Detects motion content on a page and evaluates WCAG 2.2.2 compliance.

#     Tests:
#         1. CSS @keyframe animations (via getComputedStyle)
#         2. CSS transitions (motion, not just colour changes)
#         3. Autoplay video and audio
#         4. Animated GIFs
#         5. JS animation library presence (GSAP, anime.js, Lottie, etc.)
#         6. Whether animations stop under prefers-reduced-motion: reduce
#         7. Whether a pause/stop/hide mechanism exists
#         8. [Elias] Whether pause controls meet minimum target size
#     """

#     def execute(self, url_or_html: str, persona: str = "stefan") -> dict:
#         """
#         Synchronous entry point. Runs the async analysis in an event loop.

#         Args:
#             url_or_html: A full URL (https://...) or raw HTML string.
#             persona: "stefan" or "elias" — Elias triggers target-size check.

#         Returns:
#             dict with keys:
#                 css_animations         list  — active @keyframe animations above duration threshold
#                 css_transitions        list  — active CSS transitions on motion properties
#                 autoplay_media         list  — <video>/<audio> with autoplay
#                 animated_gifs          list  — <img> elements confirmed as animated GIFs
#                 js_animation_libs      list  — JS animation libraries detected on the page
#                 reduced_motion_result  dict  — which animations stopped / persisted under reduced-motion
#                 pause_mechanism        dict  — whether a pause/stop/hide control was found
#                 target_size_issues     list  — [Elias only] pause controls below 44×44px
#                 total_motion_count     int   — sum of all motion sources found
#                 wcag_222_status        str   — "PASS" | "FAIL" | "INAPPLICABLE"
#                 tool_name              str
#         """
#         return asyncio.run(self._run(url_or_html, persona))

#     # ------------------------------------------------------------------ #
#     #  Main async pipeline                                                 #
#     # ------------------------------------------------------------------ #

#     async def _run(self, url_or_html: str, persona: str) -> dict:
#         async with async_playwright() as pw:
#             browser = await pw.chromium.launch(headless=True)

#             try:
#                 # --- Pass 1: normal rendering ---
#                 context_normal = await browser.new_context()
#                 page_normal = await context_normal.new_page()
#                 await self._load(page_normal, url_or_html)

#                 css_animations  = await self._detect_css_animations(page_normal)
#                 css_transitions = await self._detect_css_transitions(page_normal)
#                 autoplay_media  = await self._detect_autoplay_media(page_normal)
#                 animated_gifs   = await self._detect_animated_gifs(page_normal)
#                 js_libs         = await self._detect_js_animation_libs(page_normal)

#                 await context_normal.close()

#                 # --- Pass 2: prefers-reduced-motion: reduce ---
#                 context_reduced = await browser.new_context(reduced_motion="reduce")
#                 page_reduced = await context_reduced.new_page()
#                 await self._load(page_reduced, url_or_html)

#                 reduced_motion_result = await self._check_reduced_motion(
#                     page_reduced, css_animations
#                 )
#                 pause_mechanism = await self._check_pause_mechanism(page_reduced)

#                 # Elias: check target sizes of any pause controls found
#                 target_size_issues = []
#                 if persona == "elias" and pause_mechanism["controls_found"]:
#                     target_size_issues = await self._check_target_sizes(
#                         page_reduced, pause_mechanism["control_selectors"]
#                     )

#                 await context_reduced.close()

#             finally:
#                 await browser.close()

#         total_motion = (
#             len(css_animations)
#             + len(css_transitions)
#             + len(autoplay_media)
#             + len(animated_gifs)
#             + len(js_libs)
#         )

#         wcag_status = self._evaluate_wcag_222(
#             total_motion, reduced_motion_result, pause_mechanism
#         )

#         return {
#             "css_animations":        css_animations,
#             "css_transitions":       css_transitions,
#             "autoplay_media":        autoplay_media,
#             "animated_gifs":         animated_gifs,
#             "js_animation_libs":     js_libs,
#             "reduced_motion_result": reduced_motion_result,
#             "pause_mechanism":       pause_mechanism,
#             "target_size_issues":    target_size_issues,
#             "total_motion_count":    total_motion,
#             "wcag_222_status":       wcag_status,
#             "tool_name":             "AnimationDetectorAgent",
#         }

#     # ------------------------------------------------------------------ #
#     #  Page loading                                                        #
#     # ------------------------------------------------------------------ #

#     async def _load(self, page, url_or_html: str) -> None:
#         """Load a URL or raw HTML string, then wait for network idle."""
#         if url_or_html.strip().startswith("http"):
#             await page.goto(url_or_html, wait_until="networkidle", timeout=30_000)
#         else:
#             # Encode HTML as a data URL to avoid data: URI length limits
#             encoded = base64.b64encode(url_or_html.encode()).decode()
#             await page.goto(
#                 f"data:text/html;base64,{encoded}",
#                 wait_until="domcontentloaded",
#                 timeout=15_000,
#             )
#         # Give animations a moment to start
#         await page.wait_for_timeout(800)

#     # ------------------------------------------------------------------ #
#     #  Detection methods                                                   #
#     # ------------------------------------------------------------------ #

#     async def _detect_css_animations(self, page) -> list:
#         """
#         Detect elements with active CSS @keyframe animations.
#         Filters out animations shorter than DURATION_THRESHOLD_SECONDS —
#         WCAG 2.2.2 only applies to motion lasting more than 5 seconds or
#         that repeats indefinitely.
#         """
#         return await page.evaluate(
#             """(threshold) => {
#             const results = [];
#             document.querySelectorAll('*').forEach((el, idx) => {
#                 const s = window.getComputedStyle(el);
#                 const name     = s.animationName;
#                 const duration = s.animationDuration;       // e.g. "1.5s"
#                 const count    = s.animationIterationCount; // "infinite" or "3"
#                 const state    = s.animationPlayState;      // "running" | "paused"

#                 if (!name || name === 'none') return;

#                 // Parse duration in seconds
#                 const secs = parseFloat(duration) * (duration.endsWith('ms') ? 0.001 : 1);

#                 // Exempt short, finite animations (not covered by 2.2.2)
#                 const isInfinite = count === 'infinite';
#                 if (!isInfinite && secs <= threshold) return;

#                 results.push({
#                     element_index:  idx,
#                     tag:            el.tagName.toLowerCase(),
#                     class:          el.className || '',
#                     id:             el.id || '',
#                     animation_name: name,
#                     duration_sec:   secs,
#                     iteration:      count,
#                     play_state:     state,
#                     is_infinite:    isInfinite,
#                     outer_html_snippet: el.outerHTML.slice(0, 120),
#                 });
#             });
#             return results;
#         }""",
#             DURATION_THRESHOLD_SECONDS,
#         )

#     async def _detect_css_transitions(self, page) -> list:
#         """
#         Detect elements with CSS transitions on motion-related properties.
#         Colour and opacity transitions are excluded — only spatial/size motion matters.
#         """
#         MOTION_PROPS = {
#             "transform", "translate", "scale", "rotate",
#             "top", "left", "right", "bottom",
#             "width", "height", "margin", "padding",
#         }
#         return await page.evaluate(
#             """(motionProps) => {
#             const results = [];
#             document.querySelectorAll('*').forEach((el, idx) => {
#                 const s = window.getComputedStyle(el);
#                 const props    = s.transitionProperty;   // e.g. "transform, opacity"
#                 const duration = s.transitionDuration;

#                 if (!props || props === 'none' || props === 'all') return;

#                 const propList = props.split(',').map(p => p.trim().toLowerCase());
#                 const hasMotion = propList.some(p =>
#                     motionProps.some(mp => p.includes(mp))
#                 );
#                 if (!hasMotion) return;

#                 const secs = parseFloat(duration) * (duration.endsWith('ms') ? 0.001 : 1);
#                 if (secs <= 0.1) return;  // Sub-100ms transitions are imperceptible

#                 results.push({
#                     element_index:   idx,
#                     tag:             el.tagName.toLowerCase(),
#                     id:              el.id || '',
#                     class:           el.className || '',
#                     transition_props: propList.filter(p =>
#                         motionProps.some(mp => p.includes(mp))
#                     ),
#                     duration_sec:    secs,
#                 });
#             });
#             return results;
#         }""",
#             list(MOTION_PROPS),
#         )

#     async def _detect_autoplay_media(self, page) -> list:
#         """Detect <video> and <audio> elements with autoplay."""
#         return await page.evaluate("""() => {
#             const results = [];
#             ['video', 'audio'].forEach(tag => {
#                 document.querySelectorAll(tag).forEach(el => {
#                     if (el.autoplay) {
#                         results.push({
#                             type:         tag,
#                             src:          el.src || el.currentSrc || '',
#                             has_controls: el.controls,
#                             is_muted:     el.muted,
#                             is_looping:   el.loop,
#                             duration_sec: isNaN(el.duration) ? null : el.duration,
#                         });
#                     }
#                 });
#             });
#             return results;
#         }""")

#     async def _detect_animated_gifs(self, page) -> list:
#         """
#         Detect animated GIFs by downloading each .gif <img> src and
#         inspecting the binary for multiple frames (Netscape Application Block).
#         Works on both URLs and data URIs.
#         """
#         gif_srcs = await page.evaluate("""() =>
#             Array.from(document.querySelectorAll('img'))
#                  .filter(img => img.src.toLowerCase().includes('.gif') ||
#                                 img.src.startsWith('data:image/gif'))
#                  .map(img => ({ src: img.src, alt: img.alt || '', id: img.id || '' }))
#         """)

#         results = []
#         for item in gif_srcs:
#             try:
#                 if item["src"].startswith("data:"):
#                     data = base64.b64decode(item["src"].split(",", 1)[1])
#                 else:
#                     response = await page.request.get(item["src"])
#                     data = await response.body()

#                 if self._is_animated_gif(data):
#                     results.append({
#                         "src":     item["src"][:80],
#                         "alt":     item["alt"],
#                         "id":      item["id"],
#                         "is_animated": True,
#                     })
#             except Exception:
#                 pass  # Skip GIFs we can't fetch

#         return results

#     @staticmethod
#     def _is_animated_gif(data: bytes) -> bool:
#         """Check for Netscape Application Block — present in all animated GIFs."""
#         return b"NETSCAPE2.0" in data or data.count(b"\x2c") > 1  # Multiple image descriptors

#     async def _detect_js_animation_libs(self, page) -> list:
#         """Detect known JS animation library globals."""
#         return await page.evaluate(
#             """(libs) => libs.filter(lib => typeof window[lib] !== 'undefined')""",
#             JS_ANIMATION_GLOBALS,
#         )

#     # ------------------------------------------------------------------ #
#     #  Reduced-motion verification                                         #
#     # ------------------------------------------------------------------ #

#     async def _check_reduced_motion(self, page, original_animations: list) -> dict:
#         """
#         Under prefers-reduced-motion: reduce, check which animations are still running.

#         A conforming page should either:
#           - Set animation-play-state: paused, OR
#           - Set animation-name: none, OR
#           - Set animation-duration to 0s
#         """
#         if not original_animations:
#             return {
#                 "media_query_respected": True,
#                 "still_running": [],
#                 "stopped_count": 0,
#                 "still_running_count": 0,
#                 "note": "No animations to evaluate",
#             }

#         # Verify the media query is actually active in this context
#         query_active = await page.evaluate(
#             "() => matchMedia('(prefers-reduced-motion: reduce)').matches"
#         )

#         # Re-check each originally animated element
#         still_running = await page.evaluate(
#             """(threshold) => {
#             const results = [];
#             document.querySelectorAll('*').forEach((el, idx) => {
#                 const s     = window.getComputedStyle(el);
#                 const name  = s.animationName;
#                 const state = s.animationPlayState;
#                 const dur   = parseFloat(s.animationDuration) || 0;

#                 if (!name || name === 'none') return;
#                 if (state === 'paused') return;
#                 if (dur === 0) return;

#                 results.push({
#                     element_index: idx,
#                     tag:           el.tagName.toLowerCase(),
#                     id:            el.id || '',
#                     animation_name: name,
#                     play_state:    state,
#                 });
#             });
#             return results;
#         }""",
#             DURATION_THRESHOLD_SECONDS,
#         )

#         return {
#             "media_query_active":    query_active,
#             "still_running":         still_running,
#             "still_running_count":   len(still_running),
#             "stopped_count":         len(original_animations) - len(still_running),
#             "all_stopped":           len(still_running) == 0,
#         }

#     # ------------------------------------------------------------------ #
#     #  Pause/stop/hide mechanism check                                     #
#     # ------------------------------------------------------------------ #

#     async def _check_pause_mechanism(self, page) -> dict:
#         """
#         Look for a pause, stop, or hide control for moving content.

#         Checks:
#           - Buttons/links with pause-related aria-label or text content
#           - Elements with role="button" or <button> containing pause iconography
#           - Whether found controls are keyboard-focusable (tabindex ≥ 0)
#         """
#         controls = await page.evaluate(
#             """(labels) => {
#             const results = [];
#             const candidates = document.querySelectorAll(
#                 'button, [role="button"], a, input[type="button"], input[type="submit"]'
#             );
#             candidates.forEach(el => {
#                 const text      = (el.textContent || '').trim().toLowerCase();
#                 const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
#                 const title     = (el.getAttribute('title') || '').toLowerCase();
#                 const combined  = text + ' ' + ariaLabel + ' ' + title;

#                 const match = labels.find(l => combined.includes(l));
#                 if (!match) return;

#                 const tabindex   = el.getAttribute('tabindex');
#                 const focusable  = tabindex === null || parseInt(tabindex) >= 0;
#                 const rect       = el.getBoundingClientRect();

#                 results.push({
#                     tag:          el.tagName.toLowerCase(),
#                     text:         text.slice(0, 60),
#                     aria_label:   ariaLabel,
#                     matched_on:   match,
#                     focusable:    focusable,
#                     selector:     el.id ? '#' + el.id : (el.className ? '.' + el.className.split(' ')[0] : el.tagName.toLowerCase()),
#                     width_px:     Math.round(rect.width),
#                     height_px:    Math.round(rect.height),
#                 });
#             });
#             return results;
#         }""",
#             PAUSE_CONTROL_ARIA_LABELS,
#         )

#         non_focusable = [c for c in controls if not c["focusable"]]

#         return {
#             "controls_found":        len(controls) > 0,
#             "control_count":         len(controls),
#             "controls":              controls,
#             "control_selectors":     [c["selector"] for c in controls],
#             "keyboard_inaccessible": non_focusable,
#             "all_keyboard_accessible": len(non_focusable) == 0,
#         }

#     # ------------------------------------------------------------------ #
#     #  Elias: target size check                                            #
#     # ------------------------------------------------------------------ #

#     async def _check_target_sizes(self, page, selectors: list) -> list:
#         """
#         For Elias (hand tremor): verify pause controls meet 44×44px minimum.
#         Returns list of controls that are too small.
#         """
#         issues = []
#         for selector in selectors:
#             try:
#                 el = page.locator(selector).first
#                 box = await el.bounding_box()
#                 if box and (box["width"] < MIN_TARGET_SIZE_PX or box["height"] < MIN_TARGET_SIZE_PX):
#                     issues.append({
#                         "selector":   selector,
#                         "width_px":   round(box["width"]),
#                         "height_px":  round(box["height"]),
#                         "required_px": MIN_TARGET_SIZE_PX,
#                         "issue":      f"Pause control is {round(box['width'])}×{round(box['height'])}px — below 44×44px minimum for tremor accessibility",
#                     })
#             except Exception:
#                 pass
#         return issues

#     # ------------------------------------------------------------------ #
#     #  WCAG 2.2.2 verdict                                                 #
#     # ------------------------------------------------------------------ #

#     @staticmethod
#     def _evaluate_wcag_222(total_motion: int, reduced_result: dict, pause_mechanism: dict) -> str:
#         """
#         WCAG 2.2.2 PASS conditions:
#           - No motion content at all → INAPPLICABLE
#           - Motion stops via prefers-reduced-motion → PASS
#           - Pause/stop/hide mechanism exists and is keyboard accessible → PASS
#         FAIL conditions:
#           - Motion present AND does not stop under reduced-motion
#             AND no pause mechanism (or mechanism is not keyboard accessible)
#         """
#         if total_motion == 0:
#             return "INAPPLICABLE"

#         motion_suppressed = reduced_result.get("all_stopped", False)
#         mechanism_ok = (
#             pause_mechanism["controls_found"]
#             and pause_mechanism["all_keyboard_accessible"]
#         )

#         if motion_suppressed or mechanism_ok:
#             return "PASS"

#         return "FAIL"


# # --------------------------------------------------------------------------- #
# #  Tests                                                                       #
# # --------------------------------------------------------------------------- #

# if __name__ == "__main__":
#     agent = AnimationDetectorAgent()

#     # --- Test 1: Infinite CSS animation with no pause control ---
#     print("=" * 60)
#     print("TEST 1: Infinite animation, no pause mechanism")
#     print("=" * 60)

#     html1 = """<!DOCTYPE html>
#     <html><head><style>
#         @keyframes spin { to { transform: rotate(360deg); } }
#         .spinner { animation: spin 1s infinite; width: 50px; height: 50px; }
#     </style></head>
#     <body><div class="spinner">Loading</div></body></html>"""

#     r1 = agent.execute(html1, persona="stefan")
#     print(f"Animations found:   {r1['css_animations_count'] if 'css_animations_count' in r1 else len(r1['css_animations'])}")
#     print(f"Reduced-motion all stopped: {r1['reduced_motion_result'].get('all_stopped')}")
#     print(f"Pause mechanism:    {r1['pause_mechanism']['controls_found']}")
#     print(f"WCAG 2.2.2 status:  {r1['wcag_222_status']}")
#     assert r1["wcag_222_status"] == "FAIL", "Should FAIL — animation runs forever with no pause control"
#     print("✓ PASS\n")

#     # --- Test 2: Animation with pause button ---
#     print("=" * 60)
#     print("TEST 2: Animation with keyboard-accessible pause button")
#     print("=" * 60)

#     html2 = """<!DOCTYPE html>
#     <html><head><style>
#         @keyframes blink { 50% { opacity: 0; } }
#         .ad { animation: blink 1s infinite; }
#     </style></head>
#     <body>
#         <div class="ad">SALE!</div>
#         <button id="pause-btn" aria-label="Pause animation"
#                 style="width:50px;height:50px">⏸</button>
#     </body></html>"""

#     r2 = agent.execute(html2, persona="stefan")
#     print(f"Pause mechanism found: {r2['pause_mechanism']['controls_found']}")
#     print(f"Keyboard accessible:   {r2['pause_mechanism']['all_keyboard_accessible']}")
#     print(f"WCAG 2.2.2 status:     {r2['wcag_222_status']}")
#     assert r2["wcag_222_status"] == "PASS", "Should PASS — pause button exists"
#     print("✓ PASS\n")

#     # --- Test 3: Static page — inapplicable ---
#     print("=" * 60)
#     print("TEST 3: No motion content → INAPPLICABLE")
#     print("=" * 60)

#     html3 = """<!DOCTYPE html>
#     <html><body><h1>Static Page</h1><p>No animations here.</p></body></html>"""

#     r3 = agent.execute(html3, persona="elias")
#     print(f"Total motion:       {r3['total_motion_count']}")
#     print(f"WCAG 2.2.2 status:  {r3['wcag_222_status']}")
#     assert r3["wcag_222_status"] == "INAPPLICABLE"
#     print("✓ PASS\n")

#     # --- Test 4: Elias — pause button too small ---
#     print("=" * 60)
#     print("TEST 4 (Elias): Animation with undersized pause control")
#     print("=" * 60)

#     html4 = """<!DOCTYPE html>
#     <html><head><style>
#         @keyframes shake { 50% { transform: translateX(5px); } }
#         .banner { animation: shake 0.5s infinite; }
#     </style></head>
#     <body>
#         <div class="banner">News ticker</div>
#         <button id="pause" aria-label="Pause animation"
#                 style="width:20px;height:20px;font-size:10px">⏸</button>
#     </body></html>"""

#     r4 = agent.execute(html4, persona="elias")
#     print(f"Pause control found:     {r4['pause_mechanism']['controls_found']}")
#     print(f"Target size issues:      {len(r4['target_size_issues'])}")
#     if r4["target_size_issues"]:
#         print(f"  → {r4['target_size_issues'][0]['issue']}")
#     print("✓ PASS\n")

#     print("=" * 60)
#     print("ALL TESTS PASSED ✓")
#     print("=" * 60)
