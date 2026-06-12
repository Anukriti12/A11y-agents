"""
Animation Detector Tool Agent
Detects motion content on a page and evaluates WCAG 2.2.2 compliance.

Used by: Stefan, Elias
- Elias-specific: also checks pause-control target size (hand tremor consideration).

WCAG 2.2.2 Pause, Stop, Hide (Level A) only applies to motion lasting more
than 5 seconds (or that repeats indefinitely). Short, finite animations are
exempt and should NOT be flagged.

A page passes 2.2.2 if any of these is true:
  - No applicable motion content exists (INAPPLICABLE)
  - All motion stops under prefers-reduced-motion: reduce
  - A keyboard-accessible pause/stop/hide control is present

Detection coverage:
  1. CSS @keyframe animations (duration > 5s OR infinite)
  2. CSS transitions on motion properties (transform, position, size)
  3. Autoplay <video> and <audio>
  4. Animated GIFs (via Netscape Application Block signature)
  5. JS animation library globals (GSAP, anime, Lottie, Rive, etc.)
  6. Whether animations stop under prefers-reduced-motion: reduce
  7. Whether a pause/stop/hide mechanism exists and is keyboard-accessible
  8. [Elias only] Whether pause controls meet 44x44px minimum

Does NOT use axe-core. Pure Playwright.
"""

import asyncio
import base64
from playwright.async_api import async_playwright


# WCAG 2.2.2: motion lasting <= 5 seconds is exempt unless it loops indefinitely
DURATION_THRESHOLD_SECONDS = 5.0

# WCAG 2.5.5 / practical Elias threshold: 44x44px minimum for pause controls
MIN_TARGET_SIZE_PX = 44

# Text/aria-label tokens that identify a pause/stop/hide control
PAUSE_CONTROL_LABELS = [
    "pause", "stop", "hide", "freeze", "disable animation",
    "reduce motion", "stop animation", "pause animation",
    "turn off animation",
]

# JS animation library globals to detect
JS_ANIMATION_GLOBALS = [
    "gsap", "TweenMax", "TweenLite", "anime", "velocity",
    "lottie", "rive", "mojs", "ScrollMagic",
]


