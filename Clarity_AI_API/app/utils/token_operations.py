 

import jwt

from jwt import PyJWKClient

from jwt import PyJWKClient as origPyJWKClient

from jwt.exceptions import PyJWKClientError

import sys,os

import urllib.request

import json

import ssl

import logging

 

logger = logging.getLogger(__name__)

# from app.config.conf import AuthConfig

 

class PyJWKClient(origPyJWKClient):

    def fetch_data(self):

        gcontext = ssl._create_unverified_context()

        with urllib.request.urlopen(self.uri, context=gcontext) as response:

            return json.load(response)

       

class AuthConfig:

    algorithms = ["RS256"]

    jwks_endpoint = os.environ.get('jwks_endpoint','https://portalssoqa.elevancehealth.com/oauth2/ausefjy7k3J5S1AXz297/v1/keys')

    client_id = os.environ.get('client_id', '0oa1163b2oflT4JIA298')

    country = 'US'

 

def get_user_details(token):

    """

        Returns user details from the user's SSO bearer token

 

            Parameters:

                    token (str): the SSO token of the logged in user

 

            Returns:

                    user_info (dict): A dictionary with he following user details

                                        - first name

                                        - lastname

                                        - userId

                                        - emailID

                                        - GroupNames

    """

    try:

        id_token = token.split(' ')[1]

        jwks_client = PyJWKClient(AuthConfig.jwks_endpoint)

        signing_key = jwks_client.get_signing_key_from_jwt(id_token)

        user_details = jwt.decode(id_token,

        signing_key.key,

        algorithms=AuthConfig.algorithms,

        audience=AuthConfig.client_id,options={"verify_exp": False})

        ## use filteredgroups to get rid of OKTA bug

        groupnames = user_details.get("filteredgroups", [])

        user_info = {

            "userName": user_details.get("displayName",""),

            "domainID": user_details.get("domainID", ""),

            "emailID": user_details.get("mail", ""),

            "groupNames": groupnames

        }

        return user_info

    except Exception as e:

        # raise e

        logger.error(f"Token validation failed: {str(e)}", exc_info=True)

        raise

if __name__ == "__main__":

    id_token = ' '

    user_info = get_user_details(id_token)

    print(user_info)

 