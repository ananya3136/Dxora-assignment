"""Extract an evidence packet from one public HTML page."""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

MAX_BYTES = 4_000_000


class WebsiteError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def parse_url(value: str) -> httpx.URL:
    try:
        url = httpx.URL(value)
        port = url.port or {"http": 80, "https": 443}.get(url.scheme)
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or port != {"http": 80, "https": 443}[url.scheme]
            or "%" in url.host
        ):
            raise ValueError
        return url.copy_with(fragment=None)
    except (ValueError, httpx.InvalidURL) as exc:
        raise WebsiteError(422, "Provide a public HTTP or HTTPS URL using its default port.") from exc


def is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return is_public(ip.ipv4_mapped)
        if ip.is_site_local or ip.sixtofour or ip.teredo:
            return False
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


async def public_address(url: httpx.URL) -> str:
    host = url.raw_host.decode("ascii")
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            host, url.port or (443 if url.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise WebsiteError(502, "The website hostname could not be resolved.") from exc
    ips = list(dict.fromkeys(ipaddress.ip_address(result[4][0]) for result in addresses))
    if not ips or any(not is_public(ip) for ip in ips):
        raise WebsiteError(422, "The URL must resolve exclusively to public addresses.")
    return str(next((ip for ip in ips if ip.version == 4), ips[0]))


async def fetch_html(value: str) -> tuple[str, str]:
    url = parse_url(value)
    try:
        async with asyncio.timeout(12), httpx.AsyncClient(
            trust_env=False, timeout=6, limits=httpx.Limits(max_keepalive_connections=0)
        ) as client:
            for _ in range(5):
                address = await public_address(url)
                host = url.raw_host.decode("ascii")
                host_header = f"[{host}]" if ":" in host else host
                async with client.stream(
                    "GET",
                    url.copy_with(host=address),
                    headers={"Host": host_header, "Accept": "text/html,application/xhtml+xml",
                             "Accept-Encoding": "identity", "User-Agent": "WebsiteLinkAnalysis/1.0"},
                    extensions={"sni_hostname": host},
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise WebsiteError(502, "The website returned an incomplete redirect.")
                        url = parse_url(urljoin(str(url), location))
                        continue
                    if not response.is_success:
                        raise WebsiteError(502, f"The website returned HTTP {response.status_code}.")
                    content_type = response.headers.get("content-type", "").split(";")[0].lower()
                    if content_type not in {"text/html", "application/xhtml+xml"}:
                        raise WebsiteError(415, "The website did not return an HTML page.")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise WebsiteError(415, "The website returned an unsupported content encoding.")
                    body = bytearray()
                    async for chunk in response.aiter_raw(chunk_size=16_384):
                        if len(body) + len(chunk) > MAX_BYTES:
                            raise WebsiteError(413, "The website HTML exceeded the size limit.")
                        body.extend(chunk)
                    return str(url), bytes(body).decode(response.encoding or "utf-8", errors="replace")
            raise WebsiteError(502, "The website exceeded the redirect limit.")
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise WebsiteError(504, "The website took too long to respond.") from exc
    except (httpx.HTTPError, LookupError) as exc:
        raise WebsiteError(502, "The website could not be reached or decoded.") from exc


def extract_evidence(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    metadata = {}
    if soup.title:
        metadata["title"] = soup.title.get_text(" ", strip=True)[:300]
    for key in ("description", "og:site_name", "og:description", "og:title", "og:type"):
        tag = soup.find("meta", attrs={"name": key}) or soup.find("meta", attrs={"property": key})
        if tag and tag.get("content"):
            metadata[key] = tag["content"][:500]

    for element in soup.select("script, style, noscript, template, nav, footer, svg, [hidden]"):
        element.decompose()

    root = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup
    headings = list(dict.fromkeys(tag.get_text(" ", strip=True)[:200]
                                  for tag in root.select("h1,h2,h3")))[:30]
    lines = (" ".join(line.split()) for line in root.stripped_strings)
    body = "\n".join(dict.fromkeys(line for line in lines if line))[:14_000]
    description = metadata.get("og:description") or metadata.get("description", "")
    video_page = metadata.get("og:type", "").split(".")[0] == "video"
    if video_page or len(body) < 40:
        if len(description.strip()) >= 40:
            title = metadata.get("og:title") or metadata.get("title", "")
            return {"metadata": metadata, "headings": [], "body": f"{title}\n{description}",
                    "evidence_scope": "page_metadata"}
        if video_page:
            raise WebsiteError(422, "The video page had too little descriptive metadata to analyze.")
    if len(body) < 40:
        raise WebsiteError(422, "The page had too little readable content to analyze.")
    return {"metadata": metadata, "headings": headings, "body": body}
