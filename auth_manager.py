import boto3
from botocore.exceptions import ClientError
import logging
import time
import os
import json

# Try to import PyJWT correctly - handle case where 'jwt' package conflicts
try:
    import jwt
    # Verify it's PyJWT by checking for decode method
    if not hasattr(jwt, 'decode'):
        # Fallback: try to get PyJWT from a different import
        try:
            from jwt import decode as jwt_decode
            # Create a wrapper to use decode
            class JWTHelper:
                @staticmethod
                def decode(token, **kwargs):
                    return jwt_decode(token, **kwargs)
            jwt = JWTHelper()
        except ImportError:
            # Last resort: use base64 to decode token payload (less reliable but works)
            import base64
            jwt = None
except ImportError:
    jwt = None
    import base64

logger = logging.getLogger(__name__)

TOKEN_CACHE_FILE = '.token_cache'

def _decode_token_safe(token):
    """
    Safely decode JWT token to get expiration time.
    Handles different JWT library implementations.
    """
    if not token:
        return None
    
    try:
        # Try PyJWT decode first
        if jwt and hasattr(jwt, 'decode'):
            decoded = jwt.decode(token, options={"verify_signature": False})
            return decoded
    except Exception as e:
        logger.debug(f"PyJWT decode failed: {e}")
    
    # Fallback: manually decode JWT payload (base64)
    try:
        import base64
        # JWT format: header.payload.signature
        parts = token.split('.')
        if len(parts) >= 2:
            # Decode payload (second part)
            payload = parts[1]
            # Add padding if needed
            payload += '=' * (4 - len(payload) % 4)
            decoded_bytes = base64.urlsafe_b64decode(payload)
            decoded = json.loads(decoded_bytes.decode('utf-8'))
            return decoded
    except Exception as e:
        logger.debug(f"Manual decode failed: {e}")
    
    return None

def load_cached_token():
    """
    Load cached tokens from file.
    Returns tuple: (id_token, refresh_token, access_token) or (None, None, None)
    """
    try:
        if os.path.exists(TOKEN_CACHE_FILE):
            with open(TOKEN_CACHE_FILE, 'r') as f:
                cache = json.load(f)
                token = cache.get('token')  # Backward compatibility
                refresh_token = cache.get('refresh_token')
                access_token = cache.get('access_token')
                
                if token:
                    decoded = _decode_token_safe(token)
                    if decoded:
                        exp = decoded.get('exp', 0)
                        current_time = time.time()
                        # Add 5 minute buffer to avoid edge cases
                        if exp > (current_time + 300):  # 5 minutes buffer
                            logger.info(f"✅ Using cached token (expires in {int((exp - current_time) / 60)} minutes)")
                            return token, refresh_token, access_token
                        else:
                            logger.info(f"⚠️  Cached token expired or expiring soon (expires in {int((exp - current_time) / 60)} minutes)")
                            # Return tokens anyway - caller will handle refresh
                            return token, refresh_token, access_token
                    else:
                        logger.warning("⚠️  Could not decode cached token, will re-authenticate")
                else:
                    return None, None, None
    except Exception as e:
        logger.error(f"Error loading cached token: {e}")
    return None, None, None

def save_token_to_cache(id_token, refresh_token=None, access_token=None):
    """
    Save tokens to cache file.
    
    Args:
        id_token: The IdToken (required)
        refresh_token: The RefreshToken (optional, for auto-refresh)
        access_token: The AccessToken (optional)
    """
    try:
        cache_data = {'token': id_token}  # Keep 'token' key for backward compatibility
        
        if refresh_token:
            cache_data['refresh_token'] = refresh_token
        if access_token:
            cache_data['access_token'] = access_token
            
        with open(TOKEN_CACHE_FILE, 'w') as f:
            json.dump(cache_data, f)
        logger.debug("✅ Tokens saved to cache")
    except Exception as e:
        logger.error(f"Error saving token to cache: {e}")

