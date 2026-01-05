import os
import re
from datetime import datetime

def parse_countdown_to_seconds(countdown_str):
    """
    解析 '1h 20m', '5m', '1小時 20分' 為總秒數。
    若解析失敗回傳 0。
    """
    try:
        h = 0
        m = 0
        s = 0
        
        # 支援 "1h" 或 "1小時"
        match_h = re.search(r'(\d+)\s*(?:h|小時)', countdown_str, re.IGNORECASE)
        match_m = re.search(r'(\d+)\s*(?:m|分)', countdown_str, re.IGNORECASE)
        match_s = re.search(r'(\d+)\s*(?:s|秒)', countdown_str, re.IGNORECASE)
        
        if match_h: h = int(match_h.group(1))
        if match_m: m = int(match_m.group(1))
        if match_s: s = int(match_s.group(1))
        
        return h * 3600 + m * 60 + s
    except:
        return 0

def generate_dashboard(shards, dailies, clock, quests=None):
    """
    生成高美感 HTML 儀表板。
    """
    
    # 1. 準備資料
    
    # Shards (碎石)
    shard_html = ""
    if shards:
        img_html = f'<img src="{shards["image_url"]}" onclick="openModal(this.src)" class="shard-img">' if shards.get('image_url') else ""
        eruptions_html = "".join([f'<span class="tag">{t}</span>' for t in shards.get('eruptions', [])])
        shard_html = f'''
        <div class="card">
            <div class="card-header">
                <h2>每日碎石 (Shards)</h2>
                <div class="row-center">
                     <span class="badge {shards.get('type', 'Unknown')}">{shards.get('type')}</span>
                </div>
            </div>
            <div class="card-body">
                <div class="info-row highlight-row"><strong>日期：</strong> {shards.get('dateText', '')}</div>
                <div class="info-row"><strong>地圖：</strong> {shards.get('map')}</div>
                <div class="info-row"><strong>獎勵：</strong> <span class="rewards-text">{shards.get('rewards') if shards.get('rewards') else '未知 / Unknown'}</span></div>
                <div class="info-row"><strong>時間：</strong> {shards.get('time_range')}</div>
                <div class="info-row"><strong>狀態：</strong> {shards.get('remaining', '')}</div>
                <div class="eruptions-list">
                    <strong>爆發時間 (24H)：</strong>
                    <div class="tags">{eruptions_html}</div>
                </div>
                {img_html}
            </div>
        </div>
        '''
    else:
        shard_html = '<div class="card error">無法獲取碎石資訊</div>'

    # Quests (每日任務)
    quest_html = ""
    if quests:
        items_html = "".join([f'<div class="quest-item"><span class="num">{i+1}</span> {q}</div>' for i, q in enumerate(quests)])
        quest_html = f'''
        <div class="card">
            <div class="card-header">
                <h2>每日任務 (Quests)</h2>
            </div>
            <div class="card-body">
                <div class="quest-list">{items_html}</div>
            </div>
        </div>
        '''
    else:
        quest_html = '<div class="card error">無法獲取每日任務</div>'

    # Candles Helper (蠟燭助手)
    def build_candle_card(title, data, is_seasonal=False):
        if not data: return f'<div class="card error">無法獲取{title}資訊</div>'
        
        realm = data.get('realm', '未知')
        rot = data.get('rotation', '')
        header_sub = f"{realm} | {rot}" if rot else realm
        
        descs = data.get('descriptions', [])
        imgs = data.get('images', [])
        
        # HTML 自適應佈局邏輯
        is_paired = len(descs) > 0 and len(imgs) == len(descs)
        
        content_html = ""
        
        if is_paired:
            content_html += '<div class="pair-grid">'
            for i in range(len(descs)):
                img_src = imgs[i] if i < len(imgs) else ""
                img_tag = f'<img src="{img_src}" onclick="openModal(this.src)">' if img_src else ""
                content_html += f'''
                <div class="pair-item">
                    <div class="desc"><span class="num">{i+1}</span> {descs[i]}</div>
                    {img_tag}
                </div>
                '''
            content_html += '</div>'
        else:
            # 列表描述
            content_html += '<div class="desc-list">'
            for i, txt in enumerate(descs):
                content_html += f'<div class="desc"><span class="num">{i+1}</span> {txt}</div>'
            content_html += '</div>'
            
            # 列表圖片
            content_html += '<div class="img-grid">'
            for url in imgs:
                 content_html += f'<img src="{url}" onclick="openModal(this.src)">'
            content_html += '</div>'

        return f'''
        <div class="card">
            <div class="card-header">
                <h2>{title}</h2>
                <span class="subtitle">{header_sub}</span>
            </div>
            <div class="card-body scrollable">
                {content_html}
            </div>
        </div>
        '''

    treasure_html = build_candle_card("大蠟燭 (Treasure)", dailies.get('treasure', {}))
    seasonal_html = build_candle_card("季節蠟燭 (Seasonal)", dailies.get('seasonal', {}), is_seasonal=True)

    # Clock (時鐘)
    clock_html = ""
    if clock:
        def build_event_row(key, name):
            if key not in clock: return ""
            info = clock[key]
            secs = parse_countdown_to_seconds(info.get('countdown', ''))
            
            # 活躍判定邏輯 (參考 gui.py / JS)
            # 若倒數大於 1小時50分 (6600秒)，視為上一輪剛開始 -> 活躍中
            
            status_class = "waiting"
            # 這裡的文字會被 JS 覆蓋，但給個初始值
            
            return f'''
            <div class="event-row" id="event-{key}" data-seconds="{secs}">
                <div class="event-name">{name}</div>
                <div class="event-time">下次: {info.get('next')}</div>
                <div class="event-countdown">--:--:--</div>
                <div class="event-status tag {status_class}">計算中...</div>
            </div>
            '''
            
        clock_html = f'''
        <div class="card">
            <div class="card-header">
                <h2>每日事件時鐘 (Events)</h2>
            </div>
            <div class="card-body">
                {build_event_row('geyser', '噴泉 (Geyser)')}
                {build_event_row('grandma', '奶奶 (Grandma)')}
                {build_event_row('turtle', '海龜 (Turtle)')}
            </div>
        </div>
        '''
    else:
        clock_html = '<div class="card error">無法獲取時鐘資訊</div>'


    # Inject Shard Data for JS
    shard_times_json = "[]"
    if shards and 'eruptions' in shards:
        # CONVERT CHINESE TIME TO 24H HH:MM FOR JS
        # format: "下午07:38:40 - 下午11:30:00"
        import json
        clean_times = []
        for t_range in shards.get('eruptions', []):
            try:
                # Regex to find time parts
                parts = t_range.split('-')
                if len(parts) == 2:
                    
                    def to_24h(s):
                        s = s.strip()
                        prefix = s[:2]
                        body = s[2:].split(':')
                        h = int(body[0])
                        m = int(body[1])
                        if "下午" in prefix and h < 12: h += 12
                        elif "上午" in prefix and h == 12: h = 0
                        return f"{h:02d}:{m:02d}"

                    t1 = to_24h(parts[0])
                    t2 = to_24h(parts[1])
                    clean_times.append(f"{t1}-{t2}")
            except:
                pass
        
        shard_times_json = json.dumps(clean_times)

    # HTML Template
    html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sky: Children of the Light Daily Dashboard</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Outfit:wght@400;600&display=swap');
        
        :root {{
            --bg-color: #121418;
            --card-bg: #1e2229;
            --primary: #5c9aff;
            --accent: #ffcc00;
            --text-main: #e0e0e0;
            --text-sub: #a0a0a0;
            --border: #2a2f3a;
        }}

        body {{
            font-family: 'Outfit', 'Noto Sans TC', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 20px;
            overflow-x: hidden;
        }}
        
        .quest-list .quest-item {{
            padding: 8px 0;
            border-bottom: 1px solid var(--border);
            font-size: 1.1em;
        }}
        .quest-list .quest-item:last-child {{ border-bottom: none; }}
        .quest-item .num {{ 
            color: var(--accent); 
            font-weight: bold; 
            margin-right: 10px;
        }}
        
        .highlight-row {{ 
            background: rgba(255, 255, 255, 0.05); 
            padding: 5px 10px;
            border-radius: 4px;
            margin-bottom: 5px;
        }}
        .rewards-text {{ color: #ffd700; }}

        h1, h2, h3 {{ margin: 0; }}

        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px 0;
            border-bottom: 2px solid var(--border);
        }}
        
        .header h1 {{
            font-size: 2rem;
            background: linear-gradient(90deg, #fff, var(--primary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }}
        
        .timestamp {{ color: var(--text-sub); font-size: 0.9rem; }}

        .grid-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            max_width: 1600px;
            margin: 0 auto;
            align-items: start;
        }}

        /* Card Styles */
        .card {{
            background: var(--card-bg);
            border-radius: 16px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.2);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            border: 1px solid var(--border);
            transition: transform 0.2s;
        }}
        
        .card:hover {{ transform: translateY(-5px); border-color: var(--primary); }}

        .card-header {{
            padding: 15px 20px;
            background: rgba(0,0,0,0.2);
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
        }}
        
        .card-header h2 {{ font-size: 1.2rem; display: flex; align-items: center; gap: 10px; }}
        .badge {{ font-size: 0.75rem; padding: 2px 8px; border-radius: 12px; background: var(--primary); color: #fff; }}
        .badge.Red {{ background: #ff4757; }}
        .badge.Black {{ background: #2f3542; }}
        .subtitle {{ font-size: 0.9rem; color: var(--accent); }}

        .card-body {{ padding: 20px; flex: 1; }}
        .scrollable {{ max-height: 800px; overflow-y: auto; }}

        /* Shards */
        .info-row {{ margin-bottom: 8px; }}
        .tags {{ display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px; }}
        .tag {{ background: #333; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; color: #ccc; }}
        .shard-img {{ width: 100%; border-radius: 8px; margin-top: 15px; cursor: pointer; transition: opacity 0.2s; }}
        .shard-img:hover {{ opacity: 0.9; }}
        .shard-status-dynamic {{ font-weight: bold; color: var(--accent); }}

        /* Candles */
        .pair-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
        .pair-item {{ padding: 10px; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); }}
        .desc {{ margin-bottom: 10px; line-height: 1.5; font-size: 0.95rem; }}
        .num {{ color: var(--accent); font-weight: bold; margin-right: 5px; }}
        .pair-item img {{ width: 100%; border-radius: 8px; cursor: pointer; aspect-ratio: 16/9; object-fit: cover; }}
        
        .desc-list {{ margin-bottom: 20px; }}
        .img-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }}
        .img-grid img {{ width: 100%; border-radius: 8px; cursor: pointer; transition: transform 0.2s; }}
        .img-grid img:hover {{ transform: scale(1.02); }}

        /* Clock */
        .event-row {{
            background: rgba(255,255,255,0.05);
            margin-bottom: 10px;
            padding: 15px;
            border-radius: 8px;
            display: grid;
            grid-template-columns: 1fr auto;
            grid-template-rows: auto auto auto;
            gap: 5px;
        }}
        .event-name {{ font-weight: bold; font-size: 1.1rem; grid-column: 1 / -1; }}
        .event-time {{ color: var(--text-sub); }}
        .event-countdown {{ color: var(--primary); font-family: monospace; font-size: 1.2rem; font-weight: bold; text-align: right; }}
        .event-status {{ grid-column: 1 / -1; margin-top: 5px; text-align: center; background: #2a2f3a; }}
        .event-status.active {{ background: #2ed573; color: #fff; }}
        .event-status.waiting {{ background: #ffa502; color: #fff; }}

        /* Modal */
        .modal {{
            display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%;
            background-color: rgba(0,0,0,0.9); align-items: center; justify-content: center;
        }}
        .modal img {{ max-width: 90%; max-height: 90%; border-radius: 8px; box-shadow: 0 0 20px rgba(255,255,255,0.1); }}
        .close {{ position: absolute; top: 20px; right: 35px; color: #f1f1f1; font-size: 40px; font-weight: bold; cursor: pointer; }}

        /* Scrollbar */
        ::-webkit-scrollbar {{ width: 8px; }}
        ::-webkit-scrollbar-track {{ background: #1a1a1a; }}
        ::-webkit-scrollbar-thumb {{ background: #444; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #555; }}
    </style>
</head>
<body>

    <div class="header">
        <h1>Sky: Children of the Light</h1>
        <div class="timestamp">更新時間 (Updated)：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>

    <div class="grid-container">
        <!-- Column 1: Shards & Quests -->
        <div class="column-wrapper" style="display:flex; flex-direction:column; gap:20px;">
            {shard_html}
            {quest_html}
        </div>
        
        <!-- Column 2: Treasures -->
        {treasure_html}
        
        <!-- Column 3: Seasonal & Clock -->
        <div class="column-wrapper" style="display:flex; flex-direction:column; gap:20px;">
            {seasonal_html}
            {clock_html}
        </div>
    </div>

    <!-- Modal -->
    <div id="imgModal" class="modal" onclick="this.style.display='none'">
        <span class="close">&times;</span>
        <img id="modalImg">
    </div>

    <script>
        // Data injected from Python
        const SHARD_TIMES = {shard_times_json};

        // Modal
        function openModal(src) {{
            document.getElementById('imgModal').style.display = "flex";
            document.getElementById('modalImg').src = src;
        }}

        // --- SHARD LOGIC ---
        function updateShardStatus() {{
            // Find existing status element or create one if needed (though we assume one exists from template)
            // But wait, the template has <div class="info-row"><strong>狀態：</strong> {shards.get('remaining', '')}</div>
            // We should target the text node or a span inside it.
            // Let's look for the row containing "狀態：".
            
            const rows = document.querySelectorAll('.card-body .info-row');
            let statusRow = null;
            rows.forEach(r => {{
                if (r.textContent.includes("狀態：")) statusRow = r;
            }});

            if (!statusRow || SHARD_TIMES.length === 0) return;

            const now = new Date();
            let msg = "今日所有爆發已結束";
            let found = false;

            // Parse SHARD_TIMES "HH:MM - HH:MM"
            // We assume these are for today.
            
            for (let i = 0; i < SHARD_TIMES.length; i++) {{
                const range = SHARD_TIMES[i];
                const parts = range.split('-');
                if (parts.length < 2) continue;

                const startStr = parts[0].trim();
                const endStr = parts[1].trim();
                
                // Construct Date objects
                // Helper to parse "HH:MM"
                const parseTime = (str) => {{
                    const [h, m] = str.split(':').map(Number);
                    const d = new Date(now);
                    d.setHours(h, m, 0, 0);
                    return d;
                }};

                const start = parseTime(startStr);
                const end = parseTime(endStr);
                
                // Handle edge case if end < start (overnight), add 1 day to end (rare for Shards but safe)
                if (end < start) end.setDate(end.getDate() + 1);

                // Logic
                if (now < start) {{
                    // Future: Waiting
                    const diff = (start - now) / 1000;
                    const dH = Math.floor(diff / 3600);
                    const dM = Math.floor((diff % 3600) / 60);
                    const dS = Math.floor(diff % 60);
                    msg = `等待中 (距離開始: ${{dH}}小時 ${{dM}}分 ${{dS}}秒)`;
                    found = true;
                    break; // Found the next one
                }} else if (now >= start && now < end) {{
                    // Active
                    const diff = (end - now) / 1000;
                    const dM = Math.floor(diff / 60);
                    const dS = Math.floor(diff % 60);
                    msg = `進行中! (距離結束: ${{dM}}分 ${{dS}}秒)`;
                    found = true;
                    break; // Found current one
                }}
                // If now >= end, loop continues to check next slot
            }}

            if (!found) {{
                // All ended. Calculate how long ago.
                const lastRange = SHARD_TIMES[SHARD_TIMES.length - 1];
                const parts = lastRange.split('-');
                if (parts.length >= 2) {{
                    const endStr = parts[1].trim();
                    const [h, m] = endStr.split(':').map(Number);
                    const lastEnd = new Date(now);
                    lastEnd.setHours(h, m, 0, 0);
                    
                    if (now > lastEnd) {{
                        const diff = (now - lastEnd) / 1000;
                        const dH = Math.floor(diff / 3600);
                        const dM = Math.floor((diff % 3600) / 60);
                        msg = `今日爆發已結束 (已過: ${{dH}}小時 ${{dM}}分)`;
                    }}
                }}
            }}

            // Update DOM
            // We want to replace the text after "狀態："
            statusRow.innerHTML = `<strong>狀態：</strong> <span class="shard-status-dynamic">${{msg}}</span>`;
        }}


        // --- CLOCK LOGIC ---
        function isDST(date) {{
            const year = date.getFullYear();
            // DST Starts 2nd Sunday in March
            let march = new Date(year, 2, 1); // March 1
            while (march.getDay() !== 0) march.setDate(march.getDate() + 1);
            const dstStart = new Date(year, 2, march.getDate() + 7); // 2nd Sunday

            // DST Ends 1st Sunday in Nov
            let nov = new Date(year, 10, 1); // Nov 1
            while (nov.getDay() !== 0) nov.setDate(nov.getDate() + 1);
            const dstEnd = nov; // 1st Sunday

            // Reset time to midnight for comparison
            const today = new Date(date).setHours(0,0,0,0);
            return today >= dstStart.setHours(0,0,0,0) && today < dstEnd.setHours(0,0,0,0);
        }}

        const EVENTS = {{
            'geyser': {{ min: 5, duration: 10 }},
            'grandma': {{ min: 35, duration: 10 }},
            'turtle': {{ min: 50, duration: 10 }}
        }};

        function updateClock() {{
            const now = new Date();
            const dst = isDST(now);
            const startOffset = dst ? 1 : 0; // Summer: Odd (1,3..), Winter: Even (0,2..)

            for (const [key, info] of Object.entries(EVENTS)) {{
                const row = document.getElementById('event-'+key);
                if (!row) continue;

                // Find next/current event
                let foundNext = null;
                let isActive = false;
                let remainingActive = 0;

                // Check upcoming 24 hours
                for (let i = 0; i < 24; i++) {{
                    let target = new Date(now);
                    target.setHours(now.getHours() + i);
                    target.setMinutes(info.min);
                    target.setSeconds(0);
                    
                    // Check if target hour matches cycle
                    if ((target.getHours() % 2) !== startOffset) continue;

                    // If target is in the past, it might be ACTIVE
                    // Active range: target <= now < target + 10m
                    const endTime = new Date(target.getTime() + info.duration * 60000);
                    
                    if (now >= target && now < endTime) {{
                        isActive = true;
                        remainingActive = (endTime - now) / 1000; // seconds
                        foundNext = target; // It's this one
                        break;
                    }}

                    // If target is in future
                    if (target > now) {{
                        foundNext = target;
                        break;
                    }}
                }}

                if (foundNext) {{
                    const statusDiv = row.querySelector('.event-status');
                    const cdDiv = row.querySelector('.event-countdown');
                    const timeDiv = row.querySelector('.event-time');

                    // Format Next Time
                    const hStr = foundNext.getHours().toString().padStart(2, '0');
                    const mStr = foundNext.getMinutes().toString().padStart(2, '0');
                    timeDiv.textContent = `下次: ${{hStr}}:${{mStr}}`;

                    if (isActive) {{
                        const rMin = Math.floor(remainingActive / 60);
                        const rSec = Math.floor(remainingActive % 60);
                        statusDiv.textContent = `進行中 (剩餘 ${{rMin}}分 ${{rSec}}秒)`;
                        statusDiv.className = "event-status tag active";
                        cdDiv.textContent = ""; 
                    }} else {{
                        // Countdown
                        const diff = (foundNext - now) / 1000;
                        const dH = Math.floor(diff / 3600);
                        const dM = Math.floor((diff % 3600) / 60);
                        const dS = Math.floor(diff % 60);
                        
                        statusDiv.textContent = "等待中";
                        statusDiv.className = "event-status tag waiting";
                        cdDiv.textContent = `${{dH}}小時 ${{dM}}分 ${{dS}}秒`;
                    }}
                }}
            }}
        }}

        function loop() {{
            updateClock();
            updateShardStatus();
        }}

        setInterval(loop, 1000);
        loop(); // Init
    </script>
</body>
</html>
    """
    
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    return os.path.abspath("dashboard.html")
