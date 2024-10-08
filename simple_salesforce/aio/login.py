"""Async Login classes and functions for Simple-Salesforce

Heavily Modified from RestForce 1.0.0
"""

import aiofiles
import base64
from datetime import datetime, timedelta, timezone
from html import escape, unescape
from json.decoder import JSONDecodeError
import typing
import warnings

import jwt
import httpx
from httpx import Headers

from simple_salesforce.api import DEFAULT_API_VERSION
from simple_salesforce.login import DEFAULT_CLIENT_ID_PREFIX
from simple_salesforce.exceptions import SalesforceAuthenticationFailed
from simple_salesforce.util import Proxies, getUniqueElementValueFromXmlString


# pylint: disable=invalid-name,too-many-arguments,too-many-locals
async def AsyncSalesforceLogin(
    username: str | None = None,
    password: str | None = None,
    security_token: str | None = None,
    organizationId: str | None = None,
    sf_version: str = DEFAULT_API_VERSION,
    proxies: Proxies | None = None,
    session: httpx.AsyncClient | None = None,
    session_factory: typing.Callable[[], httpx.AsyncClient] | None = None,
    client_id: str | None = None,
    domain: str | None = None,
    instance_url: str | None = None,
    consumer_key: str | None = None,
    consumer_secret: str | None = None,
    privatekey_file: str | None = None,
    privatekey: str | None = None,
) -> typing.Tuple[str, str]:
    """Return a tuple of `(session_id, sf_instance)` where `session_id` is the
    session ID to use for authentication to Salesforce and `sf_instance` is
    the domain of the instance of Salesforce to use for the session.

    Arguments:

    * username -- the Salesforce username to use for authentication
    * password -- the password for the username
    * security_token -- the security token for the username
    * organizationId -- the ID of your organization
            NOTE: security_token an organizationId are mutually exclusive
    * sf_version -- the version of the Salesforce API to use, for example
                    "27.0"
    * proxies -- the optional map of scheme to proxy server
    * session -- Custom requests session, created in calling code. This
                 enables the use of requets Session features not otherwise
                 exposed by simple_salesforce.
    * client_id -- the ID of this client
    * domain -- The domain to using for connecting to Salesforce. Use
                common domains, such as 'login' or 'test', or
                Salesforce My domain. If not used, will default to
                'login'.
    * instance_url -- Non-standard instance url (instance.my) used
                for connecting to Salesforce with JWT tokens.
    * consumer_key -- the consumer key generated for the user/app
    * consumer_secret -- the consumer secret generated for the user/app
    * privatekey_file -- the path to the private key file used
                         for signing the JWT token.
    * privatekey -- the private key to use
                         for signing the JWT token.
    """

    if session is not None:
        warnings.warn("The session keyword argument for async clients is deprecated")

    if domain is None:
        domain = "login"

    if sf_version.startswith("v"):
        error_msg = (
            f"Invalid sf_version specified ({sf_version}). Version should not "
            "contain a leading 'v'"
        )
        raise ValueError(error_msg)

    if client_id:
        client_id = f"{DEFAULT_CLIENT_ID_PREFIX}/{client_id}"
    else:
        client_id = DEFAULT_CLIENT_ID_PREFIX

    # pylint: disable=E0012,deprecated-method
    username = escape(username) if username else None
    password = escape(password) if password else None

    # Check if token authentication is used
    if security_token is not None:
        # Security Token Soap request body
        login_soap_request_body = f"""<?xml version="1.0" encoding="utf-8" ?>
<env:Envelope
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:partner.soap.sforce.com">
    <env:Header>
        <urn:CallOptions>
            <urn:client>{client_id}</urn:client>
            <urn:defaultNamespace>sf</urn:defaultNamespace>
        </urn:CallOptions>
    </env:Header>
    <env:Body>
        <n1:login xmlns:n1="urn:partner.soap.sforce.com">
            <n1:username>{username}</n1:username>
            <n1:password>{password}{security_token}</n1:password>
        </n1:login>
    </env:Body>
</env:Envelope>"""

    elif (
        username is not None
        and password is not None
        and consumer_key is not None
        and consumer_secret is not None
    ):
        token_data = {
            "grant_type": "password",
            "client_id": consumer_key,
            "client_secret": consumer_secret,
            "username": unescape(username),
            "password": unescape(password) if password else None,
        }
        return await token_login(
            f"https://{domain}.salesforce.com/services/oauth2/token",
            token_data,
            domain,
            consumer_key,
            None,
            proxies,
            session_factory=session_factory,
        )

    # Check if IP Filtering is used in conjunction with organizationId
    elif organizationId is not None:
        # IP Filtering Login Soap request body
        login_soap_request_body = f"""<?xml version="1.0" encoding="utf-8" ?>
<soapenv:Envelope
        xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:partner.soap.sforce.com">
    <soapenv:Header>
        <urn:CallOptions>
            <urn:client>{client_id}</urn:client>
            <urn:defaultNamespace>sf</urn:defaultNamespace>
        </urn:CallOptions>
        <urn:LoginScopeHeader>
            <urn:organizationId>{organizationId}</urn:organizationId>
        </urn:LoginScopeHeader>
    </soapenv:Header>
    <soapenv:Body>
        <urn:login>
            <urn:username>{username}</urn:username>
            <urn:password>{password}</urn:password>
        </urn:login>
    </soapenv:Body>
</soapenv:Envelope>"""
    elif username is not None and password is not None:
        # IP Filtering for non self-service users
        login_soap_request_body = f"""<?xml version="1.0" encoding="utf-8" ?>
<soapenv:Envelope
        xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:partner.soap.sforce.com">
    <soapenv:Header>
        <urn:CallOptions>
            <urn:client>{client_id}</urn:client>
            <urn:defaultNamespace>sf</urn:defaultNamespace>
        </urn:CallOptions>
    </soapenv:Header>
    <soapenv:Body>
        <urn:login>
            <urn:username>{username}</urn:username>
            <urn:password>{password}</urn:password>
        </urn:login>
    </soapenv:Body>
</soapenv:Envelope>"""
    elif (
        username is not None
        and consumer_key is not None
        and (privatekey_file is not None or privatekey is not None)
    ):
        token_domain = instance_url if instance_url is not None else domain
        expiration = datetime.now(timezone.utc) + timedelta(minutes=3)
        payload = {
            "iss": consumer_key,
            "sub": unescape(username),
            "aud": f"https://{domain}.salesforce.com",
            "exp": f"{expiration.timestamp():.0f}",
        }
        # PyJWT allows string or bytes for private key
        key: str | bytes
        if privatekey_file is not None:
            async with aiofiles.open(privatekey_file, "rb") as key_file:
                key = await key_file.read()
        else:
            key = privatekey  # type: ignore[assignment]

        assertion = jwt.encode(payload, key, algorithm="RS256")

        token_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }

        return await token_login(
            f"https://{token_domain}.salesforce.com/services/oauth2/token",
            token_data,
            domain,
            consumer_key,
            None,
            proxies,
            session_factory=session_factory,
        )
    elif (
        consumer_key is not None
        and consumer_secret is not None
        and domain is not None
        and domain not in ("login", "test")
    ):
        token_data = {"grant_type": "client_credentials"}
        authorization = f"{consumer_key}:{consumer_secret}"
        encoded = base64.b64encode(authorization.encode()).decode()
        headers = Headers({"Authorization": f"Basic {encoded}"})
        return await token_login(
            f"https://{domain}.salesforce.com/services/oauth2/token",
            token_data,
            domain,
            consumer_key,
            headers,
            proxies,
            session_factory=session_factory,
        )
    else:
        except_code = "INVALID AUTH"
        except_msg = (
            "You must submit either a security token or organizationId for "
            "authentication"
        )
        raise SalesforceAuthenticationFailed(except_code, except_msg)

    soap_url = f"https://{domain}.salesforce.com/services/Soap/u/{sf_version}"
    login_soap_request_headers = Headers({
        "content-type": "text/xml",
        "charset": "UTF-8",
        "SOAPAction": "login",
    })

    return await soap_login(
        soap_url,
        login_soap_request_body,
        login_soap_request_headers,
        proxies,
        session_factory=session_factory,
    )


