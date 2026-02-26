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
