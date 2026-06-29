import re
import logging
import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class DtekClient:
    def __init__(self):
        # Cache sessions per base_url: { base_url: { "client": httpx.AsyncClient, "csrf_token": str } }
        self.sessions = {}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "uk,en;q=0.9",
        }

    def _get_dso_config(self, dso_id: int) -> dict:
        """Resolve DTEK base URL and default city for a given DSO ID."""
        if dso_id == 902:  # Kyiv City
            return {"base_url": "https://www.dtek-kem.com.ua", "default_city": "м. Київ"}
        elif dso_id == 301:  # Dnipro
            return {"base_url": "https://www.dtek-dnem.com.ua", "default_city": "Дніпро"}
        elif dso_id == 901:  # Kyiv Regional (Oblast)
            return {"base_url": "https://www.dtek-krem.com.ua", "default_city": ""}
        
        # Fallback default
        return {"base_url": "https://www.dtek-kem.com.ua", "default_city": "м. Київ"}

    async def _init_session(self, base_url: str):
        """Perform initial requests to bypass Incapsula WAF and parse Yii's CSRF token."""
        logger.info(f"Initializing DTEK session for: {base_url}")
        
        # Initialize AsyncClient with default headers and cookies enabled
        client = httpx.AsyncClient(headers=self.headers, follow_redirects=True, timeout=15.0)
        
        try:
            # 1. First GET to receive WAF challenge and plant session/visid cookies
            await client.get(f"{base_url}/ua/shutdowns")
            
            # 2. First dummy POST (without X-Requested-With to prevent AJAX text response) to trigger Yii 400 page
            post_headers = self.headers.copy()
            post_headers["Referer"] = f"{base_url}/ua/shutdowns"
            r = await client.post(f"{base_url}/ua/ajax", data={"method": "getHomeNum"}, headers=post_headers)
            
            # 3. Parse CSRF token from Yii's HTML error page
            csrf_match = re.search(r'name="csrf-token" content="([^"]+)"', r.text)
            if not csrf_match:
                logger.error(f"Could not parse CSRF token from Yii layout. Response: {r.text[:300]}")
                await client.aclose()
                raise HTTPException(
                    status_code=502,
                    detail="Failed to parse CSRF verification token from DTEK portal."
                )
            
            csrf_token = csrf_match.group(1)
            logger.info(f"Successfully established DTEK WAF session with CSRF token for {base_url}")
            
            # 4. Save session context
            self.sessions[base_url] = {
                "client": client,
                "csrf_token": csrf_token
            }
        except Exception as e:
            logger.error(f"DTEK session initialization failed for {base_url}: {e}")
            if not isinstance(e, HTTPException):
                raise HTTPException(status_code=502, detail=f"Failed to initialize DTEK WAF session: {str(e)}")
            raise e

    async def fetch_live_status(self, dso_id: int, city: str, street: str, retry_on_expire: bool = True) -> dict:
        """Fetch the live status of all houses on a street from the DTEK AJAX endpoint."""
        config = self._get_dso_config(dso_id)
        base_url = config["base_url"]
        
        # Ensure session exists
        if base_url not in self.sessions:
            await self._init_session(base_url)
            
        session_ctx = self.sessions[base_url]
        client = session_ctx["client"]
        csrf_token = session_ctx["csrf_token"]
        
        # Formulate query payload in Yii serialized array format
        post_data = {
            "method": "getHomeNum",
            "data[0][name]": "city",
            "data[0][value]": city,
            "data[1][name]": "street",
            "data[1][value]": street,
            "_csrf-dtek-kem": csrf_token
        }
        
        headers = self.headers.copy()
        headers["Referer"] = f"{base_url}/ua/shutdowns"
        headers["X-CSRF-Token"] = csrf_token
        
        try:
            r = await client.post(f"{base_url}/ua/ajax", data=post_data, headers=headers)
            
            # WAF Block check (returns 212-byte template or Incapsula iframe)
            if r.status_code == 200 and ("_Incapsula_Resource" in r.text or (len(r.text) < 1000 and "result" not in r.text)):
                if retry_on_expire:
                    logger.warning("DTEK session cookie expired or blocked. Retrying...")
                    await client.aclose()
                    del self.sessions[base_url]
                    return await self.fetch_live_status(dso_id, city, street, retry_on_expire=False)
                else:
                    raise Exception("Request blocked by DTEK Incapsula security system.")
            
            # CSRF/Yii mismatch check
            if r.status_code == 400:
                if retry_on_expire:
                    logger.warning("DTEK returned 400 Bad Request. CSRF token may have expired. Re-initializing...")
                    await client.aclose()
                    del self.sessions[base_url]
                    return await self.fetch_live_status(dso_id, city, street, retry_on_expire=False)
                else:
                    raise Exception("Yii CSRF token validation failed repeatedly.")
            
            r.raise_for_status()
            
            # Verify and parse JSON response
            resp_data = r.json()
            if not resp_data.get("result"):
                error_msg = resp_data.get("text") or resp_data.get("error") or "Unknown API Error"
                raise Exception(f"DTEK AJAX returned result=false: {error_msg}")
                
            return resp_data
            
        except Exception as e:
            logger.error(f"DTEK AJAX query failed for city='{city}', street='{street}': {e}")
            if retry_on_expire:
                # Close client, clear cache, and retry once
                try:
                    await client.aclose()
                except:
                    pass
                if base_url in self.sessions:
                    del self.sessions[base_url]
                return await self.fetch_live_status(dso_id, city, street, retry_on_expire=False)
            raise HTTPException(status_code=502, detail=f"Failed to query live DTEK status: {str(e)}")

    async def close(self):
        """Close all cached HTTPX client connections."""
        for base_url, session in list(self.sessions.items()):
            try:
                await session["client"].aclose()
            except:
                pass
        self.sessions.clear()

dtek_client = DtekClient()