async def soap_login(
    soap_url: str,
    request_body: str,
    headers: Headers | None,
    proxies: Proxies | None,
    session_factory: typing.Callable[[], httpx.AsyncClient] | None = None,
) -> typing.Tuple[str, str]:
    """Process SOAP specific login workflow."""
    if session_factory:
        client = session_factory()
    elif proxies and not session_factory:
        client = httpx.AsyncClient(proxies=proxies)
    else:
        client = httpx.AsyncClient()

    async with client as session:
        response = await session.post(soap_url, content=request_body, headers=headers)

    if response.status_code != 200:
        except_code = getUniqueElementValueFromXmlString(
            response.content, "sf:exceptionCode"
        )
        except_msg = getUniqueElementValueFromXmlString(
            response.content, "sf:exceptionMessage"
        ) or "Unknown Error"
        raise SalesforceAuthenticationFailed(except_code, except_msg)

    session_id = getUniqueElementValueFromXmlString(response.content, "sessionId") or ""
    server_url = getUniqueElementValueFromXmlString(response.content, "serverUrl") or ""

    sf_instance = (
        server_url.replace("http://", "")
        .replace("https://", "")
        .split("/")[0]
        .replace("-api", "")
    )

    return session_id, sf_instance


async def token_login(
    token_url: str,
    token_data: typing.Dict[str, typing.Any],
    domain: str,
    consumer_key: str,
    headers: Headers | None,
    proxies: Proxies | None,
    session_factory: typing.Callable[[], httpx.AsyncClient] | None = None,
) -> typing.Tuple[str, str]:
    """Process OAuth 2.0 JWT Bearer Token Flow."""
    if session_factory:
        client = session_factory()
    elif proxies and not session_factory:
        client = httpx.AsyncClient(proxies=proxies)
    else:
        client = httpx.AsyncClient()

    async with client as session:
        response = await session.post(token_url, data=token_data, headers=headers)

    try:
        json_response = response.json()
    except JSONDecodeError as exc:
        raise SalesforceAuthenticationFailed(
            response.status_code, response.text
        ) from exc

    if response.status_code != 200:
        except_code = json_response.get("error")
        except_msg = json_response.get("error_description")
        if except_msg == "user hasn't approved this consumer":
            auth_url = (
                f"https://{domain}.salesforce.com/services/oauth2/"
                "authorize?response_type=code&client_id="
                f"{consumer_key}&redirect_uri=<approved URI>"
            )
            warnings.warn(
                f"""
    If your connected app policy is set to "All users may
    self-authorize", you may need to authorize this
    application first. Browse to
    {auth_url}
    in order to Allow Access. Check first to ensure you have a valid
    <approved URI>."""
            )
        raise SalesforceAuthenticationFailed(except_code, except_msg)

    access_token = json_response.get("access_token")
    instance_url = json_response.get("instance_url")

    sf_instance = instance_url.replace("http://", "").replace("https://", "")

    return access_token, sf_instance
