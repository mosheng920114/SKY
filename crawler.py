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
            '会う': '拜訪/見面',
            '座る': '坐下', 'ベンチ': '長椅', '交流': '交流',
            'の': '的', 'で': '在', 'と': '和'
        }
        
        # Apply Logic
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
            
            await page.goto("https://9-bit.jp/skygold/", wait_until="domcontentloaded", timeout=60000)
            
            # Extract 9-bit Data
            nine_bit_data = await page.evaluate('''() => {
                const results = { treasure_img: null, treasure_realm: null, seasonal_img: null, seasonal_realm: null };
                
                // Treasure
                const tHeaders = Array.from(document.querySelectorAll('h2, h3, h4')); // STRICT SELECTION
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
            t_rot = "Rotation 1" # 9-bit doesn't specify rotation explicitly in header usually, assume 1 or calc?
            # 9-bit images usually show all locations.
            # I will default to Rotation 1 if found.
            
            # Process Seasonal
            s_realm = nine_bit_data.get('seasonal_realm', '')
            s_imgs = [nine_bit_data['seasonal_img']] if nine_bit_data.get('seasonal_img') else []
            s_rot = "Rotation 1"

            # Fallback for Treasure Realm (Date-based Text) if 9-bit text extraction failed
            if t_realm == "NotFound" or not t_realm:
                 try:
                    realms = ['Daylight Prairie', 'Hidden Forest', 'Valley of Triumph', 'Golden Wasteland', 'Vault of Knowledge']
                    now = datetime.now()
                    anchor = datetime(2026, 1, 5)
                    diff = (now.date() - anchor.date()).days
                    idx = (diff + 3) % 5
                    t_realm = realms[idx]
                    t_rot = "Rotation 1" 
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

if __name__ == "__main__":
    async def main():
        c = SkyCrawler()
        await c.start()
        print("Test Shards:", await c.get_shards_info())
        print("Test Dailies:", await c.get_dailies_info())
        print("Test Clock:", await c.get_clock_info())
        await c.stop()
    asyncio.run(main())
