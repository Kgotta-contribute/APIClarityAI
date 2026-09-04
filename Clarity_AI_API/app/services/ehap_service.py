
import requests

from app.config.config import settings

from typing import Optional

import os

import logging

 

logger = logging.getLogger(__name__)

 

class EHAPService:

    def __init__(self):

        self.auth_url = settings.ehap_auth_url

        self.online_url = settings.ehap_online_url

        self.chat_url = settings.ehap_chat_url

        self.client_id = settings.ehap_client_id

        self.client_secret = settings.ehap_client_secret

        self.cert_file_path = os.path.join(os.path.dirname(__file__), "..", "config", "root_chain.pem")

   

    def get_access_token(self) -> Optional[str]:

        """

        Authenticate with EHAP and get access token.

       

        Returns:

            Access token string if successful, None otherwise

        """

        headers = {

            "Content-Type": "application/json",

            "Access-Control-Allow-Credentials": "true"

        }

       

        payload = {

            "client_id": self.client_id,

            "client_secret": self.client_secret,

            "grant_type": "client_credentials"

        }

       

        try:

            res = requests.post(

                url=self.auth_url,

                headers=headers,

                json=payload,

                verify=self.cert_file_path,

                timeout=30  # 30 second timeout for authentication

            )

            if res.status_code == 200:

                return res.json().get("access_token")

            else:

                print(f"EHAP authentication failed: {res.status_code} - {res.text}")

                return None

        except requests.exceptions.Timeout as e:

            print(f"EHAP authentication timeout after 30 seconds: {str(e)}")

            logger.error(f"EHAP authentication timeout after 30 seconds: {str(e)}", exc_info=True)

            return None

        except Exception as e:

            print(f"Error during EHAP authentication: {e}")

            logger.error(f"Error during EHAP authentication: {str(e)}", exc_info=True)

            return None

   

    def chat_with_files(self, files: list[tuple[str, bytes]], prompt: str) -> Optional[dict]:

        """

        Send prompt to EHAP chat endpoint with file contents embedded in the prompt.

       

        Args:

            files: List of tuples containing (file_name, file_content) - not used in new API but kept for compatibility

            prompt: Complete formatted prompt with file contents, history, and question

       

        Returns:

            Response dict with 'text' field if successful, error dict otherwise

        """

        access_token = self.get_access_token()

       

        if not access_token:

            return {"error": "Failed to authenticate with EHAP"}

       

        headers = {

            "Content-Type": "application/json",

            "Authorization": f"Bearer {access_token}",

            "Connection": "close"

        }

       

        payload = {

            "enableWebSearch": False,

            "messages": [

                {

                    "role": "user",

                    "content": prompt

                }

            ]

        }

       

        try:

            res = requests.post(

                url=self.chat_url,

                headers=headers,

                json=payload,

                verify=self.cert_file_path,

                timeout=60

            )

           

            if res.status_code == 200:

                response_data = res.json()

                # Extract text from response structure: response.message.content

                text_content = response_data.get("message", {}).get("content", "")

               

                if text_content:

                    return {"text": text_content}

                else:

                    print(f"EHAP chat response missing content: {response_data}")

                    return {"error": "Empty response", "details": "EHAP returned a response but content was empty"}

            else:

                print(f"EHAP chat completion failed: {res.status_code} - {res.text}")

                return {"error": f"EHAP API error: {res.status_code}", "details": res.text}

        except requests.exceptions.Timeout as e:

            # error_msg = f"EHAP request timeout after 60 seconds: {str(e)}"

            # print(error_msg)

            logger.error(f"EHAP request timeout after 60 seconds: {str(e)}", exc_info=True)

            return {"error": "Request timeout", "details": "EHAP service took longer than 60 seconds to respond. Please try again or contact support if the issue persists."}

        except Exception as e:

            # print(f"Error during EHAP chat completion: {e}")

            logger.error(f"Error during EHAP chat completion: {str(e)}", exc_info=True)

            return {"error": f"Request failed: {str(e)}"}

 

ehap_service = EHAPService()