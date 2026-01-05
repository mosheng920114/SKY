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

                let img = document.querySelector('img.map_clement');
                if (!img) {
                    // Fallback 1: Search by src keyword
                    const allImgs = Array.from(document.querySelectorAll('img'));
                    img = allImgs.find(i => i.src.toLowerCase().includes('clement') || i.src.toLowerCase().includes('map'));
                    
                    // Fallback 2: Search by container header
                    if (!img) {
                         const headers = Array.from(document.querySelectorAll('h1, h2, h3, div'));
                         const mapHeader = headers.find(h => h.innerText.includes('地圖') || h.innerText.includes('Map'));
                         if (mapHeader) {
                             // Look in next sibling or parent
                             const container = mapHeader.parentElement;
                             img = container.querySelector('img');
                         }
                    }
                }
                const imgUrl = img ? img.src : null;
                
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
            
            # 3. Extract Quests (Robust Text Parsing)
            # Instead of complex JS DOM traversal, get the full text and regex it.
            # content_text = await page.input_value('body') # REMOVED
            content_text = await page.evaluate('document.body.innerText')
            
            # Key phrases for quests
            quest_keywords = ['瞑想', '光', 'キャンドル', '精霊', 'プレイヤー', 'フレンド', 'ハイタッチ', 'ハグ', 'おんぶ', 'チャット', 'スケーター', '記憶', '若木']
            
            lines = content_text.split('\n')
            
            # Find the header "デイリークエスト" or Specific Date
            start_index = -1
            
            # 1. Try finding Today's Date (e.g., "1月5日")
            # Sky resets at 00:00 PST. 
            # In Asia (GMT+8), reset is 16:00.
            # If current time < 16:00, it's still "Yesterday" in Sky logic? 
            # No, usually 9-bit posts "Today" meaning the *active* day.
            # Let's try matching Python's local date first.
            now = datetime.now()
            today_str = f"{now.month}月{now.day}日"
            
            # Scan for date header
            for i, line in enumerate(lines):
                if today_str in line and "クエスト" in line: # e.g. "1月5日 デイリークエスト"
                    start_index = i
                    print(f"DEBUG: Found Date Header: {line}")
                    break
            
            # Fallback (Just Date)
            if start_index == -1:
                for i, line in enumerate(lines):
                     if today_str in line:
                         # Heuristic: check if nearby lines have "クエスト"
                         start_index = i
                         print(f"DEBUG: Found Date Only: {line}")
                         break

            # Fallback to "Daily Quest" header if date not found
            if start_index == -1:
                for i, line in enumerate(lines):
                    if "デイリークエスト" in line and "内容" not in line and "方法" not in line and "今日の" in line:
                        start_index = i
                        break
            
            extracted_quests = []
            
            # Scan Strategy:
            # 1. If start_index found, scan next 50 lines.
            target_lines = lines[start_index:] if start_index != -1 else lines

            candidates = []
            for line in target_lines:
                line = line.strip()
                if not line: continue
                if len(candidates) >= 4 and start_index != -1: break # Limit if we found header
                if len(candidates) >= 10: break # Safety limit for global search
                
                # Check validity
                score = 0
                if any(k in line for k in quest_keywords): score += 2
                if '集める' in line or '追体験' in line or '片付ける' in line: score += 2
                if '先祖' in line or '食卓' in line: score += 1
                if len(line) > 5: score += 1
                
                # Negative
                if 'とは' in line or '方法' in line or '目次' in line: score -= 10
                if '攻略' in line or '掲示板' in line: score -= 10
                if 'シーズンキャンドル' in line: score -= 5 
                if '大キャンドル' in line: score -= 5 
                if '▲' in line: score -= 10 # Exclude tips (usually navigation instructions)


                
                if score >= 3:
                     # Check duplicates
                     if line not in candidates:
                        candidates.append(line)
            
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
        # 1. Map Locations
        loc_map = {
            '孤島': '晨島', '草原': '雲野', '雨林': '雨林', '峡谷': '霞谷', 
            '捨てられた地': '暮土', '書庫': '禁閣'
        }
        for jp, tc in loc_map.items():
            text = text.replace(jp, tc)

        # 2. Specific Terms & Phrases Map
        terms = {
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
            
            # Valley Quests (Valley of Triumph) - User Request
            '峡谷を訪れしばしの間若木を愛でる': '欣賞一下霞谷小樹苗',
            '峡谷の若木を愛でる': '欣賞一下霞谷小樹苗',
            '若木': '小樹苗', '愛でる': '欣賞一下',
            '精霊の記憶を呼び起こす': '重溫一位先靈的記憶',
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
                    
                    while (curr && !['H1','H2'].includes(curr.tagName)) {
                        const text = curr.innerText.trim();
                        if (text.length > 2) textBuffer += text + " ";
                        
                        const foundImgs = curr.querySelectorAll('img');
                        foundImgs.forEach(img => {
                            if (img.width > 40 || img.classList.contains('thumbimage')) {
                                const src = img.getAttribute('data-src') || img.src;
                                if (src && !src.includes('data:image')) {
                                     // [FIX] REMOVE SCALING
                                     let cleanSrc = src.replace(/\\/scale-to-width-down\\/\\d+/, "");
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
            s_descs = candle_data.get_seasonal_desc(s_info['realm']) 
            
            return {
                "treasure": {
                    "realm": t_info['realm'],
                    "rotation": t_info['rot'],
                    "descriptions": t_descs,
                    "images": t_info['imgs']
                },
                "seasonal": {
                    "realm": s_info['realm'],
                    "rotation": s_info['rot'],
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
