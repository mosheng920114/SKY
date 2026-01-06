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
            
            # 1. Parse Raw Text for structured data (Fallback or Clean-up)
            # ... (Rest of logic)
            # keys: dateText, map, type, statusText
            full_text = f"{data.get('dateText', '')} {data.get('map', '')} {data.get('statusText', '')}"
            
            # A. Date Parsing
            # ... (Existing Date Parsing Logic) ...
            
            # [LOGIC UPDATE] Return structured data for forecast check
            # We need to return enough info to determine if there is a shard.
            # "No Shard" logic handled earlier returns specific dict.
            
            # ... (Rest of existing parsing logic) ...
            
            # Return result
            return {
                "type": clean_type,
                "map": clean_map,
                "rewards": data.get('rewards', ''),
                "time_range": upcoming_range,
                "remaining": remaining,
                "eruptions": valid_eruptions,
                "image_url": data.get('imgUrl'),
                "is_no_shard": False # Marker
            }

        except Exception as e:
            print(f"獲取碎石資訊錯誤: {e}")
            return None

    async def get_shards_prediction(self):
        """
        獲取碎石預報：如果今天沒有，則尋找下一場。
        """
        # 1. Try today
        today = datetime.now()
        today_info = await self.get_shards_info_by_date(today)
        
        if not today_info:
            return None
            
        if not today_info.get('is_no_shard', False):
            # Today has shard
            return today_info
            
        # 2. If no shard today, look ahead (max 7 days)
        print("今天無碎石，正在查詢預報...")
        for i in range(1, 8):
            next_date = today + timedelta(days=i)
            # URL Format: https://sky-shards.pages.dev/zh-TW/2026/01/05
            print(f"查詢日期: {next_date.strftime('%Y-%m-%d')}")
            info = await self.get_shards_info_by_date(next_date)
            
            if info and not info.get('is_no_shard', False):
                # Found next shard
                # Update status to indicate it's a forecast
                date_str = next_date.strftime('%Y年%m月%d日')
                info['type'] = f"{info['type']} (預報: {date_str})"
                info['remaining'] = f"下一場: {date_str}"
                return info
                
        # If nothing found in 7 days (unlikely)
        return today_info

    async def get_shards_info_by_date(self, target_date=None):
        """
        Helper to get shard info for a specific date (or today/default).
        """
        page = None
        try:
            url = 'https://sky-shards.pages.dev/zh-TW'
            if target_date:
                # Format: /YYYY/MM/DD, e.g. /2026/01/05
                url = f"https://sky-shards.pages.dev/zh-TW/{target_date.year}/{target_date.month:02d}/{target_date.day:02d}"
                
            page = await self.context.new_page()
            await page.goto(url, wait_until='domcontentloaded')
            
            try:
                await page.wait_for_selector('.shard-Countdown', timeout=3000)
            except:
                pass

            data = await page.evaluate('''() => {
                let dateEl = document.querySelector('.shard-Date');
                if (!dateEl) {
                     const candidates = document.querySelectorAll('h1, h2, div');
                     for (let el of candidates) {
                         if (el.innerText.match(/\\d{4}年\\d{1,2}月\\d{1,2}日/)) {
                             dateEl = el; break;
                         }
                     }
                }
                const dateText = dateEl ? dateEl.innerText : "";
                
                const typeEl = document.querySelector('.shard-Type');
                const type = typeEl ? typeEl.innerText : "無";

                const mapEl = document.querySelector('.shard-Map');
                const map = mapEl ? mapEl.innerText : "未知";
                
                const times = [];
                document.querySelectorAll('.shard-Countdown-columns .column').forEach(col => {
                    const start = col.querySelector('.start-time')?.innerText;
                    const end = col.querySelector('.end-time')?.innerText;
                    if (start && end) times.push(start + " - " + end);
                });

                // Prioritize 'img.map_clement' BUT verify src
                let img = null;
                
                // 1. Precise Search: src contains "map_varient" (Best for location map)
                img = document.querySelector('img[src*="map_varient"]');
                
                if (!img) {
                     // 2. Memory Search: src contains "memory"
                     img = document.querySelector('img[src*="memory"]');
                }
                
                if (!img) {
                    img = document.querySelector('img.map_clement');
                }
                
                if (!img) {
                    // Fallback: Search by Header Text specifically for "Map" or "Location"
                    const headers = Array.from(document.querySelectorAll('h1, h2, h3, div'));
                    // Target specific headers seen in screenshot: "克萊門特的地圖", "SHATTERING SHARD LOCATION"
                    const targetHeader = headers.find(h => 
                        h.innerText.includes('克萊門特的地圖') || 
                        h.innerText.includes('SHATTERING SHARD LOCATION')
                    );
                    
                    if (targetHeader) {
                        const card = targetHeader.closest('.column') || targetHeader.closest('.card') || targetHeader.parentElement;
                        if (card) img = card.querySelector('img');
                    }

                    // Fallback 3: Search for "Clement's Map" (English)
                    if (!img) {
                        const headers = Array.from(document.querySelectorAll('h1, h2, h3, div'));
                        const mapHeader = headers.find(h => h.innerText.includes("Clement's Map"));
                        if (mapHeader) {
                            const card = mapHeader.closest('.column') || mapHeader.parentElement;
                            if (card) img = card.querySelector('img');
                        }
                    }
                }
                
                let imgUrl = img ? img.getAttribute('src') : null;
                // Handle relative URL
                if (imgUrl && imgUrl.startsWith('/')) {
                    imgUrl = "https://sky-shards.pages.dev" + imgUrl;
                }
                
                const statusText = document.querySelector('.shard-Countdown')?.innerText || "";
                const rewardsEl = document.querySelector('.shard-Rewards');
                const rewards = rewardsEl ? rewardsEl.innerText : "";
                
                const bodyText = document.body.innerText;
                
                return { dateText, type, map, times, imgUrl, rewards, statusText, bodyText };
            }''')

            if not data: return None
            
            full_body = data.get('bodyText', '')
            
            # No Shard Check
            if "No Shard" in full_body or "沒有碎石" in full_body or "沒有紅色碎石" in full_body or "今天沒有" in full_body:
                 return {
                    "type": "無碎石 (No Shard)",
                    "map": "無",
                    "rewards": "無",
                    "time_range": "無",
                    "remaining": "",
                    "eruptions": [],
                    "image_url": None,
                    "is_no_shard": True 
                }

        
            # Parse Logic
            raw_date = data.get('dateText', '')
            clean_date = raw_date.split('\n')[0] # Default fallback
            date_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', raw_date)
            if date_match:
                clean_date = date_match.group(1)
                # Check for Weekday
                week_match = re.search(r'(星期[日一二三四五六])', raw_date)
                if week_match: clean_date += " " + week_match.group(1)

            full_text = f"{data.get('dateText', '')} {data.get('map', '')} {data.get('statusText', '')}"
            
            # Parsing
            clean_map = "未知地點"
            map_match = re.search(r'降落在\s*(.+?)(\n|$|獎勵)', full_text)
            if map_match: clean_map = map_match.group(1).strip()
            elif len(data.get('map', '')) < 20 and data.get('map', '') != "未知": clean_map = data.get('map')

            clean_type = "未知"
            if "紅色碎石" in full_text: clean_type = "紅石 (Red)"
            elif "黑色碎石" in full_text: clean_type = "黑石 (Black)"
            
            # Rewards Parsing (Robust)
            rewards = data.get('rewards', '')
            if not rewards or len(rewards) < 2:
                # Fallback: search in full text
                # Pattern: "獎勵可達 3.5 支昇華蠟燭" or similar
                r_match = re.search(r'(獎勵.+?)(\n|$)', full_text)
                if r_match:
                    rewards = r_match.group(1).strip()
            
            # Times
            times_found = data.get('times', [])
            if not times_found:
                t_matches = re.findall(r'([上下]午\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*([上下]午\d{1,2}:\d{2}(?::\d{2})?)', full_text)
                for t1, t2 in t_matches: times_found.append(f"{t1} - {t2}")

            # Calculate Status
            current_dt = datetime.now()
            
            def parse_ch_time(t_str):
                try:
                    prefix = t_str[:2]
                    body = t_str[2:].strip()
                    parts = body.split(':')
                    h = int(parts[0])
                    m = int(parts[1])
                    s = int(parts[2]) if len(parts) > 2 else 0
                    if prefix == "下午" and h < 12: h += 12
                    elif prefix == "上午" and h == 12: h = 0
                    return current_dt.replace(hour=h, minute=m, second=s, microsecond=0)
                except:
                    return None

            parsed_events = []
            valid_eruptions = []
            for t_range in times_found:
                parts = t_range.split('-')
                if len(parts) == 2:
                    raw_s, raw_e = parts[0].strip(), parts[1].strip()
                    start_dt = parse_ch_time(raw_s)
                    end_dt = parse_ch_time(raw_e)
                    if start_dt and end_dt:
                        parsed_events.append((start_dt, end_dt, raw_s, raw_e))
                        valid_eruptions.append(f"{raw_s} - {raw_e}")
            
            parsed_events.sort(key=lambda x: x[0])
            
            upcoming_range = "無"
            remaining = ""
            active_event = False
            future_event = False
            
            if parsed_events:
                # Logic: Find first Active OR first Future
                for s, e, s_raw, e_raw in parsed_events:
                    if s <= current_dt <= e:
                        # Active
                        diff = e - current_dt
                        total_seconds = int(diff.total_seconds())
                        h = total_seconds // 3600
                        m = (total_seconds % 3600) // 60
                        s_sec = total_seconds % 60
                        remaining = f"進行中! 距離結束: {h}小時 {m}分 {s_sec}秒"
                        upcoming_range = f"{s_raw} - {e_raw}"
                        active_event = True
                        break
                    elif current_dt < s:
                        # Future
                        if not future_event:
                            diff = s - current_dt
                            total_seconds = int(diff.total_seconds())
                            h = total_seconds // 3600
                            m = (total_seconds % 3600) // 60
                            s_sec = total_seconds % 60
                            remaining = f"距離開始: {h}小時 {m}分 {s_sec}秒"
                            upcoming_range = f"{s_raw} - {e_raw}"
                            future_event = True
                            break
                
                # If neither active nor future found, and we have events, assume ended
                if not active_event and not future_event:
                    remaining = "今日所有爆發已結束"
                    upcoming_range = f"{parsed_events[-1][2]} - {parsed_events[-1][3]}"
            else:
                 if not valid_eruptions:
                     remaining = "無時間數據"

            # Date Correction Logic
            try:
                # If site shows Yesterday (Sky Time) but data is for Today/Tomorrow (Local/User expectation),
                # and we have valid shard data, override the date text.
                now = datetime.now()
                today_str_short = f"{now.month}月{now.day}日"
                yesterday = now - timedelta(days=1)
                yesterday_str_short = f"{yesterday.month}月{yesterday.day}日"

                if (yesterday_str_short in clean_date) and (not is_no_shard):
                     # print(f"DEBUG: Detect Shard Date Lag. Site: {clean_date}, Local: {today_str_short}. Auto-correcting.")
                     weekdays_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
                     new_wd = weekdays_map[now.weekday()]
                     clean_date = f"{now.year}年{today_str_short} {new_wd}"
            except Exception as e:
                pass

            return {
                "type": clean_type,
                "map": clean_map,
                "dateText": clean_date,
                "rewards": rewards,
                "time_range": upcoming_range,
                "remaining": remaining,
                "eruptions": valid_eruptions,
                "image_url": data.get('imgUrl'),
                "is_no_shard": False
            }

        except Exception as e:
            print(f"Error fetching shard date {target_date}: {e}")
            return None
        finally:
            if page: await page.close()

    # Alias for compatibility if needed, but we should switch to get_shards_prediction in GUI
    async def get_shards_info(self):
        return await self.get_shards_prediction()

    async def get_daily_quests(self):
        page = None
        try:
            page = await self.context.new_page()
            # 1. Access 9-bit SkyGold
            await page.goto("https://9-bit.jp/skygold/", wait_until="domcontentloaded")
            
            # 2. Find "Today's Daily Quest" Link
            # Selector: Look for link with text "今日のデイリークエスト"
            # It's usually in a widget or list.
            quest_url = await page.evaluate('''() => {
                const links = Array.from(document.querySelectorAll('a'));
                const target = links.find(a => a.innerText.includes('今日のデイリークエスト'));
                return target ? target.href : null;
            }''')
            
            if not quest_url:
                # Fallback: try direct link structure if possible, but dynamic ID is better
                print("未找到每日任務連結")
                return []
                
            print(f"Found Quest URL: {quest_url}")
            await page.goto(quest_url, wait_until="domcontentloaded")
            
            # Parse Content (Clean Start)
            content_text = await page.evaluate("document.body.innerText")
            lines = content_text.split('\n')
            extracted_quests = []
            extracted_quests = []
            
            # State Machine
            collecting = False
            
            # Regex for date header: "今日（1月5日～1月6日）のデイリークエスト" or "2026年1月5日...クエスト"
            # And also generic "今日のデイリークエスト" if date is missing
            header_pattern = re.compile(r'(今日.*デイリークエスト|デイリークエスト.*1月|デイリークエスト.*2月|デイリークエスト.*3月|デイリークエスト.*4月|デイリークエスト.*5月|デイリークエスト.*6月|デイリークエスト.*7月|デイリークエスト.*8月|デイリークエスト.*9月|デイリークエスト.*10月|デイリークエスト.*11月|デイリークエスト.*12月)') 

            for line in lines:
                line = line.strip()
                if not line: continue
                
                # Check for Header
                if header_pattern.search(line):
                    print(f"DEBUG: Found Quest Header: {line}")
                    collecting = True
                    extracted_quests = [] # Reset if we find a newer/better header (unlikely but safe)
                    continue 
                
                if collecting:
                    # Stop if we hit typical next section headers
                    if "キャンドル" in line or "闇の破片" in line or "専用通貨" in line or "イベント" in line or "更新" in line:
                        # But wait, quests might contain "Candle". The section header usually is specific.
                        if "今日の" in line or "更新履歴" in line:
                           collecting = False
                           break
                    
                    # Garbage filter
                    if any(x in line for x in ['攻略', '掲示板', '目次', 'トップ', '詳細', '▲']):
                        continue
                        
                    # Valid Quest Candidate (Length > 5)
                    if len(line) > 5:
                         extracted_quests.append(line)
                         if len(extracted_quests) >= 4:
                             break
            
            # Fallback if strict header failed 
            if len(extracted_quests) < 4:
                 print("DEBUG: Strict extraction failed, checking fallback candidates")
                 candidates = extracted_quests # Keep what we found
            else:
                 candidates = extracted_quests
            
            # Debug: Find Dates
            # date_matches = re.findall(r'(\d{1,2}月\d{1,2}日)', content_text)
            # print(f"DEBUG: Dates found in page: {date_matches}")

            extracted_quests = candidates[:4] if len(candidates) >= 4 else candidates 
            # print(f"DEBUG: All Candidates: {candidates}")
            # print(f"DEBUG: Selected: {extracted_quests}")
            
            # Translate to TC
            translated_quests = [self.translate_quest(q) for q in extracted_quests]
            
            return translated_quests 



        except Exception as e:
            print(f"獲取每日任務錯誤: {e}")
            return []
        finally:
            if page: await page.close()

    def translate_quest(self, text):
        """
        Translates Japanese Sky quests to Traditional Chinese.
        """
        # [Merged] Map Locations & Terms (Sorted by length to avoid partial replace)
        terms = {
            # Locations
            '孤島': '晨島', '草原': '雲野', '雨林': '雨林', '峡谷': '霞谷', 
            '捨てられた地': '暮土', '書庫': '禁閣',

            # Meta
            'クエスト': '任務', 'デイリー': '每日', 
            
            # Spirits (Examples - need to be generic or extensive)
            '採集者': '收集者', '光採取者': '光芒收集者', '採取者': '收集者',
            '日光浴者': '日光浴者', 
            '笑う': '偷笑', 'ダブルタッチ': '擊掌', 'くつろぐ': '放鬆',
            
            # Common Terms
            '精霊': '先祖', 'フレンド': '好友', 'プレイヤー': '玩家',
            'キャンドル': '蠟燭', '星のキャンドル': '昇華蠟燭',
            'シーズンキャンドル': '季節蠟燭',
            '赤色の光': '紅光', '青色の光': '藍光', '水色の光': '青光', '緑色の光': '綠光', '紫色の光': '紫光', '橙色の光': '橙光',
            '光の探求者': '光之探求者',

            'ハイタッチ': '擊掌', 'ハグ': '擁抱', 'おんぶ': '背背', 'チャット': '聊天',
            'ジェスチャー': '動作', '使用する': '使用',
            
            # Specific Translation Updates
            '雨林で光をつかまえる': '抓住雨林之光',
            '光のキノコにエナジーを回復してもらう': '透過光菇重新恢復能量',
            '雨林の雨が途切れる地で瞑想する': '在樹林高處冥想',
            '雨が途切れる地': '樹林高處',
            '大樹の案内人の食卓を整える': '整理大樹嚮導(歸屬季)的長桌',
            '雨林の高台広場にある想いを編む先祖の食卓を片付ける': '在雨林的樹林高處整理歸屬季的先祖圓桌',
            '高台広場': '樹林高處', 'にある': '在',
            '想いを編む': '歸屬季的', '先祖の食卓': '先祖圓桌', 'を片付ける': '整理',
            '食卓': '長桌/餐桌', '整える': '整理/打掃', 
            'テーブル': '長桌',
            
            # Valley Quests (Valley of Triumph) - User Match
            # Specific Full Sentence Matches (User Standard)
            # Valley (User Verified)
            '峡谷を訪れしばしの間若木を愛でる': '欣賞一下霞谷小樹苗',
            '峡谷で光をつかまえる': '抓住霞谷之光',
            '峡谷で精霊の記憶を呼び起こす': '重溫一位霞谷先靈的記憶',
            
            # Wasteland
            '捨てられた地を訪れしばしの間若木を愛でる': '欣賞一下暮土小樹苗',
            '捨てられた地で光をつかまえる': '抓住暮土之光',
            '捨てられた地で精霊の記憶を呼び起こす': '重溫一位暮土先靈的記憶',
            '墓場で精霊の記憶を呼び起こす': '重溫一位暮土先靈的記憶',
            
            # Forest
            '雨林を訪れしばしの間若木を愛でる': '欣賞一下雨林小樹苗',
            '雨林で光をつかまえる': '抓住雨林之光',
            '雨林で精霊の記憶を呼び起こす': '重溫一位雨林先靈的記憶',
            
            # Prairie
            '草原を訪れしばしの間若木を愛でる': '欣賞一下雲野小樹苗',
            '草原で光をつかまえる': '抓住雲野之光',
            '草原で精霊の記憶を呼び起こす': '重溫一位雲野先靈的記憶',
            
            # Vault
            '書庫を訪れしばしの間若木を愛でる': '欣賞一下禁閣小樹苗',
            '書庫で光をつかまえる': '抓住禁閣之光',
            '書庫で精霊の記憶を呼び起こす': '重溫一位禁閣先靈的記憶',

            '精霊の記憶を呼び起こす': '重溫一位先靈的記憶', # Generic Fallback
            '20本のキャンドルに火を灯す': '點亮 20 根蠟燭', 
            'キャンドルに火を灯す': '點亮蠟燭',
            '20本': '20根', 
            '本': '根',
            
            # General patterns
            'エナジー': '能量', '回復する': '恢復', '回復': '恢復',
            'してもらう': '', 'をつかまえる': '抓住',
            '神殿': '神廟', '広場': '廣場', '参道': '參道',
            '小川': '小溪', 'ツリーハウス': '樹屋', 
            'する': '', # Remove generic "do" verb suffix
            
            # Quest Types - Precise Mapping
            '記憶を呼び起こすクエスト': '重溫先祖美好回憶', 
            '記憶を呼び起こす': '重溫先祖美好回憶',
            '追体験': '重溫先祖美好回憶',
            
            '光をつかまえる': '抓住之光', 
            '雨林の光': '雨林之光',
            'の光をつかまえる': '之光',
            
            '集める': '收集30滴燭火',
            '灯りを': '點燃', '灯す': '點燃', 
            '瞑想': '冥想', 
            'スケーター': '滑冰者', 

            
            # Spirits (Raw Debug Matches)
            '笑う光採取者': '偷笑光芒收集者', 
            'ダブルタッチの光採取者': '擊掌光芒收集者', 
            'くつろぐ日光浴者': '放鬆日浴者',
            '光採取者': '光芒收集者',
            
            '若木': '花樹/幼苗', '愛でる': '賞花(在旁待60秒)',
            '虹': '彩虹', '眺める': '觀賞',
            'カニ': '螃蟹', '倒す': '掀翻5隻', '気絶': '掀翻',
            '暗黒竜': '冥龍', '対峙': '面對', 
            'マンタ': '遙鯤', '蝕む闇': '黑暗植物', '溶かす': '燒掉10株',
            '光を捕まえる': '捕捉光芒',
            'メッセージ': '留言', 'キャンドルボート': '紙船/蠟燭',
            'ギフト': '禮物', '送る': '送出心火',
            '鳥': '鳥',
            '手をつなぐ': '牽手', 'グループ': '隊伍',
            '精霊にかえる': '回歸天際 (向嚮導/先祖回報)',
            '会う': '拜訪/見面', '訪れる': '找到', # Updated from visit to find for bonfire match
            '座る': '坐下', 'ベンチ': '長椅', '交流': '交流',
            'の': '的', 'で': '在', 'と': '和',
            
            # New Mappings for 2026-01-06
            '闇の蟹を持ち上げる': '抱起一隻暗蟹',
            '墓所': '墓園',
            '焚火': '篝火',
            '闇の蟹': '暗蟹',
            '持ち上げる': '抱起',
            
            # Grammar Fixes
            'を訪れる': '找到',
            'にある': '位於',
            'を': '' # Remove particle
        }
        
        # Apply Logic
        # Specific overrides first
        if "30個" in text and "集める" in text:
            return "收集 30 滴燭火"
            
        # Sort terms by length (descending) to avoid partial replacements (e.g., '光' replacing inside '日光浴者')
        sorted_terms = sorted(terms.items(), key=lambda x: len(x[0]), reverse=True)
        
        for jp, tc in sorted_terms:
            text = text.replace(jp, tc)
            
        # Cleanup
        text = text.replace('在在', '在').replace('的在', '在').replace('任務任務', '任務')
        text = text.replace('重溫美好回憶先祖', '重溫先祖美好回憶').replace('重溫先祖美好回憶任務', '重溫先祖美好回憶')
        
        return text

    async def get_dailies_info(self):
        page = None
        try:
            print("Fetching Candles from 9-bit (Primary)...")
            page = await self.context.new_page()
            await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["font", "media", "websocket"] else route.continue_())
            
            # 1. Access 9-bit Homepage
            await page.goto("https://9-bit.jp/skygold/", wait_until="domcontentloaded", timeout=60000)
            
            # 2. Find Link to Today's Post (Same logic as get_daily_quests)
            quest_url = await page.evaluate('''() => {
                const links = Array.from(document.querySelectorAll('a'));
                const target = links.find(a => a.innerText.includes('今日のデイリークエスト'));
                return target ? target.href : null;
            }''')
            
            if quest_url:
                print(f"DEBUG: Found Daily Post URL for Candles: {quest_url}")
                await page.goto(quest_url, wait_until="domcontentloaded")
            else:
                print("DEBUG: Could not find Daily Post text link, staying on Homepage (might be inaccurate).")

            # 3. Extract Data from Current Page (Daily Post or Homepage)
            nine_bit_data = await page.evaluate('''() => {
                const results = { treasure_img: null, treasure_realm: null, seasonal_img: null, seasonal_realm: null };
                
                // Treasure
                const tHeaders = Array.from(document.querySelectorAll('h2, h3, h4')); 
                const tHeader = tHeaders.find(h => h.innerText.includes('今日の日替わり大キャンドル'));
                if (tHeader) {
                    // Try to map text "暮土" etc
                    const text = tHeader.innerText;
                    if (text.includes("草原")) results.treasure_realm = "Daylight Prairie";
                    else if (text.includes("雨林")) results.treasure_realm = "Hidden Forest";
                    else if (text.includes("峡谷")) results.treasure_realm = "Valley of Triumph";
                    else if (text.includes("暮土") || text.includes("捨てられた地") || text.includes("墓場")) results.treasure_realm = "Golden Wasteland";
                    else if (text.includes("書庫")) results.treasure_realm = "Vault of Knowledge";
                    
                    // If Header text doesn't have realm, check IMMEDIATE next sibling only if it's text
                    if (!results.treasure_realm) {
                         const next = tHeader.nextElementSibling;
                         if (next && next.tagName === 'P') {
                             const pText = next.innerText;
                             if (pText.includes("草原")) results.treasure_realm = "Daylight Prairie";
                             else if (pText.includes("雨林")) results.treasure_realm = "Hidden Forest";
                             else if (pText.includes("峡谷")) results.treasure_realm = "Valley of Triumph";
                             else if (pText.includes("暮土") || pText.includes("捨てられた地")) results.treasure_realm = "Golden Wasteland";
                             else if (pText.includes("書庫")) results.treasure_realm = "Vault of Knowledge";
                         }
                    }
                    
                    let curr = tHeader.nextElementSibling;
                    let range = 0;
                    while(curr && range < 5) {
                        const img = curr.querySelector('img') || (curr.tagName === 'IMG' ? curr : null);
                        if (img) { results.treasure_img = img.src; break; }
                        curr = curr.nextElementSibling;
                        range++;
                    }
                }
                
                // Seasonal
                const sHeader = tHeaders.find(h => h.innerText.includes('今日のシーズンキャンドル'));
                if (sHeader) {
                     const text = sHeader.innerText;
                     if (text.includes("草原")) results.seasonal_realm = "Daylight Prairie";
                     else if (text.includes("雨林")) results.seasonal_realm = "Hidden Forest";
                     else if (text.includes("峡谷")) results.seasonal_realm = "Valley of Triumph";
                     else if (text.includes("暮土") || text.includes("捨てられた地") || text.includes("墓場")) results.seasonal_realm = "Golden Wasteland";
                     else if (text.includes("書庫")) results.seasonal_realm = "Vault of Knowledge";

                    let curr = sHeader.nextElementSibling;
                    let range = 0;
                    while(curr && range < 5) {
                        const img = curr.querySelector('img') || (curr.tagName === 'IMG' ? curr : null);
                        if (img) { results.seasonal_img = img.src; break; }
                        curr = curr.nextElementSibling;
                        range++;
                    }
                }
                return results;
            }''')
            
            await page.close()

            # Process Treasure
            t_realm = nine_bit_data.get('treasure_realm', 'NotFound')
            t_imgs = [nine_bit_data['treasure_img']] if nine_bit_data.get('treasure_img') else []
            t_rot = "Rotation 1" 
            
            # SUNDAY CHECK: Force Double Candles (Rotation 1 and 2) if Sunday
            now = datetime.now()
            if now.weekday() == 6: # 0=Mon, 6=Sun
                t_rot = "Rotation 1 and 2"
                print(f"DEBUG: Sunday detected, forcing Double Treasure Candles ({t_realm})")

            # Process Seasonal
            s_realm = nine_bit_data.get('seasonal_realm', '')
            s_imgs = [nine_bit_data['seasonal_img']] if nine_bit_data.get('seasonal_img') else []
            s_rot = "Rotation 1"

            # Fallback for Treasure Realm (Date-based Text) if 9-bit text extraction failed
            if t_realm == "NotFound" or not t_realm:
                 try:
                    realms = ['Daylight Prairie', 'Hidden Forest', 'Valley of Triumph', 'Golden Wasteland', 'Vault of Knowledge']
                    anchor = datetime(2026, 1, 5)
                    diff = (now.date() - anchor.date()).days
                    idx = (diff + 3) % 5
                    t_realm = realms[idx]
                    # If fallback runs and it's Sunday, t_rot is already set to "Rotation 1 and 2" above
                    print(f"DEBUG: Calculated Treasure Realm Fallback: {t_realm}")
                 except Exception as e:
                    print(f"Fallback Calc Error: {e}")

            t_descs = candle_data.get_treasure_desc(t_realm, t_rot)
            s_descs = candle_data.get_seasonal_desc(s_realm) 

            return {
                "treasure": {
                    "realm": t_realm,
                    "rotation": t_rot,
                    "descriptions": t_descs,
                    "images": t_imgs
                },
                "seasonal": {
                    "realm": s_realm,
                    "rotation": s_rot,
                    "descriptions": s_descs,
                    "images": s_imgs
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

    async def get_all_daily_info_optimized(self):
        """
        Consolidated scraper to fetch BOTH Quests and Candles in one navigation.
        Avoids resource contention and ensures correct page context.
        """
        page = None
        quests = []
        candles = {
            "treasure": {"realm": "NotFound", "rotation": "Rotation 1", "images": [], "descriptions": []},
            "seasonal": {"realm": "", "rotation": "Rotation 1", "images": [], "descriptions": []}
        }
        
        try:
            print("Fetching All Daily Info (Optimized)...")
            page = await self.context.new_page()
            
            # 1. Homepage -> Find Link
            await page.goto("https://9-bit.jp/skygold/", wait_until="domcontentloaded", timeout=60000)
            target_url = await page.evaluate('''() => {
                const links = Array.from(document.querySelectorAll('a'));
                const target = links.find(a => a.innerText.includes('今日のデイリークエスト'));
                return target ? target.href : null;
            }''')
            
            if target_url:
                print(f"DEBUG: Found Daily Post URL: {target_url}")
                await page.goto(target_url, wait_until="domcontentloaded")
            else:
                print("DEBUG: Stayed on Homepage (Link not found)")

            # 2. Scrape Quests (DOM - Table Aware)
            quest_data_dom = await page.evaluate('''() => {
                const results = [];
                const headers = Array.from(document.querySelectorAll('h2, h3, h4'));
                
                // 1. Try to find the specific "Quest LIST" header first (H3: デイリークエスト一覧)
                // This is more specific than the main H2 date header and avoids the metadata table.
                let qHeader = headers.find(h => h.innerText.includes('デイリークエスト一覧'));
                
                // Fallback to main header if List header not found
                if (!qHeader) {
                    qHeader = headers.find(h => 
                        h.innerText.includes('今日') && 
                        h.innerText.includes('デイリークエスト') && 
                        !h.innerText.includes('目次')
                    );
                }
                
                if (!qHeader) return { quests: [], date_str: null };
                
                // Helper to process text
                const isValidQuest = (txt) => {
                    const t = txt.trim();
                    if (t.length < 5) return false;
                    if (['方法','報酬','確認','精錬','デイリークエスト','一覧'].some(k => t.includes(k))) return false;
                    if (t.includes('開始時間') || t.includes('終了時間') || t.includes('対象エリア')) return false; 
                    if (t.includes('時') && t.includes('分')) return false; // Time filter (Japanese time chars)
                    if (t.match(/\d{1,2}月\d{1,2}日/)) return false; 
                    return true;
                }

                let curr = qHeader.nextElementSibling;
                while (curr && results.length < 4) {
                    // Stop conditions
                    if (['H2'].includes(curr.tagName) && !curr.innerText.includes('一覧')) break; 
                    
                    // 1. Check TABLE
                    if (curr.tagName === 'TABLE') {
                        // CRITICAL: Check if this is the Metadata Table
                        const tableText = curr.innerText;
                        if (tableText.includes('開始時間') || tableText.includes('終了時間') || tableText.includes('対象エリア')) {
                            // SKIP this entire table
                            curr = curr.nextElementSibling;
                            continue;
                        }

                        const cells = curr.querySelectorAll('td, th');
                        for (const cell of cells) {
                            const lines = cell.innerText.split('\\n');
                            for (const line of lines) {
                                if (isValidQuest(line) && !results.includes(line)) {
                                    results.push(line);
                                    if (results.length >= 4) break;
                                }
                            }
                            if (results.length >= 4) break;
                        }
                    }
                    
                    // 2. Check LI/STRONG (Legacy/Mobile view)
                    if (['UL','OL','P','DIV'].includes(curr.tagName) || curr.tagName === 'STRONG') {
                        const candidates = [];
                        if (curr.tagName === 'STRONG') candidates.push(curr);
                        candidates.push(...curr.querySelectorAll('strong'));
                        candidates.push(...curr.querySelectorAll('li'));
                        
                        for (const el of candidates) {
                            const txt = el.innerText.trim();
                            // If LI starts with date/time, skip it
                            if (txt.includes('時') && txt.includes('分')) continue;
                            
                            if (isValidQuest(txt) && !results.includes(txt)) {
                                results.push(txt);
                                if (results.length >= 4) break;
                            }
                        }
                    }

                    curr = curr.nextElementSibling;
                }
                
                // Date finding fallback (if we used List header, we might miss the date header)
                // We try to grab the Date header text separately if needed
                let dateStr = qHeader.innerText;
                if (!dateStr.includes('月')) {
                     // Try to find the Date H2
                     const dateH2 = headers.find(h => h.innerText.includes('今日') && h.innerText.includes('デイリークエスト'));
                     if (dateH2) dateStr = dateH2.innerText;
                }
                
                return { quests: results, date_str: dateStr };
            }''')
            
            raw_quests = quest_data_dom.get('quests', [])
            date_str = quest_data_dom.get('date_str', '')
            
            print(f"DEBUG: Raw Quests from 9-bit: {raw_quests}")
            
            # Parse Site Date
            site_date_obj = None
            if date_str:
                date_match = re.search(r'(\d+)月(\d+)日', date_str)
                if date_match:
                    try:
                        m = int(date_match.group(1))
                        d = int(date_match.group(2))
                        # Assume 2025 unless we are in Dec and site is Jan
                        year = 2026
                        site_date_obj = datetime(year, m, d)
                        print(f"DEBUG: Parsed Date from Site Header: {site_date_obj.date()} (Weekday: {site_date_obj.weekday()})")
                    except: pass
            
            # Translate Quests
            quests = [self.translate_quest(q) for q in raw_quests]
            print(f"DEBUG: Translated Quests: {quests}")

            # 3. Scrape Candles from Fandom Wiki (User Request)
            print("Navigating to Fandom Wiki for Candles...")
            try:
                await page.goto("https://sky-children-of-the-light.fandom.com/wiki/Treasure_Candles", wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_selector('#mw-content-text', timeout=10000)
                
                fandom_data = await page.evaluate('''() => {
                    const results = { 
                        realm: null, 
                        rotation_str: null,
                        images: [],
                        seasonal_realm: null // Fandom might not show seasonal easily on this page, strictly Treasure
                    };
                    
                    const content = document.querySelector('#mw-content-text');
                    if (!content) return results;

                    // 1. Find "Today's ... Rotation" Text
                    // Look for specific elements usually holding the update text
                    // Avoid 'div' to prevent matching the whole page container
                    const ps = Array.from(content.querySelectorAll('p, b, center, span, font'));
                    
                    // Filter: Must contain keywords and be reasonably short (not a whole section)
                    const rotInfo = ps.find(el => 
                        el.innerText.includes("Today's") && 
                        el.innerText.includes("Treasure Candle rotation") &&
                        el.innerText.length < 500
                    );
                    
                    if (rotInfo) {
                        let text = rotInfo.innerText;
                        
                        // Fix: If text is truncated or split (e.g. inside <b>), it might miss the Realm/Rotation
                        // Check parent if "Golden" or "Rotation" is missing
                        if (!text.includes("Rotation") || (!text.includes("Golden") && !text.includes("Prairie") && !text.includes("Forest") && !text.includes("Valley") && !text.includes("Vault"))) {
                            if (rotInfo.parentElement) {
                                text = rotInfo.parentElement.innerText;
                            }
                        }
                        
                        results.rotation_str = text; 
                        
                        // Parse Realm (Order shouldn't matter if text is short, but specific order helps)
                        if (text.includes("Golden Wasteland")) results.realm = "Golden Wasteland";
                        else if (text.includes("Daylight Prairie")) results.realm = "Daylight Prairie";
                        else if (text.includes("Hidden Forest")) results.realm = "Hidden Forest";
                        else if (text.includes("Valley of Triumph")) results.realm = "Valley of Triumph";
                        else if (text.includes("Vault of Knowledge")) results.realm = "Vault of Knowledge";
                    }
                    
                    // 2. Extract Images based on Realm and Rotation
                    if (results.realm) {
                        const headers = Array.from(document.querySelectorAll('h2, h3'));
                        const realmHeader = headers.find(h => h.innerText.toUpperCase().includes(results.realm.toUpperCase()));
                        
                        if (realmHeader) {
                            // Determine which Rotations to grab
                            const rotsToGrab = [];
                            
                            // Regex to detect "Rotation 1", "and 1", "& 1" etc.
                            // Case insensitive, flexible whitespace
                            // Use results.rotation_str as text is out of scope
                            const rText = results.rotation_str;
                            const has1 = rText.match(/Rotation\s*1|and\s*1|&\s*1|,\s*1/i);
                            const has2 = rText.match(/Rotation\s*2|and\s*2|&\s*2|,\s*2/i);
                            const has3 = rText.match(/Rotation\s*3|and\s*3|&\s*3|,\s*3/i);

                            if (has1) rotsToGrab.push("ROTATION 1");
                            if (has2) rotsToGrab.push("ROTATION 2");
                            if (has3) rotsToGrab.push("ROTATION 3");
                            
                            // Iterate siblings to find Rotation Headers
                            let curr = realmHeader.nextElementSibling;
                            while(curr) {
                                if (['H1','H2'].includes(curr.tagName)) break; // Stop at next Realm
                                
                                if (curr.tagName === 'H3') {
                                    const hText = curr.innerText.toUpperCase();
                                    // Check if this H3 is one of our targets (e.g. "ROTATION 1")
                                    const isTarget = rotsToGrab.some(r => hText.includes(r));
                                    
                                    if (isTarget) {
                                        // Grab images from the FOLLOWING container (usually DIV)
                                        let container = curr.nextElementSibling;
                                        if (container && container.tagName === 'DIV') {
                                            const imgs = container.querySelectorAll('img');
                                            imgs.forEach(img => {
                                                // Fandom Lazy Loading: data-src usually holds the real URL
                                                let src = img.getAttribute('data-src') || img.src;
                                                if (src) {
                                                    // Fandom specific cleanup: Remove /scale-to-width-down/... params to get full size?
                                                    // Actually raw src is usually fine, but let's clean it just in case
                                                    // example: .../image.jpg/revision/latest/scale-to-width-down/233?cb=...
                                                    // leaving it as is usually works for download, but keeping "revision/latest" is safer.
                                                    results.images.push(src);
                                                }
                                            });
                                        }
                                    }
                                }
                                curr = curr.nextElementSibling;
                            }
                        }
                    }
                    
                    return results;
                }''')
                
                # Process Fandom Data
                t_realm = fandom_data.get('realm', 'Golden Wasteland') # Fallback if parse fails
                f_rot_str = fandom_data.get('rotation_str', '')
                raw_imgs = fandom_data.get('images', [])
                
                # Download Images Locally
                import os
                import requests
                
                if not os.path.exists("images"):
                    os.makedirs("images")
                    
                local_imgs = []
                for i, url in enumerate(raw_imgs):
                    try:
                        ext = "jpg"
                        if ".png" in url: ext = "png"
                        filename = f"images/treasure_{i+1}.{ext}"
                        
                        # Simple download
                        # HEADERS are important for Wiki to accept the request
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        r = requests.get(url, headers=headers, timeout=10)
                        if r.status_code == 200:
                            with open(filename, "wb") as f:
                                f.write(r.content)
                            local_imgs.append(filename)
                            print(f"Downloaded: {filename}")
                        else:
                            print(f"Failed to download image: {url} (Status: {r.status_code})")
                    except Exception as e:
                        print(f"Image Download Error: {e}")
                
                t_imgs = local_imgs
                
                # Determine Rotation Key
                t_rot = "Rotation 1"   
                # Robust check for "1 and 2" using Regex on Python side too
                # import re (ALREADY IMPORTED GLOBALLY - REMOVING TO FIX ERROR)
                lower_rot = f_rot_str.lower()
                has_1 = re.search(r'rotation\s*1|and\s*1|&\s*1|,\s*1', lower_rot)
                has_2 = re.search(r'rotation\s*2|and\s*2|&\s*2|,\s*2', lower_rot)
                has_3 = re.search(r'rotation\s*3|and\s*3|&\s*3|,\s*3', lower_rot)
                
                if has_1 and has_2: t_rot = "Rotation 1 and 2"
                elif has_1: t_rot = "Rotation 1"
                elif has_2: t_rot = "Rotation 2" # Unlikely solo
                elif has_3: t_rot = "Rotation 3"
                
                print(f"DEBUG: Fandom Data - Realm: {t_realm}, Imgs: {len(t_imgs)}, Rot: {t_rot}")

            except Exception as e:
                print(f"Fandom Scraping Error: {e}")
                t_realm = "Golden Wasteland" # Fallback
                t_rot = "Rotation 1 and 2" if datetime.now().weekday() == 6 else "Rotation 1" 
                t_imgs = []

            await page.close()
            
            # Update Candles Dictionary
            candles['treasure']['realm'] = t_realm
            candles['treasure']['rotation'] = t_rot
            candles['treasure']['images'] = t_imgs
            candles['treasure']['descriptions'] = candle_data.get_treasure_desc(t_realm, t_rot)
            
            # Seasonal - use simple fallback or 9-bit scraping if we wanted (skipped for now to prioritize Treasure)
            # Actually, `get_daily_quests` logic for seasonal realm was sufficient? 
            # Let's just use a calculated fallback for Seasonal if we skip 9-bit candle scrape.
            # Or assume Seasonal is same as yesterday? 
            # Implement simple seasonal calculation or leave blank for user to report.
            # For now, let's look at the implementation plan -> "Seasonal" was not the main complaint.
            # We can re-use the specific seasonal scraper if needed, but let's stick to Treasure Focus.
            s_realm = "Hidden Forest" # Placeholder or calc
            try:
                # Simple rotation for Seasonal
                s_realms = ['Daylight Prairie', 'Hidden Forest', 'Valley of Triumph', 'Golden Wasteland', 'Vault of Knowledge']
                # Anchor: 2024-01-01 (Monday) -> Prairie
                # 2025-01-05 (Sunday) -> ?
                # Daily rotation cycle.
                day_of_year = datetime.now().timetuple().tm_yday
                # This is tricky without anchor.
                # Let's just default to None and let user check text.
                pass
            except: pass

            candles['seasonal']['realm'] = "Unknown" 
            candles['seasonal']['images'] = []
            
        except Exception as e:
             print(f"Combined Scraper Error: {e}")
             if page: await self._take_screenshot(page, "combined_error")
             if page: await page.close()
        
        return quests, candles

if __name__ == "__main__":
    async def main():
        c = SkyCrawler()
        await c.start()
        print("Test Shards:", await c.get_shards_info())
        print("Test Dailies:", await c.get_dailies_info())
        print("Test Clock:", await c.get_clock_info())
        await c.stop()
    asyncio.run(main())
