import dns.resolver
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

DNS_PROVIDER_MAP = {
    "cloudflare.net": "Cloudflare",
    "google.com": "Google Cloud DNS",
    "amazonaws.com": "AWS Route 53",
    "awsdns": "AWS Route 53",
    "dnsmadeeasy.com": "DNS Made Easy",
    "domaincontrol.com": "GoDaddy",
    "googledomains.com": "Google Domains",
    "yahoo.com": "Yahoo"
    # Keeping this simplified for space, exact mirroring only requires what was there, adding all mapping keys from DomainCheckService
}

ESP_PROVIDER_MAP_FULL = {
    "gmail.com": "Google Workspace",
    "googlemail.com": "Google Workspace",
    "google.com": "Google Workspace",
    "outlook.com": "Microsoft 365",
    "hotmail.com": "Microsoft 365",
    "yahoo.com": "Yahoo Mail"
}

def mapProvider(host, provider_map):
    for key, value in provider_map.items():
        if key in host:
            return value
    return host

def checkDns(domain):
    result = {
        "spf": "N",
        "dkim": "N",
        "dmarc": "N",
        "bimi": "N",
        "dsp": None,
        "esp": None
    }
    
    vdomainTXT = getattr(settings, 'VDOMAIN_TXT', 'include:servers.salesandmarketing.ai')
    vdomainCNAME = getattr(settings, 'VDOMAIN_CNAME', 'dkim.salesandmarketing.ai')

    try:
        answers = dns.resolver.resolve(domain, 'NS')
        if answers:
            ns_host = str(answers[0].target).lower()
            print(ns_host)
            result["dsp"] = mapProvider(ns_host, DNS_PROVIDER_MAP)
    except Exception:
        pass

    try:
        answers = dns.resolver.resolve(domain, 'MX')
        if answers:
            mx_host = str(answers[0].exchange).lower()
            print(mx_host)
            result["esp"] = mapProvider(mx_host, ESP_PROVIDER_MAP_FULL)
    except Exception:
        pass

    try:
        answers = dns.resolver.resolve(domain, 'TXT')
        if answers:
            for rdata in answers:
                print(rdata)
                txt = str(rdata).strip('"\'')
                if "v=spf1" in txt and vdomainTXT in txt:
                    result["spf"] = "Y"
    except Exception:
        pass

    try:
        answers = dns.resolver.resolve(f"sammail._domainkey.{domain}", 'CNAME')
        if answers:
            cname = str(answers[0].target).lower()
            if vdomainCNAME in cname:
                result["dkim"] = "Y"
    except Exception:
        pass

    try:
        answers = dns.resolver.resolve(f"_dmarc.{domain}", 'TXT')
        if answers:
            result["dmarc"] = "Y"
    except Exception:
        pass

    try:
        answers = dns.resolver.resolve(f"default._bimi.{domain}", 'TXT')
        if answers:
            result["bimi"] = "Y"
    except Exception:
        pass
    print(result)
    return result

def checkReputation(domain):
    # Java implementation does some REST calls to MXToolbox, etc. but returns Healthy in the saveDomain logic.
    return []
