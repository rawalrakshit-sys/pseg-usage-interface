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
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--memory-pressure-off")
        chrome_options.add_argument("--max_old_space_size=128")
        chrome_options.add_argument("--aggressive-cache-discard")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-logging")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-component-extensions-with-background-pages")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--disable-dev-tools")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        return self.driver
    
    def login_with_requests(self, username: str, password: str) -> bool:
        """Memory-efficient authentication using session management and OAuth2 flow simulation"""
        try:
            print("Step 1: Checking PSE&G service availability...")
            response = self.session.get("https://nj.pseg.com", timeout=10)
            if response.status_code != 200:
                print(f"PSE&G service unavailable: {response.status_code}")
                return False
            
            print("Step 2: Attempting to locate OAuth2 authorization endpoint...")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            login_links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                if any(keyword in href.lower() for keyword in ['login', 'auth', 'oauth', 'signin']):
                    if href.startswith('/'):
                        href = 'https://nj.pseg.com' + href
                    elif not href.startswith('http'):
                        href = 'https://nj.pseg.com/' + href
                    login_links.append(href)
            
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    import re
                    oauth_matches = re.findall(r'https?://[^\s"\']+(?:oauth|auth|login)[^\s"\']*', script.string)
                    login_links.extend(oauth_matches)
            
            print(f"Step 3: Found {len(login_links)} potential authentication endpoints")
            
            if not login_links:
                print("No OAuth2 endpoints found - attempting direct form submission...")
                return self._attempt_direct_form_auth(username, password, response)
            
            for auth_url in login_links[:3]:  # Limit to first 3 to avoid excessive requests
                print(f"Step 4: Trying authentication endpoint: {auth_url}")
                try:
                    auth_response = self.session.get(auth_url, timeout=10)
                    if auth_response.status_code == 200:
                        return self._process_oauth_flow(username, password, auth_response)
                except Exception as e:
                    print(f"Failed to access {auth_url}: {e}")
                    continue
            
            print("Step 5: All OAuth endpoints failed, falling back to form detection...")
            return self._attempt_direct_form_auth(username, password, response)
            
        except Exception as e:
            print(f"Memory-efficient authentication failed: {str(e)}")
            return False
    
    def _attempt_direct_form_auth(self, username: str, password: str, response) -> bool:
        """Attempt direct form-based authentication"""
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            forms = soup.find_all('form')
            login_form = None
            
            for form in forms:
                inputs = form.find_all('input')
                has_password = any(inp.get('type') == 'password' or 'password' in inp.get('name', '').lower() 
                                 for inp in inputs)
                has_username = any('user' in inp.get('name', '').lower() or 'email' in inp.get('name', '').lower() 
                                 for inp in inputs)
                
                if has_password or has_username:
                    login_form = form
                    break
            
            if not login_form:
                print("No login form found on main page")
                return False
            
            action = login_form.get('action', '')
            method = login_form.get('method', 'POST').upper()
            
            if action.startswith('/'):
                action = 'https://nj.pseg.com' + action
            elif not action.startswith('http'):
                action = response.url + '/' + action if action else response.url
            
            form_data = {}
            
            for hidden_input in login_form.find_all('input', {'type': 'hidden'}):
                name = hidden_input.get('name')
                value = hidden_input.get('value', '')
                if name:
                    form_data[name] = value
            
            username_field = (login_form.find('input', {'name': 'identifier'}) or 
                            login_form.find('input', {'name': 'username'}) or
                            login_form.find('input', {'name': 'email'}) or
                            login_form.find('input', {'type': 'email'}))
            
            if username_field:
                form_data[username_field.get('name')] = username
            
            password_field = (login_form.find('input', {'name': 'credentials.passcode'}) or
                            login_form.find('input', {'name': 'password'}) or
                            login_form.find('input', {'type': 'password'}))
            
            if password_field:
                form_data[password_field.get('name')] = password
            
            print(f"Submitting form to: {action}")
            print(f"Form fields: {list(form_data.keys())}")
            
            if method == 'GET':
                auth_response = self.session.get(action, params=form_data, timeout=15)
            else:
                auth_response = self.session.post(action, data=form_data, timeout=15)
            
            return self._check_authentication_success(auth_response)
            
        except Exception as e:
            print(f"Direct form authentication failed: {e}")
            return False
    
    def _process_oauth_flow(self, username: str, password: str, auth_response) -> bool:
        """Process OAuth2 authentication flow"""
        try:
            soup = BeautifulSoup(auth_response.text, 'html.parser')
            
            forms = soup.find_all('form')
            
            for form in forms:
                action = form.get('action', '')
                if action.startswith('/'):
                    action = 'https://nj.pseg.com' + action
                elif not action.startswith('http'):
                    base_url = '/'.join(auth_response.url.split('/')[:3])
                    action = base_url + '/' + action if action else auth_response.url
                
                form_data = {}
                
                for hidden_input in form.find_all('input', {'type': 'hidden'}):
                    name = hidden_input.get('name')
                    value = hidden_input.get('value', '')
                    if name:
                        form_data[name] = value
                
                username_input = (form.find('input', {'name': 'identifier'}) or
                                form.find('input', {'name': 'username'}) or  
                                form.find('input', {'name': 'email'}))
                
                if username_input:
                    form_data[username_input.get('name')] = username
                
                password_input = (form.find('input', {'name': 'credentials.passcode'}) or
                                form.find('input', {'name': 'password'}))
                
                if password_input:
                    form_data[password_input.get('name')] = password
                
                if form_data:
                    print(f"Submitting OAuth form to: {action}")
                    oauth_response = self.session.post(action, data=form_data, timeout=15)
                    
                    if self._check_authentication_success(oauth_response):
                        return True
            
            return False
            
        except Exception as e:
            print(f"OAuth flow processing failed: {e}")
            return False
    
    def _check_authentication_success(self, response) -> bool:
        """Check if authentication was successful"""
        try:
            final_url = getattr(response, 'url', '')
            response_text = response.text.lower()
            
            success_indicators = [
                'myaccount' in final_url.lower(),
                'account' in final_url.lower() and 'login' not in final_url.lower(),
                'dashboard' in response_text,
                'welcome' in response_text and 'login' not in response_text,
                'usage' in response_text and 'energy' in response_text,
                'billing' in response_text and 'account' in response_text,
                response.status_code in [200, 302] and 'error' not in response_text
            ]
            
            failure_indicators = [
                'invalid' in response_text and ('credential' in response_text or 'password' in response_text),
                'incorrect' in response_text,
                'login failed' in response_text,
                'authentication failed' in response_text,
                response.status_code in [401, 403]
            ]
            
            if any(failure_indicators):
                print("Authentication failed - found failure indicators")
                return False
            
            if any(success_indicators):
                print("Authentication successful - found success indicators")
                return True
            
            print(f"Authentication status unclear - URL: {final_url}, Status: {response.status_code}")
            return False
            
        except Exception as e:
            print(f"Failed to check authentication success: {e}")
            return False
            
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
    
    def login(self, username: str, password: str) -> bool:
        try:
            if not self.driver:
                print("Driver not initialized, setting up...")
                self.setup_driver()
            
            print("Starting Selenium-based OAuth2 login...")
            self.driver.get("https://nj.pseg.com")
            
            print("Looking for login button...")
            login_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'LOGIN') or contains(text(), 'Log In')] | //a[contains(text(), 'LOGIN') or contains(text(), 'Log In')]"))
            )
            login_button.click()
            print("Clicked login button, waiting for OAuth page...")
            
            print("Looking for username field...")
            username_field = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.NAME, "identifier"))
            )
            username_field.clear()
            username_field.send_keys(username)
            print("Entered username, looking for Next button...")
            
            next_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Next'] | //button[contains(text(), 'Next')]"))
            )
            next_button.click()
            print("Clicked Next, waiting for password page...")
            
            print("Looking for password field...")
            password_field = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.NAME, "credentials.passcode"))
            )
            password_field.clear()
            password_field.send_keys(password)
            print("Entered password, looking for Sign In button...")
            
            signin_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Sign In'] | //button[contains(text(), 'Sign In')]"))
            )
            signin_button.click()
            print("Clicked Sign In, waiting for successful login...")
            
            WebDriverWait(self.driver, 20).until(
                EC.any_of(
                    EC.url_contains("myaccount.pseg.com"),
                    EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'My Account') or contains(text(), 'Usage') or contains(text(), 'Bill')]")),
                    EC.presence_of_element_located((By.CLASS_NAME, "account-dashboard")),
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'dashboard') or contains(@class, 'account')]"))
                )
            )
            
            print("Login successful!")
            return True
            
        except (TimeoutException, NoSuchElementException) as e:
            print(f"Selenium login failed: {str(e)}")
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
        print("Attempting memory-optimized Selenium authentication v4...")
        
        try:
            driver = scraper.setup_driver()
            print("Chrome driver initialized successfully with aggressive memory optimization")
            login_success = scraper.login(credentials.username, credentials.password)
        except Exception as selenium_error:
            print(f"Selenium initialization failed due to memory constraints: {selenium_error}")
            print("Falling back to lightweight authentication check...")
            login_success = scraper.login_with_requests(credentials.username, credentials.password)
        
        if not login_success:
            print("Authentication failed - either invalid credentials or memory constraints")
            return PSEGUsageResponse(
                success=False,
                data=[],
                message="Authentication failed. Please check your credentials or try again later due to system constraints.",
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