def refresh_token(refresh_token_value, debugger=None):
    """
    Refresh IdToken using RefreshToken (no MFA required).
    
    Args:
        refresh_token_value: The RefreshToken from previous authentication
        debugger: Optional debugger instance
        
    Returns:
        Tuple (id_token, refresh_token, access_token) or (None, None, None) if failed
    """
    try:
        client = boto3.client('cognito-idp', region_name='us-east-1')
        response = client.initiate_auth(
            AuthFlow='REFRESH_TOKEN_AUTH',
            AuthParameters={
                'REFRESH_TOKEN': refresh_token_value
            },
            ClientId='6fk3ot5ut181jt7r2pdp9h6m5q'
        )
        
        if 'AuthenticationResult' in response:
            auth_result = response['AuthenticationResult']
            new_id_token = auth_result.get('IdToken')
            new_access_token = auth_result.get('AccessToken')
            # Note: RefreshToken may or may not be returned in refresh response
            # If not returned, keep using the old one
            new_refresh_token = auth_result.get('RefreshToken', refresh_token_value)
            
            logger.info("✅ Token refreshed successfully (no MFA required)")
            return new_id_token, new_refresh_token, new_access_token
        else:
            logger.error("❌ Refresh token response missing AuthenticationResult")
            return None, None, None
            
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'NotAuthorizedException':
            logger.warning("⚠️  Refresh token expired or invalid - will need to re-authenticate with MFA")
        else:
            logger.error(f"❌ Token refresh failed: {e}")
        if debugger:
            debugger.log_error("Token Refresh", e)
        return None, None, None
    except Exception as e:
        logger.error(f"❌ Token refresh failed: {e}")
        if debugger:
            debugger.log_error("Token Refresh", e)
        return None, None, None

def handle_auth_flow(username, password, debugger=None):
    max_attempts = 3
    
    # First try to use cached token
    cached_id_token, cached_refresh_token, cached_access_token = load_cached_token()
    if cached_id_token:
        # Check if token is expiring soon and refresh if needed
        decoded = _decode_token_safe(cached_id_token)
        if decoded:
            exp = decoded.get('exp', 0)
            current_time = time.time()
            time_until_exp = exp - current_time
            
            # If token expires in less than 15 minutes, try to refresh
            if time_until_exp < 900 and cached_refresh_token:  # 15 minutes
                logger.info(f"🔄 Token expiring in {int(time_until_exp / 60)} minutes - attempting auto-refresh...")
                new_id_token, new_refresh_token, new_access_token = refresh_token(cached_refresh_token, debugger)
                
                if new_id_token:
                    # Save refreshed tokens
                    save_token_to_cache(new_id_token, new_refresh_token, new_access_token)
                    logger.info("✅ Token auto-refreshed successfully")
                    return new_id_token
                else:
                    # Refresh failed, but token might still be valid for a few minutes
                    logger.warning("⚠️  Auto-refresh failed, using existing token (may expire soon)")
                    return cached_id_token
            else:
                # Token is still valid, return it
                return cached_id_token
        else:
            # Couldn't decode token, try refresh if available
            if cached_refresh_token:
                logger.info("🔄 Cached token invalid, attempting refresh...")
                new_id_token, new_refresh_token, new_access_token = refresh_token(cached_refresh_token, debugger)
                if new_id_token:
                    save_token_to_cache(new_id_token, new_refresh_token, new_access_token)
                    return new_id_token
            # Fall through to re-authentication
    
    try:
        client = boto3.client('cognito-idp', region_name='us-east-1')
        response = client.initiate_auth(
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': username,
                'PASSWORD': password
            },
            ClientId='6fk3ot5ut181jt7r2pdp9h6m5q'
        )
        
        if 'ChallengeName' in response:
            current_attempt = 0
            while current_attempt < max_attempts:
                try:
                    mfa_code = input("Enter MFA code: ")
                    challenge_response = client.respond_to_auth_challenge(
                        ClientId='6fk3ot5ut181jt7r2pdp9h6m5q',
                        ChallengeName=response['ChallengeName'],
                        Session=response['Session'],
                        ChallengeResponses={
                            'USERNAME': username,
                            'SOFTWARE_TOKEN_MFA_CODE': mfa_code
                        }
                    )
                    auth_result = challenge_response['AuthenticationResult']
                    id_token = auth_result.get('IdToken')
                    refresh_token_value = auth_result.get('RefreshToken')
                    access_token = auth_result.get('AccessToken')
                    
                    # Save all tokens for future auto-refresh
                    save_token_to_cache(id_token, refresh_token_value, access_token)
                    logger.info("✅ Authentication successful - tokens cached (including refresh token)")
                    return id_token
                except ClientError as e:
                    current_attempt += 1
                    if current_attempt >= max_attempts:
                        raise e
                    logger.error(f"Invalid MFA code. {max_attempts - current_attempt} attempts remaining.")
                    continue
        
        auth_result = response['AuthenticationResult']
        id_token = auth_result.get('IdToken')
        refresh_token_value = auth_result.get('RefreshToken')
        access_token = auth_result.get('AccessToken')
        
        # Save all tokens for future auto-refresh
        save_token_to_cache(id_token, refresh_token_value, access_token)
        logger.info("✅ Authentication successful - tokens cached (including refresh token)")
        return id_token
                
    except Exception as e:
        if debugger:
            debugger.log_error("Authentication", e)
        logger.error(f"Authentication failed: {str(e)}")
        return None

def get_auth_token(username, password, debugger=None):
    return handle_auth_flow(username, password, debugger)