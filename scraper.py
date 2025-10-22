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


def scrape_ozon_product(url, verbose=False):
    """
    Scrapes a product page from Ozon.ru for its price, characteristics,
    description, and all image URLs.
    """
    if verbose:
        print(f"Scraping page: {url}", file=sys.stderr)

    driver = None
    try:
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")

        if not verbose:
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

        driver.get(url)
        if verbose:
            print("Page loaded. Waiting...", file=sys.stderr)
        time.sleep(random.uniform(4.0, 6.0))

        # Try to "unstuck" the page by sending an ESCAPE key press
        if verbose:
            print("Attempting to 'unstuck' the page...", file=sys.stderr)
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(random.uniform(0.5, 1.0))

        if verbose:
            print("Scrolling page to load all elements...", file=sys.stderr)
        total_height = int(driver.execute_script("return document.body.scrollHeight"))
        for i in range(0, total_height, 500):
            driver.execute_script(f"window.scrollTo(0, {i});")
            time.sleep(random.uniform(0.1, 0.3))
        time.sleep(random.uniform(0.8, 1.5))

        if verbose:
            print("Scraping data...", file=sys.stderr)

        scraped_data = {}
        try:
            price_element = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "span.tsHeadline600Large")
                )
            )
            scraped_data["price_text"] = price_element.text

            characteristics_section = driver.find_element(
                By.ID, "section-characteristics"
            )
            scraped_data["characteristics_text"] = characteristics_section.text

            description_section = driver.find_element(By.ID, "section-description")
            scraped_data["description_text"] = description_section.text

            if verbose:
                print("Text data scraped successfully.", file=sys.stderr)
        except Exception as e:
            if verbose:
                print(f"Could not extract text data: {e}", file=sys.stderr)
            raise

        image_urls = []
        # Scrape gallery images
        variant_selectors = driver.find_elements(By.CSS_SELECTOR, "div.pdp_x6")
        if variant_selectors and verbose:
            print(
                f"Found {len(variant_selectors)} product variants. Scraping gallery images...",
                file=sys.stderr,
            )

        for selector in variant_selectors:
            try:
                actions = ActionChains(driver)
                actions.move_to_element(selector).pause(
                    random.uniform(0.3, 0.7)
                ).click().perform()
                time.sleep(random.uniform(0.8, 1.5))
                image_container = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.pdp_v3.pdp_v4")
                    )
                )
                image_element = image_container.find_element(By.TAG_NAME, "img")
                image_url = image_element.get_attribute("src")
                if image_url:
                    image_urls.append(image_url)
            except Exception as e:
                if verbose:
                    print(f"Error processing gallery variant: {e}", file=sys.stderr)

        # Scrape description images
        if "description_section" in locals() and description_section:
            description_images = description_section.find_elements(By.TAG_NAME, "img")
            if description_images and verbose:
                print(
                    f"Found {len(description_images)} images in description. Scraping URLs...",
                    file=sys.stderr,
                )
            for img in description_images:
                image_url = img.get_attribute("src")
                if image_url:
                    image_urls.append(image_url)

        # Remove duplicates while preserving order
        scraped_data["image_urls"] = list(dict.fromkeys(image_urls))

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
        help="Enable verbose output to stderr and show the browser window.",
    )
    args = parser.parse_args()

    try:
        data = scrape_ozon_product(args.url, args.verbose)
        if data:
            print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"A critical error occurred: {e}", file=sys.stderr)
        sys.exit(1)
