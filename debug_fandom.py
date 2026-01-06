import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        print("Navigating to Fandom Wiki...")
        await page.goto("https://sky-children-of-the-light.fandom.com/wiki/Treasure_Candles", timeout=90000, wait_until='domcontentloaded')
        
        # Debug 1: Print the "Today's..." text finding logic
        data = await page.evaluate('''() => {
            const content = document.querySelector('#mw-content-text');
            const ps = Array.from(content.querySelectorAll('p, b, center, span, font, div')); // Added div
            
            const rotInfo = ps.find(el => 
                el.innerText.includes("Today's") && 
                el.innerText.includes("Treasure Candle rotation")
            );
            
            if (rotInfo) return { found: true, text: rotInfo.innerText, tag: rotInfo.tagName };
            return { found: false };
        }''')
        
        print(f"Rotation Text Detection: {data}")
        
        # Debug 2: Print Headers to see if we can find Realms
        headers = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('h2, h3')).map(h => h.innerText);
        }''')
        # print(f"Headers found: {headers}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
