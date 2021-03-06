from webdriver_manager.chrome import ChromeDriverManager
import json
from parse_utils import *
from lxml import etree
from urllib.parse import urljoin
import logging
import logging.config
import requests

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

logging.config.fileConfig('logging.conf')
logger = logging.getLogger('root')

BASE_URL = 'http://www.glassdoor.com'
LOGIN_URL = urljoin(BASE_URL, 'profile/login_input.htm')
DEFAULT_LOCATION = 'San Francisco, CA'
DELAY = 20

companies_list = ['stripe', 'workspan']


def main():

    # Launch driver
    chrome_options = webdriver.chrome.options.Options()
    # chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)

    # Log into account
    with open('secret.json') as f:
        secrets = json.load(f)

    email = secrets['email']
    pwd = secrets['pwd']

    # Log into account
    gd_login(driver, LOGIN_URL, email, pwd)

    results = []

    for company in companies_list:

        element = WebDriverWait(driver, DELAY).until(
            EC.visibility_of_element_located((By.XPATH, "//a[@href='/Reviews/index.htm']"))
        )
        element.click()

        # Enter location
        location_input = None
        try:
            location_input = WebDriverWait(driver, DELAY).until(
                EC.visibility_of_element_located((By.XPATH, "//input[@id='LocationSearch']"))
            )
        except TimeoutException:
            location_input = WebDriverWait(driver, DELAY).until(
                EC.visibility_of_element_located((By.XPATH, "//input[@id='sc.location']"))
            )
        finally:
            if location_input:
                enter_location(location_input, DEFAULT_LOCATION)
            else:
                logger.error(f'Not able to find location input element. Exiting...')
                driver.quit()
                return

        # Enter company name
        company_input = None
        try:
            company_input = WebDriverWait(driver, DELAY).until(
                EC.visibility_of_element_located((By.XPATH, "//input[@id='KeywordSearch']"))
            )
        except TimeoutException:
            company_input = WebDriverWait(driver, DELAY).until(
                EC.visibility_of_element_located((By.XPATH, "//input[@id='sc.keyword']"))
            )
        finally:
            if company_input:
                enter_company_name(company_input, company)
            else:
                logger.error(f'Not able to find keyword input element. Exiting...')
                driver.quit()
                return

        # Check if company page was opened
        try:
            WebDriverWait(driver, DELAY).until(
                EC.visibility_of_element_located((By.XPATH, "//a[@class='eiCell cell interviews ']"))
            )
            company_url = driver.current_url
        except TimeoutException:
            doc = etree.HTML(driver.page_source)
            company_url = pick_company_from_search_results(doc, company)

        if company_url:
            company_url = urljoin(BASE_URL, company_url)
            logger.info(f'Current company URL: {company_url}')
            driver.get(company_url)
        else:
            logger.error(f'Not able to find company URL. Exiting...')
            driver.quit()
            return

        try:
            interviews_link = WebDriverWait(driver, DELAY).until(
                EC.visibility_of_element_located((By.XPATH, "//a[@class='eiCell cell interviews ']"))
            )
        except TimeoutException:
            logger.error(f'Not able to find interview reviews link. Exiting...')
            driver.quit()
            return

        next_page = interviews_link.get_attribute('href')

        # Collect reviews
        reviews = []
        pages = 3
        page = 0
        while next_page and page < pages:
            url = urljoin(BASE_URL, next_page)
            logger.info(f'Current page: {url}')
            driver.get(url)
            doc = etree.HTML(driver.page_source)
            data = get_reviews(doc, company)
            reviews.extend(data)
            next_page = get_next_page(doc)
            page += 1

        preprocess(reviews)
        results.extend(reviews)

    for result in results:
        r = requests.post('https://gdreviews.herokuapp.com/api/reviews/', json=result)
        if r.status_code == 201:
            logger.info(f"Success: {result['company']} - {result['role']}")
        else:
            logger.error(f"Failure: {r.status_code} - {r.text} {result['company']}")

    with open("reviews.json", "a") as f:
        json.dump(results, f, indent=4)

    driver.quit()


if __name__ == '__main__':
    main()
