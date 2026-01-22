import datetime
import hmac
import hashlib


def get_x_sn_date(dt: datetime.datetime) -> str:
    # Format the given datetime to the following example format:
    # Fri, 03 Mar 2017 04:36:28 GMT
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def hmac_sha256(secret: bytes, content: bytes) -> hmac.HMAC:
    signature = hmac.new(secret, content, digestmod=hashlib.sha256)
    return signature


def generate_signing_key(secret: str, dt: datetime.datetime, request: str) -> bytes:
    date = dt.strftime("%Y%m%d")
    inner_secret = f"SNWS2{secret}"

    inner = hmac_sha256(bytes(inner_secret, "latin-1"), bytes(date, "latin-1"))
    outer = hmac_sha256(inner.digest(), bytes(request, "latin-1"))

    return outer.digest()


def generate_signing_key_hex(secret: str, dt: datetime.datetime, request: str) -> str:
    return generate_signing_key(secret, dt, request).hex()


def generate_signing_message(
    dt: datetime.datetime, canonical_request_message: str
) -> str:
    # The final message to sign is 3 lines of data delimited by a newline character:
    # * The literal string SNWS2-HMAC-SHA256
    # * The request date, formatted as an UTC ISO8601 timestamp like YYYYMMDD'T'HHmmss'Z'
    # * The Hex(SHA256(CanonicalRequestMessage)) where CanonicalRequestMessage is the canonical request message string as described in the previous section.
    #         For example, the signing message for a request might look like:
    #
    # SNWS2-HMAC-SHA256
    # 20170303T043628Z
    # 8f732085380ed6dc18d8556a96c58c820b0148852a61b3c828cb9cfd233ae05f
    digest = hashlib.sha256(bytes(canonical_request_message, "latin-1")).hexdigest()
    output = f'SNWS2-HMAC-SHA256\n{dt.strftime("%Y%m%dT%H%M%SZ")}\n{digest}'

    return output


# Parameters is URL encoded (foo=1&bar=hi)
def generate_canonical_request_message(
    method: str, path: str, parameters: str, signed_headers: dict[str, str], body: str
) -> str:
    # GET
    # /solarquery/api/v1/sec/datum/meta/50
    # sourceId=Foo
    # host:data.solarnetwork.net
    # x-sn-date:Fri, 03 Mar 2017 04:36:28 GMT
    #          host;x-sn-date
    # ... hash ...
    output = ""
    output += f"{method}\n{path}\n"
    output += f"{parameters}\n"

    for k, v in signed_headers.items():
        output += f"{k}:{v}\n"

    count = 0
    for k in signed_headers:
        output += f"{k}"

        if count != len(signed_headers) - 1:
            output += ";"

        count += 1

    output += "\n"

    digest = hashlib.sha256(bytes(body, "latin-1")).hexdigest()
    output += f"{digest}"
    return output


def generate_signature(message: bytes, key: bytes) -> str:
    inner = hmac_sha256(key, message)
    return inner.hexdigest()


def generate_auth_header(
    token: str,
    secret: str,
    method: str,
    path: str,
    params: str,
    signed_headers: dict[str, str],
    body: str,
    dt: datetime.datetime,
) -> str:
    canonical = generate_canonical_request_message(
        method, path, params, signed_headers, body
    )
    key = generate_signing_key(secret, dt, "snws2_request")
    msg = generate_signing_message(dt, canonical)
    sig = generate_signature(bytes(msg, "latin-1"), key)

    output = f"SNWS2 Credential={token},SignedHeaders="

    count = 0
    for k in signed_headers:
        output += f"{k}"
        if count != len(signed_headers) - 1:
            output += ";"

        count += 1

    output += f",Signature={sig}"

    return output