#!/usr/bin/env python3
import time
import os
import requests
import json
import argparse
import sys
import random
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium_stealth import stealth
from bs4 import BeautifulSoup


def scrape_ozon_product(url, verbose=False, show_window=False):
    """
    Scrapes a product page from Ozon.ru for its price, characteristics,
    description, and all image URLs using a hybrid Selenium + JSON-LD approach.
    """
    if verbose:
        print(f"Scraping page: {url}", file=sys.stderr)

    driver = None
    try:
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")

        if not show_window:
            options.add_argument("--headless")
            options.add_argument("--window-size=1200,700")

        driver = uc.Chrome(options=options, version_main=142)
        wait = WebDriverWait(driver, 30)
        
        stealth(
            driver,
            languages=["ru-RU", "ru"],
            vendor="Google Inc.",
            platform="MacIntel",
            fix_hairline=True,
        )

        if verbose:
            print("Loading page with Selenium to bypass anti-bot...", file=sys.stderr)
        driver.get(url)
        time.sleep(random.uniform(5.0, 8.0))  # Allow time for dynamic content to load

        if verbose:
            print("Scrolling to the bottom of the page...", file=sys.stderr)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        
        if verbose:
            print("Waiting for characteristics section to be present after scroll...", file=sys.stderr)
        try:
            wait.until(EC.presence_of_element_located((By.ID, "section-characteristics")))
            if verbose:
                print("- Characteristics section is present.", file=sys.stderr)
        except Exception as e:
            if verbose:
                print(f"- Timed out waiting for characteristics section: {e}", file=sys.stderr)

        if verbose:
            print("Page loaded. Parsing data...", file=sys.stderr)
        
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")
        
        scraped_data = {}

        # Step 1: Extract reliable data from JSON-LD
        script_tag = soup.find("script", {"type": "application/ld+json"})
        if script_tag:
            if verbose:
                print("Found JSON-LD script. Extracting name, description, and price.", file=sys.stderr)
            json_data = json.loads(script_tag.string)
            scraped_data["name"] = json_data.get("name")
            scraped_data["description"] = json_data.get("description").replace("\n\n", " ")
            offers = json_data.get("offers", [])
            if isinstance(offers, list) and offers:
                scraped_data["price"] = offers[0].get("price")
                scraped_data["price_currency"] = offers[0].get("priceCurrency")
            elif isinstance(offers, dict):
                scraped_data["price"] = offers.get("price")
                scraped_data["price_currency"] = offers.get("priceCurrency")
        elif verbose:
            print("!!! Could not find JSON-LD script tag. Name, description, and price will be missing.", file=sys.stderr)

        # Step 2: Use Selenium to get characteristics and images, which are not in JSON-LD
        if verbose:
            print("Using Selenium to scrape characteristics and images.", file=sys.stderr)
        
        try:
            characteristics_section = driver.find_element(By.ID, "section-characteristics")
            characteristics_text = characteristics_section.text
            
            if verbose:
                print("- Characteristics section found. Parsing text...", file=sys.stderr)

            lines = characteristics_text.strip().split('\n')
            
            # Find the start of the actual characteristics list, skipping headers
            start_index = 0
            for i, line in enumerate(lines):
                if line.strip() == "Добавить к сравнению":
                    start_index = i + 1
                    break
            
            characteristics_list = []
            # Process lines in pairs (key, value)
            # We iterate with a step of 2
            it = iter(lines[start_index:])
            for name in it:
                try:
                    value = next(it)
                    characteristics_list.append({"name": name.strip(), "value": value.strip()})
                except StopIteration:
                    # This handles the case where there's an odd number of lines
                    if verbose:
                        print(f"  - Warning: Characteristic '{name.strip()}' has no value, skipping.", file=sys.stderr)
            
            scraped_data["characteristics"] = characteristics_list
            if verbose:
                print(f"- Parsed {len(characteristics_list)} characteristics.", file=sys.stderr)

        except Exception as e:
            if verbose:
                print(f"- Could not extract or parse characteristics: {e}", file=sys.stderr)
            scraped_data["characteristics"] = []

        image_urls = []
        # Scrape gallery images by clicking variants
        variant_selectors = driver.find_elements(By.CSS_SELECTOR, "div.pdp_x7")
        if not variant_selectors and verbose:
            print("!!! No product variants found after scroll. Saving page source for debugging...", file=sys.stderr)
            page_source_path = "ozon_page_source_after_scroll.html"
            with open(page_source_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"!!! Page HTML saved to '{page_source_path}'.", file=sys.stderr)
        
        if variant_selectors and verbose:
            print(f"- Found {len(variant_selectors)} product variants. Scraping gallery images...", file=sys.stderr)
        
        for i, selector in enumerate(variant_selectors):
            try:
                if verbose:
                    print(f"  - Clicking variant {i+1}/{len(variant_selectors)}...", file=sys.stderr)
                actions = ActionChains(driver)
                actions.move_to_element(selector).pause(random.uniform(0.3, 0.7)).click().perform()
                time.sleep(random.uniform(0.8, 1.5))
                
                image_element = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "img.pdp_v6.pdp_v7.b95_3_4-a")
                    )
                )
                image_url = image_element.get_attribute("src")
                if image_url:
                    image_urls.append(image_url)
                    if verbose:
                        print(f"    - Extracted image URL: {image_url}", file=sys.stderr)
            except Exception as e:
                if verbose:
                    print(f"  - Error processing gallery variant {i+1}: {e}", file=sys.stderr)

        # Scrape description images
        try:
            description_section = driver.find_element(By.ID, "section-description")
            description_images = description_section.find_elements(By.TAG_NAME, "img")
            if description_images and verbose:
                print(f"- Found {len(description_images)} images in description. Scraping URLs...", file=sys.stderr)
            for img in description_images:
                image_url = img.get_attribute("src")
                if image_url:
                    image_urls.append(image_url)
        except Exception as e:
            if verbose:
                 print(f"- Could not find or process description images: {e}", file=sys.stderr)


        # Remove duplicates while preserving order
        scraped_data["image_urls"] = list(dict.fromkeys(image_urls))
        if verbose:
            print(f"Total unique images found: {len(scraped_data['image_urls'])}", file=sys.stderr)

        return scraped_data

    finally:
        if driver:
            driver.quit()
        if verbose:
            print("Scraping finished.", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape a product page from Ozon.ru.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
This script scrapes the following information from a given Ozon.ru product URL:
  - Price
  - Product characteristics
  - Product description
  - All image URLs (from the main gallery and the description)

The scraped data is printed to standard output as a JSON object.
Errors and verbose logging are printed to standard error.

Example:
  ./scraper.py https://www.ozon.ru/product/some-product-12345/ -v
""",
    )
    parser.add_argument("url", help="The URL of the product page to scrape.")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output to stderr.",
    )
    parser.add_argument(
        "--show-window",
        action="store_true",
        help="Show the browser window (useful for debugging).",
    )
    args = parser.parse_args()

    try:
        # The browser window is shown if either verbose mode is on or the show-window flag is set
        should_show_window = args.verbose or args.show_window
        data = scrape_ozon_product(args.url, args.verbose, show_window=should_show_window)
        if data:
            print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"A critical error occurred: {e}", file=sys.stderr)
        sys.exit(1)
