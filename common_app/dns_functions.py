import dns.resolver
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

ESP_PROVIDER_MAP = {
    "google.com": "Google Workspace",
    "outlook.com": "Microsoft 365",
    "yahoodns.net": "Yahoo",
    "zoho.com": "Zoho Mail",
    "sendgrid.net": "SendGrid",
    "mailgun.org": "Mailgun"
}

class DNSFunction:
    @staticmethod
    def getDNSProvider(domain):
        try:
            answers = dns.resolver.resolve(domain, 'NS')
            for rdata in answers:
                ns_host = str(rdata.target).lower()
                if "domaincontrol" in ns_host:
                    return "godaddy"
                elif "cloudflare" in ns_host:
                    return "cloudflare"
                elif "google" in ns_host:
                    return "google domains"
                elif "awsdns" in ns_host:
                    return "aws route 53"
        except Exception as e:
            logger.error(f"GetDNSProvider Error : {e}")
        return "other"

    @staticmethod
    def checkDMARC(domain):
        flag = 0
        try:
            # Perform a DNS query for the DMARC TXT record
            try:
                answers = dns.resolver.resolve(f"_dmarc.{domain}", 'TXT')
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                answers = None
            except Exception as e:
                logger.error(f"CheckDMARC DNS Error : {e}")
                answers = None

            if answers is not None:
                for rdata in answers:
                    # Extract the TXT record content
                    txt_record = "".join([s.decode() if isinstance(s, bytes) else str(s) for s in rdata.strings])
                    # Join tags and split by semicolon as in Java
                    tags = txt_record.split(";")
                    for tag in tags:
                        tag = tag.strip()
                        key_value = tag.split("=")
                        if len(key_value) == 2 and key_value[0] == "p":
                            if key_value[1] and key_value[1] != "":
                                if key_value[1] == "none":
                                    flag = 1
                                else:
                                    flag = 0
                            break
        except Exception as e:
            logger.error(f"CheckDMARC Error : {e}")
            
        if flag == 0:
            return False
        else:
            return True

    @staticmethod
    def checkSPF(domain, vdomain_txt=None):
        if vdomain_txt is None:
            vdomain_txt = getattr(settings, 'VDOMAIN_TXT', 'include:servers.salesandmarketing.ai')
        try:
            answers = dns.resolver.resolve(domain, 'TXT')
            for rdata in answers:
                txt = str(rdata)
                if "v=spf1" in txt and vdomain_txt in txt:
                    return True
        except Exception as e:
            logger.error(f"CheckSPF Error : {e}")
        return False

    @staticmethod
    def getESP(domain):
        try:
            answers = dns.resolver.resolve(domain, 'MX')
            if answers:
                mx_host = str(answers[0].exchange).lower().rstrip('.')
                if mx_host in ESP_PROVIDER_MAP:
                    return ESP_PROVIDER_MAP[mx_host]
        except Exception as e:
            logger.error(f"GetESP Error : {e}")
        return ""

    @staticmethod
    def getBIMI(domain):
        try:
            answers = dns.resolver.resolve(f"default._bimi.{domain}", 'TXT')
            if answers:
                return 'Y'
        except Exception as e:
            logger.error(f"GetBIMI Error : {e}")
        return 'N'

    @staticmethod
    def getTxtRecord(domain):
        try:
            answers = dns.resolver.resolve(domain, 'TXT')
            for rdata in answers:
                return str(rdata).strip('"')
        except Exception as e:
            logger.error(f"GetTxtRecord Error : {e}")
        return ""

    @staticmethod
    def getCNAMERecord(domain):
        try:
            answers = dns.resolver.resolve(domain, 'CNAME')
            for rdata in answers:
                return str(rdata.target).rstrip('.')
        except Exception:
            # logger.error(f"GetCNAMERecord Error : {e}") # CNAME lookups often fail if not present
            pass
        return ""
