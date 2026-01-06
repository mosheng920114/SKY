import asyncio
import os
import sys
from crawler import SkyCrawler
import web_exporter

async def main():
    print("Starting auto_build process...")
    
    # Ensure images directory exists (Prevent git add failure if scraper crashes)
    if not os.path.exists("images"):
        os.makedirs("images")
    
    # Create .gitkeep to ensure git add images/ always succeeds even if empty
    with open(os.path.join("images", ".gitkeep"), "w") as f:
        pass
    
    # 1. Initialize Crawler
    crawler = SkyCrawler()
    
    try:
        print("Starting crawler...")
        await crawler.start()
        
        # 2. Fetch Data
        print("Fetching data (Shards, Dailies, Clock, Quests)...")
        shards_task = asyncio.create_task(crawler.get_shards_prediction())
        optimized_task = asyncio.create_task(crawler.get_all_daily_info_optimized())
        clock_task = asyncio.create_task(crawler.get_clock_info())
        
        # Return format: shards, (quests, dailies), clock
        shards, (quests, dailies), clock = await asyncio.gather(shards_task, optimized_task, clock_task)
        
        print("Data fetched successfully.")
        # Debug prints
        # print(f"Shards: {shards}")
        # print(f"Dailies keys: {dailies.keys()}")
        # print(f"Clock keys: {clock.keys()}")

    except Exception as e:
        print(f"Error during crawling: {e}")
        shards, dailies, clock = {}, {}, {}
    finally:
        await crawler.stop()
        print("Crawler stopped.")

    # 3. Generate HTML
    try:
        print("Generating HTML dashboard...")
        # web_exporter.generate_dashboard returns the absolute path of the generated file
        # It defaults to "dashboard.html" in current dir
        generated_path = web_exporter.generate_dashboard(shards, dailies, clock, quests)
        
        # 4. Rename to index.html for GitHub Pages
        target_path = os.path.join(os.path.dirname(generated_path), "index.html")
        
        # Remove existing index.html if it exists
        if os.path.exists(target_path):
            os.remove(target_path)
            
        os.rename(generated_path, target_path)
        print(f"SUCCESS: Dashboard generated at {target_path}")
        
    except Exception as e:
        print(f"Error generating/renaming HTML: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
