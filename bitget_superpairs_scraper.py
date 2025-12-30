#!/usr/bin/env python3
"""
Bitget Super Pairs Scraper
Scrapes the official Bitget Super Pairs from their events page
Uses requests-html for JavaScript rendering
"""

import asyncio
from requests_html import AsyncHTMLSession
import json
import re
from datetime import datetime
import os

class BitgetSuperPairsScraper:
    def __init__(self):
        self.url = "https://www.bitget.com/events/super-pairs"
        self.session = AsyncHTMLSession()
        self.super_pairs = []
        
    async def scrape_super_pairs(self):
        """
        Scrape the Bitget Super Pairs page
        """
        try:
            print(f"Scraping {self.url}...")
            
            # Make request with browser-like headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0'
            }
            
            # Get the page
            response = await self.session.get(self.url, headers=headers)
            
            # Render JavaScript
            await response.html.arender(timeout=20, wait=3)
            
            # Try multiple selectors to find the pairs
            selectors = [
                # Common patterns for trading pairs
                '[class*="pair"]',
                '[class*="symbol"]',
                '[class*="coin"]',
                '[class*="trading"]',
                '[data-symbol]',
                '[data-pair]',
                'div[class*="USDT"]',
                'span[class*="USDT"]',
                'a[href*="USDT"]',
                # Text patterns
                'div:contains("USDT")',
                'span:contains("USDT")',
                'p:contains("USDT")',
                # Competition specific
                '[class*="competition"]',
                '[class*="event"]',
                '[class*="list"]'
            ]
            
            found_pairs = set()
            
            for selector in selectors:
                try:
                    elements = response.html.find(selector)
                    for element in elements:
                        text = element.text
                        # Look for USDT pairs pattern
                        pairs = re.findall(r'\b([A-Z]{2,10})/?USDT\b', text)
                        for pair in pairs:
                            if pair and len(pair) >= 2 and pair != 'USDT':
                                found_pairs.add(f"{pair}/USDT:USDT")
                except:
                    continue
            
            # Also search in the entire page text
            page_text = response.html.text
            
            # Find all USDT pairs mentioned
            text_pairs = re.findall(r'\b([A-Z]{2,10})/?USDT\b', page_text)
            for pair in text_pairs:
                if pair and len(pair) >= 2 and pair != 'USDT':
                    found_pairs.add(f"{pair}/USDT:USDT")
            
            # Look for JSON data in scripts
            scripts = response.html.find('script')
            for script in scripts:
                if script.text:
                    # Look for JSON structures
                    json_matches = re.findall(r'\{[^{}]*"symbol"[^{}]*\}', script.text)
                    for match in json_matches:
                        try:
                            data = json.loads(match)
                            if 'symbol' in data:
                                symbol = data['symbol']
                                if 'USDT' in symbol:
                                    # Convert to standard format
                                    base = symbol.replace('USDT', '').replace('/', '')
                                    if base:
                                        found_pairs.add(f"{base}/USDT:USDT")
                        except:
                            continue
            
            self.super_pairs = sorted(list(found_pairs))
            
            print(f"Found {len(self.super_pairs)} Super Pairs")
            
            # Save results
            self.save_results()
            
            return self.super_pairs
            
        except Exception as e:
            print(f"Error scraping: {e}")
            # Try alternative approach
            return await self.scrape_alternative()
    
    async def scrape_alternative(self):
        """
        Alternative scraping approach using API endpoints
        """
        try:
            print("Trying alternative approach via API...")
            
            # Try to get competition data from API
            api_urls = [
                "https://www.bitget.com/api/mix/v1/market/tickers?productType=umcbl",
                "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES",
                "https://www.bitget.com/v1/perpetual/public/products"
            ]
            
            for api_url in api_urls:
                try:
                    response = await self.session.get(api_url)
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Look for high-volume pairs (likely super pairs)
                        if 'data' in data:
                            items = data['data']
                            high_volume_pairs = []
                            
                            for item in items:
                                if isinstance(item, dict):
                                    symbol = item.get('symbol', '')
                                    volume = float(item.get('usdtVolume', 0) or item.get('quoteVolume', 0) or 0)
                                    
                                    # High volume pairs are likely featured
                                    if volume > 50_000_000 and 'USDT' in symbol:
                                        # Convert to standard format
                                        base = symbol.replace('USDT', '')
                                        if base:
                                            high_volume_pairs.append({
                                                'pair': f"{base}/USDT:USDT",
                                                'volume': volume
                                            })
                            
                            # Sort by volume and take top pairs
                            high_volume_pairs.sort(key=lambda x: x['volume'], reverse=True)
                            self.super_pairs = [p['pair'] for p in high_volume_pairs[:30]]
                            
                            if self.super_pairs:
                                print(f"Found {len(self.super_pairs)} high-volume pairs (likely Super Pairs)")
                                self.save_results()
                                return self.super_pairs
                except:
                    continue
            
        except Exception as e:
            print(f"Alternative approach failed: {e}")
        
        return []
    
    def save_results(self):
        """Save scraped super pairs to file"""
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'source': self.url,
                'super_pairs': self.super_pairs,
                'total': len(self.super_pairs)
            }
            
            with open('/app/bitget_super_pairs_scraped.json', 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"Saved {len(self.super_pairs)} pairs to bitget_super_pairs_scraped.json")
            
        except Exception as e:
            print(f"Error saving results: {e}")
    
    async def close(self):
        """Close the session"""
        await self.session.close()


async def main():
    """Main function to run the scraper"""
    scraper = BitgetSuperPairsScraper()
    
    try:
        print("=" * 70)
        print("BITGET SUPER PAIRS SCRAPER")
        print("=" * 70)
        
        super_pairs = await scraper.scrape_super_pairs()
        
        if super_pairs:
            print(f"\n✅ Successfully scraped {len(super_pairs)} Super Pairs:")
            print("-" * 70)
            
            for i, pair in enumerate(super_pairs[:20], 1):  # Show first 20
                print(f"{i:2}. {pair}")
            
            if len(super_pairs) > 20:
                print(f"... and {len(super_pairs) - 20} more")
        else:
            print("\n❌ Could not scrape Super Pairs from Bitget")
            print("The page may be protected or the structure may have changed")
            
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())