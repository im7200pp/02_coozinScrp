import asyncio
import os
import re
from datetime import datetime
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
            
            # Dismiss popup if it exists
            popup_dismiss = page.locator("text=하루간 보지 않기")
            if await popup_dismiss.is_visible():
                await log_progress("Popup detected. Dismissing popup...")
                await popup_dismiss.click()
                await page.wait_for_timeout(1000)
                
            # Get list of products with their detail links
            await log_progress("Extracting tracked product links...")
            products = await page.evaluate("""() => {
                const results = [];
                const cardElements = Array.from(document.querySelectorAll('*')).filter(el => {
                    return el.innerText && el.innerText.includes('(ID ') && el.innerText.includes('판매가');
                });
                
                const leafCards = [];
                cardElements.forEach(el => {
                    const children = Array.from(el.querySelectorAll('*')).filter(c => c.innerText && c.innerText.includes('(ID ') && c.innerText.includes('판매가'));
                    if (children.length === 0 && !el.innerText.includes("예시상품")) {
                        leafCards.push(el);
                    }
                });
                
                leafCards.forEach(el => {
                    // Extract mall name
                    const mallEl = el.querySelector('.mr-1.whitespace-nowrap.text-sm.font-bold.text-dark-black');
                    const mallName = mallEl ? mallEl.innerText.trim() : "";
                    
                    // Extract product name
                    const nameEl = el.querySelector('.overflow-hidden.text-ellipsis.whitespace-nowrap.text-sm.text-dark-black');
                    const productName = nameEl ? nameEl.innerText.trim() : "";
                    
                    // Extract product ID
                    const idMatch = el.innerText.match(/\\(ID\\s*(\\d+)\\)/);
                    const productId = idMatch ? idMatch[1] : "";
                    
                    // Extract detail link
                    const linkEl = el.closest('a') || el.querySelector('a');
                    const detailHref = linkEl ? linkEl.getAttribute('href') : "";
                    
                    if (detailHref) {
                        results.push({
                            mallName: mallName,
                            productName: productName,
                            productId: productId,
                            detailUrl: detailHref.startsWith('http') ? detailHref : 'https://itemscout.io' + detailHref
                        });
                    }
                });
                return results;
            }""")
            
            await log_progress(f"Found {len(products)} products to scrape detail pages for.")
            
            # Scrape each product detail page
            for idx, prod in enumerate(products):
                await log_progress(f"Scraping product {idx+1}/{len(products)}: {prod['productName']}")
                try:
                    await page.goto(prod['detailUrl'])
                    await page.wait_for_timeout(6000) # Wait for table to load
                    
                    # Parse daily ranking table from detail page
                    table_data = await page.evaluate("""() => {
                        const headerTable = document.querySelector('table[class*="header-table"]');
                        const bodyTable = document.querySelector('table[class*="body-table"]');
                        if (!headerTable || !bodyTable) return null;
                        
                        const ths = Array.from(headerTable.querySelectorAll('th'));
                        const headers = ths.map(th => th.innerText.trim()).filter(txt => txt !== "");
                        
                        const trs = Array.from(bodyTable.querySelectorAll('tr'));
                        const rows = [];
                        
                        trs.forEach(tr => {
                            const tds = Array.from(tr.querySelectorAll('td'));
                            if (tds.length === 0) return;
                            
                            // Col 0: Keyword and Volume
                            const col0 = tds[0];
                            const keywordSpan = col0.querySelector('.font-medium') || col0.querySelector('span');
                            let keyword = keywordSpan ? keywordSpan.innerText.trim() : col0.innerText.trim();
                            
                            const volumeSpan = col0.querySelector('.text-base-40') || col0.querySelector('.text-xs');
                            let volume = volumeSpan ? volumeSpan.innerText.trim() : "";
                            
                            if (volume && keyword.endsWith(volume)) {
                                keyword = keyword.substring(0, keyword.length - volume.length).trim();
                            }
                            
                            if (!keyword) return;
                            
                            const ranks = [];
                            for (let j = 1; j < Math.min(tds.length, headers.length + 1); j++) {
                                const col = tds[j];
                                
                                // Rank
                                const rankSpan = col.querySelector('.font-bold');
                                let rank = rankSpan ? rankSpan.innerText.trim() : col.innerText.trim().split('-')[0].trim();
                                
                                // Page Info
                                const pageSpan = col.querySelector('.text-base-40');
                                let pageInfo = pageSpan ? pageSpan.innerText.trim() : "";
                                if (pageInfo.startsWith('-')) {
                                    pageInfo = pageInfo.substring(1).trim();
                                }
                                
                                // Change Direction & Value
                                let changeDir = "none";
                                let changeVal = "0";
                                
                                const errorSpan = col.querySelector('.text-error');
                                const blueSpan = col.querySelector('.text-blue');
                                
                                if (errorSpan) {
                                    changeDir = "down";
                                    const valSpan = col.querySelector('.font-normal');
                                    changeVal = valSpan ? valSpan.innerText.replace(/[^0-9]/g, '').trim() : "0";
                                } else if (blueSpan) {
                                    changeDir = "up";
                                    const valSpan = col.querySelector('.font-normal');
                                    changeVal = valSpan ? valSpan.innerText.replace(/[^0-9]/g, '').trim() : "0";
                                }
                                
                                ranks.push({
                                    rank: rank || "-",
                                    pageInfo: pageInfo || "-",
                                    changeDir: changeDir,
                                    changeVal: changeVal || "0"
                                });
                            }
                            
                            rows.push({
                                keyword: keyword,
                                volume: volume,
                                ranks: ranks
                            });
                        });
                        
                        return { headers: headers, rows: rows };
                    }""")
                    
                    if table_data and table_data['headers'] and table_data['rows']:
                        headers = table_data['headers']
                        for row in table_data['rows']:
                            for col_idx, rank_info in enumerate(row['ranks']):
                                if col_idx >= len(headers):
                                    break
                                raw_header = headers[col_idx]
                                clean_header = raw_header.replace('\uf1fc', '').replace('', '').strip()
                                
                                # Resolve date
                                resolved_date = None
                                match = re.search(r'(\d{2})\.(\d{2})', clean_header)
                                if match:
                                    month = int(match.group(1))
                                    day = int(match.group(2))
                                    now = datetime.now()
                                    year = now.year
                                    if now.month == 1 and month == 12:
                                        year -= 1
                                    elif now.month == 12 and month == 1:
                                        year += 1
                                    resolved_date = f"{year:04d}-{month:02d}-{day:02d}"
                                else:
                                    resolved_date = datetime.now().strftime("%Y-%m-%d")
                                    
                                results.append({
                                    "date": resolved_date,
                                    "mall_name": prod['mallName'],
                                    "product_name": prod['productName'],
                                    "product_id": prod['productId'],
                                    "keyword": row['keyword'],
                                    "search_volume": row['volume'],
                                    "rank": rank_info['rank'],
                                    "page_info": rank_info['pageInfo'],
                                    "change_direction": rank_info['changeDir'],
                                    "change_value": rank_info['changeVal']
                                })
                        await log_progress(f"Successfully scraped rankings for {len(table_data['rows'])} keywords from detail page.")
                    else:
                        await log_progress(f"No rank table data found on detail page for {prod['productName']}.")
                except Exception as detail_err:
                    await log_progress(f"Error scraping detail page for {prod['productName']}: {detail_err}")
            
            await log_progress(f"Successfully scraped total of {len(results)} daily rank records.")
            
        except Exception as e:
            await log_progress(f"Error during scraping: {e}")
            raise e
        finally:
            await log_progress("Closing browser...")
            await browser.close()
            
    return results
