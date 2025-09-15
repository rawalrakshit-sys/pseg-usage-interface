from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import json
import time
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re

app = FastAPI(title="PSE&G Usage Interface", description="API for retrieving PSE&G historical usage data")

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class PSEGCredentials(BaseModel):
    username: str
    password: str

class UsageData(BaseModel):
    date: str
    usage_kwh: float
    cost: Optional[float] = None
    billing_period: Optional[str] = None

class PSEGUsageResponse(BaseModel):
    success: bool
    data: List[UsageData]
    message: str
    total_usage: float
    average_monthly_usage: float

class PSEGScraper:
    def __init__(self):
        self.driver = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=800,600")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--memory-pressure-off")
        chrome_options.add_argument("--max_old_space_size=256")
        chrome_options.add_argument("--single-process")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        return self.driver
    
    def login_with_requests(self, username: str, password: str) -> bool:
        """Requests-based login to handle PSE&G's OAuth2 authentication flow"""
        try:
            print("Step 1: Loading PSE&G main page...")
            response = self.session.get("https://nj.pseg.com", timeout=15)
            if response.status_code != 200:
                print(f"Failed to load PSE&G main page: {response.status_code}")
                return False
            
            print(f"Successfully loaded PSE&G main page (status: {response.status_code})")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            login_links = soup.find_all('a', href=True)
            oauth_url = None
            
            for link in login_links:
                href = link.get('href', '')
                text = link.get_text(strip=True).lower()
                if ('login' in text or 'log in' in text or 'sign in' in text) and href:
                    if href.startswith('http'):
                        oauth_url = href
                    elif href.startswith('/'):
                        oauth_url = f"https://nj.pseg.com{href}"
                    break
            
            if not oauth_url:
                print("Could not find login URL on main page")
                return False
            
            print(f"Step 2: Found login URL: {oauth_url}")
            
            response = self.session.get(oauth_url, timeout=15)
            if response.status_code != 200:
                print(f"Failed to load OAuth login page: {response.status_code}")
                return False
            
            print("Step 3: Successfully loaded OAuth login page")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            forms = soup.find_all('form')
            if not forms:
                print("No login form found on OAuth page")
                return False
            form = forms[0]
            
            form_action = str(form.get('action') or '')
            if isinstance(form_action, str) and form_action.startswith('/'):
                base_url = '/'.join(response.url.split('/')[:3])
                form_action = base_url + form_action
            elif isinstance(form_action, str) and not form_action.startswith('http'):
                form_action = response.url.rsplit('/', 1)[0] + '/' + form_action
            
            form_data = {}
            for hidden_input in form.find_all('input', {'type': 'hidden'}):
                name = hidden_input.get('name')
                value = hidden_input.get('value', '')
                if name:
                    form_data[name] = value
            
            username_field = form.find('input', {'name': 'identifier'}) or form.find('input', {'name': 'username'})
            if username_field:
                field_name = username_field.get('name')
                form_data[field_name] = username
                print(f"Found username field: {field_name}")
            else:
                print("Could not find username field in login form")
                print("Available input fields:")
                for inp in form.find_all('input'):
                    print(f"  - name: {inp.get('name')}, type: {inp.get('type')}")
                return False
            
            print("Step 4: Submitting username...")
            
            response = self.session.post(form_action, data=form_data, timeout=15)
            if response.status_code not in [200, 302]:
                print(f"Username submission failed: {response.status_code}")
                return False
            
            if response.status_code == 302:
                redirect_url = response.headers.get('Location')
                if redirect_url:
                    if redirect_url.startswith('/'):
                        base_url = '/'.join(response.url.split('/')[:3])
                        redirect_url = base_url + redirect_url
                    response = self.session.get(redirect_url, timeout=15)
            
            print("Step 5: Looking for password form...")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            password_forms = soup.find_all('form')
            if not password_forms:
                print("No password form found")
                return False
            password_form = password_forms[0]
            
            password_action = str(password_form.get('action') or '')
            if isinstance(password_action, str) and password_action.startswith('/'):
                base_url = '/'.join(response.url.split('/')[:3])
                password_action = base_url + password_action
            elif isinstance(password_action, str) and not password_action.startswith('http'):
                password_action = response.url.rsplit('/', 1)[0] + '/' + password_action
            
            password_data = {}
            for hidden_input in password_form.find_all('input', {'type': 'hidden'}):
                name = hidden_input.get('name')
                value = hidden_input.get('value', '')
                if name:
                    password_data[name] = value
            
            password_field = password_form.find('input', {'name': 'credentials.passcode'}) or password_form.find('input', {'name': 'password'})
            if password_field:
                password_data['credentials.passcode'] = password
            else:
                print("Could not find password field in form")
                return False
            
            print("Step 6: Submitting password...")
            
            response = self.session.post(password_action, data=password_data, timeout=15)
            if response.status_code not in [200, 302]:
                print(f"Password submission failed: {response.status_code}")
                return False
            
            final_url = response.url if hasattr(response, 'url') else ''
            response_text = response.text.lower()
            
            success_indicators = [
                'myaccount' in final_url.lower(),
                'account' in final_url.lower(),
                'dashboard' in response_text,
                'welcome' in response_text,
                'usage' in response_text and 'energy' in response_text
            ]
            
            if any(success_indicators):
                print("Step 7: Login successful - found success indicators")
                return True
            else:
                print("Step 7: Login may have failed - no success indicators found")
                print(f"Final URL: {final_url}")
                return False
            
        except Exception as e:
            print(f"Requests-based login failed: {str(e)}")
            return False
    
    def login(self, username: str, password: str) -> bool:
        try:
            self.driver.get("https://nj.pseg.com")
            
            login_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'LOGIN') or contains(text(), 'Log In')]"))
            )
            login_button.click()
            
            username_field = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.NAME, "identifier"))
            )
            username_field.clear()
            username_field.send_keys(username)
            
            next_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Next']"))
            )
            next_button.click()
            
            password_field = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.NAME, "credentials.passcode"))
            )
            password_field.clear()
            password_field.send_keys(password)
            
            signin_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Sign In']"))
            )
            signin_button.click()
            
            WebDriverWait(self.driver, 20).until(
                EC.any_of(
                    EC.url_contains("myaccount.pseg.com"),
                    EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'My Account') or contains(text(), 'Usage') or contains(text(), 'Bill')]")),
                    EC.presence_of_element_located((By.CLASS_NAME, "account-dashboard")),
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'dashboard') or contains(@class, 'account')]"))
                )
            )
            
            return True
            
        except (TimeoutException, NoSuchElementException) as e:
            print(f"Login failed: {str(e)}")
            return False
    
    def navigate_to_usage_data(self) -> bool:
        try:
            usage_links = [
                "//a[contains(text(), 'Usage') or contains(text(), 'Energy Usage')]",
                "//a[contains(text(), 'My Usage')]",
                "//a[contains(text(), 'Energy History')]",
                "//a[contains(text(), 'Usage History')]"
            ]
            
            for link_xpath in usage_links:
                try:
                    usage_link = self.driver.find_element(By.XPATH, link_xpath)
                    usage_link.click()
                    time.sleep(3)
                    break
                except NoSuchElementException:
                    continue
            
            WebDriverWait(self.driver, 10).until(
                EC.any_of(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'usage') or contains(@class, 'energy')]")),
                    EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'usage') or contains(@class, 'bill')]"))
                )
            )
            
            return True
            
        except (TimeoutException, NoSuchElementException) as e:
            print(f"Failed to navigate to usage data: {str(e)}")
            return False
    
    def extract_usage_data(self) -> List[UsageData]:
        try:
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            usage_data = []
            
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header row
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        date_text = cells[0].get_text(strip=True)
                        usage_text = cells[1].get_text(strip=True)
                        
                        try:
                            date_formats = ['%m/%d/%Y', '%Y-%m-%d', '%b %Y', '%B %Y']
                            parsed_date = None
                            for fmt in date_formats:
                                try:
                                    parsed_date = datetime.strptime(date_text, fmt)
                                    break
                                except ValueError:
                                    continue
                            
                            if parsed_date:
                                usage_match = re.search(r'(\d+\.?\d*)', usage_text.replace(',', ''))
                                if usage_match:
                                    usage_kwh = float(usage_match.group(1))
                                    
                                    cost = None
                                    if len(cells) > 2:
                                        cost_text = cells[2].get_text(strip=True)
                                        cost_match = re.search(r'\$?(\d+\.?\d*)', cost_text.replace(',', ''))
                                        if cost_match:
                                            cost = float(cost_match.group(1))
                                    
                                    usage_data.append(UsageData(
                                        date=parsed_date.strftime('%Y-%m-%d'),
                                        usage_kwh=usage_kwh,
                                        cost=cost,
                                        billing_period=date_text
                                    ))
                        except (ValueError, AttributeError):
                            continue
            
            if not usage_data:
                usage_elements = soup.find_all(['div', 'span'], text=re.compile(r'\d+\.?\d*\s*(kWh|kwh|KWH)'))
                for element in usage_elements:
                    pass
            
            usage_data.sort(key=lambda x: x.date, reverse=True)
            
            twelve_months_ago = datetime.now() - timedelta(days=365)
            filtered_data = [
                data for data in usage_data 
                if datetime.strptime(data.date, '%Y-%m-%d') >= twelve_months_ago
            ]
            
            return filtered_data
            
        except Exception as e:
            print(f"Failed to extract usage data: {str(e)}")
            return []
    
    def close(self):
        if self.driver:
            self.driver.quit()

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.post("/api/pseg/login-test")
async def test_login(credentials: PSEGCredentials):
    scraper = PSEGScraper()
    try:
        print("Testing login with requests method only...")
        success = scraper.login_with_requests(credentials.username, credentials.password)
        
        if success:
            return {"success": True, "message": "Login successful"}
        else:
            return {"success": False, "message": "Login failed - please check your credentials"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login test failed: {str(e)}")
    
    finally:
        scraper.close()

@app.post("/api/pseg/usage", response_model=PSEGUsageResponse)
async def get_usage_data(credentials: PSEGCredentials):
    scraper = PSEGScraper()
    try:
        print("Attempting requests-based login...")
        login_success = scraper.login_with_requests(credentials.username, credentials.password)
        
        if not login_success:
            print("Requests-based login failed - Selenium fallback temporarily disabled for debugging")
            print("This should prevent memory issues while we debug the requests method")
            return PSEGUsageResponse(
                success=False,
                data=[],
                message="Failed to login to PSE&G account. Please check your credentials.",
                total_usage=0.0,
                average_monthly_usage=0.0
            )
        
        nav_success = scraper.navigate_to_usage_data()
        if not nav_success:
            return PSEGUsageResponse(
                success=False,
                data=[],
                message="Successfully logged in but could not find usage data page.",
                total_usage=0.0,
                average_monthly_usage=0.0
            )
        
        usage_data = scraper.extract_usage_data()
        
        if not usage_data:
            return PSEGUsageResponse(
                success=False,
                data=[],
                message="Successfully accessed account but no usage data found for the last 12 months.",
                total_usage=0.0,
                average_monthly_usage=0.0
            )
        
        total_usage = sum(data.usage_kwh for data in usage_data)
        average_monthly_usage = total_usage / max(len(usage_data), 1)
        
        return PSEGUsageResponse(
            success=True,
            data=usage_data,
            message=f"Successfully retrieved {len(usage_data)} months of usage data.",
            total_usage=total_usage,
            average_monthly_usage=average_monthly_usage
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve usage data: {str(e)}")
    
    finally:
        scraper.close()

@app.get("/api/pseg/sample-data")
async def get_sample_data():
    """
    Returns sample usage data for demonstration purposes.
    This endpoint is for testing the frontend without requiring actual PSE&G credentials.
    """
    sample_data = []
    base_date = datetime.now()
    
    for i in range(12):
        month_date = base_date - timedelta(days=30 * i)
        base_usage = 800 if month_date.month in [6, 7, 8, 12, 1, 2] else 600  # Higher in summer/winter
        usage = base_usage + (i * 10) + (50 * (0.5 - abs(0.5 - (i / 12))))  # Some variation
        
        sample_data.append(UsageData(
            date=month_date.strftime('%Y-%m-%d'),
            usage_kwh=round(usage, 1),
            cost=round(usage * 0.12, 2),  # Approximate cost per kWh
            billing_period=month_date.strftime('%B %Y')
        ))
    
    total_usage = sum(data.usage_kwh for data in sample_data)
    average_monthly_usage = total_usage / len(sample_data)
    
    return PSEGUsageResponse(
        success=True,
        data=sample_data,
        message="Sample data for demonstration purposes",
        total_usage=total_usage,
        average_monthly_usage=average_monthly_usage
    )