class AnimationDetectorAgent:
    """
    Detects motion content on a page and returns a WCAG 2.2.2 verdict.
    """

    def execute(self, html: str, persona: str = "stefan") -> dict:
        """
        Args:
            html: A full URL (https://...) or raw HTML string.
            persona: "stefan" or "elias". Elias adds the target-size check.

        Returns a dict with the detection results and WCAG 2.2.2 status.
        """
        return asyncio.run(self._run(html, persona))

    # ------------------------------------------------------------------ #
    #  Main pipeline                                                       #
    # ------------------------------------------------------------------ #

    async def _run(self, url_or_html: str, persona: str) -> dict:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                # Pass 1: normal rendering
                ctx_normal = await browser.new_context()
                page_normal = await ctx_normal.new_page()
                await self._load(page_normal, url_or_html)

                css_animations  = await self._detect_css_animations(page_normal)
                css_transitions = await self._detect_css_transitions(page_normal)
                autoplay_media  = await self._detect_autoplay_media(page_normal)
                animated_gifs   = await self._detect_animated_gifs(page_normal)
                js_libs         = await self._detect_js_animation_libs(page_normal)

                await ctx_normal.close()

                # Pass 2: prefers-reduced-motion: reduce
                ctx_reduced = await browser.new_context(reduced_motion="reduce")
                page_reduced = await ctx_reduced.new_page()
                await self._load(page_reduced, url_or_html)

                reduced_motion_result = await self._check_reduced_motion(
                    page_reduced, css_animations
                )
                pause_mechanism = await self._check_pause_mechanism(page_reduced)

                # Elias: target-size check on any pause controls
                target_size_issues = []
                if persona == "elias" and pause_mechanism["controls_found"]:
                    target_size_issues = self._check_target_sizes(pause_mechanism["controls"])

                await ctx_reduced.close()

            finally:
                await browser.close()

        total_motion = (
            len(css_animations)
            + len(css_transitions)
            + len(autoplay_media)
            + len(animated_gifs)
            + len(js_libs)
        )

        wcag_status = self._evaluate_wcag_222(
            total_motion=total_motion,
            css_animation_count=len(css_animations),
            reduced_result=reduced_motion_result,
            pause_mechanism=pause_mechanism,
        )

        return {
            "persona": persona,
            "css_animations": css_animations,
            "css_animations_count": len(css_animations),
            "css_transitions": css_transitions,
            "css_transitions_count": len(css_transitions),
            "autoplay_media": autoplay_media,
            "autoplay_count": len(autoplay_media),
            "animated_gifs": animated_gifs,
            "animated_gifs_count": len(animated_gifs),
            "js_animation_libs": js_libs,
            "reduced_motion_result": reduced_motion_result,
            "pause_mechanism": pause_mechanism,
            "target_size_issues": target_size_issues,
            "total_motion_count": total_motion,
            "wcag_222_status": wcag_status,
            "tool_name": "AnimationDetectorAgent",
        }

    # ------------------------------------------------------------------ #
    #  Page loading                                                        #
    # ------------------------------------------------------------------ #

    async def _load(self, page, url_or_html: str) -> None:
        if url_or_html.strip().startswith("http"):
            await page.goto(url_or_html, wait_until="networkidle", timeout=30_000)
        else:
            encoded = base64.b64encode(url_or_html.encode()).decode()
            await page.goto(
                f"data:text/html;base64,{encoded}",
                wait_until="domcontentloaded",
                timeout=15_000,
            )
        # Let animations start
        await page.wait_for_timeout(800)

    # ------------------------------------------------------------------ #
    #  Detection: CSS animations                                           #
    # ------------------------------------------------------------------ #

    async def _detect_css_animations(self, page) -> list:
        """
        Find @keyframe animations. Filter out short, finite ones (not covered
        by 2.2.2). Keep infinite animations regardless of duration.
        """
        return await page.evaluate(
            """(threshold) => {
            const results = [];
            document.querySelectorAll('*').forEach((el, idx) => {
                const s = window.getComputedStyle(el);
                const name = s.animationName;
                if (!name || name === 'none') return;

                const durationStr = s.animationDuration || '0s';
                const count = s.animationIterationCount;
                const state = s.animationPlayState;
                const secs = parseFloat(durationStr) * (durationStr.endsWith('ms') ? 0.001 : 1);
                const isInfinite = count === 'infinite';

                if (!isInfinite && secs <= threshold) return;

                results.push({
                    element_index: idx,
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    class: el.className || '',
                    animation_name: name,
                    duration_sec: secs,
                    iteration: count,
                    play_state: state,
                    is_infinite: isInfinite,
                });
            });
            return results;
        }""",
            DURATION_THRESHOLD_SECONDS,
        )

    # ------------------------------------------------------------------ #
    #  Detection: CSS transitions                                          #
    # ------------------------------------------------------------------ #

    async def _detect_css_transitions(self, page) -> list:
        """
        Find CSS transitions on motion-related properties only. Color/opacity
        transitions are excluded since they aren't "motion" under 2.2.2.
        """
        motion_props = [
            "transform", "translate", "scale", "rotate",
            "top", "left", "right", "bottom",
            "width", "height", "margin", "padding",
        ]
        return await page.evaluate(
            """(motionProps) => {
            const results = [];
            document.querySelectorAll('*').forEach((el, idx) => {
                const s = window.getComputedStyle(el);
                const props = s.transitionProperty;
                const durStr = s.transitionDuration || '0s';
                if (!props || props === 'none') return;

                const propList = props.split(',').map(p => p.trim().toLowerCase());

                // Skip if it's just "all" without other signals — too broad to flag
                if (propList.length === 1 && propList[0] === 'all') return;

                const hasMotion = propList.some(p =>
                    motionProps.some(mp => p.includes(mp))
                );
                if (!hasMotion) return;

                const secs = parseFloat(durStr) * (durStr.endsWith('ms') ? 0.001 : 1);
                if (secs <= 0.1) return;

                results.push({
                    element_index: idx,
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    class: el.className || '',
                    transition_props: propList.filter(p =>
                        motionProps.some(mp => p.includes(mp))
                    ),
                    duration_sec: secs,
                });
            });
            return results;
        }""",
            motion_props,
        )

    # ------------------------------------------------------------------ #
    #  Detection: autoplay media                                           #
    # ------------------------------------------------------------------ #

    async def _detect_autoplay_media(self, page) -> list:
        return await page.evaluate("""() => {
            const results = [];
            ['video', 'audio'].forEach(tag => {
                document.querySelectorAll(tag).forEach(el => {
                    if (el.autoplay) {
                        results.push({
                            type: tag,
                            src: el.src || el.currentSrc || '',
                            has_controls: el.controls,
                            is_muted: el.muted,
                            is_looping: el.loop,
                            duration_sec: isNaN(el.duration) ? null : el.duration,
                        });
                    }
                });
            });
            return results;
        }""")

    # ------------------------------------------------------------------ #
    #  Detection: animated GIFs                                            #
    # ------------------------------------------------------------------ #

    async def _detect_animated_gifs(self, page) -> list:
        """
        Identify <img> elements pointing at .gif and probe each one for the
        Netscape Application Block signature, which only appears in multi-frame GIFs.

        Skip silently if a fetch fails (network restricted, CORS, etc).
        """
        gif_srcs = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('img'))
                .filter(img => {
                    const src = (img.src || '').toLowerCase();
                    return src.endsWith('.gif') || src.includes('.gif?') || src.startsWith('data:image/gif');
                })
                .map(img => ({
                    src: img.src,
                    alt: img.alt || '',
                    id: img.id || '',
                }))
        """)

        results = []
        for item in gif_srcs:
            try:
                src = item["src"]
                if src.startswith("data:"):
                    payload = src.split(",", 1)[1] if "," in src else ""
                    data = base64.b64decode(payload)
                else:
                    response = await page.request.get(src, timeout=5_000)
                    if response.status != 200:
                        continue
                    data = await response.body()

                if self._is_animated_gif(data):
                    results.append({
                        "src": src[:120],
                        "alt": item["alt"],
                        "id": item["id"],
                        "is_animated": True,
                    })
            except Exception:
                # Network failure or unreadable bytes. Skip this GIF; we can't
                # determine animation status without bytes.
                continue

        return results

    @staticmethod
    def _is_animated_gif(data: bytes) -> bool:
        """The Netscape Application Block appears once in animated GIFs."""
        if not data or len(data) < 6:
            return False
        if not data.startswith((b"GIF87a", b"GIF89a")):
            return False
        # Either the explicit NAB marker or multiple image-descriptor blocks
        if b"NETSCAPE2.0" in data:
            return True
        return data.count(b"\x2c") > 1

    # ------------------------------------------------------------------ #
    #  Detection: JS animation libraries                                   #
    # ------------------------------------------------------------------ #

    async def _detect_js_animation_libs(self, page) -> list:
        return await page.evaluate(
            "(libs) => libs.filter(name => typeof window[name] !== 'undefined')",
            JS_ANIMATION_GLOBALS,
        )

    # ------------------------------------------------------------------ #
    #  Reduced-motion verification                                         #
    # ------------------------------------------------------------------ #

    async def _check_reduced_motion(self, page, original_animations: list) -> dict:
        """
        Under prefers-reduced-motion: reduce, count which @keyframe animations
        are still running. A conforming page should pause them, set animation
        duration to 0, or remove the animation name.
        """
        if not original_animations:
            return {
                "media_query_active": True,
                "still_running": [],
                "still_running_count": 0,
                "stopped_count": 0,
                "all_stopped": True,
                "note": "No applicable animations to evaluate",
            }

        query_active = await page.evaluate(
            "() => matchMedia('(prefers-reduced-motion: reduce)').matches"
        )

        still_running = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('*').forEach((el, idx) => {
                const s = window.getComputedStyle(el);
                const name = s.animationName;
                const state = s.animationPlayState;
                const dur = parseFloat(s.animationDuration) || 0;

                if (!name || name === 'none') return;
                if (state === 'paused') return;
                if (dur === 0) return;

                results.push({
                    element_index: idx,
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    animation_name: name,
                    play_state: state,
                });
            });
            return results;
        }""")

        return {
            "media_query_active": query_active,
            "still_running": still_running,
            "still_running_count": len(still_running),
            "stopped_count": max(0, len(original_animations) - len(still_running)),
            "all_stopped": len(still_running) == 0,
        }

    # ------------------------------------------------------------------ #
    #  Pause/stop/hide mechanism check                                     #
    # ------------------------------------------------------------------ #

    async def _check_pause_mechanism(self, page) -> dict:
        """
        Look for a keyboard-accessible pause/stop/hide control. Match on
        text content, aria-label, or title containing recognized tokens.
        """
        controls = await page.evaluate(
            """(labels) => {
            const results = [];
            const candidates = document.querySelectorAll(
                'button, [role="button"], a[href], input[type="button"], input[type="submit"]'
            );
            candidates.forEach(el => {
                const text = (el.textContent || '').trim().toLowerCase();
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                const title = (el.getAttribute('title') || '').toLowerCase();
                const combined = text + ' ' + aria + ' ' + title;

                const match = labels.find(l => combined.includes(l));
                if (!match) return;

                const tabindex = el.getAttribute('tabindex');
                const focusable = tabindex === null || parseInt(tabindex) >= 0;
                const rect = el.getBoundingClientRect();

                results.push({
                    tag: el.tagName.toLowerCase(),
                    text: text.slice(0, 60),
                    aria_label: aria,
                    matched_on: match,
                    focusable: focusable,
                    width_px: Math.round(rect.width),
                    height_px: Math.round(rect.height),
                });
            });
            return results;
        }""",
            PAUSE_CONTROL_LABELS,
        )

        non_focusable = [c for c in controls if not c["focusable"]]

        return {
            "controls_found": len(controls) > 0,
            "control_count": len(controls),
            "controls": controls,
            "keyboard_inaccessible": non_focusable,
            "all_keyboard_accessible": len(non_focusable) == 0,
        }

    # ------------------------------------------------------------------ #
    #  Elias: target-size check                                            #
    # ------------------------------------------------------------------ #

    def _check_target_sizes(self, controls: list) -> list:
        """
        For Elias's hand tremor: any pause control below 44x44px is flagged.
        Uses the already-captured rect from _check_pause_mechanism.
        """
        issues = []
        for c in controls:
            w, h = c["width_px"], c["height_px"]
            if w < MIN_TARGET_SIZE_PX or h < MIN_TARGET_SIZE_PX:
                issues.append({
                    "matched_on": c["matched_on"],
                    "text": c["text"],
                    "width_px": w,
                    "height_px": h,
                    "required_px": MIN_TARGET_SIZE_PX,
                    "issue": (
                        f"Pause control is {w}x{h}px, below the "
                        f"{MIN_TARGET_SIZE_PX}x{MIN_TARGET_SIZE_PX}px "
                        f"minimum for tremor accessibility"
                    ),
                })
        return issues

    # ------------------------------------------------------------------ #
    #  WCAG 2.2.2 verdict                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _evaluate_wcag_222(
        total_motion: int,
        css_animation_count: int,
        reduced_result: dict,
        pause_mechanism: dict,
    ) -> str:
        """
        Verdict logic, in order of precedence:

          INAPPLICABLE: No applicable motion content found.

          PASS via pause mechanism: A keyboard-accessible pause/stop/hide
            control exists. This covers all motion types (CSS animations,
            transitions, autoplay media, GIFs, JS libraries).

          PASS via reduced-motion: All motion on the page is CSS @keyframe
            animations AND all of them stop under prefers-reduced-motion: reduce.
            This is the only case where the reduced-motion check is sufficient
            on its own, because we can only programmatically verify reduced-motion
            compliance for @keyframes (not transitions, video, GIFs, or JS).

          FAIL: Any other case where motion is present.
        """
        if total_motion == 0:
            return "INAPPLICABLE"

        pause_ok = (
            pause_mechanism["controls_found"]
            and pause_mechanism["all_keyboard_accessible"]
        )
        if pause_ok:
            return "PASS"

        only_keyframe_motion = (total_motion == css_animation_count)
        keyframes_all_stopped = reduced_result.get("all_stopped", False)
        if only_keyframe_motion and keyframes_all_stopped:
            return "PASS"

        return "FAIL"


