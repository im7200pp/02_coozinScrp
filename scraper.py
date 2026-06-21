import asyncio
import os
import re
from playwright.async_api import async_playwright

async def scrape_itemscout_rankings(username, password, progress_callback=None):
    """
    Logs in to itemscout.io, navigates to the Daily Ranking Tracker,
    and returns a list of dictionaries with daily keywords and rankings.
    """
    if not username or not password:
        raise ValueError("ITEMSCOUT_USERNAME or ITEMSCOUT_PASSWORD is not set in the environment.")
        
    async def log_progress(msg):
        print(f"[Scraper] {msg}")
        if progress_callback:
            await progress_callback(msg)

    results = []
    
    async with async_playwright() as p:
        # Launch browser in headless mode
        await log_progress("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            # 1. Navigate to main page to dismiss popup
            await log_progress("Navigating to https://itemscout.io/...")
            await page.goto("https://itemscout.io/")
            await page.wait_for_timeout(3000)
            
            # Dismiss popup if it exists
            popup_dismiss = page.locator("text=하루간 보지 않기")
            if await popup_dismiss.is_visible():
                await log_progress("Popup detected. Dismissing popup...")
                await popup_dismiss.click()
                await page.wait_for_timeout(1000)
                
            # 2. Go to sign-in page
            await log_progress("Navigating to login page...")
            await page.goto("https://itemscout.io/signin")
            await page.wait_for_selector("input[name='email']", timeout=5000)
            
            # Fill credentials
            await page.locator("input[name='email']").fill(username)
            await page.locator("input[name='password']").fill(password)
            
            # Click Email Login button
            await log_progress("Submitting email login credentials...")
            await page.locator("button:has-text('이메일 로그인')").click()
            await page.wait_for_timeout(4000)
            
            # 3. Navigate to the Daily Tracker page
            await log_progress("Navigating to Daily Ranking Tracker...")
            await page.goto("https://itemscout.io/tracking/daily")
            await page.wait_for_timeout(5000)
            
            # Parse product card details
            await log_progress("Parsing keyword rankings from daily tracker...")
            data = await page.evaluate("""() => {
                const results = [];
                const elements = Array.from(document.querySelectorAll('*'));
                
                elements.forEach(el => {
                    // Leaf card detection
                    if (el.innerText && el.innerText.includes('(ID ') && el.innerText.includes('판매가')) {
                        const childrenWithId = Array.from(el.querySelectorAll('*')).filter(child => child.innerText && child.innerText.includes('(ID ') && child.innerText.includes('판매가'));
                        if (childrenWithId.length === 0) {
                            
                            // Skip sample products
                            if (el.innerText.includes("예시상품")) {
                                return;
                            }
                            
                            // Extract mall name
                            const mallEl = el.querySelector('.mr-1.whitespace-nowrap.text-sm.font-bold.text-dark-black');
                            const mallName = mallEl ? mallEl.innerText.trim() : "";
                            
                            // Extract product name
                            const nameEl = el.querySelector('.overflow-hidden.text-ellipsis.whitespace-nowrap.text-sm.text-dark-black');
                            const productName = nameEl ? nameEl.innerText.trim() : "";
                            
                            // Extract product ID
                            const idMatch = el.innerText.match(/\\(ID\\s*(\\d+)\\)/);
                            const productId = idMatch ? idMatch[1] : "";
                            
                            // Parse keywords and rankings
                            const keywords = [];
                            const allElems = Array.from(el.querySelectorAll('*'));
                            let startParsing = false;
                            
                            for (let i = 0; i < allElems.length; i++) {
                                const subEl = allElems[i];
                                if (subEl.innerText && subEl.innerText.trim() === '변동') {
                                    startParsing = true;
                                    continue;
                                }
                                
                                if (startParsing) {
                                    if (subEl.tagName === 'SPAN' && subEl.classList.contains('font-bold')) {
                                        const keywordName = subEl.innerText.trim();
                                        
                                        // Search for its rank in next elements
                                        let rank = "-";
                                        for (let j = i + 1; j < Math.min(i + 5, allElems.length); j++) {
                                            const nextEl = allElems[j];
                                            const nextText = nextEl.innerText.trim();
                                            if (!nextText) continue;
                                            
                                            if (nextEl.tagName === 'SPAN' && nextEl.classList.contains('font-bold')) {
                                                break;
                                            }
                                            if (nextText.endsWith('위') || nextText === 'OUT' || nextText === '-') {
                                                rank = nextText;
                                                break;
                                            }
                                        }
                                        keywords.push({ keyword: keywordName, rank: rank });
                                    }
                                }
                            }
                            
                            results.push({
                                mallName: mallName,
                                productName: productName,
                                productId: productId,
                                keywords: keywords
                            });
                        }
                    }
                });
                return results;
            }""")
            
            # Re-format raw data to flat rows
            for item in data:
                for kw in item['keywords']:
                    results.append({
                        "mall_name": item['mallName'],
                        "product_name": item['productName'],
                        "product_id": item['productId'],
                        "keyword": kw['keyword'],
                        "rank": kw['rank']
                    })
            
            await log_progress(f"Successfully scraped {len(results)} keyword ranking entries.")
                    
        except Exception as e:
            await log_progress(f"Error during scraping: {e}")
            raise e
        finally:
            await log_progress("Closing browser...")
            await browser.close()
            
    return results
