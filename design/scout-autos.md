# Scout: public loan-level auto ABS data on EDGAR (Form ABS-EE, EX-102)

Status: DRAFT in progress (2026-09-08). Sections below are filled only from files saved under
`data/raw/scout/autos/`. Every number cites its file path and URL.

## 0. Access diagnostics (read first)

All SEC hosts returned HTTP 403 "Your Request Originates from an Undeclared Automated Tool" (Akamai) for
every request from this machine, starting with the very first request of the session.

What was tried (all with the mandated User-Agent `abs-risk/0.1 research (+https://github.com/User5017)`
unless noted; none faked a browser):

| Test | Host | Result | Saved response |
|---|---|---|---|
| efts full-text search, mingw curl | efts.sec.gov | 403, 4818-byte block page | `data/raw/scout/autos/_search/sdart.json` |
| company browse (atom) | www.sec.gov/cgi-bin/browse-edgar | 403 | `_search/browse_santander.atom` |
| submissions JSON | data.sec.gov | 403 | `_search/sub_test.json` |
| Archives folder index | www.sec.gov/Archives | 403 | `_search/archives_test.html` |
| same UA + `User5017@users.noreply.github.com` appended (SEC's documented "name + contact" format) | data.sec.gov, efts | 403 | `_search/diag_b.json`, `_search/diag_c.json` |
| curl forced HTTP/1.1 + Accept/Accept-Language/Accept-Encoding headers | data.sec.gov | 403 | `_search/diag_d.json` |
| Python `requests` (OpenSSL stack) | data.sec.gov, efts | 403, server header `AkamaiGHost` | (stdout only) |
| Windows System32 curl.exe 8.21 (Schannel) | data.sec.gov | 403 | `_search/diag_wincurl.json` |
| PowerShell Invoke-WebRequest | data.sec.gov | 403 | (stdout only) |
| sec.gov homepage | www.sec.gov/ | 403 (remote 23.5.4.249) | `_search/diag_home.html` |
| 10-minute full silence, then one probe | data.sec.gov | 403 at 2026-09-08T05:04:08Z | `_search/wait_probe_1.json`, log `_search/sec_wait.log` |
| IPv6 path | - | no IPv6 route on this machine | - |

Why: the machine's public IPv4 is `99.196.128.3`, hostname `99-196-128-3.cust.exede.net`, org
`AS40306 ViaSat, Inc.` (ipinfo.io lookup, printed to stdout). That is satellite internet behind carrier-grade
NAT, so one address is shared by many customers; Akamai's message "identified as part of a network of
automated tools" is the IP-reputation block, not a User-Agent rejection. Neither the UA format nor the TLS
client fingerprint changed the outcome, and a quiet period did not clear it.

Implication for the project: EDGAR pulls must run from a non-CGNAT address (a cloud box, a different ISP, or
a hotspot). The mandated UA is fine on its own; the block is the network.

(Remaining sections are filled in below as data becomes available.)