# --------------------------------------------------------------------------- #
#  Tests                                                                       #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    agent = AnimationDetectorAgent()

    # --- Test 1: Infinite animation, no pause mechanism ---
    print("=" * 60)
    print("TEST 1: Infinite spinner, no pause control")
    print("=" * 60)
    html1 = """<!DOCTYPE html><html><head><style>
        @keyframes spin { to { transform: rotate(360deg); } }
        .spinner { animation: spin 1s infinite; width: 50px; height: 50px; }
    </style></head><body>
        <div class="spinner">Loading</div>
    </body></html>"""
    r1 = agent.execute(html1, persona="stefan")
    print(f"Animations found: {r1['css_animations_count']}")
    print(f"All stopped under reduced-motion: {r1['reduced_motion_result']['all_stopped']}")
    print(f"Pause mechanism present: {r1['pause_mechanism']['controls_found']}")
    print(f"WCAG 2.2.2 status: {r1['wcag_222_status']}")
    assert r1["wcag_222_status"] == "FAIL"
    print("PASS\n")

    # --- Test 2: Animation with pause button ---
    print("=" * 60)
    print("TEST 2: Animation with keyboard-accessible pause button")
    print("=" * 60)
    html2 = """<!DOCTYPE html><html><head><style>
        @keyframes blink { 50% { opacity: 0; } }
        .ad { animation: blink 1s infinite; }
    </style></head><body>
        <div class="ad">SALE!</div>
        <button aria-label="Pause animation"
                style="width:50px;height:50px">Pause</button>
    </body></html>"""
    r2 = agent.execute(html2, persona="stefan")
    print(f"Pause control found: {r2['pause_mechanism']['controls_found']}")
    print(f"Keyboard accessible: {r2['pause_mechanism']['all_keyboard_accessible']}")
    print(f"WCAG 2.2.2 status: {r2['wcag_222_status']}")
    assert r2["wcag_222_status"] == "PASS"
    print("PASS\n")

    # --- Test 3: Reduced-motion respected ---
    print("=" * 60)
    print("TEST 3: Animation suppressed under prefers-reduced-motion")
    print("=" * 60)
    html3 = """<!DOCTYPE html><html><head><style>
        @keyframes pulse { 50% { transform: scale(1.1); } }
        .ad { animation: pulse 1s infinite; }
        @media (prefers-reduced-motion: reduce) {
            .ad { animation: none; }
        }
    </style></head><body>
        <div class="ad">Newsletter signup</div>
    </body></html>"""
    r3 = agent.execute(html3, persona="stefan")
    print(f"Animations in normal context: {r3['css_animations_count']}")
    print(f"All stopped under reduced-motion: {r3['reduced_motion_result']['all_stopped']}")
    print(f"WCAG 2.2.2 status: {r3['wcag_222_status']}")
    assert r3["wcag_222_status"] == "PASS"
    print("PASS\n")

    # --- Test 4: Short finite animation is NOT applicable ---
    print("=" * 60)
    print("TEST 4: 2-second finite animation is exempt (<5s, finite)")
    print("=" * 60)
    html4 = """<!DOCTYPE html><html><head><style>
        @keyframes fadein { from { opacity: 0; } to { opacity: 1; } }
        .hero { animation: fadein 2s 1; }
    </style></head><body>
        <div class="hero">Welcome</div>
    </body></html>"""
    r4 = agent.execute(html4, persona="stefan")
    print(f"Applicable animations: {r4['css_animations_count']}")
    print(f"WCAG 2.2.2 status: {r4['wcag_222_status']}")
    assert r4["wcag_222_status"] == "INAPPLICABLE"
    print("PASS\n")

    # --- Test 5: Static page ---
    print("=" * 60)
    print("TEST 5: Static page, no motion")
    print("=" * 60)
    html5 = """<!DOCTYPE html><html><body>
        <h1>Static Page</h1>
        <p>Nothing moves here.</p>
    </body></html>"""
    r5 = agent.execute(html5, persona="elias")
    print(f"Total motion: {r5['total_motion_count']}")
    print(f"WCAG 2.2.2 status: {r5['wcag_222_status']}")
    assert r5["wcag_222_status"] == "INAPPLICABLE"
    print("PASS\n")

    # --- Test 6: Elias persona, pause button too small ---
    print("=" * 60)
    print("TEST 6: Elias persona, undersized pause control")
    print("=" * 60)
    html6 = """<!DOCTYPE html><html><head><style>
        @keyframes shake { 50% { transform: translateX(5px); } }
        .banner { animation: shake 0.5s infinite; }
    </style></head><body>
        <div class="banner">News ticker</div>
        <button aria-label="Pause animation"
                style="width:20px;height:20px;font-size:10px;padding:0">P</button>
    </body></html>"""
    r6 = agent.execute(html6, persona="elias")
    print(f"Pause control found: {r6['pause_mechanism']['controls_found']}")
    print(f"Target size issues: {len(r6['target_size_issues'])}")
    if r6["target_size_issues"]:
        print(f"  - {r6['target_size_issues'][0]['issue']}")
    print(f"WCAG 2.2.2 status (pause exists, page passes): {r6['wcag_222_status']}")
    # The pause button exists and is keyboard-accessible so 2.2.2 passes,
    # but Elias's target_size_issues list flags the usability problem separately.
    assert r6["wcag_222_status"] == "PASS"
    assert len(r6["target_size_issues"]) >= 1
    print("PASS\n")

    # --- Test 7: Autoplay video ---
    print("=" * 60)
    print("TEST 7: Autoplay video without pause control")
    print("=" * 60)
    html7 = """<!DOCTYPE html><html><body>
        <video autoplay loop muted>
            <source src="ad.mp4" type="video/mp4">
        </video>
    </body></html>"""
    r7 = agent.execute(html7, persona="stefan")
    print(f"Autoplay media: {r7['autoplay_count']}")
    print(f"Pause mechanism: {r7['pause_mechanism']['controls_found']}")
    print(f"WCAG 2.2.2 status: {r7['wcag_222_status']}")
    assert r7["autoplay_count"] == 1
    assert r7["wcag_222_status"] == "FAIL"
    print("PASS\n")

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
