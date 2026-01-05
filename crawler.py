import asyncio
from playwright.async_api import async_playwright
import re
from datetime import datetime, timedelta
import os
import candle_data

class SkyCrawler:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        self.playwright = await async_playwright().start()
        # Launch with arguments to hide automation and improve stability
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-infobars',
                '--window-position=0,0',
                '--ignore-certificate-errors',
                '--ignore-ssl-errors',
                '--disable-gpu',
                '--disable-dev-shm-usage'
            ]
        )
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1366, 'height': 768},
            locale='zh-TW',
            timezone_id='Asia/Taipei'
        )
        
        # Add stealth scripts
        await self.context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    async def stop(self):
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright'):
                await self.playwright.stop()
        except:
            pass

    async def _take_screenshot(self, page, name):
        try:
            path = os.path.join(os.getcwd(), f"debug_{name}.png")
            await page.screenshot(path=path)
            print(f"已儲存錯誤截圖至: {path}")
        except Exception as e:
            print(f"儲存截圖失敗: {e}")

    async def get_shards_info(self):
        page = None
        try:
            page = await self.context.new_page()
            await page.goto('https://sky-shards.pages.dev/zh-TW', wait_until='domcontentloaded')
            
            # 1. Check Date match
            # The site usually shows date in format "2024年1月4日" or similar in `div.shard-Date` or header
            # We will try to find a date string.
            
            # Wait for content
            try:
                await page.wait_for_selector('.shard-Countdown', timeout=5000)
            except:
                pass

            data = await page.evaluate('''() => {
                // Try precise selector first
                let dateEl = document.querySelector('.shard-Date');
                // If not found, try to find an element with date-like text
                if (!dateEl) {
                    const candidates = document.querySelectorAll('h1, h2, h3, div, span');
                    for (let el of candidates) {
                         // Look for roughly "202X年" or similar format
                         if (el.innerText.match(/\\d{4}年\\d{1,2}月\\d{1,2}日/)) {
                             dateEl = el;
                             break;
                         }
                    }
                }
                const dateText = dateEl ? dateEl.innerText : "";
                
                const typeEl = document.querySelector('.shard-Type');
                const type = typeEl ? typeEl.innerText : "無";

                const mapEl = document.querySelector('.shard-Map');
                const map = mapEl ? mapEl.innerText : "未知";
                
                // Get all timers
                const times = [];
                document.querySelectorAll('.shard-Countdown-columns .column').forEach(col => {
                    const start = col.querySelector('.start-time')?.innerText;
                    const end = col.querySelector('.end-time')?.innerText;
                    if (start && end) times.push(start + " - " + end);
                });

                const img = document.querySelector('img.map_clement');
                const imgUrl = img ? img.src : null;
                
                const statusText = document.querySelector('.shard-Countdown')?.innerText || "";
                
                const rewardsEl = document.querySelector('.shard-Rewards');
                const rewards = rewardsEl ? rewardsEl.innerText : "";
                
                // Capture full body text for fallback analysis
                const bodyText = document.body.innerText;
                
                return { dateText, type, map, times, imgUrl, rewards, statusText, bodyText };
            }''')
            
            print(f"[除錯] 原始碎石資料: {data}")
            
            if not data:
                print("[錯誤] 碎石資料為空")
                return None

            full_body = data.get('bodyText', '')
            
            # 優先檢查: 無碎石 / 無事件
            # 檢查全文內容中是否有各種「無碎石」的關鍵字
            if "No Shard" in full_body or "沒有碎石" in full_body or "沒有紅色碎石" in full_body or "今天沒有" in full_body:
                 # 再次確認是否為「昨天無碎石」等情況?
                 # 通常 "No Shard" 是主要狀態。
                 
                 # 我們仍應嘗試找到日期以確認是今天的資訊。
                 # 重用日期邏輯或直接從內文擷取
                 date_str = "未知日期"
                 now = datetime.now()
                 date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', full_body)
                 if date_match:
                    y, m, d = map(int, date_match.groups())
                    if datetime(y, m, d).date() == now.date():
                        date_str = f"{y}年{m}月{d}日"
                 
                 # 如果找到今天的日期 且 "No Shard"，則是確定的。
                 # 或者假設頁面是當前的。
                 return {
                    "type": "今天沒有碎石 (No Shard)",
                    "map": f"[{date_str}] 無",
                    "rewards": "無",
                    "time_range": "無",
                    "remaining": "",
                    "eruptions": [],
                    "image_url": None
                }
            
            # 1. Parse Raw Text for structured data (Fallback or Clean-up)
            # ... (Rest of logic)
            # keys: dateText, map, type, statusText
            full_text = f"{data.get('dateText', '')} {data.get('map', '')} {data.get('statusText', '')}"
            
            # A. Date Parsing
            now = datetime.now()
            scraped_date = None
            date_str = "未知日期"
            
            date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', full_text)
            if date_match:
                y, m, d = map(int, date_match.groups())
                scraped_date = datetime(y, m, d)
                date_str = f"{y}年{m}月{d}日"
            
            # B. Map Parsing
            # Pattern: "降落在 霞谷 的 圓夢村" or similar
            clean_map = "未知地點"
            map_match = re.search(r'降落在\s*(.+?)(\n|$|獎勵)', full_text)
            if map_match:
                clean_map = map_match.group(1).strip()
            # If standard structured data was good, usage it, but usually it's the blob
            if len(data.get('map', '')) < 20 and data.get('map', '') != "未知":
                clean_map = data.get('map') 

            # C. Type Parsing
            clean_type = "未知"
            if "紅色碎石" in full_text: clean_type = "紅石 (Red)"
            elif "黑色碎石" in full_text: clean_type = "黑石 (Black)"
            
            # D. Times Parsing
            # Pattern: 下午06:28:40 - 下午10:20:00
            # Be careful of multiline
            times_found = []
            
            # If the structured 'times' list is empty or suspicious, parse from text
            if not data.get('times'):
                # Regex for Chinese Time Range
                # matches "下午06:28:40 - 下午10:20:00"
                t_matches = re.findall(r'([上下]午\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*([上下]午\d{1,2}:\d{2}(?::\d{2})?)', full_text)
                for t1, t2 in t_matches:
                    times_found.append(f"{t1} - {t2}")
            else:
                times_found = data.get('times')

            # Helper to convert "下午06:28:40" to time obj
            def parse_ch_time(t_str):
                try:
                    # Remove seconds if present for cleaner compare? No, keep precision
                    # t_str like "下午06:28:40"
                    prefix = t_str[:2]
                    body = t_str[2:].strip()
                    parts = body.split(':')
                    h = int(parts[0])
                    m = int(parts[1])
                    s = int(parts[2]) if len(parts) > 2 else 0
                    
                    if prefix == "下午" and h < 12: h += 12
                    elif prefix == "上午" and h == 12: h = 0
                    
                    return datetime.now().replace(hour=h, minute=m, second=s, microsecond=0)
                except:
                    return None

            # E. Status Logic
            current_dt = datetime.now()
            
            # Handle Date Mismatch
            is_stale_data = False
            if scraped_date and scraped_date.date() != current_dt.date():
                is_stale_data = True
                clean_type += f" (非今日數據: {date_str})"
                # Don't show map if wrong day? Or show with warning.
                clean_map = f"[{date_str}] {clean_map}"

            # Calculate Event Status
            upcoming_range = "無"
            remaining = ""
            
            # Process Times
            valid_eruptions = []
            active_event = None
            future_event = None
            is_all_ended = False
            
            # Convert times to objects
            parsed_events = []
            for t_range in times_found:
                parts = t_range.split('-')
                if len(parts) == 2:
                    start_dt = parse_ch_time(parts[0].strip())
                    end_dt = parse_ch_time(parts[1].strip())
                    
                    if start_dt and end_dt:
                        # Handle day crossover? 
                        # Usually site lists times for "Today".
                        # If end < start, meaningful?
                        parsed_events.append((start_dt, end_dt, parts[0].strip(), parts[1].strip()))
                        valid_eruptions.append(f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}")

            # Sorting
            parsed_events.sort(key=lambda x: x[0])
            
            if parsed_events:
                # Check status
                # 1. Active?
                # 2. Upcoming?
                # 3. Ended?
                
                # Check if ALL ended
                last_end = parsed_events[-1][1]
                if current_dt > last_end:
                    is_all_ended = True
                
                if is_all_ended:
                    remaining = "今日所有爆發已結束"
                    upcoming_range = f"{parsed_events[-1][2]} - {parsed_events[-1][3]}" # Show last for reference
                elif is_stale_data:
                    remaining = "無效日期 (請等待網站更新)"
                    upcoming_range = "無"
                else:
                    # Find active or next
                    for s, e, s_raw, e_raw in parsed_events:
                        if s <= current_dt <= e:
                            # Active
                            diff = e - current_dt
                            remaining = f"進行中! 距離結束: {str(diff).split('.')[0]}"
                            upcoming_range = f"{s_raw} - {e_raw}"
                            active_event = True
                            break
                        elif current_dt < s:
                            # This is the next one
                            if not future_event:
                                diff = s - current_dt
                                remaining = f"距離開始: {str(diff).split('.')[0]}"
                                upcoming_range = f"{s_raw} - {e_raw}"
                                future_event = True
                                # Don't break, allow finding others? No, simple logic.
                                break
            else:
                 remaining = "無時間數據"

            # Site Explicit Ended Text override
            if "所有碎石爆發已在" in full_text and "前結束" in full_text:
                 remaining = "今日所有爆發已結束"
                 is_all_ended = True

            return {
                "type": clean_type,
                "map": clean_map,
                "rewards": data.get('rewards', ''),
                "time_range": upcoming_range,
                "remaining": remaining,
                "eruptions": valid_eruptions,
                "image_url": data.get('imgUrl')
            }

        except Exception as e:
            print(f"獲取碎石資訊錯誤: {e}")
            if page: await self._take_screenshot(page, "shards_fail")
            return None

    # get_shards_info is already defined above, so we don't need to redefine it here.
    # The previous edit inserted a stub which caused the error.
    # We will just continue to get_dailies_info.

    async def get_dailies_info(self):
        page = None
        try:
            page = await self.context.new_page()
            # Fandom: Use domcontentloaded
            await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["font", "media", "websocket"] else route.continue_())
            
            await page.goto("https://sky-children-of-the-light.fandom.com/wiki/Drafts/Dailies", wait_until="domcontentloaded", timeout=60000)
            
            # Wait for content
            try:
                await page.wait_for_selector('h2', timeout=20000)
            except:
                print("每日任務標題等待逾時")

            # Force Scroll
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)

            # Extract Realm and Rotation Keys
            result = await page.evaluate('''() => {
                const data = { treasure: { realm: "", rot: "", imgs: [] }, seasonal: { realm: "", rot: "", imgs: [] } };
                
                const processSection = (keywords, isSeasonal) => {
                    let header = null;
                    for (const key of keywords.ids) {
                         const el = document.getElementById(key) || document.querySelector(`span[id*="${key}"]`);
                         if (el) { header = el.closest('h2') || el.closest('h3'); break; }
                    }
                    if (!header) {
                        const allH = Array.from(document.querySelectorAll('h2, h3'));
                        header = allH.find(h => keywords.texts.some(t => h.innerText.includes(t)));
                    }

                    if (!header) return { realm: "NotFound", rot: "", imgs: [] };

                    let realm = "";
                    let rot = "";
                    let imgs = [];
                    
                    let curr = header.nextElementSibling;
                    let textBuffer = "";
                    let realmKeywords = [];
                    
                    // 1. Traverse to find text and initial images
                    // We need to look ahead a bit to capture Realm text before filtering images if they are mixed.
                    // Actually, let's grab all text/imgs first, then filter.
                    
                    while (curr && !['H1','H2'].includes(curr.tagName)) {
                        const text = curr.innerText.trim();
                        if (text.length > 2) textBuffer += text + " ";
                        
                        const foundImgs = curr.querySelectorAll('img');
                        foundImgs.forEach(img => {
                            if (img.width > 40 || img.classList.contains('thumbimage')) {
                                const src = img.getAttribute('data-src') || img.src;
                                if (src && !src.includes('data:image')) {
                                    // Clean URL: remove scaling to get full size
                                    // e.g. /revision/latest/scale-to-width-down/300?cb=... -> /revision/latest?cb=...
                                    let cleanSrc = src.replace(/\/scale-to-width-down\/\d+/, "");
                                    imgs.push(cleanSrc);
                                }
                            }
                        });
                        curr = curr.nextElementSibling;
                    }
                    
                    // 2. Parse Realm
                    if (textBuffer.includes("Daylight Prairie") || textBuffer.includes("雲野")) { realm = "Daylight Prairie"; realmKeywords = ['prairie', 'daylight']; }
                    else if (textBuffer.includes("Hidden Forest") || textBuffer.includes("雨林")) { realm = "Hidden Forest"; realmKeywords = ['forest', 'rain']; }
                    else if (textBuffer.includes("Valley") || textBuffer.includes("霞谷")) { realm = "Valley of Triumph"; realmKeywords = ['valley', 'triumph', 'citadel', 'ice']; }
                    else if (textBuffer.includes("Wasteland") || textBuffer.includes("暮土")) { realm = "Golden Wasteland"; realmKeywords = ['wasteland', 'golden', 'krill']; }
                    else if (textBuffer.includes("Vault") || textBuffer.includes("禁閣")) { realm = "Vault of Knowledge"; realmKeywords = ['vault', 'knowledge', 'starlight']; }
                    
                    // 3. Parse Rotation (Support double)
                    if (textBuffer.match(/Rotation\\s*2\\s*(and|&)\\s*3/i)) rot = "Rotation 2 and 3";
                    else if (textBuffer.match(/Rotation\\s*1\\s*(and|&)\\s*2/i)) rot = "Rotation 1 and 2";
                    else if (textBuffer.includes("Rotation 1")) rot = "Rotation 1";
                    else if (textBuffer.includes("Rotation 2")) rot = "Rotation 2";
                    else if (textBuffer.includes("Rotation 3")) rot = "Rotation 3";
                    
                    // 4. Filter Images (Crucial for Seasonal)
                    // If we found a realm, only keep images that look like they belong to it?
                    // Or if it's Seasonal, we assume Fandom might show a gallery of ALL maps.
                    // We check if the image src contains realm keywords.
                    if (isSeasonal && realmKeywords.length > 0 && imgs.length > 2) {
                         const filtered = imgs.filter(src => realmKeywords.some(k => src.toLowerCase().includes(k)));
                         if (filtered.length > 0) imgs = filtered;
                    }

                    return { realm, rot, imgs };
                };
                
                data.treasure = processSection({ids: ['Treasure_Candles', 'Treasure_Candle'], texts: ['Treasure Candles', '大蠟燭']}, false);
                data.seasonal = processSection({ids: ['Seasonal_Candles', 'Seasonal_Candle'], texts: ['Seasonal Candles', '季節蠟燭']}, true);
                
                return data;
            }''')

            await page.close()
            
            # Map to Local DB
            t_info = result['treasure']
            s_info = result['seasonal']
            
            t_descs = candle_data.get_treasure_desc(t_info['realm'], t_info['rot'])
            s_descs = candle_data.get_seasonal_desc(s_info['realm']) # Seasonal mainly depends on Realm
            
            # Combine
            # If we extracted 4 images and have 4 descs, perfect.
            # If not matching, we just list them.
            
            return {
                "treasure": {
                    "realm": t_info['realm'],
                    "rotation": t_info['rot'],
                    "descriptions": t_descs,
                    "images": t_info['imgs']
                },
                "seasonal": {
                    "realm": s_info['realm'],
                    "rotation": s_info['rot'], # Not always used but good to have
                    "descriptions": s_descs,
                    "images": s_info['imgs']
                }
            }

        except Exception as e:
            print(f"獲取每日任務錯誤: {e}")
            if page: await self._take_screenshot(page, "dailies_fail")
            if page: await page.close()
            return None

    async def get_clock_info(self):
        try:
            import clock_pred
            # Run in executor if heavy? No, it's fast math.
            events = clock_pred.get_event_times()
            return events
        except Exception as e:
            print(f"計算時鐘錯誤: {e}")
            return None

if __name__ == "__main__":
    async def main():
        c = SkyCrawler()
        await c.start()
        print("Test Shards:", await c.get_shards_info())
        print("Test Dailies:", await c.get_dailies_info())
        print("Test Clock:", await c.get_clock_info())
        await c.stop()
    asyncio.run(main())
