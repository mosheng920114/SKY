
import os
from datetime import datetime, timedelta
import time

def is_dst(dt=None, timezone="America/Los_Angeles"):
    """
    檢查給定的日期時間是否處於日光節約時間 (DST)。
    預設時區為 US/Pacific（Sky 伺服器所在地）。
    參考：DST 於 3 月的第二個星期日開始，於 11 月的第一個星期日結束。
    """
    if dt is None:
        dt = datetime.now()
        
    year = dt.year
    # 尋找 DST 開始日 (3月的第二個星期日)
    march_1st = datetime(year, 3, 1)
    # 星期幾: 0=週一, 6=週日
    # 尋找第一個星期日
    d = march_1st
    while d.weekday() != 6: # 尋找第一個星期日
        d += timedelta(days=1)
    second_sunday_march = d + timedelta(days=7)
    
    # 尋找 DST 結束日 (11月的第一個星期日)
    nov_1st = datetime(year, 11, 1)
    d = nov_1st
    while d.weekday() != 6:
        d += timedelta(days=1)
    first_sunday_nov = d
    
    # DST 區間 (概略) - 嚴格來說是在當天凌晨 2 點切換，但以日期判斷通常足夠。
    # Sky 的重置時間通常是洛杉磯時間午夜。
    
    # 邏輯: 開始日 <= 今天 < 結束日
    return second_sunday_march.date() <= dt.date() < first_sunday_nov.date()

def get_event_times():
    """
    計算下一次 噴泉 (Geyser)、奶奶 (Grandma)、海龜 (Turtle) 的時間與倒數。
    規則：
    - 冬令 (標準時間)：偶數小時 (0, 2, ...)。
    - 夏令 (DST)：奇數小時 (1, 3, ...)。
    
    偏移量 (分)：
    - 噴泉: 05 分
    - 奶奶: 35 分
    - 海龜: 50 分
    """
    now = datetime.now()
    dst = is_dst(now)
    
    # 基準小時：冬令為 0, 2, 4...；夏令為 1, 3, 5...
    start_offset = 1 if dst else 0 
    
    # 事件定義
    events = {
        'geyser': {'minute': 5, 'duration': 10},
        'grandma': {'minute': 35, 'duration': 10},
        'turtle': {'minute': 50, 'duration': 10}
    }
    
    result = {}
    
    for key, info in events.items():
        minute_trigger = info['minute']
        duration = info['duration']
        
        # 尋找下一次發生時間
        # 檢查當前小時、下一小時、下下小時以找到第一個符合的時間點
        
        current_h = now.hour
        
        found_next = None
        
        for i in range(24): # 檢查接下來 24 小時
            h = (current_h + i) % 24
            
            # 檢查這個小時是否為有效的事件小時
            # 邏輯: (h % 2) == 1 (夏令), == 0 (冬令)
            is_event_hour = (h % 2) == start_offset
            
            if is_event_hour:
                # 建構候選時間
                
                # 正確方法:
                # 1. 從當前時間的整點開始
                base = now.replace(minute=0, second=0, microsecond=0)
                target = base + timedelta(hours=i)
                target = target.replace(minute=minute_trigger)
                
                if target > now:
                    found_next = target
                    break
                elif target <= now < (target + timedelta(minutes=duration)):
                     # 進行中!
                     # 為了簡單起見，我們回傳這個「正在進行」的事件開始時間。
                     found_next = target # 開始時間
                     break
        
        if found_next:
            # 格式化下一次時間
            next_str = found_next.strftime("%H:%M")
            
            # 格式化倒數計時
            diff = found_next - now
            total_seconds = int(diff.total_seconds())
            
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            countdown_str = f"{hours}小時 {minutes}分 {seconds}秒"
            
            result[key] = {'next': next_str, 'countdown': countdown_str}
            
    return result

if __name__ == "__main__":
    print(f"DST: {is_dst()}")
    print(get_event_times())
